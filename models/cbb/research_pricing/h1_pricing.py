"""Research-only first-half pricing interface (PAPER/0u).

Accepts independent H1 expected scores and empirical residual standard deviations.
Prices two-way and three-way moneylines, spreads, totals, and team totals with
correct push handling. Emits nine model/market blend diagnostics including blended EV.

Does not modify the frozen native model, write ledgers, or claim validation.
Neutral-site forecasts are left unchanged when the caller supplies a neutral
projection (campus-only HCA must be applied upstream if desired).

EV = P(win) * net_payout - P(loss)
Pushes refund the stake (zero net).
Fair odds account for pushes by using the conditional win probability among decisive outcomes.
"""
from __future__ import annotations
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

BLEND_WEIGHTS: Tuple[float, ...] = (0.0, 0.25, 0.5, 0.6, 0.75, 0.8, 0.9, 0.95, 1.0)

class Hold(Exception):
    """Explicit withholding reason."""

def _clip(p: float) -> float:
    return min(max(float(p), 1e-12), 1.0 - 1e-12)

def _validate_utc(s: str) -> None:
    if not isinstance(s, str) or not s.endswith("Z"):
        raise Hold("TIMESTAMP_INVALID")
    try:
        datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError:
        raise Hold("TIMESTAMP_INVALID")

def _validate_finite_positive(x: float, code: str) -> float:
    if type(x) not in (int, float) or not math.isfinite(x) or x <= 0:
        raise Hold(code)
    return float(x)

def american_to_decimal(american: float) -> float:
    if not math.isfinite(american) or american == 0:
        raise Hold("INVALID_AMERICAN_PRICE")
    if american >= 100:
        return 1.0 + american / 100.0
    if american <= -100:
        return 1.0 + 100.0 / abs(american)
    raise Hold("INVALID_AMERICAN_PRICE")

def break_even(american: float) -> float:
    return 1.0 / american_to_decimal(american)

def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

def _discrete_push(mean: float, sd: float, integer_line: float) -> float:
    """Approximate P(exact integer) using continuity correction over a 1-point window."""
    if abs(integer_line - round(integer_line)) > 1e-9:
        return 0.0
    lo = integer_line - 0.5
    hi = integer_line + 0.5
    return max(0.0, normal_cdf((hi - mean) / sd) - normal_cdf((lo - mean) / sd))

def margin_cover_probs(mean_margin: float, sd: float, home_line: float) -> Dict[str, float]:
    """
    home_line is the spread applied to the home team (negative = home favorite).
    Home covers when actual_margin + home_line > 0.
    For integer lines, report a continuity-corrected push probability.
    """
    sd = _validate_finite_positive(sd, "INVALID_DISTRIBUTION")
    if not math.isfinite(mean_margin) or not math.isfinite(home_line):
        raise Hold("INVALID_DISTRIBUTION")
    threshold = -home_line  # home covers when margin > threshold
    if abs(home_line - round(home_line)) < 1e-9:
        p_push = _discrete_push(mean_margin, sd, threshold)
        p_home = 1.0 - normal_cdf((threshold + 0.5 - mean_margin) / sd)
        p_away = normal_cdf((threshold - 0.5 - mean_margin) / sd)
        # renormalize residual mass into push already accounted
        total = p_home + p_away + p_push
        if total > 0:
            p_home, p_away, p_push = p_home/total, p_away/total, p_push/total
    else:
        p_push = 0.0
        p_home = 1.0 - normal_cdf((threshold - mean_margin) / sd)
        p_away = 1.0 - p_home
    return {"home": p_home, "away": p_away, "push": p_push}

