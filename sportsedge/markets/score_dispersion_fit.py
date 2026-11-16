"""Fit RESEARCH-ONLY score residual widths from a frozen, pre-cutoff ledger.

This is a descriptive TRAIN-ONLY fit, not independent point-in-time proof,
probability calibration, betting EV or official selection authorization.
No bookmaker odds, historical price or future results can be used as features.
All malformed, duplicate, future or unavailable records are retained as
blocked: a nonzero blocked count makes this entire fit unusable by RUN IT.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from statistics import stdev

UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SPORTS = frozenset({"NFL", "CFB", "CBB", "NBA", "MLB"})
REQUIRED = frozenset({
    "sport", "event_id", "start_utc", "forecast_asof_utc",
    "model_trained_until_utc", "features_published_utc", "features_captured_utc",
    "final_published_utc", "final_captured_utc",
    "projection_home", "projection_away", "final_home", "final_away",
    "model_sha256", "feature_sha256", "forecast_sha256", "final_sha256",
})
MAX_BYTES = 20_000_000
MAX_RECORDS = 100_000
FITTER_VERSION = "SPORTSEDGE_SCORE_RESIDUAL_TRAIN_ONLY_R1"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("NONFINITE_JSON_NUMBER")


def _clock(value, field):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise ValueError(field + ":UTC_Z_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(field + ":INVALID_TIMESTAMP") from exc


def _hash(value, field):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise ValueError(field + ":INVALID_SHA256")
    return value


def _float(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(field + ":INVALID_SCORE")
    v = float(value)
    if not math.isfinite(v) or not 0 <= v <= 500:
        raise ValueError(field + ":INVALID_SCORE")
    return v


def _actual(value, field):
    if type(value) is not int or not 0 <= value <= 500:
        raise ValueError(field + ":INVALID_FINAL")
    return value


def _one(record, sport, cutoff):
    if not isinstance(record, dict) or set(record) != REQUIRED:
        raise ValueError("INVALID_TRAINING_ROW_SCHEMA")
    if record["sport"] != sport:
        raise ValueError("MIXED_SPORT_IN_TRAINING_LEDGER")
    event = record["event_id"]
    if not isinstance(event, str) or not event.strip() or len(event)>160:
        raise ValueError("MISSING_STABLE_EVENT_ID")
    start = _clock(record["start_utc"], "start")
    freeze = _clock(record["forecast_asof_utc"], "forecast")
    trained = _clock(record["model_trained_until_utc"], "model_trained")
    published = _clock(record["features_published_utc"], "features_published")
    captured = _clock(record["features_captured_utc"], "features_captured")
    final = _clock(record["final_published_utc"], "final_published")
    settled = _clock(record["final_captured_utc"], "final_captured")
    if not (trained < freeze < start < final <= settled < cutoff
            and published <= captured <= freeze):
        raise ValueError("LOOKAHEAD_OR_UNAVAILABLE_RESULT")
    for key in ("model_sha256", "feature_sha256", "forecast_sha256", "final_sha256"):
        _hash(record[key], key)
    ph = _float(record["projection_home"], "projection_home")
    pa = _float(record["projection_away"], "projection_away")
    fh = _actual(record["final_home"], "final_home")
    fa = _actual(record["final_away"], "final_away")
    return event.strip(), start, final, (fh-fa)-(ph-pa), (fh+fa)-(ph+pa)


def private_path(value):
    path = Path(value).resolve()
    public_root = Path(__file__).resolve().parents[2]
    if path == public_root or public_root in path.parents:
        raise ValueError("PRIVATE_FIT_LEDGER_MUST_NOT_BE_IN_PUBLIC_REPO")
    return path


def fit_score_residuals(raw, *, sport, cutoff_utc, minimum_training=50,
                        minimum_dates=7):
    """Returns a strictly non-admission fit report with every rejection counted.

    Full original input census is preserved. ALL duplicate event copies are
    blocked; a single invalid row invalidates use of the fitted widths. The
    goal is auditability, not statistical claiming or automatic promotion.
    """
    if sport not in SPORTS:
        raise ValueError("UNSUPPORTED_SCORE_DISPERSION_SPORT")
    cutoff = _clock(cutoff_utc, "fit_asof")
    if type(minimum_training) is not int or minimum_training < 50:
        raise ValueError("MINIMUM_TRAINING_MUST_BE_AT_LEAST_50")
    if type(minimum_dates) is not int or minimum_dates < 7:
        raise ValueError("MINIMUM_DATES_MUST_BE_AT_LEAST_7")
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError("MISSING_OR_OVERSIZED_ORIGINAL_LEDGER")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("TRAINING_LEDGER_NOT_UTF8") from exc
    if not lines or len(lines) > MAX_RECORDS:
        raise ValueError("INVALID_TRAINING_LEDGER_SIZE")
    parsed = []
    errors = []
    for line in lines:
        if not line.strip():
            parsed.append(None)
            errors.append("EMPTY_TRAINING_RECORD")
            continue
        try:
            parsed.append(json.loads(line, object_pairs_hook=_unique,
                                     parse_constant=_reject_constant))
            errors.append(None)
        except (ValueError, TypeError, json.JSONDecodeError):
            parsed.append(None)
            errors.append("INVALID_JSONL_OR_DUPLICATE_FIELD")
    seen = Counter(
        (row.get("sport"), row.get("event_id").strip().casefold())
        for row in parsed if isinstance(row, dict) and
        isinstance(row.get("sport"), str) and
        isinstance(row.get("event_id"), str) and row.get("event_id").strip()
    )
    margin, total = [], []
    dates = set()
    latest = None
    trained_models = set()
    failed = Counter()
    for index, row in enumerate(parsed):
        error = errors[index]
        if error is None:
            if not isinstance(row, dict):
                error = "TRAINING_ROW_NOT_OBJECT"
            elif isinstance(row.get("sport"), str) and seen.get((row["sport"],
                            row.get("event_id").strip().casefold()
                            if isinstance(row.get("event_id"), str) else None), 0) > 1:
                error = "DUPLICATE_EVENT_ALL_COPIES_QUARANTINED"
            else:
                try:
                    _, start, published, m, t = _one(row, sport, cutoff)
                except (TypeError, ValueError, OverflowError, KeyError) as exc:
                    error = str(exc).splitlines()[0][:100]
                else:
                    dates.add(start.date())
                    trained_models.add(row["model_sha256"])
                    latest = published if latest is None else max(published, latest)
                    margin.append(m)
                    total.append(t)
        if error is not None:
            failed[error] += 1
    source_digest = "sha256:" + sha256(raw).hexdigest()
    n = len(margin)
    ready = n >= minimum_training and len(dates) >= minimum_dates and not failed
    width_m = stdev(margin) if n >= 2 else None
    width_t = stdev(total) if n >= 2 else None
    fit_failures = []
    if len(trained_models) != 1:
        fit_failures.append("MIXED_OR_MISSING_FORECAST_MODEL")
    if ready and (width_m is None or width_t is None or
                  not 0.1 <= width_m <= 150 or not 0.1 <= width_t <= 150):
        fit_failures.append("DEGENERATE_OR_OUT_OF_RANGE_FITTED_WIDTHS")
    if fit_failures:
        ready = False
    # Source/code/spec identity, not remotely signed historical attestation.
    spec = {"version":FITTER_VERSION, "source_sha256":source_digest,
            "sport":sport,"fit_asof_utc":cutoff_utc,
            "accepted_n":n, "minimum_training":minimum_training,
            "minimum_dates":minimum_dates,
            "code_sha256":sha256(Path(__file__).read_bytes()).hexdigest()}
    model_digest = "sha256:" + sha256(json.dumps(spec, sort_keys=True,
                separators=(",",":")).encode("utf-8")).hexdigest()
    return {
        "schema":FITTER_VERSION, "status": (
            "TRAIN_ONLY_WIDTHS_READY_RESEARCH_NOT_CALIBRATED" if ready
            else "BLOCK_DISPERSION_FIT"),
        "sport":sport, "fit_asof_utc":cutoff_utc,
        "source_file_sha256":source_digest, "fitter_model_sha256":model_digest,
        "total_rows":len(parsed), "accepted_rows":n,
        "blocked_rows":len(parsed)-n, "blocked_reasons":dict(sorted(failed.items())),
        "fit_failures":fit_failures,
        "training_model_sha256":next(iter(trained_models)) if len(trained_models)==1 else None,
        "distinct_start_dates":len(dates), "minimum_training":minimum_training,
        "minimum_dates":minimum_dates,
        "latest_accepted_final_published_utc":latest.isoformat() if latest else None,
        "sd_margin":round(width_m, 10) if ready else None,
        "sd_total":round(width_t, 10) if ready else None,
        "status_warning":("Research-only empirical residual variance. Operator "
            "timestamps and hashes are unverified; no independently authenticated "
            "PIT source, calibration, period split, odds or betting EV."),
        "official":False, "approved_stake_u":0,
        "release_gate_cleared":False,
    }


def run_cli(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True)
    p.add_argument("--sport",required=True,choices=sorted(SPORTS))
    p.add_argument("--cutoff-utc",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args(argv)
    source = private_path(args.input)
    target = private_path(args.out)
    report = fit_score_residuals(source.read_bytes(),
            sport=args.sport, cutoff_utc=args.cutoff_utc)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("x",encoding="utf-8") as f:
        json.dump(report,f,sort_keys=True,indent=2,allow_nan=False)
        f.write("\n")
    print(report["status"],"accepted",report["accepted_rows"],
          "blocked",report["blocked_rows"])


if __name__=="__main__":
    run_cli()
