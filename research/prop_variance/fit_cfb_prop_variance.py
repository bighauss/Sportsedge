#!/usr/bin/env python3
"""Walk-forward CFB player-prop variance calibration (CFB-specific; no NFL coefficients).

Source: public sportsdataverse/cfbfastR-data `player_stats/csv/player_stats_<season>.csv`
(play-level player attributions). Aggregated here to player-game totals:
  pass_yds/attempts: completion_yds by passer; attempts = completions + incompletions +
                     interceptions thrown (sacks excluded)
  rush_yds/carries:  rush_yds by rusher
  rec_yds/receptions/targets: reception_yds by receiver; targets = receptions + target rows
Rows are de-duplicated by (play_id, role). PBP-derived totals can differ from official box
scores (missing or penalty-nullified plays), so treat this as research data.

Question: are the pinned CFB PROP_SD_FRAC normal distributions calibrated around a
pre-game point forecast? Forecast = EWMA(alpha 0.35) of the player's PRIOR eligible games
only (strict season/week/game order), after >= 3 of them. Fit on TRAIN seasons only and
score on untouched HOLDOUT seasons. Proxy lines f*(1+d) rounded to .5; these are NOT
sportsbook lines, so this measures distribution calibration, not edge. Non-participation
is unobserved. PAPER research only.
"""
from __future__ import annotations
import argparse, bisect, csv, json, math, os, sys
from collections import defaultdict
from statistics import NormalDist

ALPHA, MIN_PRIOR = 0.35, 3
ELIG = {"pass_yds": ("attempts", 15), "rush_yds": ("carries", 5),
        "rec_yds": ("targets", 3), "receptions": ("targets", 3)}
# Pinned CFB model constants (models/cfb/sportsedge_cfb_model.py PROP_SD_FRAC), not refit here.
CFB_PINNED_FRAC = {"rush_yds": 0.45, "rec_yds": 0.50, "pass_yds": 0.28, "receptions": 0.40}
DELTAS = (-0.25, -0.10, 0.0, 0.10, 0.25)


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def aggregate(path):
    """Return {(season, week, game_id, player_id): totals dict} from one play-level CSV."""
    g = defaultdict(lambda: defaultdict(float))
    seen = set()
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            s, w, gid, pid = num(r.get("season")), num(r.get("week")), r.get("game_id"), r.get("play_id")
            if s is None or w is None or not gid or not pid:
                continue
            base = (int(s), int(w), gid)

            def add(role, who, **vals):
                p = r.get(who + "_player_id")
                if not p or p == "NA" or (pid, role, p) in seen:
                    return
                seen.add((pid, role, p))
                t = g[base + (p,)]
                for k, v in vals.items():
                    t[k] += v
            cy = num(r.get("completion_yds"))
            if cy is not None:
                add("cmp", "completion", pass_yds=cy, attempts=1)
            add("inc", "incompletion", attempts=1)
            add("int", "interception_thrown", attempts=1)
            ry = num(r.get("rush_yds"))
            if ry is not None:
                add("rush", "rush", rush_yds=ry, carries=1)
            rec = num(r.get("reception_yds"))
            if rec is not None:
                add("rec", "reception", rec_yds=rec, receptions=1, targets=1)
            add("tgt", "target", targets=1)
    return g


def forecasts(games):
    """games: {(season, week, game_id, player): totals}. Yield (season, stat, f, y)."""
    by = defaultdict(list)
    for (s, w, gid, p), t in games.items():
        by[p].append((s, w, gid, t))
    out = []
    for p, rows in by.items():
        rows.sort(key=lambda x: (x[0], x[1], x[2]))
        keys = [(s, w) for s, w, _, _ in rows]
        if len(keys) != len(set(keys)):
            continue  # two games for one player in one week: refuse rather than guess
        for stat, (opp, mn) in ELIG.items():
            ew, n = None, 0
            for s, w, gid, t in rows:
                y, o = t.get(stat, 0.0), t.get(opp, 0.0)
                if o < mn:
                    continue  # ineligible role game: neither scored nor used to update
                if n >= MIN_PRIOR and ew is not None and ew > 0:
                    out.append((s, stat, ew, y))
                ew = y if ew is None else ALPHA * y + (1 - ALPHA) * ew
                n += 1
    return out