def total_probs(mean: float, sd: float, line: float) -> Dict[str, float]:
    sd = _validate_finite_positive(sd, "INVALID_DISTRIBUTION")
    if not math.isfinite(mean) or not math.isfinite(line):
        raise Hold("INVALID_DISTRIBUTION")
    if abs(line - round(line)) < 1e-9:
        p_push = _discrete_push(mean, sd, line)
        p_under = normal_cdf((line - 0.5 - mean) / sd)
        p_over = 1.0 - normal_cdf((line + 0.5 - mean) / sd)
        total = p_over + p_under + p_push
        if total > 0:
            p_over, p_under, p_push = p_over/total, p_under/total, p_push/total
    else:
        p_push = 0.0
        p_under = normal_cdf((line - mean) / sd)
        p_over = 1.0 - p_under
    return {"over": p_over, "under": p_under, "push": p_push}

def ev(p_win: float, p_loss: float, american: float) -> float:
    if not (0.0 <= p_win <= 1.0 and 0.0 <= p_loss <= 1.0 and p_win + p_loss <= 1.0 + 1e-9):
        raise Hold("PROBABILITY_NOT_NORMALIZED")
    net = american_to_decimal(american) - 1.0
    return p_win * net - p_loss

def fair_decimal(p_win: float, p_push: float) -> Optional[float]:
    """Fair decimal odds accounting for pushes (conditional on a decisive outcome)."""
    decisive = p_win + (1.0 - p_win - p_push)
    if decisive <= 0 or p_win <= 0:
        return None
    p_cond = p_win / (p_win + (1.0 - p_win - p_push))
    return 1.0 / _clip(p_cond)

def nine_blends(p_model: float, p_push: float, p_market: Optional[float], american: float) -> List[Dict[str, float]]:
    """Blended EV uses the same push probability as the independent model."""
    out = []
    for w in BLEND_WEIGHTS:
        if p_market is None:
            bp = p_model if abs(w - 1.0) < 1e-9 else None
        else:
            bp = w * p_model + (1.0 - w) * p_market
        blended_ev = None
        if bp is not None:
            # Preserve independent push mass; remaining probability is loss
            p_loss = max(0.0, 1.0 - bp - p_push)
            blended_ev = ev(bp, p_loss, american)
        out.append({
            "model_weight": w,
            "market_weight": 1.0 - w,
            "blended_probability": bp,
            "blended_ev": blended_ev,
            "blended_push": p_push,
        })
    return out

def _base_row(**kwargs) -> Dict:
    return {
        "status": "PAPER_0U_RESEARCH",
        "withholding_reason": None,
        "approved_stake_u": 0,
        **kwargs,
    }

def price_h1_spread(
    *,
    game_id: str,
    home_team: str,
    away_team: str,
    expected_home: float,
    expected_away: float,
    sd_margin: float,
    line: float,
    american: float,
    side: str,
    capture_utc: str,
    dk_event_id: Optional[str] = None,
    p_market: Optional[float] = None,
) -> Dict:
    _validate_utc(capture_utc)
    if side not in ("home", "away"):
        raise Hold("INVALID_SIDE")
    mean_margin = expected_home - expected_away
    probs = margin_cover_probs(mean_margin, sd_margin, line)
    p_win = probs[side]
    p_loss = probs["away"] if side == "home" else probs["home"]
    p_push = probs["push"]
    return _base_row(
        game_id=game_id, dk_event_id=dk_event_id, market="H1_SPREAD", period="H1",
        settlement="TWO_WAY", home_team=home_team, away_team=away_team,
        selection=side, line=line, american=american, capture_utc=capture_utc,
        expected_margin=mean_margin, sd_margin=sd_margin,
        p_win=p_win, p_loss=p_loss, p_push=p_push,
        fair_decimal=fair_decimal(p_win, p_push),
        break_even=break_even(american),
        independent_ev=ev(p_win, p_loss, american),
        nine_blends=nine_blends(p_win, p_push, p_market, american),
    )

