"""Key-number-aware NFL margin CHALLENGER. PAPER / 0u.

The frozen v3 pricer (runit_ledger.py) uses Normal(mean, 13.5) for the final
margin, which puts ~3% on "won by exactly 3". This module keeps the same Normal
but re-weights the integer margins |m| in `weights` and renormalises, so spreads
can price the half-point across 3 and 7. It never edits frozen v3 rows.

fit_weights() is point-in-time: pass only finals completed BEFORE the slate.
Weights are floored at 1.0 and use +1 smoothing, so a small sample can raise a
key number but never invent a hole.
"""
from __future__ import annotations

import math
from statistics import NormalDist

N = NormalDist()
SD_MARGIN = 13.5          # same as frozen v3
KEYS = (3, 7)
SPAN = 70


def pmf(mean, sd=SD_MARGIN, weights=None):
    w = weights or {}
    p = {k: (N.cdf((k + .5 - mean) / sd) - N.cdf((k - .5 - mean) / sd)) * w.get(abs(k), 1.0)
         for k in range(-SPAN, SPAN + 1)}
    s = sum(p.values())
    return {k: v / s for k, v in p.items()}


def fit_weights(margins, sd=SD_MARGIN, keys=KEYS):
    """margins: completed-game final margins (home - away) available before the slate."""
    if not margins:
        return {}
    base = pmf(0.0, sd)
    n = len(margins)
    out = {}
    for k in keys:
        obs = (sum(abs(m) == k for m in margins) + 1) / (n + 1)
        out[k] = max(1.0, obs / (base[k] + base[-k]))
    return out


def cover(mean, line, sd=SD_MARGIN, weights=None):
    """Side with expected margin `mean` taking `line` (e.g. -3 = laying 3).
    Returns (p_win, p_push, p_loss); push only on integer lines."""
    p = pmf(mean, sd, weights)
    thr = -line
    win = sum(v for k, v in p.items() if k > thr + 1e-9)
    push = sum(v for k, v in p.items() if abs(k - thr) < 1e-9)
    return win, push, 1 - win - push


def log_loss(margins_with_means, sd=SD_MARGIN, weights=None):
    """Mean negative log-likelihood of exact final margins."""
    tot = 0.0
    for m, mu in margins_with_means:
        tot -= math.log(max(pmf(mu, sd, weights).get(m, 1e-12), 1e-12))
    return tot / len(margins_with_means)


def ev(p_win, p_push, american):
    d = 1 + (american / 100 if american > 0 else 100 / -american)
    return p_win * (d - 1) - (1 - p_win - p_push)
