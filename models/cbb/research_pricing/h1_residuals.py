"""Empirical first-half residual calibration for research pricing (PAPER/0u).

Fits residual standard deviations for H1 margin, total, and team totals from
chronological (predicted, actual) pairs. Does not promote coefficients or
write ledgers. Caller must supply only prior observations relative to the
decision time.
"""
from __future__ import annotations
import math
from statistics import mean, stdev
from typing import Dict, Iterable, List, Optional, Tuple

class Hold(Exception):
    pass

def residual_sd(pairs: Iterable[Tuple[float, float]], *, min_n: int = 30) -> Dict[str, float]:
    """
    pairs: iterable of (predicted, actual).
    Returns residual mean, residual SD, and sample size.
    Raises Hold if the sample is too small or non-finite.
    """
    residuals = []
    for pred, actual in pairs:
        if not (math.isfinite(pred) and math.isfinite(actual)):
            raise Hold("NONFINITE_RESIDUAL")
        residuals.append(actual - pred)
    n = len(residuals)
    if n < min_n:
        raise Hold("INSUFFICIENT_RESIDUAL_SAMPLE")
    mu = mean(residuals)
    sd = stdev(residuals) if n > 1 else 0.0
    if sd <= 0 or not math.isfinite(sd):
        raise Hold("NONPOSITIVE_RESIDUAL_SD")
    return {"n": n, "residual_mean": mu, "residual_sd": sd}

def fit_h1_residuals(
    margin_pairs: Iterable[Tuple[float, float]],
    total_pairs: Iterable[Tuple[float, float]],
    home_team_total_pairs: Optional[Iterable[Tuple[float, float]]] = None,
    away_team_total_pairs: Optional[Iterable[Tuple[float, float]]] = None,
    *,
    min_n: int = 30,
) -> Dict[str, Dict[str, float]]:
    """Fit residual distributions for the four H1 targets. Research only."""
    out = {
        "margin": residual_sd(margin_pairs, min_n=min_n),
        "total": residual_sd(total_pairs, min_n=min_n),
    }
    if home_team_total_pairs is not None:
        out["home_team_total"] = residual_sd(home_team_total_pairs, min_n=min_n)
    if away_team_total_pairs is not None:
        out["away_team_total"] = residual_sd(away_team_total_pairs, min_n=min_n)
    return out

def sds_for_pricing(fit: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Extract residual SDs in the shape expected by the pricing interface."""
    return {
        "sd_margin": fit["margin"]["residual_sd"],
        "sd_total": fit["total"]["residual_sd"],
        "sd_home_team_total": fit.get("home_team_total", {}).get("residual_sd"),
        "sd_away_team_total": fit.get("away_team_total", {}).get("residual_sd"),
    }
