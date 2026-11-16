"""PGA point-in-time market row admission (research only, never a price model)."""
from datetime import datetime, timezone
import math

MARKETS = {"outright", "top5", "top10", "top20", "make_cut", "miss_cut",
           "matchup", "three_ball", "round_leader", "first_round_leader",
           "round_score", "tournament_score", "birdies", "bogeys", "eagles",
           "hole_in_one", "dfs"}
REQUIRED = ("event_id", "player_id", "market", "source", "captured_utc",
            "start_utc", "odds_american", "line", "side", "round", "source_hash")


def utc(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED")
    dt = datetime.fromisoformat(s[:-1] + "+00:00")
    if dt.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_REQUIRED")
    return dt


def preflight(rows):
    """Retain every row and reason. Does NOT authenticate claimed clocks or hashes."""
    accepted, blocked = [], []
    for idx, row in enumerate(rows):
        reasons = []
        if not isinstance(row, dict):
            blocked.append({"index": idx, "reasons": ["NOT_A_ROW"]})
            continue
        for field in REQUIRED:
            if field not in row or row[field] is None or row[field] == "":
                reasons.append("MISSING_" + field.upper())
        if row.get("market") not in MARKETS:
            reasons.append("UNKNOWN_MARKET")
        for field in ("event_id", "player_id", "source", "side"):
            if not isinstance(row.get(field), str) or not row.get(field, "").strip():
                reasons.append("INVALID_" + field.upper())
        h = row.get("source_hash")
        if not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
            reasons.append("INVALID_SOURCE_HASH")
        try:
            if utc(row["captured_utc"]) >= utc(row["start_utc"]):
                reasons.append("NOT_PRESTART")
        except (ValueError, KeyError, TypeError, OverflowError):
            reasons.append("INVALID_CLOCK")
        try:
            odds = int(row["odds_american"])
            if odds == 0 or -100 < odds < 100 or not -100000 <= odds <= 100000:
                reasons.append("INVALID_ODDS")
        except (ValueError, TypeError, KeyError, OverflowError):
            reasons.append("INVALID_ODDS")
        try:
            line = float(row["line"])
            if not math.isfinite(line):
                reasons.append("INVALID_LINE")
        except (ValueError, TypeError, KeyError, OverflowError):
            reasons.append("INVALID_LINE")
        if reasons:
            blocked.append({"index": idx, "reasons": sorted(set(reasons))})
        else:
            accepted.append({"index": idx, "status": "CHRONOLOGY_ONLY_UNVERIFIED", "row": row})
    return {"accepted": accepted, "blocked": blocked,
            "betting_status": "PAPER_0U", "model_status": "NO_VALIDATED_PGA_MODEL"}
