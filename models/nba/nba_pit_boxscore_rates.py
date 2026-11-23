"""NBA pregame, prior-only boxscore rate builder (research / 0 units).

Consumes ORIGINAL NBA LiveData final-boxscore JSON bytes plus independently
supplied capture receipts. Does not fetch, infer capture timestamps, read
sportsbook odds, project availability, or release player-prop forecasts.

NBA boxscore source URL format:
https://cdn.nba.com/static/json/liveData/boxscore/boxscore_XXXXXXXXXX.json

Manifest format:
{
  "schema": "sportsedge-nba-prior-boxscore-input-v1",
  "target_game_id": "0022600123",
  "target_tipoff_utc": "2026-11-22T23:00:00Z",
  "records": [
    {"game_id":"0022600122", "source_url":"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022600122.json",
     "captured_at_utc":"2026-11-22T20:00:00Z", "sha256":"<64 hex>",
     "path":"boxscore_0022600122.json"}
  ]
}

Input path is relative to the manifest directory (no absolute paths/symlinks).
An asserted capture timestamp is NOT independently authenticated. The resulting
minutes are trailing observed averages, NEVER injury-aware projected minutes.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import json
import math
import re


SCHEMA = "sportsedge-nba-prior-boxscore-input-v1"
GAME_ID = re.compile(r"^\d{10}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
MIN_ISO = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")
MIN_CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")
MAX_BYTES = 2_500_000
MAX_GAMES = 160
MIN_GAMES_FOR_RATE = 5
MAX_TRAILING_GAMES = 10


class InputBlocked(ValueError):
    """No forecast may be created from an unresolved or contradictory source."""


def _utc(value, field):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InputBlocked("INVALID_UTC_" + field)
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputBlocked("INVALID_UTC_" + field) from exc
    if stamp.utcoffset() != timedelta(0):
        raise InputBlocked("INVALID_UTC_" + field)
    return stamp


def _number(v, field, *, limit):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise InputBlocked("INVALID_" + field)
    value = float(v)
    if not math.isfinite(value) or value < 0 or value > limit or int(value) != value:
        raise InputBlocked("INVALID_" + field)
    return int(value)


def _minutes(v):
    if not isinstance(v, str):
        raise InputBlocked("MISSING_PLAYER_MINUTES")
    m = MIN_ISO.fullmatch(v)
    if m:
        if not any(x is not None for x in m.groups()):
            raise InputBlocked("INVALID_PLAYER_MINUTES")
        minutes = 60 * int(m.group(1) or 0) + int(m.group(2) or 0) + float(m.group(3) or 0) / 60
    else:
        m = MIN_CLOCK.fullmatch(v)
        if not m or int(m.group(2)) >= 60:
            raise InputBlocked("INVALID_PLAYER_MINUTES")
        minutes = int(m.group(1)) + int(m.group(2)) / 60
    if not math.isfinite(minutes) or not 0 < minutes <= 65:
        raise InputBlocked("INVALID_PLAYER_MINUTES")
    return minutes


def _played(v):
    if v in (True, 1, "1", "true", "True"):
        return True
    if v in (False, 0, "0", "false", "False"):
        return False
    raise InputBlocked("UNKNOWN_PLAYER_PLAYED_FLAG")


def _read_original(root, item):
    if not isinstance(item, dict):
        raise InputBlocked("INVALID_RECEIPT")
    gid = str(item.get("game_id") or "")
    if not GAME_ID.fullmatch(gid):
        raise InputBlocked("INVALID_SOURCE_GAME_ID")
    url = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_" + gid + ".json"
    if item.get("source_url") != url:
        raise InputBlocked("SOURCE_URL_NOT_ALLOWLISTED")
    digest = item.get("sha256")
    if not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise InputBlocked("INVALID_SOURCE_SHA")
    rel = item.get("path")
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
        raise InputBlocked("UNSAFE_SOURCE_PATH")
    parts = Path(rel).parts
    if any(x in ("..", ".") for x in parts):
        raise InputBlocked("UNSAFE_SOURCE_PATH")
    file_path = root.joinpath(*parts)
    if not file_path.resolve().is_relative_to(root):
        raise InputBlocked("UNSAFE_SOURCE_PATH")
    if any(parent.is_symlink() for parent in (root.joinpath(*parts[:i]) for i in range(1, len(parts) + 1))):
        raise InputBlocked("SYMLINK_SOURCE_BLOCKED")
    try:
        if not file_path.is_file() or not 50 <= file_path.stat().st_size <= MAX_BYTES:
            raise InputBlocked("ORIGINAL_SIZE_INVALID")
        raw = file_path.read_bytes()
    except OSError as exc:
        raise InputBlocked("ORIGINAL_UNREADABLE") from exc
    if sha256(raw).hexdigest() != digest:
        raise InputBlocked("ORIGINAL_SHA_MISMATCH")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InputBlocked("ORIGINAL_JSON_INVALID") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("game"), dict):
        raise InputBlocked("ORIGINAL_SCHEMA_UNRECOGNIZED")
    return payload["game"], raw


def _event_rows(g, gid):
    if str(g.get("gameId")) != gid:
        raise InputBlocked("ORIGINAL_EVENT_ID_MISMATCH")
    if isinstance(g.get("gameStatus"), bool) or g.get("gameStatus") != 3:
        raise InputBlocked("SOURCE_NOT_FINAL")
    when = _utc(g.get("gameTimeUTC"), "GAME_TIME")
    team_ids, all_ids, rows = set(), set(), []
    for side in ("homeTeam", "awayTeam"):
        team = g.get(side)
        if not isinstance(team, dict) or not isinstance(team.get("players"), list):
            raise InputBlocked("SOURCE_TEAM_SCHEMA_MISSING")
        team_id = str(team.get("teamId") or "")
        tricode = team.get("teamTricode")
        if not team_id.isdigit() or not isinstance(tricode, str) or not re.fullmatch(r"[A-Z]{3}", tricode):
            raise InputBlocked("INVALID_SOURCE_TEAM_ID")
        if team_id in team_ids:
            raise InputBlocked("DUPLICATE_TEAM_ID")
        team_ids.add(team_id)
        if len(team["players"]) > 25:
            raise InputBlocked("IMPOSSIBLE_ROSTER_SIZE")
        for player in team["players"]:
            pid = str(player.get("personId") or "")
            if not pid.isdigit() or pid in all_ids:
                raise InputBlocked("DUPLICATE_OR_MISSING_ATHLETE_ID")
            all_ids.add(pid)
            if not _played(player.get("played")):
                continue
            stats = player.get("statistics")
            if not isinstance(stats, dict):
                raise InputBlocked("MISSING_PLAYER_STATISTICS")
            mins = _minutes(stats.get("minutes") or stats.get("minutesCalculated"))
            row = {"game_id": gid, "start_utc": when, "player_id": pid,
                   "team_id": team_id, "team": tricode, "minutes": mins}
            for key, field, limit in (
                ("pts", "points", 110),
                ("reb", "reboundsTotal", 60),
                ("ast", "assists", 40),
                ("fg3", "threePointersMade", 25),
            ):
                row[key] = _number(stats.get(field), field.upper(), limit=limit)
            if row["fg3"] * 3 > row["pts"]:
                raise InputBlocked("THREES_EXCEED_POINTS")
            rows.append(row)
    if len(team_ids) != 2 or not rows:
        raise InputBlocked("INCOMPLETE_FINAL_BOX")
    return when, rows


def build_report(manifest_path):
    manifest_path = Path(manifest_path)
    root = manifest_path.resolve().parent
    if manifest_path.is_symlink():
        raise InputBlocked("SYMLINK_MANIFEST_BLOCKED")
    raw = manifest_path.read_bytes()
    if not 10 <= len(raw) <= 150000:
        raise InputBlocked("INVALID_MANIFEST_SIZE")
    try:
        m = json.loads(raw)
    except ValueError as exc:
        raise InputBlocked("INVALID_MANIFEST_JSON") from exc
    if not isinstance(m, dict) or m.get("schema") != SCHEMA:
        raise InputBlocked("INVALID_MANIFEST_SCHEMA")
    target_id = str(m.get("target_game_id") or "")
    if not GAME_ID.fullmatch(target_id):
        raise InputBlocked("INVALID_TARGET_ID")
    cutoff = _utc(m.get("target_tipoff_utc"), "TARGET_TIPOFF")
    receipts = m.get("records")
    if not isinstance(receipts, list) or not 1 <= len(receipts) <= MAX_GAMES:
        raise InputBlocked("INVALID_RECORD_COUNT")
    used_games = set()
    readings, lineage = [], []
    for receipt in receipts:
        gid = str(receipt.get("game_id") or "") if isinstance(receipt, dict) else ""
        if gid in used_games or gid == target_id:
            raise InputBlocked("DUPLICATE_OR_TARGET_EVENT")
        used_games.add(gid)
        captured = _utc(receipt.get("captured_at_utc"), "CAPTURE")
        if captured >= cutoff:
            raise InputBlocked("POST_TIPOFF_CAPTURE_BLOCKED")
        game, original = _read_original(root, receipt)
        start, rows = _event_rows(game, gid)
        if start >= cutoff or captured <= start:
            raise InputBlocked("SOURCE_NOT_PRIOR_AND_COMPLETE")
        readings.extend(rows)
        lineage.append({"game_id": gid, "source_sha256": sha256(original).hexdigest(),
                        "captured_at_utc": receipt["captured_at_utc"], "start_utc": start.isoformat()})
    grouped = defaultdict(list)
    for row in readings:
        grouped[row["player_id"]].append(row)
    players = []
    for player_id, games in sorted(grouped.items()):
        games.sort(key=lambda g: (g["start_utc"], g["game_id"]))
        samples = games[-MAX_TRAILING_GAMES:]
        selected = samples[-5:]
        played_min = sum(x["minutes"] for x in samples)
        latest = samples[-1]
        rates = {k + "_pm": round(sum(x[k] for x in samples) / played_min, 6)
                 for k in ("pts", "reb", "ast", "fg3")}
        players.append({"player_id": player_id, "team_last_seen": latest["team"],
                        "team_id_last_seen": latest["team_id"],
                        "games_prior": len(games), "sample_games": len(samples),
                        "minutes_baseline_last5": round(sum(x["minutes"] for x in selected) / len(selected), 3),
                        **rates,
                        "status": ("HISTORICAL_RATE_ONLY" if len(samples) >= MIN_GAMES_FOR_RATE
                                   else "INSUFFICIENT_PRIOR_GAMES"),
                        "availability_verified": False,
                        "minutes_projection_verified": False,
                        "usable_for_betting": False})
    return {"schema": "sportsedge-nba-prior-rates-research-v1",
            "target_game_id": target_id, "target_tipoff_utc": m["target_tipoff_utc"],
            "source_receipt_assertions_only": True, "authenticated_capture": False,
            "source_records": len(lineage), "played_athletes": len(players),
            "official_counted": 0, "approved_stake_u": 0,
            "lineage": sorted(lineage, key=lambda x: x["game_id"]),
            "players": players,
            "release_blockers": ["CAPTURE_TIME_UNAUTHENTICATED",
                                 "INJURY_AND_ACTIVE_ROSTER_UNVERIFIED",
                                 "PROJECTED_MINUTES_NOT_ESTABLISHED",
                                 "PLAYER_GAME_RATE_MODEL_UNCALIBRATED",
                                 "BOOKMARKET_AND_CLV_NOT_ADMITTED"]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest")
    p.add_argument("--summary", action="store_true", help="omit player rates from stdout")
    args = p.parse_args(argv)
    try:
        report = build_report(args.manifest)
    except (InputBlocked, OSError) as exc:
        print(json.dumps({"status": "NO_FORECAST", "reason": str(exc)}))
        return 2
    if args.summary:
        report["players"] = []
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
