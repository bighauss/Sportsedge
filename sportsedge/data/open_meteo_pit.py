"""Open-Meteo no-key prospective weather source archive (NONCOMMERCIAL only).

One explicitly initiated, no-redirect official forecast GET per invocation.
Original provider bytes are retained privately. Only an original capture made
BEFORE the event may be used for PAPER forecast research: no retroactive model
run inference, no forecast/closing-book authentication and no wager admission.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlencode
from urllib import request as http

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "https://api.open-meteo.com/v1/forecast"
SCHEMA = "sportsedge-open-meteo-pregame-request-v1"
REPORT_SCHEMA = "sportsedge-open-meteo-original-forecast-receipt-v1"
FIELDS = (
    "temperature_2m", "wind_speed_10m", "wind_gusts_10m",
    "precipitation_probability", "cloud_cover",
)
UNITS = {
    "temperature_2m": "°F", "wind_speed_10m": "mp/h",
    "wind_gusts_10m": "mp/h", "precipitation_probability": "%",
    "cloud_cover": "%",
}
SPORTS = frozenset({"NFL", "CFB", "MLB", "PGA"})
ROOF = frozenset({"OPEN", "CLOSED", "RETRACTABLE_UNCONFIRMED", "UNKNOWN"})
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
MAX_BYTES = 2_000_000
QUERY_KEYS = (
    "latitude", "longitude", "hourly", "timezone", "temperature_unit",
    "wind_speed_unit", "forecast_days", "past_days",
)


class ForecastSourceError(ValueError):
    pass


def _utc(text, label):
    if not isinstance(text, str) or not text.endswith("Z"):
        raise ForecastSourceError("UTC_Z_REQUIRED:" + label)
    try:
        value = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        raise ForecastSourceError("BAD_UTC:" + label) from None
    if value.utcoffset() != timedelta(0):
        raise ForecastSourceError("BAD_UTC:" + label)
    return value


def _now(value=None):
    t = datetime.now(timezone.utc) if value is None else value
    if not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() != timedelta(0):
        raise ForecastSourceError("CAPTURE_CLOCK_MUST_BE_UTC")
    return t.astimezone(timezone.utc)


def _strict(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ForecastSourceError("DUPLICATE_ORIGINAL_JSON_KEY")
        obj[k] = v
    return obj


def _no_const(value):
    raise ForecastSourceError("NONFINITE_JSON_LITERAL")


def _json(raw, label):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ForecastSourceError("ORIGINAL_BYTES_MISSING_OR_OVERSIZED:" + label)
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict,
                         parse_constant=_no_const)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ForecastSourceError("INVALID_JSON:" + label) from None
    if not isinstance(obj, dict):
        raise ForecastSourceError("TOP_LEVEL_OBJECT_REQUIRED:" + label)
    return obj


def _number(n, name, lower, upper):
    if type(n) not in (int, float) or not math.isfinite(n) or not lower <= n <= upper:
        raise ForecastSourceError("INVALID_" + name)
    return n


def validate_request(data, *, now=None):
    if not isinstance(data, dict) or set(data) != {
            "schema", "sport", "event_id", "event_start_utc",
            "venue_id", "latitude", "longitude", "coordinate_source",
            "roof_status", "purpose"}:
        raise ForecastSourceError("INVALID_WEATHER_REQUEST_FIELDS")
    if data["schema"] != SCHEMA or data["sport"] not in SPORTS:
        raise ForecastSourceError("UNSUPPORTED_WEATHER_SPORT_OR_SCHEMA")
    for field in ("event_id", "venue_id", "coordinate_source"):
        x = data[field]
        if not isinstance(x, str) or not NAME.fullmatch(x):
            raise ForecastSourceError("INVALID_" + field.upper())
    if data["roof_status"] not in ROOF:
        raise ForecastSourceError("INVALID_ROOF_STATUS")
    if data["purpose"] != "PERSONAL_NONCOMMERCIAL_RESEARCH":
        raise ForecastSourceError("FREE_API_COMMERCIAL_USE_FORBIDDEN")
    lat = _number(data["latitude"], "LATITUDE", -90, 90)
    lon = _number(data["longitude"], "LONGITUDE", -180, 180)
    now = _now(now)
    start = _utc(data["event_start_utc"], "EVENT_START")
    if start <= now:
        raise ForecastSourceError("AFTER_EVENT_START_NO_PREGAME_CAPTURE")
    if start > now + timedelta(days=15, hours=23):
        raise ForecastSourceError("OUTSIDE_16_DAY_FORECAST_HORIZON")
    return (lat, lon, start, now)


def build_url(data, *, now=None):
    lat, lon, _, _ = validate_request(data, now=now)
    params = {
        "latitude": str(lat), "longitude": str(lon),
        "hourly": ",".join(FIELDS), "timezone": "GMT",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "forecast_days": "16", "past_days": "0",
    }
    if set(params) != set(QUERY_KEYS):
        raise ForecastSourceError("QUERY_FIELDS_MUST_BE_FIXED")
    return SOURCE + "?" + urlencode(params)


def parse_hourly(raw, data, *, now=None):
    lat, lon, start, captured = validate_request(data, now=now)
    doc = _json(raw, "OPEN_METEO_RESPONSE")
    if doc.get("error") is True:
        raise ForecastSourceError("PROVIDER_ERROR_RESPONSE")
    if doc.get("utc_offset_seconds") != 0 or doc.get("timezone") != "GMT":
        raise ForecastSourceError("PROVIDER_RESPONSE_MUST_USE_GMT")
    _number(doc.get("latitude"), "PROVIDER_LATITUDE", -90, 90)
    _number(doc.get("longitude"), "PROVIDER_LONGITUDE", -180, 180)
    if abs(doc["latitude"] - lat) > 1 or abs(doc["longitude"] - lon) > 1:
        raise ForecastSourceError("VENUE_RESPONSE_GRID_TOO_FAR")
    units = doc.get("hourly_units")
    if not isinstance(units, dict) or units.get("time") != "iso8601":
        raise ForecastSourceError("HOURLY_TIME_UNIT_MISSING")
    for key, expected in UNITS.items():
        if units.get(key) != expected:
            raise ForecastSourceError("INVALID_FORECAST_UNIT:" + key)
    hourly = doc.get("hourly")
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise ForecastSourceError("HOURLY_ARRAY_MISSING")
    times = hourly["time"]
    if not 0 < len(times) <= 400:
        raise ForecastSourceError("HOURLY_TIME_COUNT_INVALID")
    previous = None
    target = start.replace(minute=0, second=0, microsecond=0)
    target_index = None
    for index, value in enumerate(times):
        if (not isinstance(value, str)
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:00", value)):
            raise ForecastSourceError("INVALID_HOURLY_UTC_TIME")
        try:
            moment = datetime.fromisoformat(value + "+00:00")
        except ValueError:
            raise ForecastSourceError("INVALID_HOURLY_UTC_TIME") from None
        if previous is not None and moment <= previous:
            raise ForecastSourceError("DUPLICATE_OR_UNSORTED_PROVIDER_HOURLY_TIMES")
        previous = moment
        if moment == target:
            target_index = index
    if target_index is None:
        raise ForecastSourceError("EVENT_HOUR_NOT_IN_PROVIDER_FORECAST")
    result = {}
    for field in FIELDS:
        arr = hourly.get(field)
        if not isinstance(arr, list) or len(arr) != len(times):
            raise ForecastSourceError("FORECAST_HOURLY_COLUMN_LENGTH:" + field)
        number = arr[target_index]
        # Every value is a prediction at target hour, NOT an observation.
        _number(number, "EVENT_HOUR_" + field.upper(), -1000, 1000)
        if field in ("precipitation_probability", "cloud_cover") and not 0 <= number <= 100:
            raise ForecastSourceError("FORECAST_PERCENT_OUT_OF_RANGE:" + field)
        if field in ("wind_speed_10m", "wind_gusts_10m") and number < 0:
            raise ForecastSourceError("NEGATIVE_WIND_FORECAST")
        result[field] = number
    exposure = ("OUTDOOR_UNVERIFIED_COORDINATES"
                if data["roof_status"] == "OPEN" else
                "WEATHER_NOT_CONFIRMED_APPLICABLE_AT_CLOSED_OR_UNKNOWN_ROOF")
    return {
        "schema": REPORT_SCHEMA,
        "provider": "OPEN_METEO_FREE",
        "license": "CC_BY_4.0_NONCOMMERCIAL",
        "required_attribution": "Weather data by Open-Meteo.com",
        "documentation": "https://open-meteo.com/en/docs",
        "terms": "https://open-meteo.com/en/terms",
        "source_endpoint": SOURCE,
        "source_raw_sha256": "sha256:" + sha256(raw).hexdigest(),
        "source_raw_bytes": len(raw),
        "source_local_capture_utc": captured.isoformat().replace("+00:00", "Z"),
        "provider_forecast_issue_time_utc": None,
        "provider_model_run_issuance_verified": False,
        "provider_original_book_quotation_verified": False,
        "event_id": data["event_id"], "sport": data["sport"],
        "venue_id": data["venue_id"],
        "coordinates_manually_attested_only": True,
        "coordinate_source_claim": data["coordinate_source"],
        "latitude_requested": lat, "longitude_requested": lon,
        "latitude_provider_grid": doc["latitude"],
        "longitude_provider_grid": doc["longitude"],
        "roof_status_owner_claim": data["roof_status"],
        "exposure_status": exposure,
        "event_start_utc": data["event_start_utc"],
        "forecast_valid_hour_utc": target.isoformat().replace("+00:00", "Z"),
        "event_hour_forecast": result,
        "forecast_units": {key: units[key] for key in FIELDS},
        "weather_used_in_model_or_ev": False,
        "historical_pregame_publication_certified": False,
        "source_authenticated_by_independent_attestation": False,
        "event_status": "PAPER_0U_ORIGINAL_LOCAL_FORECAST_CAPTURE",
        "gate_a_closed": False, "official_counted": 0, "approved_stake_u": 0,
    }


class NoRedirect(http.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_forecast(data, *, now=None, terms_reviewed=False, opener=None):
    """Documented official endpoint only. API request is NOT an odds receipt."""
    if not terms_reviewed:
        raise ForecastSourceError("NONCOMMERCIAL_TERMS_REVIEW_REQUIRED")
    clock = _now(now)
    url = build_url(data, now=clock)
    transport = opener if opener is not None else http.build_opener(NoRedirect())
    req = http.Request(
        url, method="GET",
        headers={"Accept": "application/json", "User-Agent": "SportsEdgeWeatherResearch/1.0"},
    )
    try:
        with transport.open(req, timeout=12) as response:
            if (getattr(response, "status", None) != 200
                    or response.geturl() != url
                    or "application/json" not in response.headers.get("Content-Type", "")):
                raise ForecastSourceError("UNEXPECTED_HTTP_RESPONSE_OR_REDIRECT")
            raw = response.read(MAX_BYTES + 1)
    except (OSError, TimeoutError):
        raise ForecastSourceError("SOURCE_HTTP_UNAVAILABLE") from None
    if not 0 < len(raw) <= MAX_BYTES:
        raise ForecastSourceError("OPEN_METEO_BYTES_OVERSIZED_OR_EMPTY")
    return raw


def _private(path, *, existing=False, folder=False):
    lexical = Path(os.path.abspath(os.fspath(path)))
    resolved = lexical.resolve()
    for candidate in (lexical, resolved):
        if candidate == ROOT or ROOT in candidate.parents:
            raise ForecastSourceError("PUBLIC_REPOSITORY_PATH_FORBIDDEN")
    if any(part.is_symlink() for part in (lexical, *lexical.parents)):
        raise ForecastSourceError("SYMLINK_SOURCE_OR_OUTPUT_FORBIDDEN")
    if folder:
        if not lexical.is_dir() or lexical.stat().st_mode & 0o077:
            raise ForecastSourceError("PRIVATE_DESTINATION_0700_REQUIRED")
        return lexical
    if not lexical.parent.is_dir() or lexical.parent.stat().st_mode & 0o077:
        raise ForecastSourceError("PRIVATE_PARENT_0700_REQUIRED")
    if existing:
        if not lexical.is_file() or lexical.stat().st_mode & 0o077:
            raise ForecastSourceError("PRIVATE_INPUT_0600_REQUIRED")
    elif lexical.exists():
        raise FileExistsError("ORIGINAL_SOURCE_OUTPUT_EXISTS")
    return lexical


def read_request(path):
    p = _private(path, existing=True)
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > MAX_BYTES:
            raise ForecastSourceError("PRIVATE_SOURCE_FD_PERMISSION_OR_SIZE")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            raw = stream.read(MAX_BYTES + 1)
        return raw, _json(raw, "REQUEST")
    finally:
        if fd >= 0:
            os.close(fd)


def _write_private(path, payload):
    p = _private(path)
    fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        p.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)


def capture(request_path, destination_directory, *, terms_reviewed=False,
            opener=None, now=None):
    """Write actual provider original bytes and sanitized research receipt."""
    raw_request, info = read_request(request_path)
    clock = _now(now)
    validate_request(info, now=clock)
    folder = _private(destination_directory, folder=True)
    stem = info["event_id"] + "_" + clock.strftime("%Y%m%dT%H%M%SZ")
    original = folder / (stem + ".openmeteo.original.json")
    report = folder / (stem + ".openmeteo.report.json")
    # Check target names BEFORE an external provider request.
    _private(original)
    _private(report)
    raw = fetch_forecast(info, now=clock, terms_reviewed=terms_reviewed, opener=opener)
    # Archive original byte content even if its rows later fail validation.
    _write_private(original, raw)
    try:
        outcome = parse_hourly(raw, info, now=clock)
    except (ForecastSourceError, TypeError):
        # Keep raw evidence in private storage for independent forensic review.
        raise
    outcome["request_sha256"] = "sha256:" + sha256(raw_request).hexdigest()
    outcome["original_file_basename"] = original.name
    serialized = (json.dumps(outcome, sort_keys=True, indent=2, allow_nan=False)
                  + "\n").encode("utf-8")
    _write_private(report, serialized)
    return outcome


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_event_request")
    p.add_argument("--private-destination", required=True)
    p.add_argument("--noncommercial-terms-reviewed", action="store_true")
    args = p.parse_args(argv)
    result = capture(
        args.private_event_request, args.private_destination,
        terms_reviewed=args.noncommercial_terms_reviewed,
    )
    print(json.dumps({
        "status": result["event_status"], "event_id": result["event_id"],
        "weather_used_in_model_or_ev": False,
        "gate_a_closed": False, "approved_stake_u": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
