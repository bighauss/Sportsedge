"""Versioned skewed NFL player-prop outcome distribution (prop-skew-v1).

Empirical distribution of outcome/forecast ratios, binned by forecast size, fitted on
nflverse 2018-2022 ONLY (see research/prop_variance/fit_nfl_skew_table.py). The table is
data, not tuned by hand. P(X >= k | mean m) = 1 - F_bin(m)((k - 0.5) / m).

Replaces the symmetric normal, which overstated P(over) by 6-10 pts on rush/rec lines at
or below projection on the untouched 2023-2025 holdout (PR #571). Unvalidated vs sportsbook
lines. PAPER / 0u.
"""
from __future__ import annotations
import bisect, json
from pathlib import Path

VERSION = "prop-skew-v1"
TABLE_PATH = Path(__file__).with_name("prop_skew_v1_table.json")
_TABLE = None


def table():
    global _TABLE
    if _TABLE is None:
        _TABLE = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    return _TABLE


def _bin(stat, mean, tab):
    bins = tab["stats"][stat]["bins"]
    for b in bins:
        if b["lo"] <= mean < b["hi"]:
            return b
    return bins[-1] if mean >= bins[-1]["lo"] else bins[0]


def cdf_ratio(q, t):
    """Piecewise-linear CDF from an increasing quantile grid q at probs i/(len(q)-1)."""
    n = len(q) - 1
    if t <= q[0]:
        return 0.0
    if t >= q[-1]:
        return 1.0
    i = bisect.bisect_right(q, t) - 1
    lo, hi = q[i], q[i + 1]
    frac = 0.0 if hi == lo else (t - lo) / (hi - lo)
    return (i + frac) / n


def p_ge(stat, mean, k, tab=None):
    """P(outcome >= k) for a milestone threshold k given forecast mean (> 0)."""
    tab = tab or table()
    if stat not in tab["stats"]:
        raise KeyError("NOT_FITTED:" + str(stat))
    if not (isinstance(mean, (int, float)) and mean > 0):
        raise ValueError("NONPOSITIVE_MEAN")
    b = _bin(stat, mean, tab)
    return 1.0 - cdf_ratio(b["q"], (k - 0.5) / mean)


def p_over_half(stat, mean, line, tab=None):
    """P(outcome > line) for a half-point line (same as >= line + 0.5)."""
    return p_ge(stat, mean, line + 0.5, tab)
