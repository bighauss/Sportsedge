"""Private Open-Meteo original forecast -> RUN IT visible research overlay.

Replays the original request and provider response bytes against the captured
research report. Only exact scheduled sport/event/start matches are attached.
Weather never alters the SportsEdge forecast, sportsbook PriceReceipt or bet gate.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

from sportsedge.data.open_meteo_pit import (
    REPORT_SCHEMA, ForecastSourceError, parse_hourly, _json, _utc, _now,
)

WEATHER_SPORTS = frozenset({"NFL", "CFB", "MLB", "PGA"})
MAX_WEATHER_AGE_SECONDS = 21600
MAX_TRIPLETS = 500


class WeatherSlateError(ValueError):
    pass


def _timestamp(value, name):
    if not isinstance(value, str):
        raise WeatherSlateError("WEATHER_UTC_MISSING:" + name)
    if value.endswith("Z"):
        return _utc(value, name)
    if not value.endswith("+00:00"):
        raise WeatherSlateError("WEATHER_UTC_MUST_BE_ZERO_OFFSET:" + name)
    try:
        value = datetime.fromisoformat(value)
    except ValueError:
        raise WeatherSlateError("WEATHER_BAD_UTC:" + name) from None
    if value.utcoffset() != timedelta(0):
        raise WeatherSlateError("WEATHER_NOT_UTC:" + name)
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _verified_triplet(item):
    if not isinstance(item, dict) or set(item) != {
            "request_bytes", "original_bytes", "report_bytes",
            "original_filename"}:
        raise WeatherSlateError("INVALID_WEATHER_TRIPLET_FIELDS")
    raw_req, raw_provider, raw_report = (
        item["request_bytes"], item["original_bytes"], item["report_bytes"])
    try:
        req = _json(raw_req, "OPEN_METEO_ORIGINAL_REQUEST")
        report = _json(raw_report, "OPEN_METEO_ORIGINAL_REPORT")
    except ForecastSourceError as exc:
        raise WeatherSlateError("INVALID_WEATHER_TRIPLET_JSON:" + str(exc)) from None
    if report.get("schema") != REPORT_SCHEMA:
        raise WeatherSlateError("WRONG_WEATHER_REPORT_SCHEMA")
    captured = _timestamp(report.get("source_local_capture_utc"),
                          "local_capture")
    try:
        expected = parse_hourly(raw_provider, req, now=captured)
    except ForecastSourceError as exc:
        raise WeatherSlateError("ORIGINAL_WEATHER_REPLAY_FAILED:" + str(exc)) from None
    original_filename = item["original_filename"]
    if (not isinstance(original_filename, str) or not original_filename
            or "/" in original_filename or "\\" in original_filename
            or original_filename in (".", "..")):
        raise WeatherSlateError("INVALID_ORIGINAL_FILENAME")
    expected["request_sha256"] = "sha256:" + sha256(raw_req).hexdigest()
    expected["original_file_basename"] = original_filename
    if _canonical(expected) != _canonical(report):
        raise WeatherSlateError("WEATHER_SOURCE_REPORT_ORIGINAL_MISMATCH")
    return req, report, captured


def attach_weather_references(slate, triplets, *, now_utc=None):
    """Only presentation. Reject any tampered, unscheduled or repeated source."""
    if (not isinstance(slate, dict) or not isinstance(slate.get("events"), list)
            or slate.get("approved_stake_u") != 0
            or slate.get("official_counted") != 0
            or slate.get("issue10_release_certified") is not False
            or slate.get("card") is not None):
        raise WeatherSlateError("SLATE_NOT_PAPER_0U")
    if (not isinstance(triplets, (tuple, list))
            or len(triplets) > MAX_TRIPLETS):
        raise WeatherSlateError("BAD_WEATHER_SOURCE_BATCH")
    captured_by_event = {}
    for item in triplets:
        req, report, captured = _verified_triplet(item)
        identity = (req["sport"], req["event_id"])
        if identity in captured_by_event:
            raise WeatherSlateError("DUPLICATE_WEATHER_ORIGINAL_EVENT")
        captured_by_event[identity] = (req, report, captured)
    decision = _timestamp(slate.get("generated_at_utc"), "slate_generated")
    if now_utc is not None:
        decision = _now(now_utc)
    scheduled = {}
    for event in slate["events"]:
        if not isinstance(event, dict):
            raise WeatherSlateError("MALFORMED_SCHEDULE_EVENT")
        key = event.get("sport"), event.get("event_id")
        if key in scheduled:
            raise WeatherSlateError("DUPLICATE_SCHEDULE_EVENT")
        scheduled[key] = event
    if any(k not in scheduled for k in captured_by_event):
        raise WeatherSlateError("WEATHER_FOR_UNSCHEDULED_EVENT")
    result = deepcopy(slate)
    counts = {
        "scheduled_events": len(result["events"]),
        "original_triplets_validated": len(captured_by_event),
        "fresh_outdoor_research": 0,
        "stale_or_poststart": 0,
        "roof_or_venue_uncertain": 0,
        "unobserved_relevant_events": 0,
    }
    for event in result["events"]:
        key = event["sport"], event["event_id"]
        item = captured_by_event.get(key)
        overlay = {
            "state": ("NOT_CAPTURED_OPEN_METEO_WEATHER"
                      if key[0] in WEATHER_SPORTS
                      else "WEATHER_SOURCE_NOT_REQUESTED_FOR_THIS_SPORT"),
            "source": "OPEN_METEO_FREE_NONCOMMERCIAL",
            "original_provider_forecast_issue_utc": None,
            "provider_original_issue_clock_authenticated": False,
            "venue_mapping_independently_authenticated": False,
            "weather_model_weight_validated": False,
            "weather_used_for_odds_or_bets": False,
            "approved_stake_u": 0, "official_counted": 0,
        }
        if item is None and key[0] in WEATHER_SPORTS:
            counts["unobserved_relevant_events"] += 1
        if item is not None:
            req, receipt, captured = item
            start = _timestamp(event.get("start_utc"), "scheduled_event_start")
            requested_start = _timestamp(req["event_start_utc"], "request_start")
            if requested_start != start:
                raise WeatherSlateError("WEATHER_EVENT_START_MISMATCH")
            if captured > decision:
                raise WeatherSlateError("WEATHER_CAPTURE_AFTER_RUN_IT_DECISION")
            age = (decision - captured).total_seconds()
            if captured >= start or decision >= start:
                overlay["state"] = "BLOCK_WEATHER_LIVE_OR_AFTER_EVENT_START"
                counts["stale_or_poststart"] += 1
            elif age > MAX_WEATHER_AGE_SECONDS:
                overlay["state"] = "BLOCK_WEATHER_CAPTURE_STALE_OVER_6H"
                counts["stale_or_poststart"] += 1
            elif req["roof_status"] != "OPEN":
                overlay["state"] = "RESEARCH_WEATHER_EXPOSURE_NOT_CONFIRMED"
                counts["roof_or_venue_uncertain"] += 1
            else:
                overlay["state"] = "PAPER_OUTDOOR_FORECAST_REFERENCE_UNVERIFIED"
                counts["fresh_outdoor_research"] += 1
            overlay.update({
                "source_original_sha256": receipt["source_raw_sha256"],
                "source_request_sha256": receipt["request_sha256"],
                "local_capture_utc": receipt["source_local_capture_utc"],
                "forecast_hour_utc": receipt["forecast_valid_hour_utc"],
                "venue_id_owner_claim": receipt["venue_id"],
                "roof_status_owner_claim": receipt["roof_status_owner_claim"],
                "venue_coordinate_source_claim": receipt["coordinate_source_claim"],
                "event_hour_weather_forecast": receipt["event_hour_forecast"],
                "weather_units": receipt["forecast_units"],
                "attribution": receipt["required_attribution"],
                "mode": "NONCOMMERCIAL_RESEARCH_ONLY",
            })
        event["open_meteo_weather_reference"] = overlay
    result["open_meteo_weather_reference"] = {
        "state": "OPTIONAL_READ_ONLY_PAPER_0U_SOURCE_OVERLAY",
        "source_type": "OFFICIAL_KEYLESS_FORECAST_WITH_LOCAL_ORIGINAL_CAPTURE",
        "model_run_issue_time_verified": False,
        "source_publication_pit_certified": False,
        "commercial_reuse_permitted_by_free_tier": False,
        "forecast_model_was_not_refit_from_weather": True,
        "market_lines_and_betting_gate_unchanged": True,
        "counts": counts,
        "approved_stake_u": 0, "official_counted": 0,
    }
    return result


def load_triplets(private_path_triples):
    """Read owner-only private artifacts, don't touch network, no guessing IDs."""
    if not isinstance(private_path_triples, (list, tuple)) or len(private_path_triples) > MAX_TRIPLETS:
        raise WeatherSlateError("INVALID_PRIVATE_WEATHER_FILES")
    from sportsedge.data.open_meteo_pit import read_request
    result = []
    for trio in private_path_triples:
        if not isinstance(trio, (list, tuple)) or len(trio) != 3:
            raise WeatherSlateError("REQUEST_ORIGINAL_RECEIPT_FILES_REQUIRED")
        request_path, raw_path, report_path = trio
        if len({str(Path(p).resolve()) for p in trio}) != 3:
            raise WeatherSlateError("WEATHER_TRIPLET_PATHS_MUST_BE_DISTINCT")
        request_bytes, _ = read_request(request_path)
        raw_bytes, _ = read_request(raw_path)
        report_bytes, _ = read_request(report_path)
        result.append({
            "request_bytes": request_bytes,
            "original_bytes": raw_bytes, "report_bytes": report_bytes,
            "original_filename": Path(raw_path).name,
        })
    return result
