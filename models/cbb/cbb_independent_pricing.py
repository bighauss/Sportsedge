"""CBB pure independent pricing path (PAPER / 0u / NON_COUNTED).

Permanent rule: independent projections before market comparison.
This module forces blend_weight_model = 1.0 so that emitted probabilities
and EV use only the model distribution. Market no-vig is never mixed in.

Does not alter the experimental blend path in cbb_pricing.py.
All outputs remain research-only until chronological walk-forward
validation and untouched holdouts demonstrate measurable improvement
over baselines.
"""
from __future__ import annotations
import math
from typing import Mapping, Any

import cbb_pricing as CP
import cbbd_native_score_model as NM


def independent_config(**overrides: Any) -> Mapping[str, Any]:
    """Config that forces a pure model path (no market blend)."""
    cfg = CP.make_config(**overrides)
    cfg = dict(cfg)
    cfg["blend_weight_model"] = 1.0
    return cfg


def independent_ev(p_model: float, p_push: float, price_american: int | float) -> float:
    """Push-aware EV per 1u using only the model probability.

    EV = p_win * decimal_odds + p_push - 1
    Rejects non-finite or out-of-range inputs.
    """
    if not math.isfinite(p_model) or not math.isfinite(p_push):
        raise ValueError("NONFINITE_PROBABILITY")
    if not (0.0 <= p_model <= 1.0) or not (0.0 <= p_push <= 1.0):
        raise ValueError("PROBABILITY_OUT_OF_RANGE")
    if p_model + p_push > 1.0 + 1e-9:
        raise ValueError("PROBABILITY_MASS_EXCEEDS_ONE")
    return NM.ev_per_unit(p_model, p_push, price_american)


def price_independent(proj: Mapping[str, Any], quote: Mapping[str, Any], cfg: Mapping[str, Any] | None = None) -> dict:
    """Price a quote using only the independent model distribution.

    Returns model_prob, push, and independent_ev for both sides.
    Never blends with market no-vig.
    """
    cfg = cfg or independent_config()
    if cfg["blend_weight_model"] != 1.0:
        raise ValueError("INDEPENDENT_PATH_REQUIRES_WEIGHT_ONE")
    # Re-use native line probability helper; SDs come from cfg
    market = quote.get("market", "").lower()
    line = quote.get("line")
    if market in ("spread", "alt_spread"):
        mu = proj["margin"]
        sd = cfg["sd_margin"]
        a, push, c = NM._line_probs(mu, sd, -float(line))
        sides = ("home", "away")
    elif market in ("total", "alt_total", "team_total_home", "team_total_away"):
        if market.endswith("home"):
            mu = proj["home_points"]
        elif market.endswith("away"):
            mu = proj["away_points"]
        else:
            mu = proj["total"]
        sd = cfg["sd_total"]
        if "team_total" in market:
            sd *= cfg["team_total_sd_factor"]
        a, push, c = NM._line_probs(mu, sd, float(line))
        sides = ("over", "under")
    else:
        raise ValueError("UNSUPPORTED_MARKET_FOR_INDEPENDENT_PATH")
    pa, pb = quote["price_a"], quote["price_b"]
    return {
        "sides": sides,
        "model_prob": (a, c),
        "push": push,
        "independent_ev": (
            independent_ev(a, push, pa),
            independent_ev(c, push, pb),
        ),
        "blend_weight_model": 1.0,
        "note": "PURE_INDEPENDENT_NO_MARKET_BLEND",
    }
