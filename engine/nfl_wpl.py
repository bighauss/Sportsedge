"""Explicit win / push / loss mass for priced NFL sides (research only, PAPER/0u).

direct_wpl(S, ...)   PRIMARY. Counts win / push / loss over the simulator's own per-simulation
                     outcomes (v5.diff: >0 win, ==0 push, <0 loss). Nothing is back-solved.
wpl(...) / annotate  DIAGNOSTIC ONLY. Derives the no-push share from v5's reported pre-blend EV.
All functions validate strictly and return an UNAVAILABLE status instead of raising or emitting NaN.
There is no fallback to blended EV: annotate() requires the pre-blend `model_ev`.
"""
import math
import numbers
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

EPS = 1e-6
BASES = {"ML", "SPREAD", "TOTAL", "HOME_TT", "AWAY_TT"}
NO_LINE = {"ML"}
PERIODS = {"1Q": [0], "2Q": [1], "3Q": [2], "4Q": [3], "1H": [0, 1], "2H": [2, 3]}


def _is_real(x):
    """Strict scalar: real number, never bool / np.bool_ / str / None."""
    return isinstance(x, numbers.Real) and not isinstance(x, (bool, np.bool_))


def valid_american(x):
    """Float American odds, or None. Real, finite, integer-valued, |odds| >= 100."""
    if not _is_real(x):
        return None
    o = float(x)
    if not math.isfinite(o) or abs(o) < 100.0 or not o.is_integer():
        return None
    return o


def _payout(o):
    return o / 100.0 if o > 0 else 100.0 / -o


def _unavailable(reason):
    return dict(p_win=None, p_push=None, p_loss=None, wpl_status="UNAVAILABLE: " + reason, wpl_source=None)


def _finite_prob(x):
    if not _is_real(x):
        return None
    x = float(x)
    return x if math.isfinite(x) and 0.0 <= x <= 1.0 else None


def wpl(model_p, price, ev):
    """Diagnostic EV inversion. ev must be v5's push-aware (pre-blend) EV."""
    o = valid_american(price)
    if o is None:
        return _unavailable("invalid American odds")
    mp = _finite_prob(model_p)
    if mp is None:
        return _unavailable("model_p missing, non-real, non-finite or outside [0,1]")
    if not _is_real(ev) or not math.isfinite(float(ev)):
        return _unavailable("ev missing, non-real or not finite")
    den = mp * _payout(o) - (1.0 - mp)
    if abs(den) <= EPS:
        return _unavailable("push share unrecoverable at break-even")
    s = float(ev) / den
    if s < -1e-9 or s > 1.0 + 1e-9:
        return _unavailable("implied no-push share %.4f outside [0,1]" % s)
    s = min(max(s, 0.0), 1.0)
    return dict(p_win=s * mp, p_push=1.0 - s, p_loss=s * (1.0 - mp),
                wpl_status="DERIVED_FROM_EV", wpl_source="ev_inversion")


def annotate(o):
    """Diagnostic annotation. Requires pre-blend model_ev; never falls back to blended `ev`."""
    if "model_ev" not in o:
        o.update(_unavailable("model_ev absent; refusing to use blended ev"))
        return o
    o.update(wpl(o.get("model_p"), o.get("price"), o["model_ev"]))
    return o


def _arr1d(x):
    try:
        a = np.asarray(x)
    except Exception:
        return None
    if a.ndim != 1 or a.size == 0 or a.dtype.kind not in "iuf" or not np.isfinite(a.astype(float)).all():
        return None
    return a


def _check_sim(S, pre):
    if not isinstance(S, dict):
        return "simulation is not a dict"
    h, a = _arr1d(S.get("h")), _arr1d(S.get("a"))
    if h is None or a is None:
        return "h/a missing, non-1-D, empty or non-finite"
    if h.shape != a.shape:
        return "h and a lengths differ (%d vs %d)" % (h.size, a.size)
    if pre:
        for k in ("H", "A"):
            m = S.get(k)
            if not isinstance(m, np.ndarray) or m.ndim != 2 or m.shape[0] != h.size or m.shape[1] <= max(PERIODS[pre]):
                return "period matrix %s missing or misshapen" % k
            if not np.isfinite(m.astype(float)).all():
                return "period matrix %s non-finite" % k
    return None


def direct_wpl(S, sport, market, line, side):
    """Win/push/loss for one side straight from simulator output S (dict from v5.simulate). NFL only."""
    if sport != "NFL":
        return _unavailable("NFL only")
    if not isinstance(side, (int, np.integer)) or isinstance(side, (bool, np.bool_)) or int(side) not in (0, 1):
        return _unavailable("side must be integer 0 or 1")
    if not isinstance(market, str):
        return _unavailable("market must be a string")
    head, _, rest = market.upper().partition("_")
    pre, base = (head, rest) if head in PERIODS and rest else ("", market.upper())
    if base not in BASES:
        return _unavailable("market %s outside NFL game-line contract" % market)
    if base in NO_LINE:
        ln = 0.0
    elif not _is_real(line) or not math.isfinite(float(line)):
        return _unavailable("line missing, non-real or not finite")
    else:
        ln = float(line)
    why = _check_sim(S, pre)
    if why:
        return _unavailable(why)
    try:
        d = np.asarray(v5.diff(S, sport, market.upper(), ln), dtype=float)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return _unavailable("market not simulated: %s" % exc)
    if d.ndim != 1 or d.size != S["h"].size or not np.isfinite(d).all():
        return _unavailable("outcome array malformed")
    if int(side) == 1:
        d = -d
    n = int(d.size)
    w, p, l = float((d > 0).sum()) / n, float((d == 0).sum()) / n, float((d < 0).sum()) / n
    if abs(w + p + l - 1.0) > 1e-12:
        return _unavailable("probabilities do not normalise")
    return dict(p_win=w, p_push=p, p_loss=l, wpl_status="SIMULATED", wpl_source="simulator_counts", n_sims=n)
