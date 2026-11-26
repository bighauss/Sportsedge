"""Priced W/P/L integration for NFL RUN IT without modifying frozen v5 (research, PAPER/0u).

While one v5.run executes, v5.wl / stat_probs / td_probs are wrapped (and restored on every exit path) to record
the exact outcome mass each priced call used. Calls made inside v5.anchor() (fitting) are excluded. Each call is
recorded in ORDER with integer counts (wl) or an exactly reproduced push mass (props). Priced rows are bound to
calls sequentially: a row matches the earliest unused call for its side whose win/loss reproduce the row's own
model_p and ev bit-for-bit; one call serves at most one row per side, so identical results keep distinct identity.
Unmatched rows are UNAVAILABLE and the guard HOLDS them. Frozen v5 is untouched. Intended for a dedicated process
(CLI); installed() restores every patched name and runs under run_nfl's v5 lock.
"""
import contextlib
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402
import nfl_wpl  # noqa: E402

TOL = 1e-9
UNAVAIL = dict(p_win=None, p_push=None, p_loss=None, wpl_source=None, wpl_call_index=None)


def prop_push(spec, mean, line, seed):
    """Exact push mass for v5.stat_probs, reproduced with v5's own formulas; None if not provable."""
    try:
        mean, (form, v) = max(mean, 0.01), spec
        if form == "y":
            shape = 1.0 / v ** 2
            x = np.rint(np.random.default_rng(seed).gamma(shape, 1.0, v5.N_FIT) / shape * mean)
            return float((x == line).mean()), float((x > line).mean()), float((x < line).mean())
        ks = range(int(mean * 4 + 40))
        if v <= 1.001:
            lp = [k * math.log(mean) - mean - math.lgamma(k + 1) for k in ks]
        else:
            s = mean / (v - 1)
            lp = [math.lgamma(k + s) - math.lgamma(s) - math.lgamma(k + 1)
                  + s * math.log(s / (s + mean)) + k * math.log(mean / (s + mean)) for k in ks]
        p, k = np.exp(lp), np.arange(len(lp))
        return float(p[k == line].sum()), float(p[k > line].sum()), float(p[k < line].sum())
    except Exception:
        return None


@contextlib.contextmanager
def capturing():
    calls, state = [], dict(depth=0)
    orig = (v5.wl, v5.stat_probs, v5.td_probs, v5.anchor)

    def anchor(*a, **k):
        state["depth"] += 1
        try:
            return orig[3](*a, **k)
        finally:
            state["depth"] -= 1

    def wl(d):
        w, l = orig[0](d)
        if state["depth"] == 0:
            arr = np.asarray(d)
            n = int(arr.size)
            wins, push, loss = int((arr > 0).sum()), int((arr == 0).sum()), int((arr < 0).sum())
            ok = n > 0 and wins + push + loss == n and w == wins / n and l == loss / n
            calls.append(dict(kind="wl", src="simulator_counts", w=w, l=l, push=(push / n if ok else None),
                              counts=(wins, push, loss, n) if ok else None, used=set()))
        return w, l

    def stat_probs(spec, mean, line, seed):
        w, l = orig[1](spec, mean, line, seed)
        if state["depth"] == 0:
            r = prop_push(spec, mean, line, seed)
            push = None
            if r is not None and abs(r[1] - w) <= 1e-12 and abs(r[2] - l) <= 1e-12:
                resid = 1.0 - w - l - r[0]
                if r[0] >= 0.0 and -TOL <= resid <= 1e-6:
                    push = r[0]
            calls.append(dict(kind="stat", src="prop_exact_distribution", w=w, l=l, push=push, counts=None, used=set()))
        return w, l

    def td_probs(S, market, share, is_home):
        w, l = orig[2](S, market, share, is_home)
        if state["depth"] == 0:
            ok = abs(w + l - 1.0) <= 1e-12 and w >= 0.0 and l >= 0.0
            calls.append(dict(kind="td", src="td_closed_form", w=w, l=l, push=0.0 if ok else None, counts=None, used=set()))
        return w, l

    v5.wl, v5.stat_probs, v5.td_probs, v5.anchor = wl, stat_probs, td_probs, anchor
    try:
        yield calls
    finally:
        v5.wl, v5.stat_probs, v5.td_probs, v5.anchor = orig


