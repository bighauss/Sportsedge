"""Capture the exact outcome mass v5 prices from, without modifying frozen v5 (research, PAPER/0u).

v5.run computes each game-line row from `wl(d)` on the very outcome array it prices with, and each prop from
`stat_probs` / `td_probs`. install() wraps those module-level callables for the duration of one v5.run call and
records (win, loss, push) per call. Rows are then matched back by bit-exact reproduction of the row's own
model_p and ev from the captured (win, loss) -- no second RNG path. A row that matches zero or several
distinct captures gets UNAVAILABLE, never a guess.
Sources: wl -> simulator_counts (exact push count); stat_probs -> analytic_distribution (push = 1-w-l);
td_probs -> td_closed_form (push = 0 by construction).
"""
import contextlib
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

UNAVAIL = dict(p_win=None, p_push=None, p_loss=None, wpl_source=None)


class Capture:
    def __init__(self):
        self.items = {}      # (w, l) -> {(push, source), ...}

    def add(self, w, l, push, source):
        self.items.setdefault((float(w), float(l)), set()).add((float(push), source))


@contextlib.contextmanager
def capturing():
    cap, orig = Capture(), (v5.wl, v5.stat_probs, v5.td_probs)

    def wl(d):
        w, l = orig[0](d)
        arr = np.asarray(d)
        cap.add(w, l, float((arr == 0).mean()) if arr.size else float("nan"), "simulator_counts")
        return w, l

    def stat_probs(*a, **k):
        w, l = orig[1](*a, **k)
        cap.add(w, l, 1.0 - w - l, "analytic_distribution")
        return w, l

    def td_probs(*a, **k):
        w, l = orig[2](*a, **k)
        cap.add(w, l, 0.0, "td_closed_form")
        return w, l

    v5.wl, v5.stat_probs, v5.td_probs = wl, stat_probs, td_probs
    try:
        yield cap
    finally:
        v5.wl, v5.stat_probs, v5.td_probs = orig


def _side(o):
    try:
        return int(str(o["bet_type"]).split("|")[1])
    except (KeyError, IndexError, ValueError):
        return None


def attach(rows, cap):
    """Add p_win/p_push/p_loss/wpl_status/wpl_source to each priced row from captured outcome mass."""
    for o in rows:
        o.update(UNAVAIL, wpl_status="UNAVAILABLE: not matched")
        side, price = _side(o), o.get("price")
        if side not in (0, 1) or not isinstance(price, (int, float)) or isinstance(price, bool):
            o["wpl_status"] = "UNAVAILABLE: row side/price invalid"
            continue
        hits = set()
        for (w, l), meta in cap.items.items():
            a, b = (w, l) if side == 0 else (l, w)
            if v5.cond(a, b) == o.get("model_p") and a * v5.payout(price) - b == o.get("ev"):
                hits.add((w, l))
        if len(hits) != 1:
            o["wpl_status"] = "UNAVAILABLE: %d captured outcome sets match" % len(hits)
            continue
        w, l = next(iter(hits))
        metas = cap.items[(w, l)]
        if len(metas) != 1 or not all(math.isfinite(m[0]) for m in metas):
            o["wpl_status"] = "UNAVAILABLE: ambiguous push mass for matched outcome set"
            continue
        push, src = next(iter(metas))
        a, b = (w, l) if side == 0 else (l, w)
        if abs(a + b + push - 1.0) > 1e-9:
            o["wpl_status"] = "UNAVAILABLE: captured mass does not normalise"
            continue
        o.update(p_win=a, p_push=push, p_loss=b, wpl_status="CAPTURED", wpl_source=src)
    return rows


def install():
    """Wrap v5.run once so every row it returns carries explicit W/P/L. Idempotent. v5 source is untouched."""
    if getattr(v5.run, "_wpl_wrapped", False):
        return
    inner = v5.run

    def run(path):
        with capturing() as cap:
            rows = inner(path)
        return attach(rows, cap)
    run._wpl_wrapped = True
    v5.run = run
