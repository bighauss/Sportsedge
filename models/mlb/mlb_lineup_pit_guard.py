"""Research-only MLB starter/lineup point-in-time freeze; no model changes.

Input is normalized locally supplied source data, NOT independently authenticated
MLB provider bytes. Hash matches establish local consistency, not true provenance.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

SCHEMA = "sportsedge-mlb-lineup-pit-v1"
MANIFEST_KEYS = frozenset({
    "schema", "event_id", "event_start_utc", "forecast_asof_utc",
    "source_published_utc", "source_captured_utc", "normalized_sha256",
    "original_provider_sha256", "source_id",
})
SNAPSHOT_KEYS = frozenset({
    "schema", "event_id", "event_start_utc", "home_team_id", "away_team_id",
    "home_starter_id", "away_starter_id", "home_starter_team_id",
    "away_starter_team_id", "starters_confirmed", "lineups_confirmed",
    "home_lineup", "away_lineup",
})
LINEUP_KEYS = frozenset({"slot", "player_id", "team_id"})
SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
MLBAM = re.compile(r"[1-9][0-9]*\Z")
MAX_BYTES = 2_000_000


def _utc(value: object, field: str) -> datetime:
    if type(value) is not str or not value:
        raise ValueError("MLB_PIT_CLOCK_REQUIRED:" + field)
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("MLB_PIT_CLOCK_INVALID:" + field) from error
    if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
        raise ValueError("MLB_PIT_UTC_REQUIRED:" + field)
    return timestamp.astimezone(timezone.utc)


def _digest(value: object, field: str) -> str:
    if type(value) is not str or not SHA.fullmatch(value):
        raise ValueError("MLB_PIT_DIGEST_INVALID:" + field)
    return value


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("MLB_PIT_DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def _bad_constant(value: str):
    raise ValueError("MLB_PIT_INVALID_JSON_CONSTANT:" + value)


def _id(value: object) -> bool:
    """MLB StatsAPI/MLBAM IDs are decimal strings, never names."""
    return type(value) is str and MLBAM.fullmatch(value) is not None


def inspect_lineup_freeze(raw: bytes, manifest: dict) -> dict:
    """Return structural census only, never source certification or bets.

    Reject inconsistent bytes/clock/event/extra fields. Retain incomplete or
    unconfirmed lineups and changed starter identities as blocked reasons.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("MLB_PIT_SNAPSHOT_BYTES_REQUIRED")
    if type(manifest) is not dict or set(manifest) != MANIFEST_KEYS:
        raise ValueError("MLB_PIT_MANIFEST_FIELDS_INVALID")
    if manifest["schema"] != SCHEMA or manifest["source_id"] != "MLB_STATSAPI":
        raise ValueError("MLB_PIT_SOURCE_SCHEMA_INVALID")
    if not _id(manifest["event_id"]):
        raise ValueError("MLB_PIT_EVENT_ID_INVALID")
    expected = _digest(manifest["normalized_sha256"], "normalized")
    _digest(manifest["original_provider_sha256"], "original")
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError("MLB_PIT_NORMALIZED_BYTES_HASH_MISMATCH")
    start = _utc(manifest["event_start_utc"], "start")
    freeze = _utc(manifest["forecast_asof_utc"], "forecast")
    published = _utc(manifest["source_published_utc"], "published")
    captured = _utc(manifest["source_captured_utc"], "captured")
    if not (published <= captured <= freeze < start):
        raise ValueError("MLB_PIT_FUTURE_SOURCE_OR_FORECAST")
    try:
        snapshot = json.loads(raw.decode("utf-8-sig"),
                              object_pairs_hook=_pairs_no_duplicates,
                              parse_constant=_bad_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("MLB_PIT_SNAPSHOT_JSON_INVALID") from error
    if type(snapshot) is not dict or set(snapshot) != SNAPSHOT_KEYS:
        raise ValueError("MLB_PIT_SNAPSHOT_FIELDS_INVALID_OR_POSTGAME_DATA")
    if snapshot["schema"] != SCHEMA or snapshot["event_id"] != manifest["event_id"]:
        raise ValueError("MLB_PIT_EVENT_BINDING_INVALID")
    if _utc(snapshot["event_start_utc"], "snapshot_start") != start:
        raise ValueError("MLB_PIT_EVENT_START_CHANGED")
    if not _id(snapshot["home_team_id"]) or not _id(snapshot["away_team_id"]):
        raise ValueError("MLB_PIT_TEAM_ID_INVALID")
    if snapshot["home_team_id"] == snapshot["away_team_id"]:
        raise ValueError("MLB_PIT_DUPLICATE_OPPOSING_TEAM")

    blocked = []
    for name in ("starters_confirmed", "lineups_confirmed"):
        if type(snapshot[name]) is not bool:
            raise ValueError("MLB_PIT_CONFIRMATION_NOT_BOOLEAN:" + name)
        if not snapshot[name]:
            blocked.append("MLB_PIT_NOT_CONFIRMED:" + name)

    both_players = set()
    for side in ("home", "away"):
        team = snapshot[side + "_team_id"]
        starter = snapshot[side + "_starter_id"]
        if not _id(starter) or snapshot[side + "_starter_team_id"] != team:
            blocked.append("MLB_PIT_STARTER_ID_OR_TEAM_INVALID:" + side)
        members = snapshot[side + "_lineup"]
        if type(members) is not list or len(members) != 9:
            blocked.append("MLB_PIT_LINEUP_NOT_NINE_BATTERS:" + side)
            continue
        seen_slots = set()
        seen_players = set()
        for entry in members:
            if type(entry) is not dict or set(entry) != LINEUP_KEYS:
                blocked.append("MLB_PIT_LINEUP_FIELDS_INVALID:" + side)
                continue
            if type(entry["slot"]) is not int or entry["slot"] not in range(1, 10):
                blocked.append("MLB_PIT_LINEUP_SLOT_INVALID:" + side)
            elif entry["slot"] in seen_slots:
                blocked.append("MLB_PIT_LINEUP_SLOT_DUPLICATE:" + side)
            seen_slots.add(entry["slot"])
            if not _id(entry["player_id"]) or entry["team_id"] != team:
                blocked.append("MLB_PIT_LINEUP_PLAYER_TEAM_INVALID:" + side)
            elif entry["player_id"] in seen_players or entry["player_id"] in both_players:
                blocked.append("MLB_PIT_LINEUP_PLAYER_DUPLICATE:" + side)
            seen_players.add(entry["player_id"])
            both_players.add(entry["player_id"])
        if seen_slots != set(range(1, 10)):
            blocked.append("MLB_PIT_LINEUP_SLOTS_INCOMPLETE:" + side)
    if snapshot["home_starter_id"] == snapshot["away_starter_id"]:
        blocked.append("MLB_PIT_BOTH_TEAMS_SAME_STARTER")
    reasons = sorted(set(blocked))
    return {
        "schema": SCHEMA,
        "event_id": snapshot["event_id"],
        "status": ("PAPER_0U_STRUCTURAL_LINEUP_READY_NOT_AUTHENTICATED"
                   if not reasons else "PAPER_0U_BLOCKED_LINEUP"),
        "blocked_reasons": reasons,
        "lineup_structurally_complete": not reasons,
        "source_authenticated": False,
        "projection_calibrated": False,
        "original_provider_claim_sha256": manifest["original_provider_sha256"],
        "normalized_sha256": expected,
        "model_formula_changed": False,
        "official_counted": 0,
        "approved_stake_u": 0,
    }
