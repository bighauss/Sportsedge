#!/usr/bin/env python3
"""NFL QB/rest/venue-weather as-of evidence gate, not a points adjustment.

All observations are caller-provided source claims. A SHA of locally archived
bytes does not authenticate the provider or historical publication time.
Outputs PAPER/0u only, never fitted coefficients, probabilities or bets.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re

from score_walkforward_pit import utc

HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
QB_ID = re.compile(r"^[0-9]{2}-[0-9]{7}$")
EVENT_KEYS = frozenset({
    "event_id", "home_id", "away_id", "kickoff_utc", "freeze_utc",
})
RECEIPT_KEYS = frozenset({
    "source_id", "source_observed_utc", "captured_at_utc",
    "original_bytes_sha256",
})
ROSTER_KEYS = frozenset({
    "event_id", "home_qb_gsis_id", "away_qb_gsis_id",
    "home_qb_status", "away_qb_status", "official_inactives_received",
    "receipt",
})
REST_KEYS = frozenset({
    "event_id", "home_rest_days", "away_rest_days",
    "away_travel_km", "away_time_zones_crossed", "receipt",
})
WEATHER_KEYS = frozenset({
    "event_id", "roof_state", "forecast_valid_from_utc",
    "forecast_valid_until_utc", "wind_mph", "temperature_f",
    "precip_probability", "receipt",
})
QB_STATUS = frozenset({"EXPECTED", "CONFIRMED", "UNKNOWN"})
ROOF = frozenset({
    "OPEN_AIR", "RETRACTABLE_OPEN", "RETRACTABLE_CLOSED", "DOME_CLOSED",
    "ROOF_UNKNOWN",
})


def _shape(obj, keys, label):
    if not isinstance(obj, dict) or set(obj) != keys:
        raise ValueError("INVALID_" + label + "_SCHEMA")
    return obj


def _num(value, label, min_v, max_v):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("INVALID_" + label)
    try:
        x = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_" + label) from exc
    if not isfinite(x) or not min_v <= x <= max_v:
        raise ValueError("OUT_OF_BOUNDS_" + label)
    return x


def _receipt(record, *, event_id, freeze):
    if record["event_id"] != event_id:
        raise ValueError("SITUATIONAL_EVENT_ID_MISMATCH")
    receipt = _shape(record["receipt"], RECEIPT_KEYS, "SOURCE_RECEIPT")
    origin = receipt["source_id"]
    if not isinstance(origin, str) or not origin.strip() or len(origin) > 120:
        raise ValueError("SOURCE_ID_MISSING")
    digest = receipt["original_bytes_sha256"]
    if not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise ValueError("SOURCE_RAW_SHA256_INVALID")
    observed = utc(receipt["source_observed_utc"])
    captured = utc(receipt["captured_at_utc"])
    if not observed <= captured <= freeze:
        raise ValueError("SOURCE_NOT_AVAILABLE_AT_FORECAST_FREEZE")
    return {"source_id": origin, "source_observed_utc": observed.isoformat(),
            "captured_at_utc": captured.isoformat(), "sha256": digest,
            "independently_authenticated": False}


def situational_census(event, *, roster, rest, weather):
    e = _shape(event, EVENT_KEYS, "GAME_EVENT")
    event_id = e["event_id"]
    home, away = e["home_id"], e["away_id"]
    if not all(isinstance(s, str) and s.strip() for s in (event_id, home, away)):
        raise ValueError("EMPTY_EVENT_OR_TEAM_ID")
    if home == away:
        raise ValueError("HOME_AWAY_TEAM_ID_COLLISION")
    kickoff = utc(e["kickoff_utc"])
    freeze = utc(e["freeze_utc"])
    if freeze >= kickoff:
        raise ValueError("MODEL_FREEZE_NOT_PREGAME")
    r = _shape(roster, ROSTER_KEYS, "ROSTER")
    s = _shape(rest, REST_KEYS, "REST_TRAVEL")
    w = _shape(weather, WEATHER_KEYS, "WEATHER")
    receipts = {
        "roster": _receipt(r, event_id=event_id, freeze=freeze),
        "schedule": _receipt(s, event_id=event_id, freeze=freeze),
        "weather": _receipt(w, event_id=event_id, freeze=freeze),
    }
    issues = []
    qb = {}
    for side in ("home", "away"):
        ident = r[side+"_qb_gsis_id"]
        status = r[side+"_qb_status"]
        if status not in QB_STATUS:
            raise ValueError("UNSUPPORTED_QB_STATUS")
        if ident is not None and (not isinstance(ident, str) or not QB_ID.fullmatch(ident)):
            raise ValueError("UNBOUND_OR_MALFORMED_QB_GSIS_ID")
        if status == "CONFIRMED" and ident is None:
            raise ValueError("CONFIRMED_QB_WITHOUT_ID")
        if status != "CONFIRMED":
            issues.append(side.upper()+"_QB_NOT_CONFIRMED")
        qb[side+"_qb_gsis_id"] = ident
        qb[side+"_qb_status"] = status
    if type(r["official_inactives_received"]) is not bool:
        raise ValueError("INACTIVES_BOOLEAN_REQUIRED")
    if not r["official_inactives_received"]:
        issues.append("OFFICIAL_INACTIVES_NOT_CONFIRMED")
    home_rest = _num(s["home_rest_days"], "HOME_REST_DAYS", 0, 30)
    away_rest = _num(s["away_rest_days"], "AWAY_REST_DAYS", 0, 30)
    travel = _num(s["away_travel_km"], "AWAY_TRAVEL_KM", 0, 7500)
    zones = _num(s["away_time_zones_crossed"], "AWAY_TIME_ZONES", 0, 6)
    for name, value in (
        ("HOME_REST_DAYS", home_rest), ("AWAY_REST_DAYS", away_rest),
        ("AWAY_TRAVEL_KM", travel), ("AWAY_TIME_ZONES", zones),
    ):
        if value is None:
            issues.append("MISSING_"+name)
    roof = w["roof_state"]
    if roof not in ROOF:
        raise ValueError("UNKNOWN_ROOF_STATE_VALUE")
    valid_from = utc(w["forecast_valid_from_utc"])
    valid_until = utc(w["forecast_valid_until_utc"])
    if not valid_from <= kickoff <= valid_until:
        raise ValueError("WEATHER_VALIDITY_DOES_NOT_SPAN_KICKOFF")
    wind = _num(w["wind_mph"], "WIND_MPH", 0, 150)
    temp = _num(w["temperature_f"], "TEMPERATURE_F", -100, 150)
    precip = _num(w["precip_probability"], "PRECIP_PROBABILITY", 0, 1)
    if roof == "ROOF_UNKNOWN":
        issues.append("ROOF_STATE_NOT_CONFIRMED")
    elif roof in ("OPEN_AIR", "RETRACTABLE_OPEN"):
        if wind is None or temp is None or precip is None:
            issues.append("OUTDOOR_WEATHER_FORECAST_INCOMPLETE")
    # Closed roofs suppress weather adjustments; never replace missing outdoor
    # wind with an invented 0 mph value.
    weather_applicable = roof in ("OPEN_AIR", "RETRACTABLE_OPEN")
    output = {
        "status": "PAPER_HOLD_0U",
        "event_id": event_id,
        "home_id": home, "away_id": away,
        "kickoff_utc": kickoff.isoformat(),
        "freeze_utc": freeze.isoformat(),
        "qb": qb,
        "official_inactives_received_claim": r["official_inactives_received"],
        "home_rest_days": home_rest,
        "away_rest_days": away_rest,
        "away_travel_km": travel,
        "away_time_zones_crossed": zones,
        "roof_state": roof,
        "weather_applies_to_score_model": weather_applicable,
        "wind_mph_if_applicable": wind if weather_applicable else None,
        "temperature_f_if_applicable": temp if weather_applicable else None,
        "precip_probability_if_applicable": precip if weather_applicable else None,
        "issues": sorted(set(issues)),
        "claimed_inputs_complete": not bool(issues),
        "source_receipts": receipts,
        "independent_authentication": False,
        "fitted_situational_coefficients": None,
        "projected_score_adjustment": None,
        "official_counted": 0,
        "approved_stake_u": 0,
    }
    return output


def _read_payload(path):
    raw = Path(path).read_bytes()
    if not raw:
        raise ValueError("EMPTY_SOURCE_EXPORT")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("INPUT_JSON_OBJECT_REQUIRED")
    return payload, "sha256:" + sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--roster", required=True)
    parser.add_argument("--rest", required=True)
    parser.add_argument("--weather", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data, hashes = {}, {}
    for kind, path in (
        ("event", args.event), ("roster", args.roster),
        ("rest", args.rest), ("weather", args.weather),
    ):
        data[kind], hashes[kind] = _read_payload(path)
    result = situational_census(data["event"], roster=data["roster"],
                                rest=data["rest"], weather=data["weather"])
    result["local_export_file_sha256"] = hashes
    with Path(args.out).open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({"status": "PAPER_HOLD_0U",
                      "issues": result["issues"], "out": args.out}, sort_keys=True))


if __name__ == "__main__":
    main()