def fit_power(train):
    xs, ys = [], []
    for f, y in train:
        r2 = (y - f) ** 2
        if f > 0 and r2 > 0:
            xs.append(math.log(f)); ys.append(math.log(r2))
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    b2 = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a2 = math.exp(my - b2 * mx + 1.2704)  # undo E[log chi2_1] bias
    return math.sqrt(a2), b2 / 2


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
            return (len(v) - bisect.bisect_right(v, line / f) + 0.5) / (len(v) + 1)
    return None


def score(pairs):
    eps, n = 1e-6, len(pairs)
    br = sum((p - o) ** 2 for p, o in pairs) / n
    ll = -sum(o * math.log(max(p, eps)) + (1 - o) * math.log(max(1 - p, eps)) for p, o in pairs) / n
    rel = defaultdict(lambda: [0, 0.0, 0])
    for p, o in pairs:
        k = min(int(p * 10), 9); rel[k][0] += 1; rel[k][1] += p; rel[k][2] += o
    ece = sum(abs(s - h) for c, s, h in rel.values()) / n
    return {"n": n, "brier": round(br, 5), "logloss": round(ll, 5), "ece": round(ece, 4)}


def evaluate(test, sd_fn=None, bins=None):
    pairs, by_d = [], defaultdict(lambda: [0, 0.0, 0])
    for f, y in test:
        for d in DELTAS:
            line = math.floor(f * (1 + d)) + 0.5
            if line <= 0:
                continue
            p = p_over_ratio(bins, f, line) if bins is not None else 1 - NormalDist(f, max(1.0, sd_fn(f))).cdf(line)
            if p is None:
                continue
            p = min(max(p, 1e-6), 1 - 1e-6); o = 1 if y > line else 0
            pairs.append((p, o)); b = by_d[d]; b[0] += 1; b[1] += p; b[2] += o
    out = score(pairs)
    out["p_over_bias_by_line"] = {f"{1 + d:.2f}f": round((s - h) / c, 4) for d, (c, s, h) in sorted(by_d.items())}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="folder with player_stats_<season>.csv")
    ap.add_argument("--train", default="2014-2021")
    ap.add_argument("--holdout", default="2022-2025")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    t0, t1 = map(int, a.train.split("-")); h0, h1 = map(int, a.holdout.split("-"))
    games = {}
    for s in range(t0, h1 + 1):
        p = os.path.join(a.dir, f"player_stats_{s}.csv")
        if os.path.exists(p):
            games.update(aggregate(p))
    fc = forecasts(games)
    rep = {"schema": "sportsedge-cfb-prop-variance-v1", "alpha": ALPHA, "min_prior": MIN_PRIOR,
           "train": [t0, t1], "holdout": [h0, h1], "line_source": "PROXY_LINES_NOT_SPORTSBOOK",
           "status": "PAPER_RESEARCH_ONLY", "player_games": len(games), "stats": {}}
    for stat in ELIG:
        train = [(f, y) for s, st, f, y in fc if st == stat and t0 <= s <= t1]
        test = [(f, y) for s, st, f, y in fc if st == stat and h0 <= s <= h1]
        if len(train) < 500 or len(test) < 200:
            rep["stats"][stat] = {"state": "INSUFFICIENT_SAMPLE", "train": len(train), "test": len(test)}
            continue
        a_, b_ = fit_power(train)
        mf = sum(f for f, _ in test) / len(test)
        rmse = math.sqrt(sum((y - f) ** 2 for f, y in test) / len(test))
        frac = CFB_PINNED_FRAC[stat]
        rep["stats"][stat] = {
            "train_n": len(train), "holdout_n": len(test), "holdout_mean_forecast": round(mf, 2),
            "holdout_mae": round(sum(abs(y - f) for f, y in test) / len(test), 2),
            "holdout_rmse": round(rmse, 2),
            "holdout_signed_bias_y_minus_f": round(sum(y - f for f, y in test) / len(test), 2),
            "holdout_median_ratio": round(sorted(y / f for f, y in test)[len(test) // 2], 3),
            "pinned_frac": frac, "implied_frac_at_mean": round(rmse / mf, 3),
            "power_fit_train": {"a": round(a_, 4), "b": round(b_, 4)},
            "pinned_fixed_frac_normal": evaluate(test, lambda f: frac * f),
            "train_power_law_normal": evaluate(test, lambda f: a_ * f ** b_),
            "train_empirical_ratio": evaluate(test, bins=ratio_bins(train)),
        }
    js = json.dumps(rep, indent=1)
    if a.out:
        open(a.out, "w").write(js)
    print(js)


if __name__ == "__main__":
    sys.exit(main())
