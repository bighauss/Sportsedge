"""The only Issue #10 research card gate. Can NEVER emit a counted/real card.

This deliberately executes recovered v2.1 diagnostic on *every* candidate, but
overrides caller claims about receipt verification. External source proof, model
forward calibration and closing-line evidence are not available in this module.
"""
from __future__ import annotations

from datetime import datetime

from research.risk.v21_risk_contract import diagnostic
from .evidence import DualSourceDecision, PITBinding, QuoteReceipt, utc
from .storage import EvidenceChain


def gate_candidate(
    candidate: dict,
    dual: DualSourceDecision,
    pit: PITBinding | None,
    primary: QuoteReceipt | None,
    decision_at_utc: datetime,
    *,
    secondary: QuoteReceipt | None = None,
    chain: EvidenceChain | None = None,
    ledger=(),
    closing_observations=(),
) -> dict:
    now = utc(decision_at_utc, "decision")
    # Never accept self-asserted provenance from user-provided candidate fields.
    sanitized = dict(candidate)
    sanitized["source_receipt_verified"] = False
    sanitized["independent_model_verified"] = False
    try:
        v21 = diagnostic(sanitized, ledger=ledger,
                         closing_observations=closing_observations)
    except (ValueError, TypeError, KeyError) as exc:
        v21 = {"status": "BLOCK", "approved_stake_u": 0,
               "flags": ["V21_RUNTIME_ERROR:" + type(exc).__name__]}
    reasons = list(dual.reasons)
    if dual.state == "BLOCK":
        reasons.append("DUAL_SOURCE_GATE_BLOCKED")
    if primary is None:
        reasons.append("PRIMARY_RECEIPT_MISSING")
    pit_problems = ()
    if pit is None:
        reasons.append("PIT_PACKAGE_MISSING")
    elif primary is not None:
        pit_problems = pit.check(primary)
        reasons.extend(pit_problems)
    v21_flags = v21.get("flags", ())
    if not isinstance(v21_flags, (list, tuple)) or any(
        not isinstance(flag, str) or not flag for flag in v21_flags
    ):
        v21_flags = ("INVALID_V21_DIAGNOSTIC_FLAGS",)
    reasons.extend("V21:" + flag for flag in v21_flags)
    # A diagnostic object marked PAPER can still contain mandatory blocking
    # flags. Never promote a candidate from BLOCK to paper-card eligibility
    # merely because the v2.1 diagnostic never proposes an approved stake.
    v21_blocked = bool(v21_flags) or v21.get("status") != "PAPER_0U"
    if v21_blocked:
        reasons.append("V21_POLICY_BLOCKED")
    state = "BLOCK" if (
        dual.state != "RESEARCH_ONLY" or primary is None or pit is None
        or bool(pit_problems) or v21_blocked
    ) else "PAPER_0U"
    report = {
        "status": state, "card": None, "approved_stake_u": 0,
        "official_counted": 0,
        "reasons": sorted(set(reasons)),
        "dual_state": dual.state,
        "pit_status": "MISSING" if pit is None else "CHECKED",
        "v21_status": str(v21.get("status", "BLOCK")),
        "v21_diagnostic_u": 0,  # Hide hypothetical stake from a nonvalidated path.
        "source_externally_authenticated": False,
        "hash_chain_head": None,
    }
    if chain is not None:
        if not candidate.get("bet_id"):
            raise ValueError("DECISION_ID_REQUIRED_FOR_AUDIT")
        audit = {
            "decision_id": str(candidate["bet_id"]),
            "asof_utc": now.isoformat(),
            "primary_receipt_id": dual.primary_receipt_id,
            "secondary_receipt_id": dual.secondary_receipt_id,
            "source_payload_hashes": [
                q.payload_sha256 for q in (primary, secondary) if q is not None
            ],
            "market_key": list(primary.market.key()) if primary is not None else None,
            "state": state, "reason_codes": report["reasons"],
            "pit_status": report["pit_status"],
            "v21_status": report["v21_status"],
            "approved_stake_u": 0, "official_counted": 0,
        }
        report["hash_chain_head"] = chain.append(audit)
    return report
