"""Strictest v2.1/v2.2 *research-only* risk overlay for all seven sports.

Never authorizes a wager, authenticates a receipt, or changes the frozen v5
kernel. Unknown or missing essential evidence fails closed. The owner chose the
stricter v2.1 2u per-event exposure ceiling over v2.2's proposed removal.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from research.risk.v21_risk_contract import dec, diagnostic as v21_diagnostic

POLICY_VERSION = "SPORTSEDGE_STRICT_V21_V22_20261115_R1"
SPORTS = frozenset({"NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"})
GAP_REVIEW = Decimal("0.03")
GAP_HOLD = Decimal("0.12")
DOG_ML_PRICE = 200
DOG_CAP_U = Decimal("0.25")


def _valid_probability(value):
    p = dec(value)
    if not (Decimal(0) < p < Decimal(1)):
        raise ValueError("PROBABILITY_OUT_OF_RANGE")
    return p


def _american(value):
    if isinstance(value, bool):
        raise ValueError("INVALID_PRICE")
    s = str(value).replace("−", "-").replace("＋", "+")
    p = Decimal(s)
    if not p.is_finite() or p != p.to_integral_value() or (
            -100 < p < 100):
        raise ValueError("INVALID_PRICE")
    return int(p)


def diagnostic(candidate, ledger=(), closing_observations=()):
    """Produce a research diagnostic. Approved stake is *always* 0u.

    The external boolean "features_asof_verified" is a caller assertion and
    cannot substitute for independent PIT publication/authenticity evidence.
    The official card gate independently blocks unsourced candidates.
    """
    if not isinstance(candidate, dict):
        return {
            "rules": POLICY_VERSION, "policy_version": POLICY_VERSION,
            "research_only": True, "approved_stake_u": 0,
            "diagnostic_u": 0, "status": "PAPER_0U",
            "flags": ["V22_INVALID_CANDIDATE_OBJECT"],
            "v22_observations": [], "v22_applied_rules": [],
        }

    proposed = dict(candidate)
    policy_flags = []
    observations = []
    rules = []
    sport = str(proposed.get("sport", "")).upper()
    if sport not in SPORTS:
        policy_flags.append("V22_UNSUPPORTED_SPORT")
    if proposed.get("features_asof_verified") is not True:
        policy_flags.append("V22_CRITICAL_ASOF_FEATURE_EVIDENCE_MISSING")

    half_present = proposed.get("ratings_half_present")
    if type(half_present) is not bool:
        policy_flags.append("V22_RATINGS_HALF_STATUS_UNVERIFIED")

    raw_model = market = None
    try:
        raw_model = _valid_probability(proposed.get("p_model"))
        market = _valid_probability(proposed.get("p_market_novig"))
    except (ValueError, InvalidOperation, TypeError):
        policy_flags.append("V22_MODEL_MARKET_PROBABILITY_UNVERIFIED")

    if raw_model is not None and market is not None:
        raw_gap = abs(raw_model - market)
        proposed_gap = raw_gap
        if half_present is False:
            # Only an explicitly recorded half-only model may use this
            # fallback. The other critical as-of inputs must be present.
            proposed["p_model"] = str((raw_model + market) / Decimal(2))
            proposed["confidence"] = "LOW"
            proposed_gap = abs(_valid_probability(proposed["p_model"]) - market)
            rules.append("V22_MISSING_HALF_50_PERCENT_SHRINK_AND_LOW")
        if raw_gap > GAP_REVIEW or proposed_gap > GAP_REVIEW:
            observations.append("V22_MODEL_MARKET_GAP_GT_3PTS_REVIEW")
        # Check the raw gap too: a shrink must not conceal a huge mismatch.
        if raw_gap > GAP_HOLD or proposed_gap > GAP_HOLD:
            policy_flags.append("V22_MODEL_MARKET_GAP_GT_12PTS_HOLD")
        rules.append("V22_RAW_GAP_CHECK")
    elif half_present is False:
        policy_flags.append("V22_CANNOT_SHRINK_UNVERIFIED_PROBABILITY")

    result = dict(v21_diagnostic(
        proposed, ledger=ledger, closing_observations=closing_observations))
    flags = list(result.get("flags", ()))
    flags.extend(policy_flags)

    if str(proposed.get("market", "")).upper() in ("ML", "MONEYLINE"):
        try:
            price = _american(proposed.get("price_american"))
        except (ValueError, InvalidOperation, TypeError):
            flags.append("V22_ML_PRICE_UNVERIFIED")
        else:
            if price >= DOG_ML_PRICE:
                # No self-reported 50-play CLV flag unlocks this cap.
                rules.append("V22_DOG_ML_PERMANENT_025U_CAP_PENDING_ATTESTATION")
                try:
                    existing = dec(result.get("diagnostic_u", 0))
                    result["diagnostic_u"] = str(
                        min(DOG_CAP_U, max(Decimal(0), existing)))
                except (ValueError, InvalidOperation, TypeError):
                    flags.append("V22_INVALID_BASE_DIAGNOSTIC")

    result["flags"] = list(dict.fromkeys(flags))
    if result["flags"]:
        result["diagnostic_u"] = 0
    result["policy_version"] = POLICY_VERSION
    result["v22_observations"] = observations
    result["v22_applied_rules"] = rules
    # No possible input can turn this helper into a live authorization.
    result["status"] = "PAPER_0U"
    result["research_only"] = True
    result["approved_stake_u"] = 0
    return result
