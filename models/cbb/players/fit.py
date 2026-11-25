"""Chronological parameter fit for the CBB player-prop model (numpy).

Fit only on feature rows whose games precede the forecast origin. Per stat:
pace and opponent elasticities by grid (Poisson deviance), a multiplicative
debias factor, NB2 dispersion by moments, and the residual correlation of
points/rebounds/assists used for the combo markets.
"""
import math

from players.features import STATS

B_PACE = (0.0, 0.5, 1.0, 1.5)
B_OPP = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
MIN_TRAIN_ROWS = 5000
CORR_STATS = ("POINTS", "REBOUNDS", "ASSISTS")


def _dev(y, mu):
    import numpy as np
    mu = np.maximum(mu, 1e-9)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(y > 0, y * np.log(y / mu), 0.0)
    return float(np.mean(2 * (t - (y - mu))))


def fit(rows):
    import numpy as np
    if len(rows) < MIN_TRAIN_ROWS:
        raise ValueError("FIT_INSUFFICIENT_TRAINING_ROWS")
    pace = np.array([r["pace_ratio"] for r in rows], float)
    out = {"n_train": len(rows), "train_first_day": min(r["day"] for r in rows),
           "train_last_day": max(r["day"] for r in rows), "stats": {}}
    mus, resid = {}, {}
    for s in STATS:
        base = np.array([r["base"][s] for r in rows], float)
        opp = np.array([r["opp_factor"][s] for r in rows], float)
        y = np.array([r["actual"][s] for r in rows], float)
        best = None
        for bp in B_PACE:
            for bo in B_OPP:
                p0 = base * pace ** bp * opp ** bo
                c = y.sum() / p0.sum()
                d = _dev(y, c * p0)
                if best is None or d < best[0]:
                    best = (d, bp, bo, c)
        d, bp, bo, c = best
        mu = c * base * pace ** bp * opp ** bo
        alpha = max(0.0, float(((y - mu) ** 2 - mu).sum() / (mu ** 2).sum()))
        out["stats"][s] = {"b_pace": bp, "b_opp": bo, "calibration": float(c),
                           "alpha": alpha, "train_deviance": d}
        mus[s] = mu
        resid[s] = (y - mu) / np.sqrt(mu + alpha * mu * mu + 1e-12)
    m = np.corrcoef(np.vstack([resid[s] for s in CORR_STATS]))
    out["rho"] = {f"{a}|{b}": float(m[i, j]) for i, a in enumerate(CORR_STATS)
                  for j, b in enumerate(CORR_STATS) if i < j}
    return out


def rho_of(params, a, b):
    return params["rho"].get(f"{a}|{b}", params["rho"].get(f"{b}|{a}", 0.0))
