"""Bind a real pregame forecast file to a prior seven-sport PIT research freeze.

This is a local, owner-private, create-only RESEARCH receipt. Source publication
and wall-clock truth are NOT independently authenticated, and it never authorizes
wagers, promotions, prices, +EV claims or live CLV. No retroactive forecasts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from sportsedge.validation.seven_sport_pit_freeze import (
    _private_path, _raw_file, _utc, _unique_json, SPORTS, FAMILIES,
    PERIODS, SHA,
)

SCHEMA = "sportsedge-prospective-forecast-v1"
FREEZE_SCHEMA = "sportsedge-seven-sport-pit-freeze-record-v1"
FORECAST_FIELDS = frozenset({
    "schema", "state", "sport", "event_id", "market_family", "period",
    "model_version", "freeze_record_sha256", "model_code_sha256",
    "model_config_sha256", "feature_source_hashes", "generated_utc",
    "captured_utc", "predictions",
})
ROW_FIELDS = frozenset({"market_identity", "model_probability"})
MAX_FORECAST_BYTES = 5_000_000


def _parse(raw, label):
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json,
                          parse_constant=lambda x: (_ for _ in ()).throw(
                              ValueError("NONFINITE_JSON:" + x)))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("INVALID_OR_AMBIGUOUS_JSON:" + label) from exc
    if not isinstance(data, dict):
        raise ValueError("JSON_OBJECT_REQUIRED:" + label)
    return data


def _digest(x, label):
    if not isinstance(x, str) or not SHA.fullmatch(x):
        raise ValueError("INVALID_SHA256:" + label)
    return x


def _required(d, names, label):
    if not isinstance(d, dict) or not names <= set(d):
        raise ValueError("MISSING_REQUIRED_FIELDS:" + label)
    return d


def _prob(raw):
    if type(raw) is not str or not raw.strip():
        raise ValueError("PROBABILITY_MUST_BE_DECIMAL_STRING")
    try:
        x = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("INVALID_MODEL_PROBABILITY") from exc
    if not x.is_finite() or not Decimal(0) < x < Decimal(1):
        raise ValueError("MODEL_PROBABILITY_OUT_OF_OPEN_UNIT_INTERVAL")
    return x


def _identity(values, expected):
    if not isinstance(values, list) or len(values) != 10:
        raise ValueError("EXACT_TEN_PART_CANONICAL_MARKET_ID_REQUIRED")
    if any(type(v) is not str or len(v) > 128 or "|" in v or
           any(ord(ch) < 32 or ord(ch) > 126 for ch in v) or
           v.strip() != v for v in values):
        raise ValueError("INVALID_CANONICAL_MARKET_TOKEN")
    if values[:4] != expected or any(not values[i] for i in (4, 9)):
        raise ValueError("FORECAST_ROW_EVENT_MARKET_OR_SETTLEMENT_MISMATCH")
    return tuple(v.casefold() for v in values)


def _freeze_claims(freeze):
    required = frozenset((
        "schema", "state", "sport", "event_id", "market_family", "period",
        "model_version", "freeze_utc_claimed", "event_start_utc_claimed",
        "local_archive_created_utc", "model_code", "model_config",
        "feature_sources", "original_request_sha256",
        "source_externally_authenticated", "release_certified",
        "official_counted", "approved_stake_u",
    ))
    _required(freeze, required, "freeze_record")
    if (freeze["schema"] != FREEZE_SCHEMA
            or freeze["state"] != "PAPER_0U_LOCAL_CHRONOLOGY_ONLY"
            or freeze["source_externally_authenticated"] is not False
            or freeze["release_certified"] is not False
            or type(freeze["official_counted"]) is not int
            or freeze["official_counted"] != 0
            or type(freeze["approved_stake_u"]) is not int
            or freeze["approved_stake_u"] != 0):
        raise ValueError("NOT_AN_UNPROMOTED_SEVEN_SPORT_FREEZE")
    if (freeze["sport"] not in SPORTS or
            freeze["market_family"] not in FAMILIES or
            freeze["period"] not in PERIODS):
        raise ValueError("FREEZE_SPORT_MARKET_UNSUPPORTED")
    for field in ("event_id", "model_version"):
        if not isinstance(freeze[field], str) or not freeze[field].strip():
            raise ValueError("FREEZE_ID_INVALID:" + field)
    _digest(freeze["original_request_sha256"], "freeze_request")
    code = _digest(_required(freeze["model_code"], {"sha256"},
                             "model_code")["sha256"], "model_code")
    config = _digest(_required(freeze["model_config"], {"sha256"},
                               "model_config")["sha256"], "model_config")
    features = freeze["feature_sources"]
    if not isinstance(features, list) or not 1 <= len(features) <= 1000:
        raise ValueError("FREEZE_FEATURE_CENSUS_INVALID")
    hashes = {}
    for row in features:
        _required(row, {"source_id", "raw_file"}, "source_receipt")
        ident = row["source_id"]
        if not isinstance(ident, str) or not ident.strip() or ident in hashes:
            raise ValueError("DUPLICATE_OR_INVALID_FREEZE_SOURCE")
        hashes[ident] = _digest(_required(row["raw_file"], {"sha256"},
                                        "source_hash")["sha256"], "source")
    return code, config, hashes


def assess(freeze, forecast, *, original_freeze, original_forecast, actual_now=None):
    code, config, features = _freeze_claims(freeze)
    if not isinstance(forecast, dict) or set(forecast) != FORECAST_FIELDS:
        raise ValueError("INVALID_FORECAST_FIELDS")
    if (forecast["schema"] != SCHEMA or forecast["state"] != "PAPER_0U"
            or any(forecast[k] != freeze[k] for k in
                   ("sport", "event_id", "market_family", "period", "model_version"))):
        raise ValueError("FORECAST_NOT_SAME_UNPROMOTED_FREEZE")
    if _digest(forecast["freeze_record_sha256"], "freeze_ref") != (
            "sha256:" + sha256(original_freeze).hexdigest()):
        raise ValueError("FORECAST_DOES_NOT_BIND_ORIGINAL_FREEZE_BYTES")
    if (_digest(forecast["model_code_sha256"], "code") != code or
            _digest(forecast["model_config_sha256"], "config") != config):
        raise ValueError("FORECAST_MODEL_OR_CONFIG_HASH_CHANGED")
    if (not isinstance(forecast["feature_source_hashes"], dict) or
            forecast["feature_source_hashes"] != features):
        raise ValueError("FORECAST_INPUT_SOURCE_CENSUS_MISMATCH")
    frozen = _utc(freeze["freeze_utc_claimed"], "freeze")
    archived = _utc(freeze["local_archive_created_utc"], "archive")
    generated = _utc(forecast["generated_utc"], "forecast_generated")
    captured = _utc(forecast["captured_utc"], "forecast_captured")
    start = _utc(freeze["event_start_utc_claimed"], "event_start")
    now = datetime.now(timezone.utc) if actual_now is None else actual_now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("ACTUAL_NOW_MUST_BE_UTC")
    if not frozen <= archived <= generated <= captured <= now < start:
        raise ValueError("FORECAST_NOT_PROSPECTIVE_BEFORE_EVENT_START")
    if now - captured > timedelta(minutes=5):
        raise ValueError("STALE_BACKDATED_FORECAST_CAPTURE")
    rows = forecast["predictions"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
        raise ValueError("NONEMPTY_BOUNDED_FORECAST_ROWS_REQUIRED")
    seen = set()
    digests = []
    expected = [forecast[k] for k in ("sport", "event_id", "market_family", "period")]
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS:
            raise ValueError("INVALID_FORECAST_ROW_FIELDS")
        key = _identity(row["market_identity"], expected)
        if key in seen:
            raise ValueError("DUPLICATE_CANONICAL_FORECAST_SELECTION")
        seen.add(key)
        _prob(row["model_probability"])
        digests.append("sha256:" + sha256(
            json.dumps(key, separators=(",",":"), ensure_ascii=True).encode()
        ).hexdigest())
    if not isinstance(original_forecast, bytes) or not original_forecast:
        raise ValueError("ORIGINAL_FORECAST_BYTES_REQUIRED")
    return {
        "schema": "sportsedge-prospective-forecast-receipt-v1",
        "state": "PAPER_0U_LOCAL_FORECAST_BOUND_TO_FREEZE",
        "sport": forecast["sport"], "event_id": forecast["event_id"],
        "market_family": forecast["market_family"], "period": forecast["period"],
        "model_version": forecast["model_version"],
        "original_freeze_sha256": "sha256:" + sha256(original_freeze).hexdigest(),
        "original_forecast_sha256": "sha256:" + sha256(original_forecast).hexdigest(),
        "model_code_sha256": code, "model_config_sha256": config,
        "feature_count": len(features), "prediction_count": len(rows),
        "selection_identity_sha256": sorted(digests),
        "forecast_generated_utc_claimed": generated.isoformat(),
        "forecast_captured_utc_claimed": captured.isoformat(),
        "local_receipt_created_utc": now.isoformat(),
        "event_start_utc_claimed": start.isoformat(),
        "upstream_timestamps_authenticated": False,
        "original_forecast_independently_attested": False,
        "model_calibration_verified": False,
        "bookmaker_quote_verified": False,
        "clv_verified": False, "release_certified": False,
        "official_counted": 0, "approved_stake_u": 0, "card": None,
    }


def record_files(freeze_file, forecast_file, destination, *, actual_now=None):
    src = _private_path(freeze_file, "freeze")
    pred = _private_path(forecast_file, "forecast")
    out = _private_path(destination, "receipt", output=True)
    if src == pred or out in (src, pred):
        raise ValueError("SOURCE_AND_OUTPUT_PATHS_MUST_DIFFER")
    raw_freeze = _raw_file(src, "freeze")
    raw_forecast = _raw_file(pred, "forecast")
    if not len(raw_forecast) <= MAX_FORECAST_BYTES:
        raise ValueError("FORECAST_BYTES_TOO_LARGE")
    report = assess(_parse(raw_freeze, "freeze"), _parse(raw_forecast, "forecast"),
                    original_freeze=raw_freeze, original_forecast=raw_forecast,
                    actual_now=actual_now)
    payload = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(out, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--forecast", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    report = record_files(args.freeze, args.forecast, args.out)
    print(json.dumps({
        "status": report["state"], "sport": report["sport"],
        "predictions": report["prediction_count"],
        "approved_stake_u": 0, "official_counted": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
