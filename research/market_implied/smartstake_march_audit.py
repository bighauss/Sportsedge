"""Offline source qualification, NOT a consensus, opening/closing or EV feed."""
import argparse
import hashlib
import json


MARCH_SHA = "c1058237807fbd39306a3b5091460cf4c02e63948e457e3c0a2a3b1aa4e0fba3"

# Each source-native game/player/market/half-line observed anywhere in the
# single book's pregame archive is in the retrospective coverage denominator.
# No carry-forward: both sides must be observed exactly 60 min before start.
QUERY = """
WITH contracts AS (
 SELECT game_id, start_time, player, market, line,
   count(*) FILTER (WHERE ts = start_time - interval '60 minutes') AS ticks,
   count(*) FILTER (WHERE ts = start_time - interval '60 minutes'
      AND side='over' AND isfinite(odds) AND odds>1) AS overs,
   count(*) FILTER (WHERE ts = start_time - interval '60 minutes'
      AND side='under' AND isfinite(odds) AND odds>1) AS unders
 FROM read_parquet(?)
 WHERE book='bet365' AND ts < start_time
   AND game_id IS NOT NULL AND player IS NOT NULL AND market IS NOT NULL
   AND line >= 0 AND line % 1 = 0.5
 GROUP BY ALL
), players AS (
 SELECT game_id, start_time, player, market, count(*) AS contracts,
    count(*) FILTER (WHERE ticks=0) AS absent,
    count(*) FILTER (WHERE ticks=2 AND overs=1 AND unders=1) AS paired
 FROM contracts GROUP BY ALL
)
SELECT market, sum(contracts)::bigint AS observed_contracts,
       sum(absent)::bigint AS missing_minute, sum(paired)::bigint AS paired,
       sum(contracts-absent-paired)::bigint AS unpaired_or_ambiguous,
       count(*) AS player_game_markets, count(*) FILTER (WHERE paired>=2) AS multi_rung
FROM players GROUP BY market ORDER BY market
"""


def audit(path, *, example=False):
    import duckdb  # optional offline audit dependency; not needed by pricing
    with open(path, "rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != MARCH_SHA:
            raise ValueError("UNEXPECTED_SOURCE_BYTES")
    with duckdb.connect() as db:
        if example:
            # Source-qualification example, chosen for complete geometry, not
            # selected by outcome. No result/grade is queried. Keep rules UNKNOWN.
            from .devig import BookQuote, METHODS
            from .ladder import integer_count_bounds
            rows = db.execute("""
                SELECT line, side, odds FROM read_parquet(?)
                WHERE game_id='m~6af39360' AND player='rafael devers' AND market='player bases'
                  AND start_time=TIMESTAMP '2026-03-26 00:05:00' AND book='fanatics'
                  AND ts=TIMESTAMP '2026-03-26 00:02:00' AND line IN (0.5,1.5)
                ORDER BY line, side""", [str(path)]).fetchall()
            if [(line, side) for line, side, _ in rows] != [
                (.5, "over"), (.5, "under"), (1.5, "over"), (1.5, "under")
            ]:
                raise ValueError("EXAMPLE_CONTRACT_NOT_EXACTLY_PAIRED")
            when = "2026-03-26T00:02:00Z"
            quotes = [BookQuote("fanatics", (o[2], u[2]), sport="MLB", event_id="m~6af39360",
                       player_id="source-name:rafael devers", market="prop_total_bases",
                       period="source-game", rules="UNKNOWN_SOURCE_RULES_NOT_FOR_EXECUTION",
                       capture_utc=when, start_utc="2026-03-26T00:05:00Z", fmt="decimal",
                       outcomes=("over","under"), line=o[0]) for o, u in (rows[:2], rows[2:])]
            return {m: integer_count_bounds(quotes, 1, as_of=when,
                    max_age_seconds=60, method=m)["bounds"] for m in METHODS}
        cur = db.execute(QUERY, [str(path)])
        keys = [col[0] for col in cur.description]
        return [dict(zip(keys, row)) for row in cur.fetchall()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("march_parquet")
    parser.add_argument("--example", action="store_true", help="replay a single Fanatics ladder")
    args = parser.parse_args()
    print(json.dumps(audit(args.march_parquet, example=args.example), indent=2))
