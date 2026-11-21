"""Three-sport train-only player-stat baseline from archived prior games.

Produces no bookmaker-derived inputs. This is a deliberately simple,
unvalidated research baseline: last-five-game mean opportunities, pooled
per-opportunity rate, and empirical sample SD. It requires a separately
captured/normalized game-stat ledger, an externally established pregame roster
and activity confirmations, source clocks and hash. It DOES NOT fetch live
provider feeds, authenticate those clocks, or authorize bets.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from statistics import stdev
from csv import DictReader
import io
import json
import math

from .player_projection_builder import (
    SCHEMA as FEATURES_SCHEMA, BASKETBALL_UNITS, FOOTBALL_UNITS,
    build_player_forecast_csv,
)
from .source_ingestion import SOURCES

SCHEMA = "sportsedge-prepregame-player-game-stats-v1"
REQUIRED = frozenset({
    "schema", "sport", "event_id", "home_id", "away_id",
    "event_start_utc", "forecast_asof_utc",
    "source_published_utc", "source_captured_utc",
    "normalized_history_sha256", "original_provider_sha256",
    "source_id", "frozen_roster", "confirmed_activity",
})
CSV_COLUMNS = (
    "sport", "game_id", "game_end_utc", "player_id", "team_id",
    "stat", "opportunity_unit", "opportunities", "actual_stat",
)
PRIOR_GAMES = 5
MIN_GAMES = 4
MAX_CSV = 8_000_000
MAX_ROWS = 100_000
SPORTS = frozenset({"NFL","CFB","CBB"})
ROOT = Path(__file__).resolve().parents[2]


def _utc(value, field):
    if type(value) is not str or not value:
        raise ValueError("HISTORY_TIMESTAMP_REQUIRED:" + field)
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("HISTORY_TIMESTAMP_INVALID:" + field) from exc
    if date.tzinfo is None or date.utcoffset().total_seconds() != 0:
        raise ValueError("HISTORY_TIMESTAMP_NOT_UTC:" + field)
    return date.astimezone(timezone.utc)


def _hash(value, field):
    if type(value) is not str or len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("HISTORY_SHA256_REQUIRED:" + field)
    if any(c not in "0123456789abcdef" for c in value[7:]):
        raise ValueError("HISTORY_SHA256_REQUIRED:" + field)
    return value


def _rate(value, field):
    if type(value) is not str or value.strip() != value or not value:
        raise ValueError("HISTORY_NONNUMERIC:" + field)
    try:
        f = float(value)
    except ValueError as exc:
        raise ValueError("HISTORY_NONNUMERIC:" + field) from exc
    if not math.isfinite(f) or f < 0:
        raise ValueError("HISTORY_NONFINITE_NEGATIVE:" + field)
    return f


def _read_rows(raw: bytes, sport: str, frozen_at: datetime,
               published_at: datetime) -> tuple[list[dict], int]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CSV:
        raise ValueError("HISTORY_ARCHIVE_EMPTY_OR_OVERSIZED")
    try:
        reader = DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""),
                            restkey=None, restval=None)
        header = reader.fieldnames or []
        if len(header) != len(CSV_COLUMNS) or set(header) != set(CSV_COLUMNS):
            raise ValueError("HISTORY_HEADER_MISSING_EXTRA_OR_DUPLICATE")
        parsed = list(reader)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("HISTORY_INVALID_CSV") from exc
    if not parsed or len(parsed) > MAX_ROWS:
        raise ValueError("HISTORY_EMPTY_OR_TOO_MANY_ROWS")
    if any(None in row or any(value is None for value in row.values())
           for row in parsed):
        raise ValueError("HISTORY_RAGGED_CSV")
    units = BASKETBALL_UNITS if sport == "CBB" else FOOTBALL_UNITS
    out = []
    seen = set()
    other_sport = 0
    for row in parsed:
        if row["sport"] != sport:
            other_sport += 1
            continue
        for field in ("game_id", "player_id", "team_id"):
            if not row[field] or row[field].strip() != row[field]:
                raise ValueError("HISTORY_ID_MISSING")
        if row["stat"] not in units or row["opportunity_unit"] != units[row["stat"]]:
            raise ValueError("HISTORY_UNSUPPORTED_STAT_OR_UNIT")
        end = _utc(row["game_end_utc"], "game_end")
        if end >= frozen_at or end > published_at:
            raise ValueError("HISTORY_FUTURE_GAME_OR_SOURCE_LOOKAHEAD")
        identity = (row["game_id"],row["player_id"],row["stat"])
        if identity in seen:
            raise ValueError("HISTORY_DUPLICATE_PLAYER_GAME_STAT")
        seen.add(identity)
        exposure = _rate(row["opportunities"], "opportunities")
        actual = _rate(row["actual_stat"], "actual_stat")
        if exposure == 0 and actual != 0:
            raise ValueError("HISTORY_STAT_WITHOUT_OPPORTUNITY")
        out.append({
            "game_id": row["game_id"], "player_id": row["player_id"],
            "team_id": row["team_id"], "stat": row["stat"],
            "game_end": end, "opportunities": exposure, "actual": actual,
        })
    if not out:
        raise ValueError("HISTORY_NO_PRIOR_SPORT_ROWS")
    return out, other_sport


def fit_player_history(raw: bytes, context: dict) -> tuple[dict, dict]:
    """All sport-supported independent stat recipes; never select by DK lines."""
    if type(context) is not dict or set(context) != REQUIRED:
        raise ValueError("HISTORY_CONTEXT_KEYS_REQUIRED_NO_BOOKMARKET_INPUT")
    if context["schema"] != SCHEMA or context["sport"] not in SPORTS:
        raise ValueError("HISTORY_SCHEMA_SPORT_UNSUPPORTED")
    sport = context["sport"]
    if context["source_id"] not in SOURCES or SOURCES[context["source_id"]].sport != sport:
        raise ValueError("HISTORY_SOURCE_SPORT_MISMATCH")
    for field in ("event_id","home_id","away_id"):
        if type(context[field]) is not str or not context[field].strip():
            raise ValueError("HISTORY_ID_MISSING:" + field)
    if context["home_id"] == context["away_id"]:
        raise ValueError("HISTORY_SAME_EVENT_TEAMS")
    event_start = _utc(context["event_start_utc"], "start")
    freeze = _utc(context["forecast_asof_utc"], "freeze")
    published = _utc(context["source_published_utc"], "published")
    captured = _utc(context["source_captured_utc"], "captured")
    if not published <= captured <= freeze < event_start:
        raise ValueError("HISTORY_SOURCE_PUBLICATION_OR_FREEZE_LOOKAHEAD")
    digest = "sha256:" + sha256(raw).hexdigest() if type(raw) is bytes else None
    if digest != _hash(context["normalized_history_sha256"], "normalized"):
        raise ValueError("HISTORY_NORMALIZED_ORIGINAL_BYTES_HASH_MISMATCH")
    _hash(context["original_provider_sha256"], "original_provider")
    roster = context["frozen_roster"]
    active = context["confirmed_activity"]
    if (type(roster) is not dict or not roster or
        type(active) is not dict or set(active) != set(roster)):
        raise ValueError("HISTORY_FROZEN_ROSTER_ACTIVITY_CENSUS_REQUIRED")
    for player, team in roster.items():
        if (type(player) is not str or not player or
            team not in (context["home_id"],context["away_id"]) or
            type(active[player]) is not bool):
            raise ValueError("HISTORY_ROSTER_PLAYER_TEAM_OR_ACTIVE_INVALID")
    hist, other_sport = _read_rows(raw, sport, freeze, published)
    units = BASKETBALL_UNITS if sport == "CBB" else FOOTBALL_UNITS
    by = {}
    for row in hist:
        pid = row["player_id"]
        if pid not in roster:
            continue
        # Reject possible midseason identity changes for those players.
        if roster[pid] != row["team_id"]:
            raise ValueError("HISTORY_PLAYER_CHANGED_TEAM_IDENTITY_REQUIRES_REFIT")
        by.setdefault((pid,row["stat"]),[]).append(row)
    fitted = []
    blocked = []
    maximum_end = None
    for pid, team in sorted(roster.items()):
        for stat in sorted(units):
            key = (pid,stat)
            if not active[pid]:
                blocked.append({"player_id":pid,"stat":stat,
                                "reason":"PLAYER_NOT_CONFIRMED_ACTIVE"})
                continue
            history = sorted(by.get(key,()), key=lambda x:(
                x["game_end"],x["game_id"]), reverse=True)[:PRIOR_GAMES]
            if len(history) < MIN_GAMES:
                blocked.append({"player_id":pid,"stat":stat,
                                "reason":"HISTORY_INSUFFICIENT_EARLIER_GAMES"})
                continue
            opportunities = sum(r["opportunities"] for r in history)
            if opportunities <= 0:
                blocked.append({"player_id":pid,"stat":stat,
                                "reason":"HISTORY_ZERO_OPPORTUNITY"})
                continue
            mean_opp = opportunities/len(history)
            if units[stat] == "TARGETS" and mean_opp < 4:
                blocked.append({"player_id":pid,"stat":stat,
                                "reason":"RECEIVING_PROP_TARGET_VOLUME_BELOW_FLOOR"})
                continue
            if units[stat] == "RUSH_ATT" and mean_opp < 10:
                blocked.append({"player_id":pid,"stat":stat,
                                "reason":"RUSHING_PROP_ATTEMPT_VOLUME_BELOW_FLOOR"})
                continue
            sd = stdev([r["actual"] for r in history])
            if not math.isfinite(sd) or sd <= 0:
                blocked.append({"player_id":pid,"stat":stat,
                                "reason":"HISTORY_UNIDENTIFIABLE_STAT_VARIANCE"})
                continue
            rate = sum(r["actual"] for r in history)/opportunities
            if not math.isfinite(rate) or rate < 0:
                raise ValueError("HISTORY_RATE_INVALID")
            maximum_end = max(maximum_end or history[0]["game_end"],
                              *(r["game_end"] for r in history))
            fitted.append({
                "player_id": pid, "team_id":team, "stat":stat,
                "opportunity_unit":units[stat],
                "opportunities": mean_opp,
                "rate_per_opportunity": rate,
                "standard_deviation":sd,
                "confirmed_active":True,
            })
    if maximum_end is None:
        raise ValueError("HISTORY_NO_VALID_TRAINED_STATS")
    features = {
        "schema":FEATURES_SCHEMA, "sport":sport,
        "event_id":context["event_id"],"home_id":context["home_id"],
        "away_id":context["away_id"],
        "event_start_utc":event_start.isoformat(),
        "forecast_asof_utc":freeze.isoformat(),
        "trained_until_utc":maximum_end.isoformat(),
        "source_published_utc":published.isoformat(),
        "source_captured_utc":captured.isoformat(),
        "source_snapshot_sha256":digest,"source_id":context["source_id"],
        "frozen_roster":roster, "players":fitted,
    }
    csv_raw, builder = build_player_forecast_csv(features)
    report = {
        "schema":"sportsedge-prior-game-player-fit-census-v1",
        "sport":sport,"event_id":context["event_id"],
        "history_sha256":digest,
        "original_provider_claim_sha256":context["original_provider_sha256"],
        "history_rows":len(hist),"other_sport_rows":other_sport,
        "forecast_rows":builder["produced"],
        "history_blocked":blocked,
        "builder_blocked":builder["blocked"],
        "forecast_csv_sha256":builder["file_sha256"],
        "status":"PAPER_0U_UNCALIBRATED_PRIOR_GAMES_BASELINE",
        "source_authenticated":False,
        "variance_forward_calibrated":False,
        "official_counted":0, "approved_stake_u":0,
        "method":"FIXED_LAST_5_PRIOR_GAMES_MIN_4_EMPRATE_EMPIRICAL_SD",
        "opportunity_model":"PRIOR_5_GAME_MEAN_NOT_OPPONENT_ADJUSTED",
    }
    return features, report


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description="Prior-game research-only player fit")
    parser.add_argument("history_csv")
    parser.add_argument("private_event_context_json")
    parser.add_argument("new_features_json")
    parser.add_argument("new_census_json")
    args=parser.parse_args(argv)
    paths=[Path(x).resolve() for x in (
        args.history_csv,args.private_event_context_json,
        args.new_features_json,args.new_census_json)]
    if len(set(paths)) != len(paths):
        raise ValueError("HISTORY_PRIVATE_DISTINCT_PATHS_REQUIRED")
    if any(p == ROOT or ROOT in p.parents for p in paths):
        raise ValueError("HISTORY_PRIVATE_PATH_REQUIRED")
    def nodup(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError("HISTORY_DUPLICATE_JSON_KEY")
            result[key]=value
        return result
    def nonfinite(s): raise ValueError("HISTORY_NONFINITE_JSON:"+s)
    context=json.loads(paths[1].read_bytes(),object_pairs_hook=nodup,parse_constant=nonfinite)
    features,report=fit_player_history(paths[0].read_bytes(),context)
    first=(json.dumps(features,indent=2,sort_keys=True,allow_nan=False)+"\n").encode()
    second=(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n").encode()
    if paths[2].exists() or paths[3].exists():
        raise ValueError("HISTORY_OUTPUT_CREATE_ONLY")
    # A feature file without its paired census is incomplete evidence.
    # Clean up only new outputs from this invocation on ordinary write errors;
    # never overwrite existing source files or other researchers' artifacts.
    import os
    created = []
    try:
        for destination, payload in ((paths[2], first), (paths[3], second)):
            with destination.open("xb") as w:
                created.append(destination)
                w.write(payload)
                w.flush()
                os.fsync(w.fileno())
    except BaseException:
        for destination in reversed(created):
            destination.unlink(missing_ok=True)
        raise
    return 0


if __name__=="__main__":
    raise SystemExit(main())
