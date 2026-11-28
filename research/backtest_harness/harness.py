#!/usr/bin/env python3
"""SportsEdge market-comparison + selection-bias backtest harness (PAPER research only).

Input CSV, one row per priced selection, all prices captured PREGAME:
  event_id, date, market, selection, line, model_p, push_p, price, opp_price, outcome[, close_price, close_opp_price]
  model_p  = model P(win) (unconditional), push_p = model P(push) (0 if half-point)
  price/opp_price = DraftKings American odds for this side and the opposite side
  outcome  = W / L / P (V = void, dropped and counted)

Outputs (JSON):
  * scoring on decided rows: Brier, log loss, ECE for model (conditional on no push) vs no-vig market
  * paired log-loss and Brier difference (model - market) with a BLOCK bootstrap CI;
    blocks = event_id by default (or date), so same-game selections are not independent
  * flat-stake ROI and max drawdown for selections with EV > threshold
  * CLV diagnostic when close prices are present (not proof of profit)
  * selection-bias null: shuffle model_p within market (breaks model-outcome link but keeps
    the EV distribution), pick top-k by EV, repeat; report observed top-k EV net of the
    null's expected max fake edge, and realized ROI vs the null's
  * minimum detectable ROI given n, effective n under clustering, alpha .05, power .80
"""
from __future__ import annotations
import argparse, csv, json, math, random, sys
from collections import defaultdict

EPS = 1e-6


def dec(a):
    a = float(a)
    if not math.isfinite(a) or abs(a) < 100 or not a.is_integer():
        raise ValueError("INVALID_AMERICAN_ODDS")
    return 1 + a / 100 if a > 0 else 1 + 100 / -a


def imp(a):
    return 1 / dec(a)


def novig(a, b):
    x, y = imp(a), imp(b)
    return x / (x + y)


class Row:
    __slots__ = ("event", "date", "market", "sel", "line", "p", "push", "price", "opp", "out",
                 "close", "close_opp", "q")


def load(path):
    rows, rejected = [], defaultdict(int)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                x = Row()
                x.event, x.date, x.market, x.sel = r["event_id"], r.get("date", ""), r["market"], r["selection"]
                x.line = r.get("line", "")
                x.p = float(r["model_p"]); x.push = float(r.get("push_p") or 0)
                if not (0 <= x.p <= 1 and 0 <= x.push < 1 and x.p + x.push <= 1 + 1e-9):
                    raise ValueError("INVALID_PROBABILITY")
                x.price, x.opp = int(float(r["price"])), int(float(r["opp_price"]))
                x.q = novig(x.price, x.opp)
                x.out = r["outcome"].strip().upper()
                if x.out not in ("W", "L", "P", "V"):
                    raise ValueError("INVALID_OUTCOME")
                c, co = r.get("close_price"), r.get("close_opp_price")
                x.close = int(float(c)) if c not in (None, "") else None
                x.close_opp = int(float(co)) if co not in (None, "") else None
            except (KeyError, ValueError, TypeError) as e:
                rejected[str(e).split(":")[0][:40] or "INVALID_ROW"] += 1
                continue
            rows.append(x)
    keys = [(x.event, x.market, x.sel, x.line) for x in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_SELECTION_ROWS")
    return rows, dict(rejected)


def ev(x):
    return x.p * (dec(x.price) - 1) - (1 - x.p - x.push)


def cond_p(x):
    d = 1 - x.push
    return min(max(x.p / d, EPS), 1 - EPS) if d > 0 else 0.5


def score(pairs):
    n = len(pairs)
    if not n:
        return None
    br = sum((p - o) ** 2 for p, o in pairs) / n
    ll = -sum(o * math.log(max(p, EPS)) + (1 - o) * math.log(max(1 - p, EPS)) for p, o in pairs) / n
    bins = defaultdict(lambda: [0, 0.0, 0])
    for p, o in pairs:
        b = bins[min(int(p * 10), 9)]; b[0] += 1; b[1] += p; b[2] += o
    ece = sum(abs(s - h) for c, s, h in bins.values()) / n
    return {"n": n, "brier": br, "logloss": ll, "ece": ece}


def _ll(p, o):
    return -(o * math.log(max(p, EPS)) + (1 - o) * math.log(max(1 - p, EPS)))


def block_bootstrap(diffs_by_block, reps=2000, seed=7):
    blocks = list(diffs_by_block.values())
    rng = random.Random(seed)
    tot_n = sum(len(b) for b in blocks)
    point = sum(sum(b) for b in blocks) / tot_n
    stats = []
    for _ in range(reps):
        s = n = 0
        for _ in range(len(blocks)):
            b = blocks[rng.randrange(len(blocks))]; s += sum(b); n += len(b)
        stats.append(s / n)
    stats.sort()
    return {"mean": point, "ci95": [stats[int(.025 * reps)], stats[int(.975 * reps) - 1]], "blocks": len(blocks)}


def returns(rows):
    r = []
    for x in rows:
        if x.out == "W":
            r.append(dec(x.price) - 1)
        elif x.out == "L":
            r.append(-1.0)
        elif x.out == "P":
            r.append(0.0)
    return r


def roi_dd(rows):
    r = returns(rows)
    if not r:
        return {"n": 0}
    eq = peak = dd = 0.0
    for v in r:
        eq += v; peak = max(peak, eq); dd = max(dd, peak - eq)
    return {"n": len(r), "units": eq, "roi": eq / len(r), "max_drawdown_u": dd}


def clv(rows):
    v = [novig(x.close, x.close_opp) * dec(x.price) - 1 for x in rows if x.close is not None and x.close_opp is not None]
    return {"n": len(v), "mean_clv_ev": sum(v) / len(v)} if v else {"n": 0}


def selection_null(rows, k, reps=500, seed=11):
    """Top-k by EV under shuffled model_p within market (zero true edge by construction)."""
    rng = random.Random(seed)
    obs = sorted(rows, key=ev, reverse=True)[:k]
    obs_ev = sum(ev(x) for x in obs) / len(obs)
    obs_roi = roi_dd(obs).get("roi")
    by_m = defaultdict(list)
    for x in rows:
        by_m[x.market].append(x)
    null_ev, null_roi = [], []
    for _ in range(reps):
        shuffled = []
        for xs in by_m.values():
            ps = [(x.p, x.push) for x in xs]; rng.shuffle(ps)
            for x, (p, pu) in zip(xs, ps):
                y = Row()
                for s in Row.__slots__:
                    setattr(y, s, getattr(x, s))
                y.p, y.push = p, pu
                if y.p + y.push > 1:
                    y.p = 1 - y.push
                shuffled.append(y)
        top = sorted(shuffled, key=ev, reverse=True)[:k]
        null_ev.append(sum(ev(x) for x in top) / k)
        rr = roi_dd(top).get("roi")
        if rr is not None:
            null_roi.append(rr)
    ne = sum(null_ev) / reps
    out = {"k": k, "M": len(rows), "observed_topk_mean_ev": obs_ev, "null_expected_topk_ev": ne,
           "ev_net_of_selection_bias": obs_ev - ne, "observed_topk_roi": obs_roi,
           "null_topk_roi_mean": sum(null_roi) / len(null_roi) if null_roi else None}
    if null_roi and obs_roi is not None:
        out["p_value_roi_vs_null"] = (1 + sum(r >= obs_roi for r in null_roi)) / (1 + len(null_roi))
    return out


def mde(rows, block_key):
    """Minimum detectable ROI (alpha .05 two-sided, power .80) with clustering design effect."""
    r = returns(rows)
    n = len(r)
    if n < 2:
        return {"n": n}
    m = sum(r) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in r) / (n - 1))
    groups = defaultdict(list)
    for x, v in zip([x for x in rows if x.out in ("W", "L", "P")], r):
        groups[block_key(x)].append(v)
    # one-way ANOVA estimate of intra-block correlation
    g = len(groups); mbar = n / g
    if g > 1 and mbar > 1:
        msb = sum(len(v) * (sum(v) / len(v) - m) ** 2 for v in groups.values()) / (g - 1)
        msw = sum(sum((u - sum(v) / len(v)) ** 2 for u in v) for v in groups.values()) / max(n - g, 1)
        icc = max(0.0, (msb - msw) / (msb + (mbar - 1) * msw)) if (msb + (mbar - 1) * msw) > 0 else 0.0
    else:
        icc = 0.0
    deff = 1 + (mbar - 1) * icc
    neff = n / deff
    return {"n": n, "blocks": g, "icc": icc, "design_effect": deff, "n_effective": neff,
            "sd_per_bet_u": sd, "mde_roi": (1.96 + 0.8416) * sd / math.sqrt(neff)}


