#!/usr/bin/env python3
"""Walk-forward NFL player-prop variance calibration on public nflverse weekly stats.

Question: how wide is the real outcome distribution around a pre-game point forecast,
and do the fixed SD fractions used by SportsEdge prop pricing (e.g. CFB PROP_SD_FRAC)
produce calibrated over/under probabilities? NFL only; CFB must be fitted separately.

Point forecast: EWMA (alpha=0.35) of the player's PRIOR games only (strict time order,
regular + post season, no same-week or future data), after >= MIN_PRIOR prior eligible
games. Eligibility (role filter) also uses prior games only.

Fit on TRAIN seasons, evaluate on untouched HOLDOUT seasons:
  * fixed fraction:   sd = frac * f          (frac from SportsEdge constants)
  * fitted power law: sd = a * f**b          (least squares on log |resid| moments, train only)
  * empirical ratio:  P(Y > L) from the train distribution of Y/f in forecast-size bins
Proxy lines: no historical prop lines are available, so thresholds are set at
f*(1+d) rounded to .5 for d in {-0.25,-0.10,0,+0.10,+0.25}. This measures calibration of
the distribution, NOT edge vs a sportsbook. Non-participation is not observed (nflverse
rows exist only for players with stats), so DNP risk is excluded and real variance is
understated, not overstated.
PAPER / research only.
"""
from __future__ import annotations
import argparse, csv, gzip, json, math, sys
from collections import defaultdict
from statistics import NormalDist

ALPHA, MIN_PRIOR = 0.35, 3
STATS = {  # stat -> (column, opportunity column, min opportunities for eligibility)
    "pass_yds": ("passing_yards", "attempts", 15),
    "rush_yds": ("rushing_yards", "carries", 5),
    "rec_yds": ("receiving_yards", "targets", 3),
    "receptions": ("receptions", "targets", 3),
}
CURRENT_FRAC = {"pass_yds": 0.28, "rush_yds": 0.45, "rec_yds": 0.50, "receptions": 0.40}
DELTAS = (-0.25, -0.10, 0.0, 0.10, 0.25)
N = NormalDist()


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def load(paths):
    rows = []
    for p in paths:
        with gzip.open(p, "rt", newline="") as f:
            for r in csv.DictReader(f):
                st = (r.get("season_type") or "").upper()
                if st not in ("REG", "POST"):
                    continue
                rows.append(r)
    return rows


def forecasts(rows):
    """Yield (season, stat, f, y) with f from strictly prior eligible games."""
    by = defaultdict(list)
    for r in rows:
        pid = r.get("player_id")
        s, w = num(r.get("season")), num(r.get("week"))
        if not pid or s is None or w is None:
            continue
        by[pid].append((int(s), int(w), 1 if r["season_type"].upper() == "POST" else 0, r))
    out = []
    for pid, games in by.items():
        games.sort(key=lambda g: (g[0], g[1]))
        keys = [(g[0], g[1]) for g in games]
        if len(keys) != len(set(keys)):
            continue  # duplicate player-week rows: refuse rather than guess
        for stat, (col, opp, mn) in STATS.items():
            ew, n = None, 0
            for s, w, _, r in games:
                y, o = num(r.get(col)), num(r.get(opp))
                if y is None or o is None:
                    continue
                if n >= MIN_PRIOR and ew is not None and ew > 0 and o >= mn:
                    out.append((s, stat, ew, y))
                if o >= mn:  # update only from eligible-role games
                    ew = y if ew is None else ALPHA * y + (1 - ALPHA) * ew
                    n += 1
    return out


def fit_power(train):
    """sd = a f^b via regression of log(resid^2) on log f, with lognormal bias correction."""
    xs, ys = [], []
    for f, y in train:
        r2 = (y - f) ** 2
        if f > 0 and r2 > 0:
            xs.append(math.log(f)); ys.append(math.log(r2))
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    b2 = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    c = my - b2 * mx
    # E[log r^2] = log var + E[log chi2_1] (= -1.2704); undo that bias
    a2 = math.exp(c + 1.2704)
    a, b = math.sqrt(a2), b2 / 2
    return a, b


def ratio_bins(train, edges=(0, 10, 25, 50, 100, 200, 1e9)):
    bins = defaultdict(list)
    for f, y in train:
        for lo, hi in zip(edges, edges[1:]):
            if lo <= f < hi:
                bins[(lo, hi)].append(y / f); break
    return {k: sorted(v) for k, v in bins.items() if len(v) >= 200}


