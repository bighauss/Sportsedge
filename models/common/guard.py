"""Shared model-vs-market guard for every sport/card (approved by Isaac Nov 15 2026).
A play is an input gap (hidden, listed) when the model probability is more than 1.5x or less than 0.67x
the no-vig market probability, or the gap exceeds 0.12. Same-game plays on one side/total share a theme group
(see exposure_group) so they size as one exposure. No per-game unit cap."""

import math

RATIO_MAX, RATIO_MIN, GAP_MAX = 1.5, 0.67, 0.12


def is_input_gap(p_model: float, p_market_nv: float) -> bool:
    # Invalid, missing, non-finite or impossible probabilities must never
    # evade the guard through NaN comparison semantics.
    try:
        model = float(p_model)
        market = float(p_market_nv)
    except (TypeError, ValueError, OverflowError):
        return True
    if not (math.isfinite(model) and math.isfinite(market)):
        return True
    if not (0.0 <= model <= 1.0 and 0.0 < market < 1.0):
        return True
    ratio = model / market
    return ratio > RATIO_MAX or ratio < RATIO_MIN or abs(model - market) > GAP_MAX


def exposure_group(game: str, kind: str, subject: str) -> str:
    """Correlated plays share a group: all side bets (ML/spread) for a game are one; all totals are one;
    props group by player."""
    if kind in ("ML", "Spread", "Side"):
        return f"{game}:side"
    if kind in ("Total", "TeamTotal", "Over", "Under"):
        return f"{game}:total"
    return f"{game}:{subject}"
