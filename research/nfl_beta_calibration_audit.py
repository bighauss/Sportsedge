"""Prospective PAPER calibration; receipts prove integrity, not capture time."""
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from copy import deepcopy


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    return dt.astimezone(timezone.utc)


def _canonical_receipt(predictions):
    return json.dumps(
        {"schema": "nfl-beta-freeze-v1", "predictions": predictions},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def freeze_predictions(result, *, frozen_at_utc):
    """Return pregame PAPER records and exact canonical bytes for external storage.

    A local digest is an integrity link, not proof of source authenticity or
    independent capture/freeze time. Persist the receipt in an independently
    timestamped, append-only system before kickoff.
    """
    frozen = _utc(frozen_at_utc)
    if (not isinstance(result, dict) or result.get("status") != "RESEARCH_PAPER_0U"
            or not isinstance(result.get("rows"), list)):
        raise ValueError("INVALID_PRICING_RESULT")
    records, seen = [], set()
    for row in result["rows"]:
        if (not isinstance(row, dict) or row.get("status") != "PAPER_HOLD_0U"
                or type(row.get("stake_u")) is not int or row["stake_u"] != 0):
            raise ValueError("NOT_PAPER")
        offer = row.get("offer")
        if not isinstance(offer, dict):
            raise ValueError("EXACT_OFFER_REQUIRED")
        try:
            model_at = _utc(offer["model_asof_utc"])
            captured = _utc(offer["captured_at_utc"])
            decided = _utc(row["decision_utc"])
            kickoff = _utc(offer["kickoff_utc"])
            if not (model_at <= captured <= decided <= frozen < kickoff):
                raise ValueError("TIMESTAMP_ORDER")
            if (frozen - captured).total_seconds() > 300:
                raise ValueError("STALE_FREEZE_QUOTE")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("NO_VERIFIABLE_PREGAME_FREEZE") from exc
        identity = [offer.get(k) for k in ("event_id", "book", "quote_id")]
        if any(type(x) is not str or not x for x in identity):
            raise ValueError("INVALID_PREDICTION_IDENTITY")
        if (row.get("event_id") != identity[0]
                or row.get("offer_id") != identity[2]
                or row.get("kind") != offer.get("kind")):
            raise ValueError("OFFER_IDENTITY_MISMATCH")
        key = "sha256:" + hashlib.sha256(
            json.dumps(identity, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if key in seen:
            raise ValueError("DUPLICATE_PREDICTION")
        seen.add(key)
        record = deepcopy(row)
        record.update(prediction_id=key, frozen_at_utc=frozen_at_utc,
                      kickoff_utc=offer["kickoff_utc"])
        records.append(record)
    try:
        receipt = _canonical_receipt(records)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("NON_CANONICAL_FREEZE_INPUT") from exc
    digest = "sha256:" + hashlib.sha256(receipt).hexdigest()
    # The receipt hash is deliberately external to the hashed payload:
    # including its own SHA inside the bytes would be self-referential.
    for record in records:
        record["receipt_sha256"] = digest
    return records, receipt


def verify_frozen_receipt(records, receipt):
    """Check an exact receipt/record pair; does NOT authenticate its origin."""
    if type(records) is not list or type(receipt) is not bytes:
        raise ValueError("INVALID_FREEZE_RECEIPT")
    digest = "sha256:" + hashlib.sha256(receipt).hexdigest()
    payload = []
    for record in records:
        if type(record) is not dict or record.get("receipt_sha256") != digest:
            raise ValueError("RECEIPT_RECORD_LINK_MISMATCH")
        canonical_record = deepcopy(record)
        del canonical_record["receipt_sha256"]
        payload.append(canonical_record)
    try:
        reconstructed = _canonical_receipt(payload)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("NON_CANONICAL_RECEIPT_RECORD") from exc
    if reconstructed != receipt:
        raise ValueError("RECEIPT_RECORD_LINK_MISMATCH")
    return digest


def audit(predictions, outcomes, *, min_graded=100):
    if not isinstance(predictions, list) or not isinstance(outcomes, list):
        raise ValueError("INVALID_LEDGER")
    if type(min_graded) is not int or min_graded < 1:
        raise ValueError("INVALID_SAMPLE_FLOOR")
    actual = {}
    for o in outcomes:
        if not isinstance(o, dict) or not isinstance(o.get("prediction_id"), str) or not o["prediction_id"]:
            raise ValueError("INVALID_OUTCOME_ID")
        k = o["prediction_id"]
        if k in actual or type(o.get("result")) is not int or o["result"] not in (0, 1):
            raise ValueError("DUPLICATE_OR_INVALID_OUTCOME")
        actual[k] = o["result"]
    seen, buckets, ungraded = set(), defaultdict(list), 0
    for p in predictions:
        if not isinstance(p, dict) or not isinstance(p.get("prediction_id"), str) or not p["prediction_id"]:
            raise ValueError("INVALID_PREDICTION_ID")
        k = p["prediction_id"]
        if k in seen:
            raise ValueError("DUPLICATE_PREDICTION")
        seen.add(k)
        if p.get("status") != "PAPER_HOLD_0U" or type(p.get("stake_u")) is not int or p["stake_u"] != 0:
            raise ValueError("NOT_PAPER")
        prob = p.get("beta_probability")
        if prob is None:
            ungraded += 1
            continue
        if isinstance(prob, bool) or not isinstance(prob, (float, int)) or not math.isfinite(prob) or not 0 <= prob <= 1:
            raise ValueError("INVALID_PROBABILITY")
        try:
            if _utc(p["frozen_at_utc"]) >= _utc(p["kickoff_utc"]):
                raise ValueError("NO_VERIFIABLE_PREGAME_FREEZE")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("NO_VERIFIABLE_PREGAME_FREEZE") from exc
        if not isinstance(p.get("receipt_sha256"), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", p["receipt_sha256"]):
            raise ValueError("NO_FROZEN_RECEIPT")
        if p.get("kind") not in ("XPLUS", "FIRST_TD", "SGP"):
            raise ValueError("INVALID_MARKET_KIND")
        if k not in actual:
            ungraded += 1
            continue
        buckets[p["kind"]].append((prob, actual[k]))
    if set(actual) - seen:
        raise ValueError("ORPHAN_OUTCOME")
    summary = {}
    for kind, pairs in sorted(buckets.items()):
        n = len(pairs)
        brier = sum((p - y) ** 2 for p, y in pairs) / n
        base = sum(y for _, y in pairs) / n
        base_brier = sum((base - y) ** 2 for _, y in pairs) / n
        summary[kind] = dict(n=n, brier=round(brier, 6),
                             observed_hit_rate=round(base, 6),
                             baseline_brier=round(base_brier, 6),
                             baseline_scope="IN_SAMPLE_DESCRIPTIVE_NOT_PROSPECTIVE",
                             prospective_baseline_brier=None,
                             validated=False,
                             reason=("INSUFFICIENT_PROSPECTIVE_SAMPLE" if n < min_graded
                                     else "NEEDS_CHRONOLOGICAL_HOLDOUT_AND_CLV"))
    return dict(status="AUDIT_ONLY_NO_PROMOTION", families=summary,
                missing_or_ungraded=ungraded, official_bets=0)
