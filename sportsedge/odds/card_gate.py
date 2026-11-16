"""The only Issue #10 research card gate. Can NEVER emit a counted/real card.

This deliberately executes recovered v2.1 diagnostic on *every* candidate, but
overrides caller claims about receipt verification. External source proof, model
forward calibration and closing-line evidence are not available in this module.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from research.risk.strict_v21_v22 import diagnostic, POLICY_VERSION as EXECUTED_STRICT_POLICY
from research.risk.v22_policy_guard import assess as assess_v22, VERSION as HISTORICAL_V22_ADDENDUM
from .evidence import (DualSourceDecision, PITBinding, QuoteReceipt,
                       evaluate_dual_source, utc)
from .storage import EvidenceChain
from .independent_chain_contract import inspect as inspect_independent_chain, ChainHold
from .completeness_gate import evaluate as evaluate_completeness, CompletenessError
from research.edge.forward_holdout_contract import evaluate as evaluate_forward, Hold


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
    chain_primary: dict | None = None,
    chain_secondary: dict | None = None,
    completeness_archive: dict | None = None,
    forward_freeze: dict | None = None,
    forward_rows: list | None = None,
) -> dict:
    now = utc(decision_at_utc, "decision")
    # Never accept self-asserted provenance from user-provided candidate fields.
    sanitized = dict(candidate)
    sanitized["source_receipt_verified"] = False
    sanitized["independent_model_verified"] = False
    # A LATER owner direction selected the STRICTER of v2.1's 2u event cap
    # and v2.2's no-cap addendum. That selects the existing 2u strict overlay
    # for new research; never invent a 1u policy or silently remove the cap.
    # Continue evaluating older v2.2 conditions as an UNAUTHENTICATED paper
    # preflight. No source flags are independent provider attestations.
    requested_policy = candidate.get("rules_version")
    v22_inputs = {
        # Independently test historical addendum arithmetic even when the
        # candidate correctly declares the newer selected strict policy.
        "rules_version": HISTORICAL_V22_ADDENDUM,
        "source_receipt_verified": False,
        "independent_model_verified": False,
        "model_freeze_verified": False,
        "independent_quote_chain_verified": False,
        "ratings_half_present": candidate.get("ratings_half_present"),
        "market_family": candidate.get("market", ""),
        "p_model": candidate.get("p_model"),
        "p_market_novig": candidate.get("p_market_novig"),
        "price_american": primary.odds_american if primary else candidate.get("price_american"),
        "projection_market_points_gap": candidate.get("projection_market_points_gap"),
    }
    try:
        v22 = assess_v22(v22_inputs)
    except (ValueError, TypeError, KeyError) as exc:
        v22 = {"status": "BLOCK", "flags": ["V22_RUNTIME_ERROR:" + type(exc).__name__]}
    try:
        v21 = diagnostic(sanitized, ledger=ledger,
                         closing_observations=closing_observations)
    except (ValueError, TypeError, KeyError) as exc:
        v21 = {"status": "BLOCK", "approved_stake_u": 0,
               "flags": ["V21_RUNTIME_ERROR:" + type(exc).__name__]}
    reasons = list(dual.reasons)
    # The later stricter-cap owner direction supersedes the earlier
    # no-game-cap clause, but Gate E is still not externally certified.
    # A forged paper diagnostic must never produce a release-eligible card.
    if requested_policy != EXECUTED_STRICT_POLICY:
        reasons.append("SELECTED_STRICT_POLICY_VERSION_MISSING_OR_MISMATCHED")
    reasons.extend((
        "GATE_E_STRICT_CARD_LEDGER_NOT_CERTIFIED",
        "STRICT_2U_EVENT_CAP_OVERRIDES_EARLIER_V22_NO_CAP_ADDENDUM",
        "SELECTED_POLICY:" + EXECUTED_STRICT_POLICY,
        "EXECUTED_POLICY:" + EXECUTED_STRICT_POLICY,
        "HISTORICAL_V22_ADDENDUM:" + HISTORICAL_V22_ADDENDUM,
    ))
    v22_flags = v22.get("flags", ())
    if not isinstance(v22_flags, (list, tuple)) or any(
        not isinstance(flag, str) or not flag for flag in v22_flags
    ):
        v22_flags = ("INVALID_V22_DIAGNOSTIC_FLAGS",)
    reasons.extend("V22:" + flag for flag in v22_flags)
    if v22.get("status") != "PAPER_0U":
        reasons.append("V22_RESEARCH_PREFLIGHT_BLOCKED")
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
    # Separate research-only original-source claims. Never derive these from
    # bookmaker logos, quote objects, or untrusted candidate flags.
    if chain_primary is None or chain_secondary is None:
        reasons.append("INDEPENDENT_CHAIN_EVIDENCE_MISSING")
    else:
        try:
            inspect_independent_chain(
                chain_primary, chain_secondary,
                decision_utc=now.isoformat().replace("+00:00", "Z"))
        except ChainHold as exc:
            reasons.append("INDEPENDENT_CHAIN:" + str(exc))
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            reasons.append("INDEPENDENT_CHAIN_RUNTIME_ERROR:" + type(exc).__name__)
    # Research-only checks; their output never authorizes a stake.
    if completeness_archive is None:
        reasons.append("COMPLETENESS_EVIDENCE_MISSING")
    else:
        try:
            coverage = evaluate_completeness(completeness_archive)
            if coverage.get("failures"):
                reasons.append("COMPLETENESS_INCOMPLETE")
            if coverage.get("status") != "PAPER_0U_COMPLIANT_INVENTORY":
                reasons.append("COMPLETENESS_NOT_FULLY_ACCOUNTED")
        except (CompletenessError, TypeError, ValueError, KeyError, AttributeError) as exc:
            reasons.append("COMPLETENESS_INVALID:" + str(exc))
    if forward_freeze is None or forward_rows is None:
        reasons.append("FORWARD_HOLDOUT_EVIDENCE_MISSING")
    else:
        try:
            forward = evaluate_forward(forward_freeze, forward_rows)
            if forward.get("status") != "PAPER_0U_UNATTESTED_FORWARD_RESEARCH":
                reasons.append("FORWARD_HOLDOUT_INVALID_STATUS")
        except (Hold, TypeError, ValueError, KeyError, AttributeError) as exc:
            reasons.append("FORWARD_HOLDOUT_INVALID:" + str(exc))
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
    # The selected strict 2u risk overlay remains a research diagnostic,
    # NOT end-to-end original sportsbook authentication or Gate E approval.
    state = "BLOCK"
    report = {
        "status": state, "card": None, "approved_stake_u": 0,
        "official_counted": 0,
        "reasons": sorted(set(reasons)),
        "dual_state": dual.state,
        "pit_status": "MISSING" if pit is None else "CHECKED",
        "v21_status": str(v21.get("status", "BLOCK")),
        "v21_diagnostic_u": 0,  # Hide hypothetical stake from a nonvalidated path.
        "v22_status": str(v22.get("status", "BLOCK")),
        "selected_risk_policy_version": EXECUTED_STRICT_POLICY,
        "historical_v22_addendum_version": HISTORICAL_V22_ADDENDUM,
        "declared_candidate_risk_policy_version": (
            requested_policy if isinstance(requested_policy, str) else None),
        "executed_risk_policy_version": EXECUTED_STRICT_POLICY,
        "v22_original_gap_pp_unattested": v22.get("original_gap_pp"),
        "v22_effective_gap_pp_unattested": v22.get("effective_gap_pp"),
        "risk_policy_conflict": requested_policy != EXECUTED_STRICT_POLICY,
        "strict_2u_game_cap_selected": True,
        "gate_e_v22_connected": False,
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
