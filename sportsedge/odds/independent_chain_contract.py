"""Research-only check of independently attested original bookmaker source chains.

A logo, aggregator display, hash, or self-reported provider is NOT authentication.
"""
import re
from datetime import datetime, timezone

class ChainHold(ValueError):
    pass

SHA = re.compile(r"^[a-f0-9]{64}$")
FIELDS = ("sport", "event_id", "market", "period", "participant_id", "side", "line", "settlement_rule")
SPORTS = {"NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"}

def _utc(v):
    if not isinstance(v, str) or not v.endswith("Z"):
        raise ChainHold("UTC_REQUIRED")
    try:
        t = datetime.fromisoformat(v[:-1] + "+00:00")
    except ValueError as e:
        raise ChainHold("UTC_INVALID") from e
    return t.astimezone(timezone.utc)

def _identity(q):
    vals = []
    for field in FIELDS:
        v = q.get(field)
        if isinstance(v, bool) or not isinstance(v, (str, int, float)) or not str(v).strip():
            raise ChainHold("SELECTION_IDENTITY_INVALID")
        if isinstance(v, float):
            import math
            if not math.isfinite(v):
                raise ChainHold("SELECTION_IDENTITY_INVALID")
        vals.append((type(v).__name__, str(v)))
    if q["sport"] not in SPORTS:
        raise ChainHold("SPORT_UNSUPPORTED")
    return tuple(vals)

def inspect(primary, secondary, *, decision_utc):
    """Requires externally witnessed evidence flags; does not verify those flags."""
    if not isinstance(primary, dict) or not isinstance(secondary, dict):
        raise ChainHold("RECEIPTS_REQUIRED")
    if _identity(primary) != _identity(secondary):
        raise ChainHold("EXACT_SELECTION_MISMATCH")
    decision = _utc(decision_utc)
    for q in (primary, secondary):
        if q.get("source_attestation") != "EXTERNAL_VERIFIED":
            raise ChainHold("EXTERNAL_ATTESTATION_MISSING")
        for field in ("bookmaker_id", "upstream_chain_id", "transport_id", "original_receipt_id"):
            if not isinstance(q.get(field), str) or not q[field].strip():
                raise ChainHold("SOURCE_IDENTITY_MISSING")
        if not isinstance(q.get("original_sha256"), str) or not SHA.fullmatch(q["original_sha256"]):
            raise ChainHold("ORIGINAL_HASH_INVALID")
        observed, captured = _utc(q.get("provider_observed_utc")), _utc(q.get("local_captured_utc"))
        if not observed <= captured <= decision:
            raise ChainHold("SOURCE_CHRONOLOGY_INVALID")
        if (decision - captured).total_seconds() > 300:
            raise ChainHold("STALE_SOURCE")
    # Case/space variants are not distinct bookmaker or transport chains.
    # A shared transport can expose two logos with different claimed upstream
    # IDs, and must NOT be counted as an independent second feed.
    normalized = lambda q, field: q[field].strip().casefold()
    if normalized(primary,"bookmaker_id") == normalized(secondary,"bookmaker_id"):
        raise ChainHold("SAME_BOOKMAKER")
    if normalized(primary,"upstream_chain_id") == normalized(secondary,"upstream_chain_id"):
        raise ChainHold("SHARED_UPSTREAM_CHAIN")
    if normalized(primary,"transport_id") == normalized(secondary,"transport_id"):
        raise ChainHold("SHARED_TRANSPORT")
    if primary["original_receipt_id"] == secondary["original_receipt_id"] or primary["original_sha256"] == secondary["original_sha256"]:
        raise ChainHold("DUPLICATE_ORIGINAL_RECEIPT")
    return {"status": "RESEARCH_CHAIN_CLAIMS_ONLY", "official": False, "stake_u": 0,
            "externally_attested_by_this_module": False, "selection_identity": "EXACT_MATCH",
            "independent_upstream_claims": True}
