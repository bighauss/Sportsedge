#!/usr/bin/env python3
"""Owner-adopted v2.2 risk preflight (PAPER / 0u only).

This is NOT a live sizing implementation, source authenticator or a replacement
for the historical v2.1 engine. It never emits an approved stake.
"""
from decimal import Decimal, InvalidOperation

VERSION = "RUN_IT_V2_2_ADOPTED_20261115"
CAP_DAY_U = Decimal("5")
CAP_THEME_U = Decimal("3")
CAP_GAME_U = None  # Owner-adopted v2.2: event is a cluster, NOT a unit limit.


def _number(value, name):
    if value is None or isinstance(value, bool):
        raise ValueError("MISSING_OR_BOOLEAN_" + name)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("INVALID_" + name) from None
    if not number.is_finite():
        raise ValueError("NONFINITE_" + name)
    return number


def assess(candidate):
    """Inspect probability-gap and long-dog policy without authorizing wagers.

    Caller-supplied verified flags are assertions, not authentication.
    All outputs remain 0u, irrespective of claimed source or model status.
    """
    result = {
        "rules_version": VERSION,
        "official": False,
        "approved_stake_u": 0,
        "status": "BLOCK",
        "flags": [],
        "risk_caps_u": {"ct_day": "5", "theme": "3", "game": None},
        "market_authentication": "NOT_ESTABLISHED_BY_THIS_PREFLIGHT",
        "long_dog_diagnostic_max_u": None,
    }
    flags = result["flags"]
    if not isinstance(candidate, dict):
        flags.append("INVALID_CANDIDATE")
        return result
    if candidate.get("rules_version") != VERSION:
        flags.append("WRONG_OR_MISSING_POLICY_VERSION")
    for field in (
        "source_receipt_verified",
        "independent_model_verified",
        "model_freeze_verified",
        "independent_quote_chain_verified",
    ):
        if candidate.get(field) is not True:
            flags.append("UNVERIFIED_" + field.upper())

    try:
        original = _number(candidate.get("p_model"), "MODEL_PROBABILITY")
        market = _number(candidate.get("p_market_novig"), "MARKET_PROBABILITY")
        if not (Decimal(0) < original < Decimal(1)):
            raise ValueError("MODEL_PROBABILITY_OUT_OF_RANGE")
        if not (Decimal(0) < market < Decimal(1)):
            raise ValueError("MARKET_PROBABILITY_OUT_OF_RANGE")

        ratings = candidate.get("ratings_half_present")
        if ratings is False:
            effective = (original + market) / 2
            flags.append("RATINGS_HALF_MISSING_LOW_CONFIDENCE")
            result["confidence_ceiling"] = "LOW"
        elif ratings is True:
            effective = original
        else:
            flags.append("RATINGS_HALF_STATE_UNKNOWN")
            effective = original

        original_gap = abs(original - market)
        effective_gap = abs(effective - market)
        blended = Decimal("0.30") * effective + Decimal("0.70") * market
        result.update(
            original_model_probability=str(original),
            effective_model_probability=str(effective),
            market_novig_probability=str(market),
            blended_probability=str(blended),
            original_gap_pp=str(original_gap * 100),
            effective_gap_pp=str(effective_gap * 100),
        )
        # Conservative hold: missing-half shrink must NOT hide the raw gap.
        if original_gap > Decimal("0.12") or effective_gap > Decimal("0.12"):
            flags.append("GAP_HOLD_GREATER_THAN_12PP")

        if candidate.get("projection_market_points_gap") is not None:
            points_gap = abs(
                _number(candidate.get("projection_market_points_gap"), "POINTS_GAP")
            )
            result["projection_market_points_gap"] = str(points_gap)
            if points_gap > Decimal("3"):
                flags.append("PROJECTION_MARKET_POINTS_GAP_OVER_3")
        else:
            result["projection_market_points_gap"] = None

        market_family = str(candidate.get("market_family", "")).upper()
        if market_family in ("ML", "MONEYLINE"):
            american = _number(candidate.get("price_american"), "AMERICAN_PRICE")
            if american != american.to_integral_value():
                raise ValueError("NONINTEGER_AMERICAN_PRICE")
            if american >= 200:
                # A trusted evaluator must prove 50 CLV-graded dog MLs and
                # positive CLV before lifting this cap. This function cannot
                # authenticate such a record, even if the caller claims one.
                result["long_dog_diagnostic_max_u"] = "0.25"
                flags.append("DOG_ML_PLUS_200_CAP_RETAINED_PENDING_CLV_PROOF")
            elif -100 < american < 100:
                raise ValueError("INVALID_AMERICAN_PRICE")
        elif market_family == "":
            flags.append("MISSING_MARKET_FAMILY")
    except ValueError as exc:
        flags.append(str(exc))

    blockers = (
        "WRONG_OR_MISSING_POLICY_VERSION",
        "GAP_HOLD_GREATER_THAN_12PP",
        "RATINGS_HALF_STATE_UNKNOWN",
        "MISSING_MARKET_FAMILY",
    )
    # Low-confidence and informational notices do not qualify as a
    # certification. Even a clean row is PAPER / 0u, never OFFICIAL.
    if not any(
        flag.startswith("UNVERIFIED_") or flag in blockers
        or flag.startswith(("INVALID_", "MISSING_", "NONFINITE_",
                            "MODEL_PROBABILITY_", "MARKET_PROBABILITY_",
                            "NONINTEGER_"))
        for flag in flags
    ):
        result["status"] = "PAPER_0U"
    return result
