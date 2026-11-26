"""Priced W/P/L capture for NFL RUN IT without modifying frozen v5 (research, PAPER/0u).

While one v5.run executes, v5.wl / stat_probs / td_probs are wrapped (restored on every exit path). Each priced call
records its exact outcome mass and the SELECTION IDENTITY read from the calling frame, accepted only when that frame
is real v5 pricing code (module in CALLSITE_MODULES, not a lambda/genexpr such as the fitting bisect). Calls inside
v5.anchor() are excluded. An output row binds to a call only through (sport, game, bet_type, player, price) AND the
pick label v5 prints: v5.game_labels for game lines, "{player} {TD_NAMES[stat]}" / "{player} No {TD_NAMES[stat]}" for
touchdown markets, "{player} Over|Under {line:g} {Stat Name}" for other props. The mass must also reproduce the row's
model_p and ev exactly. Missing identity, no match, several different masses, a line that %g cannot represent exactly,
or a numeric mismatch give UNAVAILABLE and the guard HOLDS the row. validate_board() additionally REJECTS the whole
board before pricing when any NFL line is not exactly representable by %g, so a valid and an invalid line can never
share a printed label. Frozen v5 is untouched.
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
ID_KEYS = {"market", "price_a", "price_b", "home"}
CALLSITE_MODULES = {v5.__name__}
UNAVAIL = dict(p_win=None, p_push=None, p_loss=None, wpl_source=None, wpl_binding=None)


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


def _is_game_line(market):
    head, _, rest = str(market).upper().partition("_")
    base = rest if rest and head in nfl_wpl.PERIODS else str(market).upper()
    return base in nfl_wpl.BASES


def _exact_g(line):
    """True when %g formatting round-trips the line, so a printed label identifies it exactly."""
    return nfl_wpl._is_real(line) and float("%g" % line) == float(line)


def _labels(i):
    """Pick labels (side 0, side 1) exactly as v5 prints them; None when they cannot be derived exactly."""
    try:
        market, player = i.get("market", ""), i.get("player")
        if _is_game_line(market):
            if not _exact_g(i.get("line", 0.0)):
                return None
            return tuple(v5.game_labels(i["sport"], i))
        if not player:
            return None
        stat = str(i.get("stat") or market)
        td = getattr(v5, "TD_NAMES", None)
        if isinstance(td, dict) and stat in td:
            return ("%s %s" % (player, td[stat]), "%s No %s" % (player, td[stat]))
        line = i.get("line")
        if not _exact_g(line):
            return None
        name = stat.replace("_", " ").title()
        return ("%s Over %g %s" % (player, line, name), "%s Under %g %s" % (player, line, name))
    except Exception:
        return None


def _identity():
    """Board row v5 is pricing, from the frame that called the wrapper (0 here, 1 wrapper, 2 caller)."""
    try:
        frame = sys._getframe(2)
    except ValueError:
        return None
    if frame.f_code.co_name.startswith("<") or frame.f_globals.get("__name__") not in CALLSITE_MODULES:
        return None
    loc = frame.f_locals
    cands = {k: v for k, v in loc.items() if isinstance(v, dict) and ID_KEYS <= set(v)}
    r = cands.get("r") if "r" in cands else (next(iter(cands.values())) if len(cands) == 1 else None)
    if r is None:
        return None
    ident = dict(r)
    ident["sport"] = str(ident.get("sport") or loc.get("sport") or "")
    ident["labels"] = _labels(ident)
    return ident


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
                              counts=(wins, push, loss, n) if ok else None, ident=_identity()))
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
            calls.append(dict(kind="stat", src="prop_exact_distribution", w=w, l=l, push=push, counts=None,
                              ident=_identity()))
        return w, l

    def td_probs(S, market, share, is_home):
        w, l = orig[2](S, market, share, is_home)
        if state["depth"] == 0:
            ok = abs(w + l - 1.0) <= 1e-12 and w >= 0.0 and l >= 0.0
            calls.append(dict(kind="td", src="td_closed_form", w=w, l=l, push=0.0 if ok else None, counts=None,
                              ident=_identity()))
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


def _reproduces(w, l, side, price, o):
    a, b = (w, l) if side == 0 else (l, w)
    return v5.cond(a, b) == o.get("model_p") and a * v5.payout(int(price)) - b == o.get("ev")


def _selection_index(calls):
    """(sport, game, bet_type, player, price, pick) -> [(side, call)]; calls without derivable labels are skipped."""
    index = {}
    for c in calls:
        i = c.get("ident")
        if not i or not i.get("labels"):
            continue
        game = "%s @ %s" % (i.get("away", ""), i.get("home", ""))
        for side, col in ((0, "price_a"), (1, "price_b")):
            price = i.get(col)
            if not nfl_wpl._is_real(price) or price == 0:
                continue
            bt = "%s|%d|%s" % (i.get("market", ""), side, i.get("sgp", "") or "")
            key = (i["sport"], game, bt, i.get("player", "") or "", int(price), i["labels"][side])
            index.setdefault(key, []).append((side, c))
    return index


def attach(rows, calls):
    """Bind each priced row to captured outcome mass through selection identity, then verify numerically."""
    index = _selection_index(calls)
    for o in rows:
        o.update(UNAVAIL, wpl_status="UNAVAILABLE: no selection-bound simulator call")
        side, price = _side(o), o.get("price")
        if side is None or not nfl_wpl._is_real(price):
            o["wpl_status"] = "UNAVAILABLE: row side/price invalid"
            continue
        key = (o.get("sport"), o.get("game"), o.get("bet_type"), o.get("player", "") or "", int(price), o.get("pick"))
        cands = [c for s, c in index.get(key, []) if s == side]
        if not cands:
            continue
        masses = {(c["w"], c["l"], c["push"]) for c in cands}
        if len(masses) != 1:
            o["wpl_status"] = "UNAVAILABLE: %d different outcome masses for one selection identity" % len(masses)
            continue
        w, l, push = masses.pop()
        a, b = (w, l) if side == 0 else (l, w)
        if not _reproduces(w, l, side, price, o):
            o["wpl_status"] = "UNAVAILABLE: identity-bound mass does not reproduce the row's model_p/ev"
            continue
        if push is None:
            o["wpl_status"] = "UNAVAILABLE: push mass not provable (%s)" % cands[0]["kind"]
            continue
        if min(a, push, b) < 0.0 or not all(math.isfinite(x) for x in (a, push, b)) or abs(a + push + b - 1.0) > 1e-9:
            o["wpl_status"] = "UNAVAILABLE: mass invalid or not normalised"
            continue
        o.update(p_win=a, p_push=push, p_loss=b, wpl_status="CAPTURED",
                 wpl_source=",".join(sorted({c["src"] for c in cands})), wpl_binding="selection_identity")
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
    """Reject, BEFORE v5 runs, any NFL row with invalid American odds (v5 truncates them with int()) or a line
    that %g cannot represent exactly (two lines such as 44 and 44.00001 would print as the same label)."""
    bad, bad_lines = [], []
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
            if r.get("line"):
                try:
                    ln = v5.num(r["line"])
                except ValueError:
                    ln = None
                if ln is None or not _exact_g(ln):
                    bad_lines.append("line %d line=%r" % (i, r["line"]))
    if bad:
        raise ValueError("invalid American odds on NFL rows: " + "; ".join(bad[:20]))
    if bad_lines:
        raise ValueError("non-canonical line on NFL rows: " + "; ".join(bad_lines[:20]))


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
