"""PIT research contract for NFL season, last-three and venue splits.

Screenshots are NOT authenticated source data. No weighting or betting output.
"""
from datetime import datetime, timezone
from math import isfinite
import re

SPLITS = ("season", "last3", "venue")
METRICS = ("points_per_game", "yards_per_play", "rush_yards_per_attempt",
           "pass_yards_per_attempt", "third_down_pct", "red_zone_td_pct",
           "opp_points_per_game", "opp_yards_per_play", "opp_rush_yards_per_attempt",
           "opp_pass_yards_per_attempt", "opp_third_down_pct", "opp_red_zone_td_pct")
PERCENT = frozenset(x for x in METRICS if x.endswith("_pct"))
SHA = re.compile(r"^[a-f0-9]{64}$")

def utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("UTC_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("INVALID_UTC") from exc

def validate(package):
    if not isinstance(package, dict):
        raise ValueError("PACKAGE_REQUIRED")
    for key in ("event_id", "away_team_id", "home_team_id", "source_id"):
        if not isinstance(package.get(key), str) or not package[key].strip():
            raise ValueError("IDENTITY_MISSING:" + key)
    if package["away_team_id"] == package["home_team_id"]:
        raise ValueError("TEAM_COLLISION")
    if not isinstance(package.get("source_sha256"), str) or not SHA.fullmatch(package["source_sha256"]):
        raise ValueError("SOURCE_HASH_INVALID")
    if not utc(package.get("source_available_utc")) <= utc(package.get("freeze_utc")) < utc(package.get("event_start_utc")):
        raise ValueError("LOOKAHEAD")
    rows = package.get("rows")
    if not isinstance(rows, list) or len(rows) != 6:
        raise ValueError("SIX_SPLIT_ROWS_REQUIRED")
    seen = set()
    samples = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("ROW_INVALID")
        team, split = row.get("team_id"), row.get("split")
        if team not in (package["away_team_id"], package["home_team_id"]) or split not in SPLITS:
            raise ValueError("SPLIT_IDENTITY_INVALID")
        if (team, split) in seen:
            raise ValueError("DUPLICATE_SPLIT")
        seen.add((team, split))
        if type(row.get("games")) is not int or row["games"] < 1:
            raise ValueError("SPLIT_SAMPLE_INVALID")
        if split == "last3" and row["games"] > 3:
            raise ValueError("LAST3_SAMPLE_INVALID")
        if split == "venue":
            expected = "away" if team == package["away_team_id"] else "home"
            if row.get("venue") != expected:
                raise ValueError("VENUE_MISMATCH")
        metrics = row.get("metrics")
        if not isinstance(metrics, dict) or set(metrics) != set(METRICS):
            raise ValueError("METRIC_SCHEMA_INVALID")
        for metric, value in metrics.items():
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError("METRIC_INVALID:" + metric)
            if metric in PERCENT and not 0 <= value <= 100:
                raise ValueError("PERCENT_OUT_OF_RANGE:" + metric)
            if metric not in PERCENT and value < 0:
                raise ValueError("NEGATIVE_METRIC:" + metric)
        samples[(team,split)]=row["games"]
    # A last-three or venue record cannot have more completed games than
    # the same team's full-season record on the identical feature freeze.
    for team in (package["away_team_id"], package["home_team_id"]):
        if samples[(team,"last3")] > samples[(team,"season")]:
            raise ValueError("LAST3_EXCEEDS_SEASON")
        if samples[(team,"venue")] > samples[(team,"season")]:
            raise ValueError("VENUE_EXCEEDS_SEASON")
    return {"status": "PAPER_0U_UNAUTHENTICATED_SPLIT_RESEARCH",
            "official_counted": 0, "approved_stake_u": 0,
            "rows_validated": len(rows), "source_authenticated": False,
            "weights_calibrated": False}
