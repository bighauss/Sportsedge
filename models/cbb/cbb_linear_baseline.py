"""CBB linear regression baseline (PAPER / 0u / NON_COUNTED).

Simple OLS on team efficiency and tempo features for home/away points.
Used as the chronological walk-forward floor that advanced models must beat.
No sportsbook inputs. Coefficients are untested starting values.
"""
from __future__ import annotations
import math
from typing import Mapping, Sequence, Any


def _ols_fit(X: Sequence[Sequence[float]], y: Sequence[float]) -> list[float]:
    """Minimal OLS for small feature sets. Returns coefficients including intercept."""
    n = len(y)
    if n == 0 or len(X) != n:
        raise ValueError("OLS_EMPTY_OR_MISMATCHED")
    # Add intercept column
    X_aug = [[1.0] + list(row) for row in X]
    p = len(X_aug[0])
    # Normal equations (XtX) beta = Xt y
    XtX = [[0.0] * p for _ in range(p)]
    Xty = [0.0] * p
    for i in range(n):
        for a in range(p):
            Xty[a] += X_aug[i][a] * y[i]
            for b in range(p):
                XtX[a][b] += X_aug[i][a] * X_aug[i][b]
    # Gaussian elimination (small p)
    for col in range(p):
        # pivot
        pivot = col
        for r in range(col + 1, p):
            if abs(XtX[r][col]) > abs(XtX[pivot][col]):
                pivot = r
        XtX[col], XtX[pivot] = XtX[pivot], XtX[col]
        Xty[col], Xty[pivot] = Xty[pivot], Xty[col]
        div = XtX[col][col]
        if abs(div) < 1e-12:
            raise ValueError("OLS_SINGULAR")
        for r in range(col, p):
            XtX[col][r] /= div
        Xty[col] /= div
        for r in range(p):
            if r == col:
                continue
            factor = XtX[r][col]
            for c in range(col, p):
                XtX[r][c] -= factor * XtX[col][c]
            Xty[r] -= factor * Xty[col]
    return Xty


def project_linear(home: Mapping[str, Any], away: Mapping[str, Any], coef_home: list[float], coef_away: list[float]) -> dict:
    """Project home and away points from efficiency/tempo features."""
    features = [
        home.get("adjoe") or 105.0,
        home.get("adjde") or 105.0,
        home.get("adj_t") or 67.5,
        away.get("adjoe") or 105.0,
        away.get("adjde") or 105.0,
        away.get("adj_t") or 67.5,
    ]
    def pred(coef):
        return coef[0] + sum(c * f for c, f in zip(coef[1:], features))
    hp = pred(coef_home)
    ap = pred(coef_away)
    if not (math.isfinite(hp) and math.isfinite(ap)):
        raise ValueError("NONFINITE_LINEAR_PROJECTION")
    return {
        "home_points": hp,
        "away_points": ap,
        "margin": hp - ap,
        "total": hp + ap,
        "label": "LINEAR_BASELINE_UNVALIDATED",
        "release_ready": False,
        "approved_stake_u": 0,
    }
