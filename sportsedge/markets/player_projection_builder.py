"""Deterministic pregame player-stat means for NFL, CFB and CBB (PAPER / 0u).

This converts separately frozen *opportunity and per-opportunity rate* features
to independent forecast CSV accepted by player_forecast_intake.py. No prices,
market-implied means, inferred player identities, retrospective feature repairs
or invented variance estimates. Upstream timestamps/hashes are declarations,
NOT independently authenticated provider evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import io
import math

from .allmarkets_research import STAT_NAMES, _hash
from .projection_distribution import PlayerMoment
from .source_ingestion import SOURCES

SCHEMA = "sportsedge-three-sport-player-opportunities-v1"
SPORTS = frozenset({"NFL", "CFB", "CBB"})
ROOT_KEYS = frozenset({
    "schema", "sport", "event_id", "home_id", "away_id", "event_start_utc",
    "forecast_asof_utc", "trained_until_utc", "source_published_utc",
    "source_captured_utc", "source_snapshot_sha256", "source_id",
    "frozen_roster", "players",
})
PLAYER_KEYS = frozenset({
    "player_id", "team_id", "stat", "opportunity_unit", "opportunities",
    "rate_per_opportunity", "standard_deviation", "confirmed_active",
})
COLUMNS = (
    "sport", "event_id", "player_id", "team_id", "stat", "mean", "sd",
    "asof_utc", "trained_until_utc", "source_snapshot_sha256", "source_id",
    "confirmed_active", "projected_targets", "projected_rush_attempts",
    "projected_minutes", "confirmed_pitcher", "confirmed_batting_lineup",
)
FOOTBALL_UNITS = {
    "PASS_YDS": "PASS_ATT", "COMPLETIONS": "PASS_ATT",
    "PASS_TDS": "PASS_ATT", "INTERCEPTIONS": "PASS_ATT",
    "PASS_ATT": "TEAM_DROPBACKS",
    "RUSH_YDS": "RUSH_ATT", "RUSH_TDS": "RUSH_ATT",
    "RUSH_ATT": "TEAM_RUSH_PLAYS",
    "REC_YDS": "TARGETS", "RECEPTIONS": "TARGETS",
    "REC_TDS": "TARGETS", "TARGETS": "TEAM_PASS_ATT",
}
BASKETBALL_UNITS = {
    "POINTS": "MINUTES", "REBOUNDS": "MINUTES", "ASSISTS": "MINUTES",
    "3PM": "MINUTES", "STEALS": "MINUTES", "BLOCKS": "MINUTES",
    "TURNOVERS": "MINUTES",
}


def _timestamp(value: object, name: str) -> datetime:
    if type(value) is not str:
        raise ValueError("PLAYER_BUILD_INVALID_UTC:" + name)
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("PLAYER_BUILD_INVALID_UTC:" + name) from exc
    if d.tzinfo is None or d.utcoffset().total_seconds() != 0:
        raise ValueError("PLAYER_BUILD_INVALID_UTC:" + name)
    return d.astimezone(timezone.utc)


def _nonnegative(value: object, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError("PLAYER_BUILD_INVALID_NUMBER:" + name)
    f = float(value)
    if not math.isfinite(f) or f < 0 or (positive and f <= 0):
        raise ValueError("PLAYER_BUILD_INVALID_NUMBER:" + name)
    return f


def _identifier(value: object, name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError("PLAYER_BUILD_INVALID_ID:" + name)
    return value


def build_player_forecast_csv(payload: dict) -> tuple[bytes, dict]:
    """Return exact forecast CSV bytes + explicit research/blocked census.

    Each supplied opportunity/rate and SD must be computed using *earlier*
    frozen features. This does not estimate those features or fit distributions.
    Unsupported compound/order-stat props remain blocked, not approximated.
    """
    if type(payload) is not dict or set(payload) != ROOT_KEYS:
        raise ValueError("PLAYER_BUILD_INVALID_ROOT_OR_FORBIDDEN_FEATURE")
    if payload["schema"] != SCHEMA or payload["sport"] not in SPORTS:
        raise ValueError("PLAYER_BUILD_UNSUPPORTED_SCHEMA_OR_SPORT")
    sport = payload["sport"]
    event_id = _identifier(payload["event_id"], "event_id")
    home = _identifier(payload["home_id"], "home_id")
    away = _identifier(payload["away_id"], "away_id")
    if home == away:
        raise ValueError("PLAYER_BUILD_DUPLICATE_EVENT_TEAMS")
    start = _timestamp(payload["event_start_utc"], "start")
    freeze = _timestamp(payload["forecast_asof_utc"], "freeze")
    trained = _timestamp(payload["trained_until_utc"], "trained")
    published = _timestamp(payload["source_published_utc"], "published")
    captured = _timestamp(payload["source_captured_utc"], "captured")
    if not (trained < freeze < start and published <= captured <= freeze):
        raise ValueError("PLAYER_BUILD_LOOKAHEAD_OR_SOURCE_CLOCK")
    snapshot_sha = _hash(payload["source_snapshot_sha256"])
    source_id = payload["source_id"]
    if source_id not in SOURCES or SOURCES[source_id].sport != sport:
        raise ValueError("PLAYER_BUILD_SOURCE_SPORT_MISMATCH")
    roster = payload["frozen_roster"]
    if type(roster) is not dict or not roster:
        raise ValueError("PLAYER_BUILD_FROZEN_ROSTER_REQUIRED")
    for player_id, team_id in roster.items():
        _identifier(player_id, "roster_player")
        if team_id not in (home, away):
            raise ValueError("PLAYER_BUILD_ROSTER_TEAM_NOT_IN_GAME")
    rows = payload["players"]
    if type(rows) is not list or not rows or len(rows) > 5000:
        raise ValueError("PLAYER_BUILD_NO_PLAYER_FEATURES_OR_OVERSIZED")

    units = BASKETBALL_UNITS if sport == "CBB" else FOOTBALL_UNITS
    output = []
    blocked = []
    seen = set()
    for index, player in enumerate(rows):
        if type(player) is not dict or set(player) != PLAYER_KEYS:
            raise ValueError("PLAYER_BUILD_INVALID_PLAYER_FIELDS_OR_ODDS_FEATURE")
        pid = _identifier(player["player_id"], "player_id")
        team = _identifier(player["team_id"], "team_id")
        stat = _identifier(player["stat"], "stat")
        key = (pid, stat)
        if key in seen:
            raise ValueError("PLAYER_BUILD_DUPLICATE_PLAYER_STAT")
        seen.add(key)
        if team not in (home, away) or roster.get(pid) != team:
            raise ValueError("PLAYER_BUILD_PLAYER_TEAM_EVENT_UNBOUND")
        if type(player["confirmed_active"]) is not bool:
            raise ValueError("PLAYER_BUILD_ACTIVITY_CONFIRMATION_REQUIRED")
        if not player["confirmed_active"]:
            blocked.append({"player_id": pid, "stat": stat, "reason": "PLAYER_NOT_CONFIRMED_ACTIVE"})
            continue
        if stat not in STAT_NAMES[sport]:
            blocked.append({"player_id": pid, "stat": stat, "reason": "STAT_NOT_SUPPORTED_FOR_SPORT"})
            continue
        if stat not in units:
            blocked.append({"player_id": pid, "stat": stat, "reason": "NO_INDEPENDENT_STAT_RECIPE"})
            continue
        if player["opportunity_unit"] != units[stat]:
            raise ValueError("PLAYER_BUILD_WRONG_STAT_OPPORTUNITY_UNIT")
        n = _nonnegative(player["opportunities"], "opportunities")
        rate = _nonnegative(player["rate_per_opportunity"], "rate")
        sd = _nonnegative(player["standard_deviation"], "sd", positive=True)
        mean = n * rate
        if not math.isfinite(mean):
            raise ValueError("PLAYER_BUILD_INVALID_PROJECTED_MEAN")
        targets = (n if units[stat] == "TARGETS" else
                   mean if stat == "TARGETS" else None)
        rush = (n if units[stat] == "RUSH_ATT" else
                mean if stat == "RUSH_ATT" else None)
        minutes = n if sport == "CBB" else None
        moment = PlayerMoment(
            player_id=pid, team_id=team, stat=stat,
            projected_mean=mean, standard_deviation=sd,
            raw_features_sha256=snapshot_sha,
            trained_until_utc=trained, projection_asof_utc=freeze,
            confirmed_active=True, projected_targets=targets,
            projected_rush_attempts=rush, projected_minutes=minutes,
        )
        try:
            moment.validate(sport, freeze)
        except ValueError as exc:
            blocked.append({"player_id": pid, "stat": stat, "reason": str(exc)})
            continue
        fmt = lambda x: "" if x is None else format(x, ".12g")
        output.append({
            "sport": sport, "event_id": event_id, "player_id": pid,
            "team_id": team, "stat": stat, "mean": fmt(mean), "sd": fmt(sd),
            "asof_utc": freeze.isoformat(),
            "trained_until_utc": trained.isoformat(),
            "source_snapshot_sha256": snapshot_sha, "source_id": source_id,
            "confirmed_active": "1", "projected_targets": fmt(targets),
            "projected_rush_attempts": fmt(rush),
            "projected_minutes": fmt(minutes),
            "confirmed_pitcher": "0", "confirmed_batting_lineup": "0",
        })
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(output)
    raw = stream.getvalue().encode("utf-8")
    digest = "sha256:" + sha256(raw).hexdigest()
    model_hash = "sha256:" + sha256(Path(__file__).read_bytes()).hexdigest()
    return raw, {
        "schema": "sportsedge-three-sport-player-forecast-census-v1",
        "sport": sport, "event_id": event_id,
        "submitted": len(rows), "produced": len(output), "blocked": blocked,
        "file_sha256": digest, "model_sha256": model_hash,
        "source_snapshot_sha256": snapshot_sha,
        "source_authenticated": False, "calibration_verified": False,
        "official_counted": 0, "approved_stake_u": 0,
        "status": "PAPER_0U_UNVERIFIED" if output else "BLOCK_NO_PLAYER_FORECASTS",
    }


def main(argv: list[str] | None = None) -> int:
    """Create-only private files for existing player_file intake."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="PAPER / 0u pregame player means")
    parser.add_argument("features_json")
    parser.add_argument("forecast_csv")
    parser.add_argument("census_json")
    args = parser.parse_args(argv)
    source = Path(args.features_json).resolve()
    csv_out = Path(args.forecast_csv).resolve()
    census_out = Path(args.census_json).resolve()
    repository = Path(__file__).resolve().parents[2]
    for candidate in (source, csv_out, census_out):
        if candidate == repository or repository in candidate.parents:
            raise ValueError("PLAYER_BUILD_PRIVATE_DATA_MUST_STAY_OUTSIDE_PUBLIC_REPO")
    if csv_out == census_out or csv_out.exists() or census_out.exists():
        raise ValueError("PLAYER_BUILD_CREATE_ONLY_OUTPUT_REQUIRED")

    def no_dupes(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("PLAYER_BUILD_DUPLICATE_JSON_KEY")
            obj[key] = value
        return obj

    def no_nan(value):
        raise ValueError("PLAYER_BUILD_NONFINITE_JSON:" + value)

    payload = json.loads(source.read_bytes(), object_pairs_hook=no_dupes,
                         parse_constant=no_nan)
    raw, census = build_player_forecast_csv(payload)
    # A zero-row research output is never admitted as a valid player file.
    if not census["produced"]:
        raise ValueError("PLAYER_BUILD_NO_ADMISSIBLE_FORECAST_ROWS")
    with csv_out.open("xb") as out:
        out.write(raw)
    with census_out.open("xb") as out:
        out.write((json.dumps(census, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
