"""Versioned skewed player-prop outcome distributions (CFB / CBB), evaluated from data tables.

A table is the train-season empirical distribution of outcome/forecast ratios, binned by
forecast size (see research/prop_variance/fit_skew_tables.py). Tables are fitted per sport;
never reuse another sport's table. Outcomes are integer counts/yards, so

    P(X >= k | mean m) = 1 - F_bin(m)((k - 0.5) / m)

and for a line L:
    half-point L:  over = P(X >= ceil(L)), push = 0,           under = 1 - over
    integer   L:   over = P(X >= L + 1),   push = P(X = L),    under = P(X <= L - 1)
These sum to 1 exactly and P(over) is non-increasing in L by construction.

Low volume: a forecast below the table's ``min_mean`` (lowest fitted bin edge) is refused
(LOW_VOLUME_FORECAST) rather than extrapolated. Forecasts above the top bin use the top bin
(documented open-ended bucket). PAPER / 0u. Not validated against sportsbook lines.
"""
from __future__ import annotations
import bisect
import json
import math
from pathlib import Path


class SkewError(ValueError):
    pass


_CACHE = {}


def load(path):
    p = Path(path)
    if p not in _CACHE:
        tab = json.loads(p.read_text(encoding="utf-8"))
        if tab.get("schema") != "sportsedge-prop-skew-table-v1":
            raise SkewError("UNSUPPORTED_TABLE_SCHEMA")
        _CACHE[p] = tab
    return _CACHE[p]


def _cdf(q, t):
    n = len(q) - 1
    if t <= q[0]:
        return 0.0
    if t >= q[-1]:
        return 1.0
    i = bisect.bisect_right(q, t) - 1
    lo, hi = q[i], q[i + 1]
    return (i + (0.0 if hi == lo else (t - lo) / (hi - lo))) / n


def _bin(st, mean):
    if mean < st["min_mean"]:
        raise SkewError("LOW_VOLUME_FORECAST")
    for b in st["bins"]:
        if b["lo"] <= mean < b["hi"]:
            return b
    return st["bins"][-1]


def p_ge(tab, stat, mean, k):
    """P(outcome >= k), k integer."""
    st = tab["stats"].get(stat)
    if st is None:
        raise SkewError("NOT_FITTED:" + str(stat))
    if isinstance(mean, bool) or not isinstance(mean, (int, float)) or not math.isfinite(mean) or mean <= 0:
        raise SkewError("NONPOSITIVE_MEAN")
    return 1.0 - _cdf(_bin(st, mean)["q"], (k - 0.5) / mean)


def three_way(tab, stat, mean, line):
    """(p_over, p_push, p_under) for a .0 or .5 line."""
    if isinstance(line, bool) or not isinstance(line, (int, float)) or not math.isfinite(line) or (line * 2) % 1:
        raise SkewError("LINE_OFF_HALF_POINT_GRID")
    if float(line).is_integer():
        k = int(line)
        over, at_least = p_ge(tab, stat, mean, k + 1), p_ge(tab, stat, mean, k)
        return over, at_least - over, 1.0 - at_least
    over = p_ge(tab, stat, mean, math.ceil(line))
    return over, 0.0, 1.0 - over
