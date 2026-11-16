"""SportsEdge evidence/quality monitor: immutable research inspection, never certification.

Input is PRIVATE, synthetic tests only in public GitHub. A SHA-256 field proves
neither provider authenticity nor point-in-time access. Never feed report output
back into a model or selection gate. No official pick, stake or pricing actions.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean

HASH = re.compile(r"^(?:sha256:)?[a-fA-F0-9]{64}$")
UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
SPORTS = {"NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"}
OUTCOMES = {"W", "L", "P"}


class Blocked(ValueError):
    pass


def _utc(value, field):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise Blocked(field + ":UTC_Z_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise Blocked(field + ":INVALID_TIME") from exc


def _digest(value, field):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise Blocked(field + ":INVALID_SHA256")
    return value.lower().removeprefix("sha256:")


def _required(data, name, keys):
    if not isinstance(data, dict):
        raise Blocked(name + ":OBJECT_REQUIRED")
    for key in keys:
        if key not in data or data[key] is None or data[key] == "":
            raise Blocked(name + ":MISSING_" + key.upper())
    return data


def _name(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise Blocked(field + ":INVALID")
    return " ".join(value.split()).casefold()


def _line(value):
    if value is None or value == "":
        return ""
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise Blocked("INVALID_LINE")
        return format(number.normalize(), "f")
    except (InvalidOperation, TypeError) as exc:
        raise Blocked("INVALID_LINE") from exc


def _prob(value):
    if isinstance(value, bool):
        raise Blocked("INVALID_PROBABILITY")
    try:
        p = float(value)
    except (TypeError, ValueError) as exc:
        raise Blocked("INVALID_PROBABILITY") from exc
    if not math.isfinite(p) or not 0 < p < 1:
        raise Blocked("INVALID_PROBABILITY")
    return p


def _price(value):
    if isinstance(value, bool):
        raise Blocked("INVALID_PRICE")
    try:
        v = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise Blocked("INVALID_PRICE") from exc
    if not v.is_finite() or v != v.to_integral_value() or abs(v) < 100 or abs(v) > 100000:
        raise Blocked("INVALID_PRICE")
    return int(v)


def _decimal_odds(price):
    return 1 + (price / 100 if price > 0 else 100 / abs(price))


def _identity(row):
    _required(row, "row", ("sport", "event_id", "period", "market", "side",
                           "tipoff_utc", "model", "source", "quote"))
    if row["sport"] not in SPORTS:
        raise Blocked("UNKNOWN_SPORT")
    for field in ("event_id", "period", "market", "side"):
        _name(row[field], field)
    market = _name(row["market"], "market")
    is_prop = ("prop" in market or any(x in market for x in
                ("passing", "rushing", "receiving", "rebounds", "assists",
                 "shots", "saves", "td", "first_basket", "home_run")))
    if is_prop and not row.get("subject_id"):
        raise Blocked("UNBOUND_SUBJECT_ID")
    if "total" in market or "spread" in market or is_prop or "alt" in market:
        if row.get("line") in (None, ""):
            raise Blocked("LINE_REQUIRED")
    return (row["sport"], _name(row["event_id"], "event_id"),
            _name(row["period"], "period"), market, _name(row["side"], "side"),
            _line(row.get("line")), _name(row["subject_id"], "subject_id")
            if row.get("subject_id") else "")


def _source(source, freeze):
    _required(source, "source", ("sha256", "data_through_utc", "published_utc",
                                 "captured_utc", "provider"))
    _digest(source["sha256"], "source")
    _name(source["provider"], "provider")
    through = _utc(source["data_through_utc"], "source.data_through_utc")
    published = _utc(source["published_utc"], "source.published_utc")
    captured = _utc(source["captured_utc"], "source.captured_utc")
    if not through <= published <= captured <= freeze:
        raise Blocked("SOURCE_LOOKAHEAD_OR_CLOCK_ORDER")


def _quote(quote, freeze, tipoff):
    _required(quote, "quote", ("sha256", "captured_utc", "price_american", "book"))
    _digest(quote["sha256"], "quote")
    _name(quote["book"], "quote.book")
    capture = _utc(quote["captured_utc"], "quote.captured_utc")
    if capture > freeze or capture >= tipoff:
        raise Blocked("QUOTE_AFTER_FREEZE_OR_TIPOFF")
    return _price(quote["price_american"]), capture


def _closing(close, row, take_price, take_capture, tipoff, fingerprint):
    if close is None:
        return None, "NO_CLOSING_RECEIPT"
    _required(close, "close", ("sha256", "captured_utc", "price_american",
                               "book", "sport", "event_id", "period",
                               "market", "side"))
    _digest(close["sha256"], "close")
    close_fingerprint = _identity({**row, "sport": close["sport"],
                                   "event_id": close["event_id"],
                                   "period": close["period"], "market": close["market"],
                                   "side": close["side"], "line": close.get("line"),
                                   "subject_id": close.get("subject_id")})
    if fingerprint != close_fingerprint:
        raise Blocked("CLOSE_MARKET_IDENTITY_MISMATCH")
    if _name(close["book"], "close.book") != _name(row["quote"]["book"], "quote.book"):
        raise Blocked("CLOSE_BOOK_MISMATCH")
    at = _utc(close["captured_utc"], "close.captured_utc")
    if not take_capture <= at < tipoff:
        raise Blocked("CLOSE_NOT_BETWEEN_TAKE_AND_TIPOFF")
    price = _price(close["price_american"])
    # Positive if our original price offers more payout than same-side close.
    prob_gain = 1 / _decimal_odds(price) - 1 / _decimal_odds(take_price)
    return round(prob_gain, 8), None


def inspect_one(row):
    """A single private frozen research row; never infer provider authenticity."""
    fingerprint = _identity(row)
    tipoff = _utc(row["tipoff_utc"], "tipoff_utc")
    model = _required(row["model"], "model", ("sha256", "trained_until_utc",
                                              "freeze_utc", "probability"))
    _digest(model["sha256"], "model")
    freeze = _utc(model["freeze_utc"], "model.freeze_utc")
    trained = _utc(model["trained_until_utc"], "model.trained_until_utc")
    if not trained < freeze < tipoff:
        raise Blocked("MODEL_FIT_FREEZE_TIPOFF_ORDER")
    p = _prob(model["probability"])
    _source(row["source"], freeze)
    take_price, captured = _quote(row["quote"], freeze, tipoff)
    result = None
    outcome = row.get("outcome")
    if outcome is not None:
        _required(outcome, "outcome", ("result", "settled_utc"))
        if outcome["result"] not in OUTCOMES:
            raise Blocked("UNKNOWN_RESULT")
        if _utc(outcome["settled_utc"], "outcome.settled_utc") <= tipoff:
            raise Blocked("OUTCOME_BEFORE_END")
        result = outcome["result"]
    clv = None
    clv_reason = "NO_CLOSING_RECEIPT"
    if row.get("close") is not None:
        clv, clv_reason = _closing(row["close"], row, take_price, captured,
                                  tipoff, fingerprint)
    return {"fingerprint": fingerprint, "captured": captured.isoformat(),
            "model_p": p, "result": result, "clv": clv,
            "clv_reason": clv_reason, "sport": row["sport"],
            "market": fingerprint[3]}


def _row_hash(row):
    try:
        raw = json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raw = repr(type(row))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _mean_or_none(values):
    return round(mean(values), 7) if values else None


def _quality_metrics(valid):
    decided = [x for x in valid if x["result"] in ("W", "L")]
    brier = [(x["model_p"] - int(x["result"] == "W"))**2 for x in decided]
    losses = [-math.log(x["model_p"] if x["result"] == "W"
                        else 1-x["model_p"]) for x in decided]
    closes = [x["clv"] for x in valid if x["clv"] is not None]
    return {"n_decided": len(decided), "n_clv_matched": len(closes),
            "n_clv_unmatched": len(valid)-len(closes),
            "brier_descriptive_not_forward_certified": _mean_or_none(brier),
            "log_loss_descriptive_not_forward_certified": _mean_or_none(losses),
            "clv_prob_gain_same_selection": _mean_or_none(closes)}


def inspect(rows):
    if not isinstance(rows, list):
        raise Blocked("ROWS_MUST_BE_LIST")
    output = []
    parsed_rows = []
    for i, row in enumerate(rows):
        item = {"input_index": i, "row_digest_prefix": _row_hash(row),
                "status": "BLOCKED", "official": False, "stake_u": 0}
        try:
            parsed = inspect_one(row)
            parsed_rows.append(parsed)
            item.update(status="RESEARCH_ONLY_CLOCK_CHECKED",
                        issue="NOT_PROVIDER_AUTHENTICATED",
                        market=parsed["market"], sport=parsed["sport"])
            if parsed["clv_reason"]:
                item["close_status"] = parsed["clv_reason"]
        except (Blocked, KeyError, TypeError, ValueError, OverflowError) as exc:
            parsed_rows.append(None)
            item["reason"] = str(exc).splitlines()[0][:100]
        output.append(item)

    # A selection decision is unique across different capture snapshots.
    # Do not accept the first copy and suppress later ones: ALL copies remain
    # blocked so nothing leaked into denominator or descriptive calibration.
    counts = Counter(p["fingerprint"] for p in parsed_rows if p is not None)
    valid = []
    for item, parsed in zip(output, parsed_rows):
        if parsed is None:
            continue
        if counts[parsed["fingerprint"]] > 1:
            item["status"] = "BLOCKED"
            item["reason"] = "DUPLICATE_SELECTION_ALL_COPIES_QUARANTINED"
            item.pop("issue", None)
            item.pop("close_status", None)
            continue
        valid.append(parsed)
    reasons = Counter(x.get("reason") for x in output if x["status"] == "BLOCKED")
    stats = _quality_metrics(valid)
    return {"schema": "SPORTSEDGE_OBSERVABILITY_V1",
            "status": "RESEARCH_ONLY_NOT_ADMISSION",
            "source_authenticated": False, "forward_validated": False,
            "official": False, "stake_u": 0, "pricing_enabled": False,
            "input_rows": len(rows), "clock_consistent_rows": len(valid),
            "blocked_rows": len(rows)-len(valid), "reasons": dict(sorted(reasons.items())),
            "metrics": stats, "rows": output,
            "scope_warning": "No bookmaker/source attestation, no no-vig or calibrated odds; never claim official EV/CLV certification."}


def run_cli(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="PRIVATE JSONL, not in public repo")
    p.add_argument("--out", required=True, help="create-only PRIVATE JSON report")
    args = p.parse_args(argv)
    src, dest = Path(args.input).resolve(), Path(args.out).resolve()
    root = Path(__file__).resolve().parents[2]
    for path in (src, dest):
        if path == root or root in path.parents:
            p.error("PRIVATE_DATA_AND_REPORT_PATH_OUTSIDE_PUBLIC_REPO_REQUIRED")
    if dest.exists():
        p.error("OUTPUT_EXISTS_CREATE_ONLY")
    lines = src.read_text(encoding="utf-8").splitlines()
    if len(lines) > 100000:
        p.error("ROW_LIMIT_100000")
    records = [json.loads(x) for x in lines if x.strip()]
    result = inspect(records)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("x", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("RESEARCH_ONLY / 0u; checked:", result["clock_consistent_rows"],
          "blocked:", result["blocked_rows"])


if __name__ == "__main__":
    run_cli()