def _side(o):
    try:
        s = int(str(o["bet_type"]).split("|")[1])
    except (KeyError, IndexError, ValueError):
        return None
    return s if s in (0, 1) else None


def attach(rows, calls):
    """Bind rows to captured calls in order; set p_win/p_push/p_loss/wpl_status/wpl_source/wpl_call_index."""
    ptr = 0
    for o in rows:
        o.update(UNAVAIL, wpl_status="UNAVAILABLE: no matching simulator call")
        side, price = _side(o), o.get("price")
        if side is None or not nfl_wpl._is_real(price):
            o["wpl_status"] = "UNAVAILABLE: row side/price invalid"
            continue
        pay = v5.payout(int(price))
        for k in range(ptr, len(calls)):
            c = calls[k]
            if side in c["used"]:
                continue
            a, b = (c["w"], c["l"]) if side == 0 else (c["l"], c["w"])
            if v5.cond(a, b) == o.get("model_p") and a * pay - b == o.get("ev"):
                c["used"].add(side)
                ptr = k
                if c["push"] is None:
                    o["wpl_status"] = "UNAVAILABLE: push mass not provable (%s)" % c["kind"]
                    break
                if c["counts"] is not None:
                    wins, push, loss, n = c["counts"]
                    pw, pp, pl = (wins, push, loss) if side == 0 else (loss, push, wins)
                    pw, pp, pl = pw / n, pp / n, pl / n
                else:
                    pw, pp, pl = a, c["push"], b
                if min(pw, pp, pl) < 0.0 or not all(math.isfinite(x) for x in (pw, pp, pl)) or abs(pw + pp + pl - 1.0) > 1e-9:
                    o["wpl_status"] = "UNAVAILABLE: mass invalid or not normalised"
                    break
                o.update(p_win=pw, p_push=pp, p_loss=pl, wpl_status="CAPTURED", wpl_source=c["src"], wpl_call_index=k)
                break
    return rows


def priced_guard(orig_guard, o, gaps):
    """Run run_nfl.guard, then price from captured push mass and HOLD any NFL row lacking validated mass."""
    g = orig_guard(o, gaps)
    if g.get("sport") != "NFL":
        return g
    reasons = [r for r in str(g.get("held", "")).split("; ") if r]
    st = g.get("wpl_status", "UNAVAILABLE: not annotated")
    if st != "CAPTURED":
        reasons.append("simulator W/P/L unavailable: %s" % st.replace("UNAVAILABLE: ", ""))
    else:
        pay = v5.payout(int(g["price"]))
        if abs(g["p_win"] * pay - g["p_loss"] - g["model_ev"]) > 1e-9:
            reasons.append("captured W/P/L disagrees with v5 EV")
        reasons = [r for r in reasons if not r.startswith("push share not recoverable")]
        if g.get("status") == "BLENDED":
            s, p = g["p_win"] + g["p_loss"], g["blend_p"]
            g["ev"] = s * (p * pay - (1 - p))
            g["score"] = v5.score(g["ev"])
    g["held"] = "; ".join(reasons)
    return g


def validate_board(path):
    """Reject non-integer / sub-100 American odds on NFL rows BEFORE v5 truncates them with int()."""
    bad = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, raw in enumerate(csv.DictReader(f), start=2):
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            if r.get("sport", "").upper() != "NFL":
                continue
            for col in ("price_a", "price_b"):
                if r.get(col):
                    try:
                        v = v5.num(r[col])
                    except ValueError:
                        v = None
                    if nfl_wpl.valid_american(v) is None:
                        bad.append("line %d %s=%r" % (i, col, r[col]))
    if bad:
        raise ValueError("invalid American odds on NFL rows: " + "; ".join(bad[:20]))


@contextlib.contextmanager
def installed():
    """Temporarily route run_nfl through captured W/P/L pricing; always restores. Holds run_nfl's v5 lock."""
    import run_nfl
    with run_nfl._V5_LOCK:
        orig_run, orig_guard = v5.run, run_nfl.guard

        def run(path):
            validate_board(path)
            with capturing() as calls:
                rows = orig_run(path)
            return attach(rows, calls)

        def guard(o, gaps):
            return priced_guard(orig_guard, o, gaps)

        v5.run, run_nfl.guard = run, guard
        try:
            yield
        finally:
            v5.run, run_nfl.guard = orig_run, orig_guard