def price_h1_total(
    *,
    game_id: str,
    expected_home: float,
    expected_away: float,
    sd_total: float,
    line: float,
    american: float,
    side: str,
    capture_utc: str,
    dk_event_id: Optional[str] = None,
    p_market: Optional[float] = None,
) -> Dict:
    _validate_utc(capture_utc)
    if side not in ("over", "under"):
        raise Hold("INVALID_SIDE")
    mean_total = expected_home + expected_away
    probs = total_probs(mean_total, sd_total, line)
    p_win = probs[side]
    p_loss = probs["under"] if side == "over" else probs["over"]
    p_push = probs["push"]
    return _base_row(
        game_id=game_id, dk_event_id=dk_event_id, market="H1_TOTAL", period="H1",
        settlement="TWO_WAY", selection=side, line=line, american=american,
        capture_utc=capture_utc, expected_total=mean_total, sd_total=sd_total,
        p_win=p_win, p_loss=p_loss, p_push=p_push,
        fair_decimal=fair_decimal(p_win, p_push),
        break_even=break_even(american),
        independent_ev=ev(p_win, p_loss, american),
        nine_blends=nine_blends(p_win, p_push, p_market, american),
    )

def price_h1_moneyline(
    *,
    game_id: str,
    home_team: str,
    away_team: str,
    expected_home: float,
    expected_away: float,
    sd_margin: float,
    american: float,
    side: str,
    capture_utc: str,
    three_way: bool = False,
    dk_event_id: Optional[str] = None,
    p_market: Optional[float] = None,
) -> Dict:
    _validate_utc(capture_utc)
    if side not in ("home", "away", "draw"):
        raise Hold("INVALID_SIDE")
    mean_margin = expected_home - expected_away
    # Treat moneyline as spread of 0
    probs = margin_cover_probs(mean_margin, sd_margin, 0.0)
    if three_way:
        if side == "draw":
            p_win = probs["push"]
            p_loss = 1.0 - p_win
            p_push = 0.0
        else:
            # Home or away loses on a tie in a three-way market
            p_win = probs[side]
            p_loss = 1.0 - p_win  # includes the tie
            p_push = 0.0
    else:
        if side == "draw":
            raise Hold("DRAW_NOT_AVAILABLE_ON_TWO_WAY")
        # Two-way: push refunds
        p_win = probs[side]
        p_loss = probs["away"] if side == "home" else probs["home"]
        p_push = probs["push"]
    return _base_row(
        game_id=game_id, dk_event_id=dk_event_id, market="H1_MONEYLINE", period="H1",
        settlement="THREE_WAY" if three_way else "TWO_WAY",
        home_team=home_team, away_team=away_team, selection=side,
        line=0.0, american=american, capture_utc=capture_utc,
        expected_margin=mean_margin, sd_margin=sd_margin,
        p_win=p_win, p_loss=p_loss, p_push=p_push,
        fair_decimal=fair_decimal(p_win, p_push),
        break_even=break_even(american),
        independent_ev=ev(p_win, p_loss, american),
        nine_blends=nine_blends(p_win, p_push, p_market, american),
    )

def price_h1_team_total(
    *,
    game_id: str,
    team: str,
    expected: float,
    sd: float,
    line: float,
    american: float,
    side: str,
    capture_utc: str,
    dk_event_id: Optional[str] = None,
    p_market: Optional[float] = None,
) -> Dict:
    _validate_utc(capture_utc)
    if side not in ("over", "under"):
        raise Hold("INVALID_SIDE")
    probs = total_probs(expected, sd, line)
    p_win = probs[side]
    p_loss = probs["under"] if side == "over" else probs["over"]
    p_push = probs["push"]
    return _base_row(
        game_id=game_id, dk_event_id=dk_event_id, market="H1_TEAM_TOTAL", period="H1",
        settlement="TWO_WAY", team=team, selection=side, line=line,
        american=american, capture_utc=capture_utc, expected=expected, sd=sd,
        p_win=p_win, p_loss=p_loss, p_push=p_push,
        fair_decimal=fair_decimal(p_win, p_push),
        break_even=break_even(american),
        independent_ev=ev(p_win, p_loss, american),
        nine_blends=nine_blends(p_win, p_push, p_market, american),
    )
