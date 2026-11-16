"""Research-only NFL quarterback EPA/PFF feature intake.

No chart pixel estimates, no PFF scraping, no betting probabilities or stakes.
Requires licensed/authorized PFF values if PFF is used at all.
"""
from datetime import datetime, timezone
from math import isfinite
import re

SHA = re.compile(r"^[a-f0-9]{64}$")
REQUIRED = ("event_id", "qb_id", "team_id", "opponent_id", "season", "dropbacks",
            "epa_per_dropback", "source_sha256", "source_available_utc",
            "feature_freeze_utc", "event_start_utc", "source_name")

def utc(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError("UTC_REQUIRED")
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("INVALID_UTC") from exc

def validate(rows, *, minimum_dropbacks=150):
    if type(minimum_dropbacks) is not int or minimum_dropbacks < 1:
        raise ValueError("INVALID_THRESHOLD")
    if not isinstance(rows, list) or not rows:
        raise ValueError("ROWS_REQUIRED")
    seen = set()
    output = []
    for row in rows:
        if not isinstance(row, dict) or any(k not in row for k in REQUIRED):
            raise ValueError("QB_SCHEMA_INCOMPLETE")
        for key in ("event_id", "qb_id", "team_id", "opponent_id", "source_name"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError("QB_IDENTITY_INVALID")
        if row["team_id"] == row["opponent_id"]:
            raise ValueError("TEAM_COLLISION")
        identity = (row["event_id"], row["qb_id"])
        if identity in seen:
            raise ValueError("DUPLICATE_QB_EVENT")
        seen.add(identity)
        if type(row["season"]) is not int or not 2000 <= row["season"] <= 2100:
            raise ValueError("SEASON_INVALID")
        if type(row["dropbacks"]) is not int or row["dropbacks"] < 0:
            raise ValueError("DROPBACKS_INVALID")
        if type(row["epa_per_dropback"]) not in (int, float) or not isfinite(row["epa_per_dropback"]):
            raise ValueError("EPA_INVALID")
        if not isinstance(row["source_sha256"], str) or not SHA.fullmatch(row["source_sha256"]):
            raise ValueError("SOURCE_HASH_INVALID")
        if not utc(row["source_available_utc"]) <= utc(row["feature_freeze_utc"]) < utc(row["event_start_utc"]):
            raise ValueError("LOOKAHEAD")
        grade = row.get("pff_offensive_grade")
        if grade is not None:
            if row.get("pff_use_authorized") is not True:
                raise ValueError("PFF_AUTHORIZATION_REQUIRED")
            if type(grade) not in (int, float) or not isfinite(grade) or not 0 <= grade <= 100:
                raise ValueError("PFF_GRADE_INVALID")
            if not row.get("pff_source_sha256") or not SHA.fullmatch(str(row["pff_source_sha256"])):
                raise ValueError("PFF_SOURCE_HASH_REQUIRED")
            if utc(row.get("pff_available_utc")) > utc(row["feature_freeze_utc"]):
                raise ValueError("PFF_LOOKAHEAD")
        output.append({
            "event_id": row["event_id"], "qb_id": row["qb_id"],
            "dropbacks": row["dropbacks"],
            "eligible_for_threshold_analysis": row["dropbacks"] >= minimum_dropbacks,
            "epa_per_dropback": row["epa_per_dropback"],
            "pff_offensive_grade": grade,
            "source_authenticated": False,
        })
    return {"status": "PAPER_0U_QB_RESEARCH", "official_counted": 0,
            "approved_stake_u": 0, "minimum_dropbacks": minimum_dropbacks,
            "rows": output}
