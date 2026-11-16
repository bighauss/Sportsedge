"""Shared model-vs-market guard for every sport/card (approved by Isaac Nov 15 2026).
A play is an input gap (hidden, listed) when the model probability is more than 1.5x or less than 0.67x
the no-vig market probability, or the gap exceeds 0.12. Same-game plays on one side/total share a theme group
(see exposure_group) so they size as one exposure. No per-game unit cap."""

RATIO_MAX, RATIO_MIN, GAP_MAX = 1.5, 0.67, 0.12


def is_input_gap(p_model: float, p_market_nv: float) -> bool:
    if p_market_nv <= 0:
        return True
    ratio = p_model / p_market_nv
    return ratio > RATIO_MAX or ratio < RATIO_MIN or abs(p_model - p_market_nv) > GAP_MAX


def exposure_group(game: str, kind: str, subject: str) -> str:
    """Correlated plays share a group: all side bets (ML/spread) for a game are one; all totals are one;
    props group by player."""
    if kind in ("ML", "Spread", "Side"):
        return f"{game}:side"
    if kind in ("Total", "TeamTotal", "Over", "Under"):
        return f"{game}:total"
    return f"{game}:{subject}"
