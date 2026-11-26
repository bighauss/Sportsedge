"""Explicit win / push / loss mass for priced NFL sides (research only, PAPER/0u).

Two paths:
  direct_wpl(S, ...)  PRIMARY. Counts win / push / loss over the simulator's own per-simulation
                      outcomes (v5.diff: >0 win, ==0 push, <0 loss). Nothing is back-solved.
  wpl(...) / annotate DIAGNOSTIC ONLY. Derives the no-push share from v5's reported EV for rows
                      where the simulation object is not available. Fails closed, never guesses.
All functions validate inputs and return an UNAVAILABLE status instead of raising or emitting
NaN. There is no fallback to blended EV: annotate() requires the pre-blend `model_ev`.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

EPS = 1e-6


def valid_american(x):
    """Return float American odds, or None. Requires finite and |odds| >= 100 (so +50, 0, NaN fail)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        o = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(o) or abs(o) < 100.0:
        return None
    return o


def _payout(o):
    return o / 100.0 if o > 0 else 100.0 / -o


def _unavailable(reason):
    return dict(p_win=None, p_push=None, p_loss=None, wpl_status="UNAVAILABLE: " + reason, wpl_source=None)


def _finite_prob(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and 0.0 <= x <= 1.0 else None


def wpl(model_p, price, ev):
    """Diagnostic EV inversion. ev must be v5's push-aware (pre-blend) EV."""
    o = valid_american(price)
    if o is None:
        return _unavailable("invalid American odds")
    mp = _finite_prob(model_p)
    if mp is None:
        return _unavailable("model_p missing, non-finite or outside [0,1]")
    try:
        e = float(ev)
    except (TypeError, ValueError):
        return _unavailable("ev missing or non-numeric")
    if not math.isfinite(e):
        return _unavailable("ev not finite")
    den = mp * _payout(o) - (1.0 - mp)
    if abs(den) <= EPS:
        return _unavailable("push share unrecoverable at break-even")
    s = e / den
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


def direct_wpl(S, sport, market, line, side):
    """Win/push/loss for one side straight from simulator output S (dict from v5.simulate)."""
    if side not in (0, 1) or isinstance(side, bool):
        return _unavailable("side must be 0 or 1")
    try:
        ln = float(line)
    except (TypeError, ValueError):
        return _unavailable("line not numeric")
    if not math.isfinite(ln):
        return _unavailable("line not finite")
    try:
        d = np.asarray(v5.diff(S, sport, market, ln), dtype=float)
    except (ValueError, KeyError) as exc:
        return _unavailable("market not simulated: %s" % exc)
    if d.size == 0 or not np.isfinite(d).all():
        return _unavailable("empty or non-finite simulation outcomes")
    if side == 1:
        d = -d
    n = int(d.size)
    w, p, l = float((d > 0).sum()) / n, float((d == 0).sum()) / n, float((d < 0).sum()) / n
    if abs(w + p + l - 1.0) > 1e-12:
        return _unavailable("probabilities do not normalise")
    return dict(p_win=w, p_push=p, p_loss=l, wpl_status="SIMULATED", wpl_source="simulator_counts", n_sims=n)