def p_over_ratio(bins, f, line):
    for (lo, hi), v in bins.items():
        if lo <= f < hi:
            t = line / f
            # count of ratios strictly above t (continuous-ish; lines are .5 so ties are rare)
            import bisect
            return (len(v) - bisect.bisect_right(v, t) + 0.5) / (len(v) + 1)
    return None


def score(pairs):
    """pairs: (p, outcome). Brier, log loss, and 10-bin reliability."""
    eps = 1e-6
    n = len(pairs)
    br = sum((p - o) ** 2 for p, o in pairs) / n
    ll = -sum(o * math.log(max(p, eps)) + (1 - o) * math.log(max(1 - p, eps)) for p, o in pairs) / n
    rel = defaultdict(lambda: [0, 0.0, 0])
    for p, o in pairs:
        k = min(int(p * 10), 9); rel[k][0] += 1; rel[k][1] += p; rel[k][2] += o
    ece = sum(abs(s / c - h / c) * c for c, s, h in rel.values()) / n
    table = {f"{k/10:.1f}-{(k+1)/10:.1f}": {"n": c, "pred": round(s / c, 3), "obs": round(h / c, 3)}
             for k, (c, s, h) in sorted(rel.items())}
    return {"n": n, "brier": round(br, 5), "logloss": round(ll, 5), "ece": round(ece, 4), "reliability": table}


def evaluate(test, sd_fn=None, bins=None):
    pairs = []
    for f, y in test:
        for d in DELTAS:
            line = math.floor(f * (1 + d)) + 0.5
            if line <= 0:
                continue
            if bins is not None:
                p = p_over_ratio(bins, f, line)
                if p is None:
                    continue
            else:
                p = 1 - NormalDist(f, max(1.0, sd_fn(f))).cdf(line)
            pairs.append((min(max(p, 1e-6), 1 - 1e-6), 1 if y > line else 0))
    return score(pairs)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--train", default="2018-2022")
    ap.add_argument("--holdout", default="2023-2025")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    tr = range(int(a.train.split("-")[0]), int(a.train.split("-")[1]) + 1)
    ho = range(int(a.holdout.split("-")[0]), int(a.holdout.split("-")[1]) + 1)
    fc = forecasts(load(a.files))
    report = {"schema": "sportsedge-nfl-prop-variance-v1", "alpha": ALPHA, "min_prior": MIN_PRIOR,
              "train_seasons": list(tr), "holdout_seasons": list(ho), "status": "PAPER_RESEARCH_ONLY",
              "line_source": "PROXY_LINES_NOT_SPORTSBOOK", "stats": {}}
    for stat in STATS:
        train = [(f, y) for s, st, f, y in fc if st == stat and s in tr]
        test = [(f, y) for s, st, f, y in fc if st == stat and s in ho]
        if len(train) < 500 or len(test) < 200:
            report["stats"][stat] = {"state": "INSUFFICIENT_SAMPLE", "train": len(train), "test": len(test)}
            continue
        a_, b_ = fit_power(train)
        mae = sum(abs(y - f) for f, y in test) / len(test)
        rmse = math.sqrt(sum((y - f) ** 2 for f, y in test) / len(test))
        mean_f = sum(f for f, _ in test) / len(test)
        bins = ratio_bins(train)
        frac = CURRENT_FRAC[stat]
        report["stats"][stat] = {
            "train_n": len(train), "holdout_n": len(test),
            "holdout_mean_forecast": round(mean_f, 2), "holdout_mae": round(mae, 2), "holdout_rmse": round(rmse, 2),
            "holdout_signed_bias_y_minus_f": round(sum(y - f for f, y in test) / len(test), 2),
            "current_frac": frac, "implied_frac_at_mean": round(rmse / mean_f, 3),
            "power_fit": {"a": round(a_, 4), "b": round(b_, 4)},
            "fixed_frac": evaluate(test, lambda f: frac * f),
            "power_law_normal": evaluate(test, lambda f: a_ * f ** b_),
            "empirical_ratio": evaluate(test, bins=bins),
        }
    js = json.dumps(report, indent=1)
    if a.out:
        open(a.out, "w").write(js)
    print(js)


if __name__ == "__main__":
    sys.exit(main())
