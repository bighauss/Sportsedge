"""Frozen-from-tune residual adjustments, longshot calibration and side-bias corrections.

CHALLENGER research only (PAPER / 0u, NON_COUNTED). Coefficients are fit on the TUNE
window (2020-22) and then held frozen. Callers must not refit on validation or the
already-used 2026-27 confirmatory window.

Projection adjustments are outcome-only (actual minus independent forecast). They do
not take market lines as inputs. Longshot and side-bias maps are also fit on model
probability vs outcome, not vs the market. Market Brier/bias remain evaluation metrics
only; ESPN odds are an auxiliary comparator.
"""
from __future__ import annotations

import math

from .context import EARLY_N, early_flag

# Feature names for each ablation. ``ctx`` is the combined specification chosen as the
# candidate; every name is also scored alone so failures are visible.
VARIANTS = {
    "rest":     ("intercept", "rest_diff", "home_b2b", "away_b2b"),
    "travel":   ("intercept", "away_miles100", "home_miles100", "away_moved", "home_moved"),
    "neutral":  ("intercept", "is_neutral"),
    "early":    ("intercept", "early"),
    "ctx":      ("intercept", "rest_diff", "home_b2b", "away_b2b", "is_neutral",
                 "away_miles100", "home_miles100", "early"),
}


