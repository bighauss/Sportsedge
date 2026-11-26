"""Explicit win / push / loss mass for one priced NFL side (research only, PAPER/0u).

v5 reports model_p as the win probability conditional on no push, and ev as the
push-aware EV:  ev = s * (model_p * pay - (1 - model_p)),  s = P(no push).
Inverting gives s, hence p_win = s * model_p, p_loss = s * (1 - model_p), p_push = 1 - s.
When the conditional EV is ~0 the share is unrecoverable; probabilities are then None
(never guessed). This is a derived view of simulator output, not a new model.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sportsedge_v5 as v5  # noqa: E402

EPS = 1e-6


def wpl(model_p, price, ev):
    """Return dict(p_win, p_push, p_loss, wpl_status)."""
    none = dict(p_win=None, p_push=None, p_loss=None)
    if model_p is None or ev is None or not (0.0 <= model_p <= 1.0):
        return dict(none, wpl_status="UNAVAILABLE: missing or invalid model_p/ev")
    den = model_p * v5.payout(price) - (1.0 - model_p)
    if abs(den) <= EPS:
        return dict(none, wpl_status="UNAVAILABLE: push share unrecoverable at break-even")
    s = ev / den
    if s < -1e-9 or s > 1.0 + 1e-9:
        return dict(none, wpl_status="UNAVAILABLE: implied no-push share %.4f outside [0,1]" % s)
    s = min(max(s, 0.0), 1.0)
    return dict(p_win=s * model_p, p_push=1.0 - s, p_loss=s * (1.0 - model_p), wpl_status="DERIVED")


def annotate(o):
    """Add explicit W/P/L fields to a priced row using v5's own (pre-blend) EV."""
    ev = o.get("model_ev", o.get("ev"))
    o.update(wpl(o.get("model_p"), o.get("price"), ev))
    return o
