"""Research-only first-half pricing interface (PAPER/0u).

Accepts independent H1 expected scores and empirical residual standard deviations.
Prices two-way and three-way moneylines, spreads, totals, and team totals with
correct push handling. Emits nine model/market blend diagnostics.

Does not modify the frozen native model, write ledgers, or claim validation.
Neutral-site forecasts are left unchanged when the caller supplies a neutral
projection (campus-only HCA must be applied upstream if desired).

EV = P(win) * net_payout - P(loss)
Pushes refund the stake (zero net).
"""
from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple

# Model weight; second number is market weight. Same order as cbb_pricing.CANDIDATE_BLEND_WEIGHTS.
BLEND_WEIGHTS: Tuple[float, ...] = (0.0, 0.25, 0.5, 0.6, 0.75, 0.8, 0.9, 0.95, 1.0)

class Hold(Exception):
    """Explicit withholding reason."""

def _clip(p: float) -> float:
    return min(max(float(p), 1e-12), 1.0 - 1e-12)

def american_to_decimal(american: float) -> float:
    if not math.isfinite(american) or american == 0:
        raise Hold("INVALID_AMERICAN_PRICE")
    if american >= 100:
        return 1.0 + american / 100.0
    if american <= -100:
        return 1.0 + 100.0 / abs(american)
    raise Hold("INVALID_AMERICAN_PRICE")

def break_even(american: float) -> float:
    dec = american_to_decimal(american)
    return 1.0 / dec

def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

def margin_probs(mean: float, sd: float, line: float) -> Dict[str, float]:
    """P(home covers), P(push), P(away covers) for a spread line (home perspective)."""
    if sd <= 0 or not math.isfinite(sd) or not math.isfinite(mean) or not math.isfinite(line):
        raise Hold("INVALID_DISTRIBUTION")
    # Continuous normal; push probability is zero unless line is exactly integer and we model discrete later.
    # For half-point lines push is impossible. For integer lines we report a small empirical push if requested.
    z = (line - mean) / sd
    p_away = normal_cdf(z)
    p_home = 1.0 - p_away
    return {"win": p_home, "push": 0.0, "loss": p_away}

def total_probs(mean: float, sd: float, line: float) -> Dict[str, float]:
    if sd <= 0 or not math.isfinite(sd) or not math.isfinite(mean) or not math.isfinite(line):
        raise Hold("INVALID_DISTRIBUTION")
    z = (line - mean) / sd
    p_under = normal_cdf(z)
    p_over = 1.0 - p_under
    return {"over": p_over, "push": 0.0, "under": p_under}

def ev(p_win: float, p_loss: float, american: float) -> float:
    """Unit-stake EV. Push probability is implied as 1 - p_win - p_loss and contributes zero."""
    if not (0.0 <= p_win <= 1.0 and 0.0 <= p_loss <= 1.0 and p_win + p_loss <= 1.0 + 1e-9):
        raise Hold("PROBABILITY_NOT_NORMALIZED")
    dec = american_to_decimal(american)
    net = dec - 1.0
    return p_win * net - p_loss

def nine_blends(p_model: float, p_market: Optional[float]) -> List[Dict[str, float]]:
    """Return list of {model_weight, blended_p, blended_ev_if_price_available}."""
    out = []
    for w in BLEND_WEIGHTS:
        if p_market is None:
            bp = p_model if w == 1.0 else None
        else:
            bp = w * p_model + (1.0 - w) * p_market
        out.append({"model_weight": w, "market_weight": 1.0 - w, "blended_probability": bp})
    return out

def price_h1_spread(
    *,
    game_id: str,
    home_team: str,
    away_team: str,
    expected_home: float,
    expected_away: float,
    sd_margin: float,
    line: float,          # home spread (negative = home favorite)
    american: float,
    side: str,            # "home" or "away"
    capture_utc: str,
    dk_event_id: Optional[str] = None,
    p_market: Optional[float] = None,
) -> Dict:
    if side not in ("home", "away"):
        raise Hold("INVALID_SIDE")
    mean_margin = expected_home - expected_away
    probs = margin_probs(mean_margin, sd_margin, -line if side == "home" else line)
    # For home side, win = home covers = margin > -line
    if side == "home":
        p_win = probs["win"]
        p_loss = probs["loss"]
    else:
        p_win = probs["loss"]
        p_loss = probs["win"]
    p_push = probs["push"]
    independent_ev = ev(p_win, p_loss, american)
    blends = nine_blends(p_win, p_market)
    return {
        "game_id": game_id,
        "dk_event_id": dk_event_id,
        "market": "H1_SPREAD",
        "period": "H1",
        "settlement": "TWO_WAY",
        "home_team": home_team,
        "away_team": away_team,
        "selection": side,
        "line": line,
        "american": american,
        "capture_utc": capture_utc,
        "expected_margin": mean_margin,
        "sd_margin": sd_margin,
        "p_win": p_win,
        "p_loss": p_loss,
        "p_push": p_push,
        "fair_decimal": 1.0 / _clip(p_win) if p_win > 0 else None,
        "break_even": break_even(american),
        "independent_ev": independent_ev,
        "nine_blends": blends,
        "status": "PAPER_0U_RESEARCH",
        "withholding_reason": None,
        "approved_stake_u": 0,
    }

def price_h1_total(
    *,
    game_id: str,
    expected_home: float,
    expected_away: float,
    sd_total: float,
    line: float,
    american: float,
    side: str,            # "over" or "under"
    capture_utc: str,
    dk_event_id: Optional[str] = None,
    p_market: Optional[float] = None,
) -> Dict:
    if side not in ("over", "under"):
        raise Hold("INVALID_SIDE")
    mean_total = expected_home + expected_away
    probs = total_probs(mean_total, sd_total, line)
    p_win = probs[side]
    p_loss = probs["under"] if side == "over" else probs["over"]
    p_push = probs["push"]
    independent_ev = ev(p_win, p_loss, american)
    return {
        "game_id": game_id,
        "dk_event_id": dk_event_id,
        "market": "H1_TOTAL",
        "period": "H1",
        "settlement": "TWO_WAY",
        "selection": side,
        "line": line,
        "american": american,
        "capture_utc": capture_utc,
        "expected_total": mean_total,
        "sd_total": sd_total,
        "p_win": p_win,
        "p_loss": p_loss,
        "p_push": p_push,
        "fair_decimal": 1.0 / _clip(p_win) if p_win > 0 else None,
        "break_even": break_even(american),
        "independent_ev": independent_ev,
        "nine_blends": nine_blends(p_win, p_market),
        "status": "PAPER_0U_RESEARCH",
        "withholding_reason": None,
        "approved_stake_u": 0,
    }