def run(rows, k=20, ev_threshold=0.0, block="event", reps=2000):
    key = (lambda x: x.event) if block == "event" else (lambda x: x.date)
    dec_rows = [x for x in rows if x.out in ("W", "L")]
    mp = [(cond_p(x), 1 if x.out == "W" else 0) for x in dec_rows]
    qp = [(min(max(x.q, EPS), 1 - EPS), 1 if x.out == "W" else 0) for x in dec_rows]
    dll, dbr = defaultdict(list), defaultdict(list)
    for x, (p, o), (q, _) in zip(dec_rows, mp, qp):
        dll[key(x)].append(_ll(p, o) - _ll(q, o)); dbr[key(x)].append((p - o) ** 2 - (q - o) ** 2)
    picked = [x for x in rows if ev(x) > ev_threshold]
    return {
        "schema": "sportsedge-backtest-harness-v1", "status": "PAPER_RESEARCH_ONLY",
        "rows": len(rows), "voids": sum(x.out == "V" for x in rows), "block": block,
        "model": score(mp), "market_novig": score(qp),
        "paired_logloss_model_minus_market": block_bootstrap(dll, reps) if dll else None,
        "paired_brier_model_minus_market": block_bootstrap(dbr, reps) if dbr else None,
        "flat_stake_ev_gt_threshold": {"threshold": ev_threshold, **roi_dd(picked)},
        "clv_diagnostic": clv(picked),
        "selection_bias": selection_null(rows, min(k, len(rows))) if rows else None,
        "power": mde(picked or rows, key),
        "interpretation": "Negative paired difference = model scores better than no-vig market. "
                          "CLV is a diagnostic, not proof. PAPER / 0u.",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--ev-threshold", type=float, default=0.0)
    ap.add_argument("--block", choices=("event", "date"), default="event")
    ap.add_argument("--reps", type=int, default=2000)
    a = ap.parse_args(argv)
    rows, rejected = load(a.csv)
    out = run(rows, a.k, a.ev_threshold, a.block, a.reps)
    out["rejected_rows"] = rejected
    print(json.dumps(out, indent=1, default=lambda v: round(v, 6) if isinstance(v, float) else v))


if __name__ == "__main__":
    sys.exit(main())
