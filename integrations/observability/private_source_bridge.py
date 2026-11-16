"""Private original-byte decision -> local observability v1 bridge.

No source accounts, signed upstream clock, original book authenticity, real
betting/CLV verification, model promotion, or external telemetry is implied.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
import math
import os
from pathlib import Path
import re
import stat

from integrations.observability import quality_gate

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "sportsedge-private-observability-attempt-v1"
SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_BYTES = 8_000_000
MAX_ROWS = 10000
REQUIRED = ("freeze", "forecast", "source", "take")


class BridgeHold(ValueError):
    pass


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise BridgeHold("ORIGINAL_JSON_NONFINITE")
    if isinstance(value, dict):
        for v in value.values():
            _finite(v)
    elif isinstance(value, list):
        for v in value:
            _finite(v)


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise BridgeHold("ORIGINAL_JSON_DUPLICATE_KEY")
        obj[key] = value
    return obj


def _json(raw):
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              BridgeHold("ORIGINAL_JSON_NONFINITE")))
        _finite(data)
    except (UnicodeError, json.JSONDecodeError, OverflowError, RecursionError) as exc:
        raise BridgeHold("ORIGINAL_JSON_MALFORMED") from exc
    if type(data) is not dict:
        raise BridgeHold("ORIGINAL_OBJECT_REQUIRED")
    return data


def _path(value, *, output=False):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise BridgeHold("PRIVATE_ABSOLUTE_PATH_REQUIRED")
    path = Path(os.path.abspath(value))
    resolved = path.resolve()
    for check in (path, resolved):
        if check == ROOT or ROOT in check.parents:
            raise BridgeHold("PUBLIC_REPO_PATH_REFUSED")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise BridgeHold("PRIVATE_SYMLINK_REFUSED")
    parent = path.parent
    if (not parent.is_dir() or parent.stat().st_uid != os.getuid()
            or stat.S_IMODE(parent.stat().st_mode) != 0o700):
        raise BridgeHold("PRIVATE_PARENT_MUST_BE_OWNER_0700")
    if output:
        if path.exists():
            raise BridgeHold("PRIVATE_OUTPUT_MUST_BE_NEW")
        return path
    if not path.is_file():
        raise BridgeHold("PRIVATE_ORIGINAL_NOT_FILE")
    return path


def _read(value, expected=None):
    path = _path(value)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or stat.S_IMODE(st.st_mode) != 0o600
                or not 0 < st.st_size <= MAX_BYTES):
            raise BridgeHold("ORIGINAL_NOT_OWNER_0600_OR_BOUNDED")
        with os.fdopen(fd, "rb") as f:
            fd = -1
            raw = f.read(MAX_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    if not 0 < len(raw) <= MAX_BYTES:
        raise BridgeHold("ORIGINAL_BYTES_INVALID")
    actual = "sha256:" + sha256(raw).hexdigest()
    if expected is not None and actual != expected:
        raise BridgeHold("ORIGINAL_SHA_MISMATCH")
    return raw, actual


def _receipt(attempt, name, expected=None):
    ref = attempt["originals"].get(name)
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise BridgeHold("MISSING_ORIGINAL_RECEIPT:" + name)
    digest = ref["sha256"]
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise BridgeHold("ORIGINAL_DIGEST_INVALID:" + name)
    raw, actual = _read(ref["path"], digest)
    if expected is not None and actual != expected:
        raise BridgeHold("CLAIMED_RECEIPT_SHA_MISMATCH:" + name)
    return raw, actual


def _identity(selection):
    try:
        return quality_gate._identity({
            **selection, "source": {}, "quote": {}, "model": {},
        })
    except (ValueError, KeyError, TypeError) as exc:
        raise BridgeHold("INVALID_SELECTION_IDENTITY") from exc


def _exact_document(raw, marker, selection, fields):
    doc = _json(raw)
    if doc.get("schema") != marker or doc.get("selection") != selection:
        raise BridgeHold("ORIGINAL_SELECTION_OR_SCHEMA_MISMATCH")
    for name, value in fields.items():
        if doc.get(name) != value:
            raise BridgeHold("ORIGINAL_RECEIPT_CONTENT_MISMATCH:" + name)


def _safe_attempt(attempt):
    if type(attempt) is not dict or attempt.get("schema") != SCHEMA:
        raise BridgeHold("ATTEMPT_SCHEMA_INVALID")
    if not isinstance(attempt.get("decision_id"), str) or not attempt["decision_id"].strip():
        raise BridgeHold("DECISION_ID_REQUIRED")
    if attempt.get("state") == "BLOCKED":
        reason = attempt.get("block_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise BridgeHold("ORIGINAL_EXCLUSION_REASON_REQUIRED")
        return None, "ORIGINAL_BLOCKED:" + reason.strip()[:80]
    if attempt.get("state") != "PAPER_0U":
        raise BridgeHold("ATTEMPT_NOT_RESEARCH_ONLY")
    selection = attempt.get("selection")
    if not isinstance(selection, dict):
        raise BridgeHold("SELECTION_OBJECT_REQUIRED")
    _identity(selection)
    original = attempt.get("originals")
    if not isinstance(original, dict):
        raise BridgeHold("ORIGINAL_RECEIPT_CENSUS_REQUIRED")
    model, source, take = (attempt.get(k) for k in ("model", "source", "take"))
    if not all(isinstance(x, dict) for x in (model, source, take)):
        raise BridgeHold("MODEL_SOURCE_TAKE_REQUIRED")
    expected_names = set(REQUIRED)
    if attempt.get("close") is not None:
        expected_names.add("close")
    if attempt.get("outcome") is not None:
        expected_names.add("outcome")
    if set(original) != expected_names:
        raise BridgeHold("ORIGINAL_RECEIPT_DENOMINATOR_MISMATCH")
    freeze_raw, freeze_sha = _receipt(attempt, "freeze")
    forecast_raw, forecast_sha = _receipt(attempt, "forecast")
    _receipt(attempt, "source", source.get("sha256"))
    take_raw, _ = _receipt(attempt, "take", take.get("sha256"))
    # This checks locally present bytes, NOT their upstream signer or
    # independent publication time.
    _exact_document(forecast_raw, "SPORTSEDGE_OBS_FORECAST_ROW_V1", selection, {
        "model_sha256": model.get("sha256"),
        "freeze_sha256": freeze_sha,
        "model_probability": model.get("probability"),
    })
    _exact_document(take_raw, "SPORTSEDGE_OBS_QUOTE_ROW_V1", selection, {
        "book": take.get("book"),
        "price_american": take.get("price_american"),
        "captured_utc": take.get("captured_utc"),
    })
    if "forecast_sha256" not in model or model["forecast_sha256"] != forecast_sha:
        raise BridgeHold("MODEL_FORECAST_ORIGINAL_SHA_MISMATCH")
    if attempt.get("freeze_sha256") != freeze_sha:
        raise BridgeHold("ORIGINAL_FREEZE_BINDING_MISMATCH")
    close = attempt.get("close")
    if close is not None:
        if type(close) is not dict:
            raise BridgeHold("CLOSE_OBJECT_REQUIRED")
        close_raw, _ = _receipt(attempt, "close", close.get("sha256"))
        _exact_document(close_raw, "SPORTSEDGE_OBS_QUOTE_ROW_V1", selection, {
            "book": close.get("book"),
            "price_american": close.get("price_american"),
            "captured_utc": close.get("captured_utc"),
        })
    outcome = attempt.get("outcome")
    if outcome is not None:
        if type(outcome) is not dict:
            raise BridgeHold("OUTCOME_OBJECT_REQUIRED")
        final_raw, _ = _receipt(attempt, "outcome", outcome.get("sha256"))
        _exact_document(final_raw, "SPORTSEDGE_OBS_OUTCOME_ROW_V1", selection, {
            "result": outcome.get("result"),
            "settled_utc": outcome.get("settled_utc"),
        })
        if ("observed_utc" not in outcome or "captured_utc" not in outcome):
            raise BridgeHold("OUTCOME_OBSERVATION_CLOCKS_REQUIRED")
        try:
            settled = quality_gate._utc(outcome["settled_utc"], "settled")
            observed = quality_gate._utc(outcome["observed_utc"], "observed")
            captured = quality_gate._utc(outcome["captured_utc"], "captured")
        except (quality_gate.Blocked, KeyError, TypeError) as exc:
            raise BridgeHold("INVALID_FINAL_OBSERVATION_CLOCKS") from exc
        if not settled <= observed <= captured:
            raise BridgeHold("OUTCOME_OBSERVATION_BEFORE_SETTLEMENT")
    row = {**selection,
           "model": {k: model[k] for k in (
               "sha256", "trained_until_utc", "freeze_utc", "probability")},
           "source": source, "quote": take}
    if close is not None:
        row["close"] = {k: v for k, v in close.items() if k != "sha256"}
        row["close"]["sha256"] = close["sha256"]
    if outcome is not None:
        row["outcome"] = {"result": outcome["result"],
                          "settled_utc": outcome["settled_utc"]}
    try:
        quality_gate.inspect_one(row)
    except (quality_gate.Blocked, KeyError, TypeError, ValueError) as exc:
        raise BridgeHold("QUALITY_GATE:" + str(exc).splitlines()[0][:80]) from exc
    # Model/source/quote are intentionally still only self-reported originals.
    return row, None


def transform(raw_lines):
    """Return one downstream row PER original attempt, including failures."""
    if not isinstance(raw_lines, list) or not 0 < len(raw_lines) <= MAX_ROWS:
        raise BridgeHold("ORIGINAL_ATTEMPT_COUNT_REQUIRED")
    records = []
    for i, raw in enumerate(raw_lines):
        attempt, key, ident = None, None, None
        reason = None
        try:
            attempt = _json(raw)
            ident = attempt.get("decision_id")
            if isinstance(attempt.get("selection"), dict):
                try:
                    key = _identity(attempt["selection"])
                except BridgeHold:
                    pass
            row, reason = _safe_attempt(attempt)
        except OSError:
            # Host OS errors can contain the PRIVATE full path or player name;
            # never copy their raw exception text into a diagnostics report.
            row = None
            reason = "PRIVATE_ORIGINAL_IO_FAILURE"
        except (BridgeHold, KeyError, TypeError, ValueError) as exc:
            row = None
            reason = str(exc).splitlines()[0][:100]
        records.append({"index": i, "identity": key, "decision_id": ident,
                        "row": row, "reason": reason,
                        "attempt_sha256": sha256(raw).hexdigest()})
    ids = Counter(x["decision_id"] for x in records
                  if isinstance(x["decision_id"], str) and x["decision_id"])
    choices = Counter(x["identity"] for x in records if x["identity"] is not None)
    normalized = []
    report_rows = []
    for item in records:
        reasons = []
        if item["reason"]:
            reasons.append(item["reason"])
        if item["identity"] is not None and choices[item["identity"]] > 1:
            reasons.append("DUPLICATE_CANONICAL_SELECTION_ALL_COPIES_BLOCKED")
        if isinstance(item["decision_id"], str) and ids[item["decision_id"]] > 1:
            reasons.append("DUPLICATE_DECISION_ID_ALL_COPIES_BLOCKED")
        reason = "|".join(sorted(set(reasons)))
        if reason:
            normalized.append({"bridge_refusal": "BLOCKED_NOT_AUTHENTICATED"})
        else:
            normalized.append(item["row"])
        report_rows.append({
            "input_index": item["index"],
            "original_attempt_sha256": item["attempt_sha256"],
            "status": "BLOCKED" if reason else "RESEARCH_ONLY_UNAUTHENTICATED",
            "reason": reason or None,
        })
    downstream = quality_gate.inspect(normalized)
    accepted = sum(x["status"] != "BLOCKED" for x in report_rows)
    return normalized, {
        "schema": "SPORTSEDGE_PRIVATE_SOURCE_BRIDGE_V1",
        "state": ("BLOCKED_INCOMPLETE_OR_CONFLICTING_ORIGINALS"
                  if accepted < len(records) else "PAPER_0U_LOCAL_ONLY"),
        "attempted_rows": len(records), "locally_checked_rows": accepted,
        "blocked_rows": len(records)-accepted,
        "rows": report_rows,
        "quality_gate_aggregate": {
            "input_rows": downstream["input_rows"],
            "clock_consistent_rows": downstream["clock_consistent_rows"],
            "blocked_rows": downstream["blocked_rows"],
            "n_clv_matched_unverified": downstream["metrics"]["n_clv_matched"],
        },
        "source_original_book_authenticated": False,
        "provider_publication_clock_authenticated": False,
        "genuine_clv_certified": False, "forward_validated": False,
        "official": False, "approved_stake_u": 0,
    }


def _write_new(path, payload):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as dst:
            fd = -1
            dst.write(payload)
            dst.flush()
            os.fsync(dst.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)


def private_cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", required=True)
    parser.add_argument("--normalized", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    src = _path(args.attempts)
    out = _path(args.normalized, output=True)
    report = _path(args.report, output=True)
    if len({src, out, report}) != 3:
        raise BridgeHold("INPUT_OUTPUT_PATH_COLLISION")
    raw, _ = _read(str(src))
    original_lines = [v for v in raw.splitlines() if v.strip()]
    normalized, result = transform(original_lines)
    payload = b"".join(
        (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode()
        for row in normalized
    )
    result["original_attempts_sha256"] = "sha256:" + sha256(raw).hexdigest()
    encoded = (json.dumps(result, sort_keys=True, allow_nan=False, indent=2)
               + "\n").encode()
    _write_new(out, payload)
    try:
        _write_new(report, encoded)
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    print(json.dumps({
        "status": result["state"], "attempted_rows": result["attempted_rows"],
        "blocked_rows": result["blocked_rows"], "official": False,
        "approved_stake_u": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(private_cli())
