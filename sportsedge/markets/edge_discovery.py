"""Research-only projection → model/market disagreement evidence.

This is NOT positive EV certification. Unfitted score/prop dispersion, a
synthetic market quote, and a locally consistent hash are never proof of an
independent fair probability or original sportsbook offer. This module only
packages the existing five-sport simulator's price_market evidence, separates
Monte Carlo draw error from epistemic uncertainty, and shortlists signals for
human investigation. It never changes original model, weights, risk or stake.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Iterable

from .allmarkets_research import Market, PriceReceipt, _implied, _decimal_odds


def _unit_float(value: object, field: str, *, allow_zero: bool = False) -> float:
    if type(value) not in (float, int):
        raise ValueError("SIGNAL_INVALID_" + field.upper())
    result = float(value)
    if not math.isfinite(result) or not (0 <= result <= 1 if allow_zero else 0 < result < 1):
        raise ValueError("SIGNAL_INVALID_" + field.upper())
    return result


def _count(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("SIGNAL_INVALID_" + field.upper())
    return value


def _wilson_interval(wins: int, trials: int) -> tuple[float, float]:
    """MC sampling interval only, NOT a calibrated predictive uncertainty CI."""
    if trials < 1 or wins < 0 or wins > trials:
        raise ValueError("SIGNAL_INVALID_NONPUSH_TRIALS")
    p = wins / trials
    z = 1.959963984540054
    z2 = z*z
    denom = 1+z2/trials
    center = (p+z2/(2*trials))/denom
    radius = z*math.sqrt(p*(1-p)/trials+z2/(4*trials*trials))/denom
    return max(0.0,center-radius), min(1.0,center+radius)


def evaluate_signal(
    priced: dict,
    market: Market,
    primary: PriceReceipt | None,
    opponent: PriceReceipt | None = None,
) -> dict | None:
    """Extract audit-friendly provisional disagreement from a PASSED PAPER pricer.

    price_market() is responsible for validating original quote *shape*,
    line/period identity and decision-time freshness before this function is
    invoked. Optional opponent adds an independent internal arithmetic check.
    Nothing here authenticates the external bookmaker or a fitted model.
    """
    if not isinstance(priced, dict):
        raise ValueError("SIGNAL_PRICE_REPORT_REQUIRED")
    if priced.get("status") == "BLOCK":
        return None
    if priced.get("status") != "PAPER_0U":
        raise ValueError("SIGNAL_UNKNOWN_PRICE_STATUS")
    if not isinstance(market, Market) or not isinstance(primary, PriceReceipt):
        raise ValueError("SIGNAL_PRIMARY_MARKET_QUOTE_REQUIRED")
    if primary.market.identity() != market.identity():
        raise ValueError("SIGNAL_QUOTE_IDENTITY_MISMATCH")

    try:
        n = _count(priced["simulations"], "simulations")
        wins = _count(priced["wins"], "wins")
        losses = _count(priced["losses"], "losses")
        pushes = _count(priced["pushes"], "pushes")
        win_given = _unit_float(priced["model_p_win"], "model_p_win", allow_zero=True)
        loss_given = _unit_float(priced["model_p_loss"], "model_p_loss", allow_zero=True)
        push_given = _unit_float(priced["model_p_push"], "model_p_push", allow_zero=True)
        no_vig = _unit_float(priced["no_vig_market_p_conditional"], "no_vig_probability")
        raw_ev = float(priced["raw_ev_unverified"])
    except (KeyError, TypeError, OverflowError, ValueError) as exc:
        raise ValueError("SIGNAL_REQUIRED_PAPER_PRICING_FIELDS_INVALID") from exc

    if n < 1000 or wins+losses+pushes != n or min(wins, losses) < 25:
        raise ValueError("SIGNAL_SIMULATION_CENSUS_OR_TAIL_INVALID")
    if any(abs(a-b/n) > 1e-9 for a, b in
           ((win_given, wins), (loss_given, losses), (push_given, pushes))):
        raise ValueError("SIGNAL_INCONSISTENT_SCENARIO_PROBABILITIES")
    dec = float(_decimal_odds(primary.odds_american))
    implied = 1/dec
    expected_ev = (wins/n)*(dec-1) - (losses/n)
    if not math.isfinite(raw_ev) or abs(expected_ev-raw_ev) > 1e-8:
        raise ValueError("SIGNAL_RAW_EV_ARITHMETIC_MISMATCH")

    if opponent is not None:
        if (not isinstance(opponent, PriceReceipt) or
                primary.book.casefold() != opponent.book.casefold() or
                not market.opposite(opponent.market)):
            raise ValueError("SIGNAL_OPPOSITE_MARKET_IDENTITY_MISMATCH")
        a = float(_implied(primary.odds_american))
        b = float(_implied(opponent.odds_american))
        if abs(no_vig - a/(a+b)) > 1e-9:
            raise ValueError("SIGNAL_NO_VIG_PAIR_MISMATCH")

    nonpush = wins+losses
    conditional = wins/nonpush
    lower, upper = _wilson_interval(wins, nonpush)
    gap_book = (conditional-no_vig)*100
    gap_quote = (conditional-implied)*100
    return {
        "status": "PAPER_UNVERIFIED_DISAGREEMENT",
        "source_authentication_verified": False,
        "calibration_verified": False,
        "forward_tested": False,
        "positive_ev_verified": False,
        "official": False,
        "approved_stake_u": 0,
        "market": list(market.identity()),
        "primary_receipt_id": primary.receipt_id,
        "opponent_receipt_id": opponent.receipt_id if opponent else None,
        "model_sha256": priced.get("model_sha256"),
        "feature_sha256": priced.get("feature_sha256"),
        "quoted_american_unverified": primary.odds_american,
        "simulations": n,
        "simulated_wins": wins,
        "simulated_losses": losses,
        "simulated_pushes": pushes,
        "simulated_nonpush_count": nonpush,
        "model_p_win_unconditional": wins/n,
        "model_p_loss_unconditional": losses/n,
        "model_p_push": pushes/n,
        "model_p_conditional_nonpush": conditional,
        "no_vig_book_p_conditional": no_vig,
        "quote_break_even_p_conditional": implied,
        "model_minus_market_pp": round(gap_book, 6),
        "model_minus_quote_pp": round(gap_quote, 6),
        "mc_wilson95_lower_conditional": lower,
        "mc_wilson95_upper_conditional": upper,
        "mc_only_lower_minus_market_pp": round((lower-no_vig)*100, 6),
        "mc_only_lower_minus_quote_pp": round((lower-implied)*100, 6),
        "raw_ev_unverified": raw_ev,
        "uncertainty_warning": (
            "Wilson interval reflects ONLY finite simulation draws; it does NOT "
            "bound model misspecification, input errors, probability calibration, "
            "injury/roster uncertainty or external sportsbook authenticity."
        ),
    }


def shortlist_signals(
    rows: Iterable[tuple[int, Market, dict | None]], *, limit: int = 25
) -> list[dict]:
    """One positive *MC-only* gap per mirrored market, no wager recommendation.

    Existing source/pricer failures remain in parent rows. We do not call a
    signal an edge: the 95% interval is conditional on an UNVERIFIED model.
    Distinct alternate line rungs, periods, players and books are not pooled.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("INVALID_RESEARCH_SIGNAL_LIMIT")
    candidates = []
    for index, market, item in rows:
        if item is None:
            continue
        if type(index) is not int or index < 0 or not isinstance(market, Market):
            raise ValueError("INVALID_RESEARCH_SIGNAL_IDENTITY")
        if item.get("status") != "PAPER_UNVERIFIED_DISAGREEMENT" or                 item.get("market") != list(market.identity()) or                 item.get("official") is not False or item.get("approved_stake_u") != 0:
            raise ValueError("FORGED_OR_MISBOUND_RESEARCH_SIGNAL")
        if item["mc_only_lower_minus_quote_pp"] <= 0 or                 item["mc_only_lower_minus_market_pp"] <= 0:
            continue
        score = min(item["mc_only_lower_minus_market_pp"],
                    item["mc_only_lower_minus_quote_pp"])
        candidates.append((score, index, market, item))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    chosen: list[tuple[Market, dict]] = []
    for score, index, market, item in candidates:
        if any(market.opposite(already) or market.identity()==already.identity()
               for already, _ in chosen):
            continue
        chosen.append((market, item))
        if len(chosen) == limit:
            break
    return [{
        "row_index": next(i for score, i, mk, data in candidates
                          if mk.identity() == market.identity() and data is item),
        "market": list(market.identity()),
        "screening_score_pp_mc_only": min(
            item["mc_only_lower_minus_market_pp"],
            item["mc_only_lower_minus_quote_pp"]),
        "model_minus_market_pp": item["model_minus_market_pp"],
        "model_minus_quote_pp": item["model_minus_quote_pp"],
        "status": "PAPER_ONLY_NOT_AN_ACTIONABLE_EDGE",
        "official": False, "approved_stake_u": 0,
        "positive_ev_verified": False,
        "note": "Ranked only by simulated-model disagreement; not calibrated or authenticated.",
    } for market, item in chosen]
