"""CFB original-source PIT preflight: never a provider authenticator or betting gate.

This validates an operator-supplied CFB research bundle before any model use.
The five independently preserved original byte streams are supplied to audit().
No current provider API is assumed; timestamps and inventory are caller claims.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re

SCHEMA = "sportsedge-cfb-source-pit-v1"
SOURCES = ("game", "team_stats", "qb", "weather", "injuries")
FAMILIES = ("ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP",
            "PERIOD", "SPECIAL", "ALTERNATE", "SGP")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:.-]{0,95}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_SOURCE_BYTES = 8_000_000
MAX_SOURCE_ROWS = 20_000


class PITRefused(ValueError):
    pass


def _utc(value):
    if not isinstance(value, str):
        raise PITRefused("SOURCE_TIME_INVALID")
    try:
        time = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise PITRefused("SOURCE_TIME_INVALID") from None
    if time.tzinfo is None or time.utcoffset().total_seconds() != 0:
        raise PITRefused("SOURCE_UTC_REQUIRED")
    return time.astimezone(timezone.utc)


def _identity(value):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise PITRefused("UNSTABLE_EVENT_OR_PARTICIPANT_ID")
    return value


def _unique_pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise PITRefused("ORIGINAL_DUPLICATE_JSON_KEY")
        out[k] = v
    return out


def _finite(v):
    if isinstance(v, float) and not math.isfinite(v):
        raise PITRefused("ORIGINAL_NONFINITE_NUMBER")
    if isinstance(v, dict):
        for x in v.values():
            _finite(x)
    elif isinstance(v, list):
        for x in v:
            _finite(x)


def _decode(data):
    try:
        parsed = json.loads(data, object_pairs_hook=_unique_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                PITRefused("ORIGINAL_NONFINITE_NUMBER")))
        _finite(parsed)
    except (UnicodeError, json.JSONDecodeError, OverflowError) as e:
        raise PITRefused("ORIGINAL_JSON_INVALID") from e
    if isinstance(parsed, list) and len(parsed) > MAX_SOURCE_ROWS:
        raise PITRefused("SOURCE_TOO_MANY_ROWS")
    return parsed


def _bounded_number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise PITRefused("MODEL_SOURCE_STAT_INVALID")
    return value


def _exact_two(rows, teams, *, kind):
    if not isinstance(rows, list):
        raise PITRefused(kind + "_ROWS_REQUIRED")
    ids = []
    for row in rows:
        if not isinstance(row, dict):
            raise PITRefused(kind + "_NONOBJECT")
        ids.append(_identity(row.get("team_id")))
    if len(ids) != len(set(ids)):
        raise PITRefused(kind + "_DUPLICATE_TEAM")
    if set(ids) != teams:
        raise PITRefused(kind + "_TEAM_ID_MISMATCH")
    return rows


def _market_census(rows):
    if not isinstance(rows, list):
        raise PITRefused("MARKET_FAMILY_CENSUS_REQUIRED")
    found = {}
    for row in rows:
        if not isinstance(row, dict):
            raise PITRefused("MARKET_ROW_INVALID")
        family = row.get("family")
        if family not in FAMILIES or family in found:
            raise PITRefused("MARKET_FAMILY_DUPLICATE_OR_UNKNOWN")
        state = row.get("state")
        if state not in ("NOT_CAPTURED", "BLOCKED", "CAPTURED_UNVERIFIED"):
            # A manually declared NOT_OFFERED is not source evidence.
            raise PITRefused("UNAUTHENTICATED_OFFER_STATE")
        if state == "CAPTURED_UNVERIFIED":
            if not isinstance(row.get("receipt_sha256"), str) or not HASH.fullmatch(row["receipt_sha256"]):
                raise PITRefused("CAPTURED_ROW_REQUIRES_ORIGINAL_RECEIPT_HASH")
        elif not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise PITRefused("UNAVAILABLE_MARKET_REASON_REQUIRED")
        found[family] = state
    if set(found) != set(FAMILIES):
        raise PITRefused("INCOMPLETE_ALL_MARKET_FAMILY_CENSUS")
    return found


def audit(original_bytes: dict[str, bytes], manifest: dict) -> dict:
    """Return a local PAPER/HOLD research verdict, never certified source proof."""
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise PITRefused("CFB_MANIFEST_SCHEMA_INVALID")
    if not isinstance(original_bytes, dict) or set(original_bytes) != set(SOURCES):
        raise PITRefused("ALL_FIVE_ORIGINAL_SOURCES_REQUIRED")
    eid = _identity(manifest.get("event_id"))
    season = manifest.get("season")
    if type(season) is not int or not 1900 <= season <= 2100:
        raise PITRefused("CFB_SEASON_INVALID")
    frozen, kickoff = _utc(manifest.get("frozen_utc")), _utc(manifest.get("kickoff_utc"))
    if frozen >= kickoff:
        raise PITRefused("FREEZE_NOT_BEFORE_KICKOFF")
    clocks = manifest.get("source_clock_receipts")
    if not isinstance(clocks, dict) or set(clocks) != set(SOURCES):
        raise PITRefused("SOURCE_CLOCK_CENSUS_INCOMPLETE")
    payloads, hashes = {}, {}
    for key in SOURCES:
        raw = original_bytes[key]
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_SOURCE_BYTES:
            raise PITRefused("ORIGINAL_SOURCE_BYTES_INVALID:" + key)
        receipt = clocks[key]
        if not isinstance(receipt, dict) or not isinstance(receipt.get("provider"), str) or not receipt["provider"].strip():
            raise PITRefused("SOURCE_PROVIDER_CLAIM_MISSING:" + key)
        digest = sha256(raw).hexdigest()
        if receipt.get("sha256") != digest:
            raise PITRefused("ORIGINAL_SOURCE_SHA_MISMATCH:" + key)
        published, observed, captured = (
            _utc(receipt.get(k)) for k in ("published_utc", "observed_utc", "captured_utc")
        )
        if not published <= observed <= captured <= frozen:
            raise PITRefused("SOURCE_LOOKAHEAD_OR_CLOCK_ORDER:" + key)
        payloads[key] = _decode(raw)
        hashes[key] = digest

    game = payloads["game"]
    if not isinstance(game, dict) or game.get("event_id") != eid or game.get("season") != season:
        raise PITRefused("CFB_GAME_ID_OR_SEASON_MISMATCH")
    if _utc(game.get("kickoff_utc")) != kickoff:
        raise PITRefused("GAME_KICKOFF_REVISED_WITHOUT_REFREEZE")
    home, away = _identity(game.get("home_team_id")), _identity(game.get("away_team_id"))
    if home == away:
        raise PITRefused("IDENTICAL_HOME_AWAY_TEAM")
    teams = {home, away}
    for row in _exact_two(payloads["team_stats"], teams, kind="STATS"):
        if row.get("season") != season:
            raise PITRefused("TEAM_STATS_SEASON_MISMATCH")
        _bounded_number(row.get("offense_ppa"), -5, 5)
        _bounded_number(row.get("defense_ppa"), -5, 5)
        _bounded_number(row.get("plays_per_game"), 10, 150)
    qb = _exact_two(payloads["qb"], teams, kind="QB")
    reasons = []
    for row in qb:
        _identity(row.get("qb_id"))
        status = row.get("starter_status")
        if status not in ("CONFIRMED", "QUESTIONABLE", "OUT", "UNKNOWN"):
            raise PITRefused("QB_STATUS_INVALID")
        if status != "CONFIRMED":
            reasons.append("QB_STARTER_NOT_CONFIRMED:" + row["team_id"])
    weather = payloads["weather"]
    if not isinstance(weather, dict) or weather.get("event_id") != eid:
        raise PITRefused("WEATHER_EVENT_ID_MISMATCH")
    if weather.get("is_forecast") is not True:
        reasons.append("WEATHER_NOT_A_PREGAME_FORECAST")
    else:
        _bounded_number(weather.get("wind_mph"), 0, 180)
    injuries = payloads["injuries"]
    if not isinstance(injuries, list):
        raise PITRefused("INJURY_CENSUS_REQUIRED")
    injury_ids = set()
    for item in injuries:
        if not isinstance(item, dict) or _identity(item.get("team_id")) not in teams:
            raise PITRefused("INJURY_TEAM_ID_MISMATCH")
        pid = _identity(item.get("player_id"))
        if (item["team_id"], pid) in injury_ids:
            raise PITRefused("DUPLICATE_INJURY_PLAYER_ID")
        injury_ids.add((item["team_id"], pid))
        if item.get("status") not in ("OUT", "QUESTIONABLE", "PROBABLE", "AVAILABLE", "UNKNOWN"):
            raise PITRefused("INJURY_STATUS_INVALID")
        if item["status"] in ("QUESTIONABLE", "UNKNOWN"):
            reasons.append("INJURY_PARTICIPATION_UNRESOLVED:" + pid)
    market_states = _market_census(manifest.get("market_family_census"))
    if any(x != "CAPTURED_UNVERIFIED" for x in market_states.values()):
        reasons.append("ORIGINAL_ALL_MARKET_QUOTES_INCOMPLETE")
    # Even a perfectly matched source hash and complete market census are
    # just local operator claims, NOT authenticated primary DK/book lineage.
    return {
        "status": "BLOCK" if reasons else "PAPER_0U_LOCAL_CFB_SOURCE_CLAIMS_ONLY",
        "reasons": sorted(set(reasons)),
        "sport": "CFB", "event_id": eid, "season": season,
        "home_team_id": home, "away_team_id": away,
        "source_raw_sha256": hashes,
        "observed_market_family_states": market_states,
        "source_externally_authenticated": False,
        "market_inventory_authenticated": False,
        "no_future_features_proven_externally": False,
        "model_projections_generated": False,
        "market_priced": False,
        "gate_a_closed": False, "gate_b_closed": False,
        "official_counted": 0, "approved_stake_u": 0,
    }
