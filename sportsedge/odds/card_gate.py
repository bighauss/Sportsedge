"""The only Issue #10 research card gate. Can NEVER emit a counted/real card.

This deliberately executes recovered v2.1 diagnostic on *every* candidate, but
overrides caller claims about receipt verification. External source proof, model
forward calibration and closing-line evidence are not available in this module.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from research.risk.v21_risk_contract import diagnostic
from .evidence import (DualSourceDecision, PITBinding, QuoteReceipt,
                       evaluate_dual_source, utc)
from .storage import EvidenceChain


def _numeric_identity(value, expected):
    if isinstance(value, bool):
        return False
    try:
        first, second = Decimal(str(value)), Decimal(str(expected))
    except (InvalidOperation, ValueError, TypeError):
        return False
    return first.is_finite() and second.is_finite() and first == second


def _candidate_receipt_mismatches(candidate, primary):
    """Validate candidate's declared selection against the original quote.

    Absence is handled by mandatory v2.1 candidate schema. Explicitly
    conflicting declared fields must never be treated as merely missing.
    """
    checks = {
        "event_id": primary.market.event_id,
        "sport": primary.market.sport,
        "market": primary.market.kind,
        "period": primary.market.period,
        "side": primary.market.side,
        "team_id": primary.market.team_id,
        "player_id": primary.market.player_id,
        "stat": primary.market.stat,
        "settlement": primary.market.settlement,
    }
    errors = []
    for name, expected in checks.items():
        if name in candidate and candidate[name] != expected:
            errors.append("CANDIDATE_" + name.upper() + "_QUOTE_MISMATCH")
    if "price_american" in candidate and not _numeric_identity(
            candidate["price_american"], primary.odds_american):
        errors.append("CANDIDATE_PRICE_QUOTE_MISMATCH")
    if "line" in candidate:
        source_line = candidate["line"]
        if primary.market.kind == "MONEYLINE":
            valid = source_line in ("", "0", 0)
        elif primary.market.line == "":
            valid = source_line == ""
        else:
            valid = _numeric_identity(source_line, primary.market.line)
        if not valid:
            errors.append("CANDIDATE_LINE_QUOTE_MISMATCH")
    return errors


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
    if secondary is None:
        reasons.append("SECONDARY_RECEIPT_MISSING")
    binding_problems = []
    if primary is not None:
        binding_problems.extend(_candidate_receipt_mismatches(candidate, primary))
    # The supplied research decision alone is not trusted to describe the
    # actual receipts. Re-run structural market, clock and independence checks
    # against these objects; TRUE here means only a local schema comparison,
    # NEVER externally verified source mapping or original book transport.
    structural = evaluate_dual_source(
        primary, secondary, now, market_mapping_verified=True)
    if structural.state == "BLOCK":
        binding_problems.extend("RECHECK:" + x for x in structural.reasons)
    if dual.primary_receipt_id != (primary.receipt_id if primary else None):
        binding_problems.append("DUAL_PRIMARY_RECEIPT_ID_MISMATCH")
    if dual.secondary_receipt_id != (secondary.receipt_id if secondary else None):
        binding_problems.append("DUAL_SECONDARY_RECEIPT_ID_MISMATCH")
    if primary is not None and secondary is not None and (
            primary.receipt_id == secondary.receipt_id):
        binding_problems.append("DUPLICATED_PRIMARY_SECONDARY_RECEIPT_ID")
    reasons.extend(binding_problems)
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
        dual.state != "RESEARCH_ONLY" or primary is None or secondary is None
        or pit is None or bool(binding_problems) or bool(pit_problems)
        or v21_blocked
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
