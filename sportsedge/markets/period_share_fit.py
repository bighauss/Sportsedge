"""Train-only regulation-period shares for five-sport RUN IT research.

NFL/CFB/NBA regulation quarters, MLB regulation innings, and NCAA
men's CBB actual first/second halves are supported. Inventing four CBB
quarter shares from two halves is forbidden.

This code never authenticates an original statistical source, certifies a
distribution, infers game line value, updates model weights or stakes money.
Every malformed/future/duplicate row remains in the denominator and blocks
the *entire* fitting result. Do not optimize fitted shares on holdout returns.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
import argparse
import json
import math
from pathlib import Path
import re

UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
PERIODS = {
    "NFL": ("Q1", "Q2", "Q3", "Q4"),
    "CFB": ("Q1", "Q2", "Q3", "Q4"),
    "NBA": ("Q1", "Q2", "Q3", "Q4"),
    "CBB": ("H1", "H2"),
    "MLB": tuple("I" + str(i) for i in range(1, 10)),
}
FIT_VERSION = "SPORTSEDGE_REGULATION_PERIOD_SHARES_TRAIN_ONLY_R1"
KEYS = {
    "sport", "event_id", "game_start_utc", "final_published_utc",
    "final_captured_utc", "source_original_sha256",
    "periods", "regulation_home", "regulation_away",
    "settlement_scope",
}
MAX_SIZE = 20_000_000
MAX_ROWS = 100_000


def _duplicate_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("DUPLICATE_JSON_FIELD")
        data[key] = value
    return data


def _nonfinite(value):
    raise ValueError("NONFINITE_JSON_NUMBER")


def _clock(value, name):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise ValueError(name + "_MUST_BE_UTC_Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(name + "_INVALID_TIME") from exc


def _identity(record):
    if not isinstance(record, dict):
        return None
    sport, event = record.get("sport"), record.get("event_id")
    if isinstance(sport, str) and isinstance(event, str) and event.strip():
        return sport.strip().upper(), event.strip().casefold()
    return None


def _row(row, sport, cutoff):
    if not isinstance(row, dict) or set(row) != KEYS:
        raise ValueError("PERIOD_SOURCE_ROW_SCHEMA_MISMATCH")
    if row["sport"] != sport:
        raise ValueError("PERIOD_WRONG_SPORT")
    if _identity(row) is None or len(row["event_id"]) > 180:
        raise ValueError("PERIOD_EVENT_ID_MISSING")
    if row["settlement_scope"] != "REGULATION_ONLY":
        raise ValueError("PERIOD_OVERTIME_OR_EXTRA_INNINGS_NOT_SEPARATED")
    raw_hash = row["source_original_sha256"]
    if not isinstance(raw_hash, str) or not HASH.fullmatch(raw_hash):
        raise ValueError("PERIOD_SOURCE_HASH_NOT_PRESENT")
    start = _clock(row["game_start_utc"], "GAME_START")
    published = _clock(row["final_published_utc"], "FINAL_PUBLISHED")
    captured = _clock(row["final_captured_utc"], "FINAL_CAPTURED")
    if not start < published <= captured < cutoff:
        raise ValueError("PERIOD_FUTURE_OR_UNAVAILABLE_FINAL")
    periods = row["periods"]
    expected = PERIODS[sport]
    if not isinstance(periods, dict) or set(periods) != set(expected):
        raise ValueError("PERIOD_INCOMPLETE_OR_EXTRA_PERIOD")
    values = []
    for period in expected:
        points = periods[period]
        if (not isinstance(points, list) or len(points) != 2 or
                any(type(p) is not int or not 0 <= p <= 200 for p in points)):
            raise ValueError("PERIOD_INVALID_REGULATION_POINTS")
        values.append((points[0], points[1]))
    home, away = row["regulation_home"], row["regulation_away"]
    if (type(home) is not int or type(away) is not int
            or not 0 <= home <= 500 or not 0 <= away <= 500):
        raise ValueError("PERIOD_INVALID_REGULATION_TOTAL")
    if sum(v[0] for v in values) != home or sum(v[1] for v in values) != away:
        raise ValueError("PERIOD_REGULATION_TOTAL_RECONCILIATION_FAILED")
    return start.date(), [h+a for h, a in values]


def _private_path(raw_path):
    path = Path(raw_path)
    if path.is_symlink():
        raise ValueError("PERIOD_SOURCE_SYMLINK_REFUSED")
    p = path.resolve()
    root = Path(__file__).resolve().parents[2]
    if p == root or root in p.parents:
        raise ValueError("PERIOD_PRIVATE_PATH_REQUIRED")
    return p


def fit_period_shares(raw, *, sport, fit_asof_utc,
                      minimum_training=50, minimum_dates=7):
    """Aggregate all earlier regulation-period points, fail closed if any bad row.

    This is a deterministic *training-data-only* proportion estimate. It does
    NOT estimate period variance or validate conditional game simulation.
    """
    if sport not in PERIODS:
        raise ValueError("UNSUPPORTED_PERIOD_SHARE_SPORT")
    cutoff = _clock(fit_asof_utc, "PERIOD_FIT_ASOF")
    if type(minimum_training) is not int or minimum_training < 50:
        raise ValueError("PERIOD_MINIMUM_TRAINING_TOO_SMALL")
    if type(minimum_dates) is not int or minimum_dates < 7:
        raise ValueError("PERIOD_MINIMUM_DATES_TOO_SMALL")
    if type(raw) is not bytes or not raw or len(raw) > MAX_SIZE:
        raise ValueError("PERIOD_LEDGER_MISSING_OR_OVERSIZE")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("PERIOD_SOURCE_UTF8_REQUIRED") from exc
    if not lines or len(lines) > MAX_ROWS:
        raise ValueError("PERIOD_LEDGER_ROW_COUNT_INVALID")

    parsed = []
    failures = []
    for line in lines:
        try:
            parsed.append(json.loads(line, object_pairs_hook=_duplicate_keys,
                                     parse_constant=_nonfinite))
            failures.append(None)
        except (ValueError, TypeError, json.JSONDecodeError):
            parsed.append(None)
            failures.append("PERIOD_INVALID_JSON_OR_DUPLICATE_KEY")
    duplicate_counts = Counter(
        key for key in (_identity(rec) for rec in parsed) if key is not None)
    scored = [0]*len(PERIODS[sport])
    valid_rows = 0
    days = set()
    blocks = Counter()
    for index, row in enumerate(parsed):
        reason = failures[index]
        if reason is None:
            identity = _identity(row)
            if identity is not None and duplicate_counts[identity] > 1:
                reason = "PERIOD_DUPLICATE_EVENT_ALL_COPIES_QUARANTINED"
            else:
                try:
                    day, nums = _row(row, sport, cutoff)
                except (ValueError, TypeError, KeyError, OverflowError) as exc:
                    reason = str(exc).splitlines()[0][:120]
                else:
                    days.add(day)
                    valid_rows += 1
                    for j, value in enumerate(nums):
                        scored[j] += value
        if reason is not None:
            blocks[reason] += 1

    total = sum(scored)
    ready = valid_rows >= minimum_training and len(days) >= minimum_dates and not blocks
    fit_failures = []
    if total <= 0 or any(count == 0 for count in scored):
        fit_failures.append("PERIOD_ZERO_OBSERVED_REGULATION_SCORING")
    if fit_failures:
        ready = False
    original = "sha256:" + sha256(raw).hexdigest()
    spec = json.dumps({
        "version": FIT_VERSION, "sport": sport, "source": original,
        "cutoff": fit_asof_utc, "min_games": minimum_training,
        "min_dates": minimum_dates,
        "code": sha256(Path(__file__).read_bytes()).hexdigest(),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema": FIT_VERSION,
        "status": ("TRAIN_ONLY_PERIOD_SHARES_RESEARCH_UNCALIBRATED"
                   if ready else "BLOCK_PERIOD_SHARE_FIT"),
        "sport": sport, "fit_asof_utc": fit_asof_utc,
        "source_file_sha256": original,
        "period_fit_model_sha256": "sha256:" + sha256(spec).hexdigest(),
        "period_keys": list(PERIODS[sport]),
        "total_rows": len(parsed), "accepted_rows": valid_rows,
        "blocked_rows": len(parsed)-valid_rows,
        "blocked_reasons": dict(sorted(blocks.items())),
        "fit_failures": fit_failures,
        "distinct_dates": len(days),
        "period_shares": [value/total for value in scored] if ready else None,
        "source_authenticated": False,
        "holdout_calibrated": False,
        "official": False, "approved_stake_u": 0,
        "warning": "Observed regulation proportions only; not variance, "
                   "conditional timing dependence, original source attestation "
                   "or wagering edge certification.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sport", required=True)
    parser.add_argument("--fit-asof-utc", required=True)
    args = parser.parse_args(argv)
    src = _private_path(args.input)
    out = _private_path(args.out)
    if not src.is_file():
        parser.error("PERIOD_LEDGER_NOT_FOUND")
    result = fit_period_shares(src.read_bytes(), sport=args.sport,
                               fit_asof_utc=args.fit_asof_utc)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as fd:
        json.dump(result, fd, indent=2, sort_keys=True, allow_nan=False)
        fd.write("\n")
    print(result["status"], "accepted:", result["accepted_rows"],
          "blocked:", result["blocked_rows"])


if __name__ == "__main__":
    main()