def features(row, names):
    early = early_flag(row.get("n_home", 0), row.get("n_away", 0))
    bag = {
        "intercept": 1.0,
        "rest_diff": float(row.get("rest_diff") or 0.0),
        "home_b2b": float(row.get("home_b2b") or 0.0),
        "away_b2b": float(row.get("away_b2b") or 0.0),
        "is_neutral": float(row.get("is_neutral") or 0.0),
        "away_miles100": float(row.get("away_miles") or 0.0) / 100.0,
        "home_miles100": float(row.get("home_miles") or 0.0) / 100.0,
        "away_moved": float(row.get("away_moved") or 0.0),
        "home_moved": float(row.get("home_moved") or 0.0),
        "early": float(early),
    }
    return [bag[n] for n in names]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _solve(A, b):
    """Gaussian elimination with partial pivot. A is mutated; returns x or None if singular."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for k in range(n):
        piv = max(range(k, n), key=lambda i: abs(M[i][k]))
        if abs(M[piv][k]) < 1e-12:
            return None
        M[k], M[piv] = M[piv], M[k]
        for i in range(k + 1, n):
            f = M[i][k] / M[k][k]
            for j in range(k, n + 1):
                M[i][j] -= f * M[k][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / M[i][i]
    return x


def fit_ridge(X, y, lam=1.0):
    """Ridge (X'X + lam I) b = X'y, intercept (col 0) left un-penalized."""
    n, p = len(X), len(X[0])
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for row, yi in zip(X, y):
        for i in range(p):
            xty[i] += row[i] * yi
            for j in range(p):
                xtx[i][j] += row[i] * row[j]
    for i in range(1, p):
        xtx[i][i] += lam
    return _solve(xtx, xty)


def fit_variant(rows, names, target, lam=1.0, min_n=50):
    """target is 'margin' or 'total'. Residual = actual - FG1 forecast. Returns coef or None."""
    X, y = [], []
    for r in rows:
        f = r.get("f", {}).get("FG1")
        if not f:
            continue
        X.append(features(r, names))
        if target == "margin":
            y.append((r["home_points"] - r["away_points"]) - f["margin"])
        else:
            y.append((r["home_points"] + r["away_points"]) - f["total"])
    if len(y) < min_n:
        return None
    coef = fit_ridge(X, y, lam=lam)
    if coef is None:
        return None
    return {"names": list(names), "coef": coef, "n": len(y), "target": target, "lam": lam}


def apply_fit(row, fit, forecast):
    """Return adjusted (margin, total) given an FG1 forecast dict and a {'margin','total'} fit pair."""
    m = forecast["margin"]
    t = forecast["total"]
    if fit.get("margin"):
        m = m + _dot(fit["margin"]["coef"], features(row, fit["margin"]["names"]))
    if fit.get("total"):
        t = t + _dot(fit["total"]["coef"], features(row, fit["total"]["names"]))
    hp = (t + m) / 2.0
    ap = (t - m) / 2.0
    return {"home_points": hp, "away_points": ap, "margin": m, "total": t,
            "possessions": forecast.get("possessions")}


# ---------------------------------------------------------------- longshot / favourite calibration (outcome-only)
def _logit(p):
    p = min(1 - 1e-9, max(1e-9, p))
    return math.log(p / (1 - p))


def _sig(z):
    z = max(-30, min(30, z))
    return 1.0 / (1.0 + math.exp(-z))


def fit_longshot(pairs, edges=(0.05, 0.08, 0.12)):
    """Empirical win rate in the left tail of model p, fit on tune pairs (p, y).

    ``shrink`` maps a tail threshold -> (model mean p, empirical rate, n). Applied by
    linearly shrinking p toward the empirical rate when p is below the threshold
    (and symmetrically above 1-threshold). The smallest edge with n>=30 is preferred
    at apply time via ``primary``.
    """
    out = {"edges": {}, "primary": None, "n": len(pairs)}
    for e in edges:
        tail = [(p, y) for p, y in pairs if p <= e or p >= 1 - e]
        if len(tail) < 20:
            out["edges"][str(e)] = {"n": len(tail), "model": None, "rate": None}
            continue
        # evaluate the LOW side (p<=e) and mirror
        low = [(p, y) for p, y in tail if p <= e]
        if len(low) < 10:
            out["edges"][str(e)] = {"n": len(tail), "model": None, "rate": None}
            continue
        model = sum(p for p, _ in low) / len(low)
        rate = sum(y for _, y in low) / len(low)
        out["edges"][str(e)] = {"n": len(low), "model": model, "rate": rate}
        if out["primary"] is None:
            out["primary"] = e
    return out


def apply_longshot(p, cal):
    if not cal or cal.get("primary") is None:
        return p
    e = cal["primary"]
    info = cal["edges"][str(e)]
    if not info or info["model"] is None or info["model"] <= 1e-9:
        return p
    rate, model = info["rate"], info["model"]
    # shrink factor so that the bin mean moves from model -> rate; apply proportionally
    # in the tail, identity in the interior.
    if p <= e:
        # p' = p * (rate/model), clipped to (0, 0.5)
        return max(1e-6, min(0.5, p * (rate / model)))
    if p >= 1 - e:
        q = apply_longshot(1 - p, cal)
        return 1 - q
    return p


def fit_fav_bump(pairs):
    """Constant add-on to the model's favourite probability, fit on tune (p_home, y_home).

    Independent of the market: the favourite is the side the MODEL prefers.
    """
    d = []
    for p, y in pairs:
        if p >= 0.5:
            d.append(y - p)
        else:
            d.append((1 - y) - (1 - p))
    if len(d) < 50:
        return {"delta": 0.0, "n": len(d)}
    return {"delta": sum(d) / len(d), "n": len(d)}


def apply_fav_bump(p, bump):
    if not bump:
        return p
    d = bump["delta"]
    if p >= 0.5:
        return max(0.5, min(1 - 1e-6, p + d))
    return min(0.5, max(1e-6, p - d))


def fit_over_shift(pairs):
    """Constant shift to P(over), fit on tune (p_over, y_over) at the model's OWN total
    (a 50-cent line on the independent projection). Market lines are not used."""
    if len(pairs) < 50:
        return {"delta": 0.0, "n": len(pairs)}
    d = sum(y - p for p, y in pairs) / len(pairs)
    return {"delta": d, "n": len(pairs)}


def apply_over_shift(p, shift):
    if not shift:
        return p
    return max(1e-6, min(1 - 1e-6, p + shift["delta"]))
