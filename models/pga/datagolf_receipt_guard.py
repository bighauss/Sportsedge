"""Offline fail-closed DataGolf receipt checks (engineering, not source authentication).

A local hash proves byte consistency only; it cannot prove the provider produced
the bytes or that their embedded timestamps are authentic.
"""
import hashlib
import re
from datetime import datetime, timezone

HEX = re.compile(r"^[0-9a-f]{64}$")
def utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("INVALID_UTC") from exc
    if result.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_REQUIRED")
    return result

def validate_receipt(receipt, *, decision_utc, event_start_utc,
                     max_age_seconds=300, require_observed=True):
    """Reject missing or inconsistent evidence before any model/market admission.

    The caller must supply provider-observed UTC independently; capture time
    alone is not proof that a quote or player update was current.
    """
    if not isinstance(receipt, dict):
        raise ValueError("RECEIPT_REQUIRED")
    raw = receipt.get("raw_bytes")
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("RAW_BYTES_REQUIRED")
    digest = receipt.get("source_sha256")
    if not isinstance(digest, str) or not HEX.fullmatch(digest):
        raise ValueError("INVALID_SHA256")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("ALTERED_BYTES")
    if receipt.get("status") != "UNVERIFIED_RESEARCH_PAPER_0U":
        raise ValueError("RESEARCH_STATUS_REQUIRED")
    if receipt.get("endpoint") not in {
        "players", "schedule", "field", "rankings", "skill", "decompositions",
        "pregame", "live_stats", "live_predictions", "outrights", "matchups",
        "historical_event_list", "historical_rounds", "pregame_archive"
    }:
        raise ValueError("UNKNOWN_ENDPOINT")
    captured = utc(receipt.get("captured_utc"))
    decision = utc(decision_utc)
    start = utc(event_start_utc)
    if not decision < start:
        raise ValueError("DECISION_NOT_PREGAME")
    if captured > decision:
        raise ValueError("CAPTURE_AFTER_DECISION")
    if not isinstance(max_age_seconds, (int,float)) or isinstance(max_age_seconds,bool) or max_age_seconds <= 0:
        raise ValueError("INVALID_MAX_AGE")
    observed_value = receipt.get("provider_observed_utc")
    if observed_value is None:
        if require_observed:
            raise ValueError("PROVIDER_OBSERVATION_MISSING")
        return {"status":"PAPER_0U_NO_OBSERVATION","digest":digest}
    observed = utc(observed_value)
    if observed > captured:
        raise ValueError("OBSERVED_AFTER_CAPTURE")
    if (decision - observed).total_seconds() > max_age_seconds:
        raise ValueError("STALE_SOURCE")
    return {"status":"PAPER_0U_UNAUTHENTICATED","digest":digest,
            "decision_utc":decision_utc,"captured_utc":receipt["captured_utc"]}
