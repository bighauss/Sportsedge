"""Shared statistics: calibration (P1.3), performance & drawdown (P1.5), bootstrap,
streaks, Wilson CIs, variance tests (Theo 21, 31, 43, 45; Rusty T1#5, T2#2,#3,#8).
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Callable, Iterable, Sequence

from .odds import american_to_decimal

EPS = 1e-12


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def brier(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)


def log_loss(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    return -sum(o * math.log(max(p, EPS)) + (1 - o) * math.log(max(1 - p, EPS))
                for p, o in zip(probs, outcomes)) / len(probs)


def calibration_table(probs, outcomes, edges=None, min_n: int = 30) -> list[dict]:
    """Bucket predictions (default 5% buckets) → observed rate, Wilson CI, verdict."""
    edges = edges or [i / 20 for i in range(21)]
    rows = []
    for lo, hi in zip(edges, edges[1:]):
        idx = [i for i, p in enumerate(probs) if lo <= p < hi or (hi == 1 and p == 1)]
        if not idx:
            continue
        n = len(idx)
        k = sum(outcomes[i] for i in idx)
        mp = sum(probs[i] for i in idx) / n
        ci = wilson(k, n)
        verdict = ("SMALL_SAMPLE" if n < min_n else
                   "OVERCONFIDENT" if mp > ci[1] else
                   "UNDERCONFIDENT" if mp < ci[0] else "OK")
        rows.append({"bucket": f"{lo:.0%}-{hi:.0%}", "n": n, "mean_pred": mp,
                     "observed": k / n, "ci_lo": ci[0], "ci_hi": ci[1], "verdict": verdict})
    return rows


def ece(probs, outcomes, bins: int = 10) -> float:
    tot = len(probs)
    err = 0.0
    for b in range(bins):
        idx = [i for i, p in enumerate(probs) if b / bins <= p < (b + 1) / bins or (b == bins - 1 and p == 1)]
        if idx:
            err += len(idx) / tot * abs(sum(probs[i] for i in idx) / len(idx)
                                        - sum(outcomes[i] for i in idx) / len(idx))
    return err


def reliability_svg(table: list[dict], size: int = 320) -> str:
    """Reliability diagram as standalone SVG (phone-viewable)."""
    pad = 30
    s = size - 2 * pad
    pts = "".join(
        f'<circle cx="{pad + r["mean_pred"] * s:.1f}" cy="{pad + (1 - r["observed"]) * s:.1f}" '
        f'r="{3 + min(8, r["n"] ** .5 / 3):.1f}" fill="#2dd4bf"/>' for r in table)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'style="background:#0b1020"><line x1="{pad}" y1="{pad + s}" x2="{pad + s}" y2="{pad}" '
            f'stroke="#555" stroke-dasharray="4"/><rect x="{pad}" y="{pad}" width="{s}" height="{s}" '
            f'fill="none" stroke="#888"/>{pts}<text x="{pad}" y="{size - 8}" fill="#aaa" '
            f'font-size="11">predicted →  (y: observed)</text></svg>')


def platt_fit(probs, outcomes, iters: int = 2000, lr: float = 0.05) -> tuple[float, float]:
    """Recommend-only recalibration: logit(p') = a*logit(p) + b. Fit on HOLDOUT only."""
    a, b = 1.0, 0.0
    xs = [math.log(max(p, EPS) / max(1 - p, EPS)) for p in probs]
    n = len(xs)
    for _ in range(iters):
        ga = gb = 0.0
        for x, y in zip(xs, outcomes):
            q = 1 / (1 + math.exp(-(a * x + b)))
            ga += (q - y) * x
            gb += q - y
        a -= lr * ga / n
        b -= lr * gb / n
    return a, b


def bet_profit(bet: dict) -> float:
    """Net units for a graded bet. result in {W,L,P,V}; stake default 1 (flat baseline)."""
    stake = float(bet.get("stake", 1.0))
    r = bet["result"]
    if r == "W":
        return stake * (american_to_decimal(float(bet["odds"])) - 1)
    if r == "L":
        return -stake
    return 0.0


def performance(bets: Sequence[dict], flat: bool = True) -> dict:
    """Win rate, ROI, units, max drawdown, longest losing streak. Never drops losers."""
    graded = [b for b in bets if b.get("result") in ("W", "L", "P", "V")]
    ungraded = len(bets) - len(graded)
    if flat:
        graded = [{**b, "stake": 1.0} for b in graded]
    profits = [bet_profit(b) for b in graded]
    risked = sum(float(b.get("stake", 1)) for b in graded if b["result"] in ("W", "L"))
    w = sum(b["result"] == "W" for b in graded)
    l = sum(b["result"] == "L" for b in graded)
    cum = peak = mdd = 0.0
    streak = longest = 0
    curve = []
    for b, p in zip(graded, profits):
        cum += p
        curve.append(cum)
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
        streak = streak + 1 if b["result"] == "L" else (streak if b["result"] in "PV" else 0)
        longest = max(longest, streak)
    sd = (sum((p - sum(profits) / len(profits)) ** 2 for p in profits) / max(1, len(profits) - 1)) ** .5 if profits else 0
    return {"n": len(graded), "ungraded": ungraded, "wins": w, "losses": l,
            "pushes": len(graded) - w - l, "win_rate": w / (w + l) if w + l else None,
            "win_rate_ci": wilson(w, w + l), "units": cum, "risked": risked,
            "roi": cum / risked if risked else None, "max_drawdown": mdd,
            "longest_losing_streak": longest,
            "sharpe_per_bet": (sum(profits) / len(profits)) / sd if sd else None,
            "curve": curve}


def bootstrap_roi(bets: Sequence[dict], iters: int = 5000, cluster_key: str | None = "game_id",
                  seed: int = 7) -> dict:
    """Cluster bootstrap (resample whole games) so correlated bets aren't counted as independent.

    Returns ROI CI, drawdown CI and P(ROI <= 0) — the chance profit is just variance.
    """
    rng = random.Random(seed)
    graded = [{**b, "stake": 1.0} for b in bets if b.get("result") in ("W", "L", "P", "V")]
    groups = defaultdict(list)
    for i, b in enumerate(graded):
        groups[b.get(cluster_key, i) if cluster_key else i].append(b)
    keys = list(groups)
    rois, mdds = [], []
    for _ in range(iters):
        sample = [b for k in (rng.choice(keys) for _ in keys) for b in groups[k]]
        p = performance(sample)
        if p["roi"] is not None:
            rois.append(p["roi"])
            mdds.append(p["max_drawdown"])
    rois.sort()
    mdds.sort()
    q = lambda xs, a: xs[min(len(xs) - 1, int(a * len(xs)))]
    return {"clusters": len(keys), "n_bets": len(graded), "roi_ci95": (q(rois, .025), q(rois, .975)),
            "roi_median": q(rois, .5), "p_roi_le_0": sum(r <= 0 for r in rois) / len(rois),
            "max_dd_ci95": (q(mdds, .025), q(mdds, .975))}


def streak_probability(win_rate: float, streak: int, n_bets: int, losing: bool = True,
                       iters: int = 20000, seed: int = 3) -> float:
    rng = random.Random(seed)
    p = 1 - win_rate if losing else win_rate
    hits = 0
    for _ in range(iters):
        run = 0
        for _ in range(n_bets):
            run = run + 1 if rng.random() < p else 0
            if run >= streak:
                hits += 1
                break
    return hits / iters


def bankroll_sim(p_win: float, odds: float, stake_frac: float, n_bets: int = 500,
                 iters: int = 5000, ruin_level: float = 0.2, seed: int = 11,
                 true_p: float | None = None) -> dict:
    """Bankroll stress test (Theo 20/21). true_p lets you test 'edge is half what I think'."""
    rng = random.Random(seed)
    dec = american_to_decimal(odds)
    tp = true_p if true_p is not None else p_win
    finals, ruins, mdds = [], 0, []
    for _ in range(iters):
        br, peak, mdd = 1.0, 1.0, 0.0
        for _ in range(n_bets):
            s = br * stake_frac
            br += s * (dec - 1) if rng.random() < tp else -s
            peak = max(peak, br)
            mdd = max(mdd, 1 - br / peak)
        finals.append(br)
        mdds.append(mdd)
        ruins += br < ruin_level
    finals.sort()
    mdds.sort()
    return {"median_final": finals[len(finals) // 2], "p5_final": finals[len(finals) // 20],
            "p_ruin": ruins / iters, "median_max_dd": mdds[len(mdds) // 2],
            "p95_max_dd": mdds[int(.95 * len(mdds))]}


def two_proportion_z(k1, n1, k2, n2) -> float:
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) or EPS
    return (k1 / n1 - k2 / n2) / se


def edge_decay(periods: Sequence[tuple[int, int]]) -> dict:
    """periods: [(wins, decisions), ...] in order. Tests first vs last and trend."""
    (k1, n1), (k2, n2) = periods[0], periods[-1]
    z = two_proportion_z(k1, n1, k2, n2)
    return {"z_first_vs_last": z, "significant": abs(z) > 1.96,
            "rates": [k / n if n else None for k, n in periods],
            "verdict": "DECAY_LIKELY" if z > 1.96 else "WITHIN_VARIANCE"}


def group_by(rows: Iterable[dict], key: str | Callable) -> dict:
    out = defaultdict(list)
    for r in rows:
        out[key(r) if callable(key) else r.get(key)].append(r)
    return dict(out)
