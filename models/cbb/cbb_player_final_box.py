"""ESPN final box-score admission and conditional player outcome diagnostics.

No bookmaker settlement rule or authenticated source is implied. DNP, missing,
ambiguous and malformed rows are withheld, never converted to zero.
"""
import re
from cbb_player_residual_pricing import STATS, COMBOS, vector


def integer(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("INVALID_INTEGER")
    return int(value)


def minutes_positive(value):
    if isinstance(value, bool):
        return False
    m = re.fullmatch(r"(\d+)(?::([0-5]\d))?", str(value))
    return bool(m and (int(m[1]) > 0 or int(m[2] or 0) > 0))


def extract(summary, event_id, home_id, away_id, home_score, away_score):
    """Return exact (team_id, player_id) -> final stat vector from a completed event."""
    h = summary["header"]
    if str(h["id"]) != str(event_id):
        raise ValueError("FINAL_EVENT_MISMATCH")
    games = h["competitions"]
    if len(games) != 1 or not games[0]["status"]["type"].get("completed") is True:
        raise ValueError("FINAL_NOT_COMPLETE")
    game = games[0]
    if str(game["id"]) != str(event_id):
        raise ValueError("FINAL_EVENT_MISMATCH")
    competitors = game["competitors"]
    if len(competitors) != 2:
        raise ValueError("FINAL_TEAM_MISMATCH")
    by_side = {c["homeAway"]: c for c in competitors}
    if set(by_side) != {"home", "away"}:
        raise ValueError("FINAL_TEAM_MISMATCH")
    for side, tid, score in (("home", home_id, home_score), ("away", away_id, away_score)):
        c = by_side[side]
        if str(c["team"]["id"]) != str(tid) or integer(c["score"]) != score:
            raise ValueError("FINAL_TEAM_SCORE_MISMATCH")
    blocks = summary["boxscore"]["players"]
    if len(blocks) != 2 or {str(b["team"]["id"]) for b in blocks} != {str(home_id), str(away_id)}:
        raise ValueError("BOX_TEAM_MISMATCH")
    admitted, seen, duplicates = {}, set(), set()
    for block in blocks:
        tid = str(block["team"]["id"])
        for group in block.get("statistics", []):
            labels = group.get("labels", [])
            if len(labels) != len(set(labels)) or not {"MIN", "PTS", "REB", "AST", "3PT"}.issubset(labels):
                continue
            for athlete in group.get("athletes", []):
                pid = str((athlete.get("athlete") or {}).get("id") or "")
                if not pid:
                    continue
                key = (tid, pid)
                if key in seen:
                    duplicates.add(key)
                    continue
                seen.add(key)
                stats = athlete.get("stats") or []
                if athlete.get("didNotPlay") is True or len(stats) != len(labels):
                    continue
                values = dict(zip(labels, stats))
                if not minutes_positive(values["MIN"]):
                    continue
                try:
                    made = re.fullmatch(r"(\d+)-(\d+)", str(values["3PT"]))
                    if not made or int(made[1]) > int(made[2]):
                        raise ValueError("INVALID_THREES")
                    final = {"PTS": integer(values["PTS"]), "REB": integer(values["REB"]),
                             "AST": integer(values["AST"]), "3PM": int(made[1])}
                    vector(final, actual=True)
                except (ValueError, TypeError):
                    continue
                admitted[key] = final
    for key in duplicates:
        admitted.pop(key, None)
    # A player ID may not appear for both opponents even if one row is DNP.
    counts = {}
    for tid, pid in seen:
        counts[pid] = counts.get(pid, 0) + 1
    return {key: value for key, value in admitted.items() if counts[key[1]] == 1}


def outcome(market, line, stats):
    vector(stats, actual=True)
    stat, kind = market.removeprefix("PLAYER_").split("_", 1)
    if stat not in STATS and stat not in COMBOS:
        raise ValueError("UNKNOWN_STAT")
    import math
    if isinstance(line, bool) or not isinstance(line, (int, float)) or not math.isfinite(line) or line < 0:
        raise ValueError("INVALID_LINE")
    value = sum(stats[k] for k in COMBOS.get(stat, (stat,)))
    if kind == "AT_LEAST":
        if line < 1 or not float(line).is_integer():
            raise ValueError("INVALID_MILESTONE")
        return "yes" if value >= line else "no"
    if kind != "OU":
        raise ValueError("UNKNOWN_CONTRACT")
    return "push" if value == line else ("over" if value > line else "under")
