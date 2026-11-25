"""CBB multi-season rolling-origin backtest (research only; PAPER / 0u; NON_COUNTED).

Origins: every Monday 00:00 (calendar date) of each season. At an origin O a model is
fit ONLY on admitted finals with game day < O (plus previous-season end ratings as a
preseason prior) and forecasts every game in [O, O+7d). All models are scored on the
IDENTICAL set of rows on which every built-in model produced a forecast.

Predictive SDs (margin/total) are the RMSE of the same model's own earlier forecast
residuals, using only rows whose game day < O (current + previous season), min 300.

Three chronological splits for blend-weight selection, FIXED IN CODE before any run
(see SPLITS): train seasons only warm up residual-SD history; the blend weight is
selected on VALIDATION seasons by mean log loss (never by profit); the selected
weight is then reported once on the untouched TEST seasons.

Blend weights (independent / market), canonical owner grid from the Nov 25 spec:
100/0, 87.5/12.5, 75/25, 62.5/37.5, 50/50, 37.5/62.5, 25/75, 12.5/87.5, 0/100.
Blend: p = w * p_independent + (1 - w) * p_market_novig (probability space). The
independent forecast never sees market data; the market enters only in the blend.
"""
import argparse
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from statistics import mean

from . import models as M
from . import data as D

BLEND_WEIGHTS = (1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0)
BLEND_SOURCE = "Owner spec Nov 25 2026 (t26u item 6): 100/0, 87.5/12.5, 75/25, 62.5/37.5, 50/50, 37.5/62.5, 25/75, 12.5/87.5, 0/100"
SPLITS = {"train": (2019, 2020, 2021), "validation": (2022, 2023, 2024), "test": (2025, 2026)}
MIN_PRIOR_GAMES = 150
MIN_SD_RESIDUALS = 300
FAMILIES = ("ml", "spread", "total")
EPS = 1e-6


# ---------------------------------------------------------------- math
def phi(z):
    return (1 + math.erf(z / math.sqrt(2))) / 2


def line_probs(mu, sd, threshold):
    """(P over threshold, P push, P under); integer thresholds push (native rule)."""
    if float(threshold).is_integer():
        lo, hi = phi((threshold - .5 - mu) / sd), phi((threshold + .5 - mu) / sd)
        return 1 - hi, hi - lo, lo
    b = phi((threshold - mu) / sd)
    return 1 - b, 0.0, b


def dec(american):
    return 1 + (american / 100 if american > 0 else 100 / -american)


def novig(pa, pb):
    if pa is None or pb is None:
        return None
    a, b = 1 / dec(pa), 1 / dec(pb)
    return a / (a + b)


def split_of(season):
    for k, v in SPLITS.items():
        if season in v:
            return k
    return "outside"


# ---------------------------------------------------------------- rolling origin
def origins_for(games):
    days = sorted({g["day"] for g in games})
    if not days:
        return []
    o = days[0] - timedelta(days=days[0].weekday())
    out = []
    while o <= days[-1]:
        out.append(o)
        o += timedelta(days=7)
    return out


def forecast_season(games, carry, model_names, leakage_log):
    rows = []
    for o in origins_for(games):
        window = [g for g in games if o <= g["day"] < o + timedelta(days=7)]
        if not window:
            continue
        prior = [g for g in games if g["day"] < o and g["possessions"] is not None]
        # leakage check 1: nothing on/after origin enters the fit
        leakage_log["origins"] += 1
        if any(g["day"] >= o for g in prior):
            leakage_log["violations"].append(f"prior_after_origin {o}")
        builders = {}
        if len(prior) >= MIN_PRIOR_GAMES:
            oc = dict(carry, _origin=o)
            for name in model_names:
                try:
                    builders[name] = M.MODELS[name](prior, oc)
                except Exception as e:  # abstain, recorded
                    builders[name] = e
        for g in window:
            r = {"event_id": g["event_id"], "season": g["season"], "day": g["day"], "origin": o,
                 "home": g["home"], "away": g["away"], "neutral": g["neutral"],
                 "home_points": g["home_points"], "away_points": g["away_points"],
                 "margin": g["margin"], "total": g["total"], "prior_n": len(prior), "f": {}, "hold": {}}
            for name in model_names:
                b = builders.get(name)
                if b is None:
                    r["hold"][name] = "WARMUP"
                elif isinstance(b, Exception):
                    r["hold"][name] = "BUILD:" + str(b)[:40]
                else:
                    try:
                        if getattr(b, "wants_site", False):
                            r["f"][name] = b(g["home"], g["away"], g["neutral"], g.get("site"))
                        else:
                            r["f"][name] = b(g["home"], g["away"], g["neutral"])
                    except Exception as e:
                        r["hold"][name] = str(e)[:40]
            rows.append(r)
    return rows


def attach_sd(rows, model_names):
    """Chronological predictive SD per model: RMSE of residuals with day < origin."""
    by_day = sorted(rows, key=lambda r: r["day"])
    for name in model_names:
        hist = [(r["day"], r["season"], r["f"][name]["margin"] - r["margin"], r["f"][name]["total"] - r["total"])
                for r in by_day if name in r["f"]]
        for r in rows:
            if name not in r["f"]:
                continue
            res = [(m, t) for d, s, m, t in hist if d < r["origin"] and s >= r["season"] - 1]
            if len(res) >= MIN_SD_RESIDUALS:
                r["f"][name]["sd_margin"] = math.sqrt(mean(m * m for m, _ in res))
                r["f"][name]["sd_total"] = math.sqrt(mean(t * t for _, t in res))
                r["f"][name]["sd_n"] = len(res)
                r["f"][name]["sd_max_day"] = max(d for d, s, m, t in hist if d < r["origin"] and s >= r["season"] - 1)


def attach_sd_fast(rows, model_names):
    """Same rule as attach_sd, vectorised by origin (equivalent; tested)."""
    for name in model_names:
        hist = sorted(((r["day"], r["season"], r["f"][name]["margin"] - r["margin"], r["f"][name]["total"] - r["total"])
                       for r in rows if name in r["f"]), key=lambda x: x[0])
        cache = {}
        for r in rows:
            if name not in r["f"]:
                continue
            key = (r["origin"], r["season"])
            if key not in cache:
                sel = [(m, t, d) for d, s, m, t in hist if d < r["origin"] and s >= r["season"] - 1]
                cache[key] = None if len(sel) < MIN_SD_RESIDUALS else (
                    math.sqrt(mean(m * m for m, _, _ in sel)), math.sqrt(mean(t * t for _, t, _ in sel)),
                    len(sel), max(d for _, _, d in sel))
            c = cache[key]
            if c:
                f = r["f"][name]
                f["sd_margin"], f["sd_total"], f["sd_n"], f["sd_max_day"] = c


def probabilities(r, name):
    """Independent-model probabilities for ML (home), spread (home covers close), total (over close)."""
    f, m = r["f"][name], r.get("mkt")
    out = {}
    if "sd_margin" not in f:
        return out
    out["ml"] = (phi(f["margin"] / f["sd_margin"]), 0.0)
    if m and m.get("close_spread_home") is not None:
        o, p, u = line_probs(f["margin"], f["sd_margin"], -m["close_spread_home"])
        out["spread"] = (o, p)
    if m and m.get("close_total") is not None:
        o, p, u = line_probs(f["total"], f["sd_total"], m["close_total"])
        out["total"] = (o, p)
    return out


def outcome(r, fam):
    m = r.get("mkt")
    if fam == "ml":
        return 1 if r["margin"] > 0 else 0
    if fam == "spread":
        v = r["margin"] + m["close_spread_home"]
    else:
        v = r["total"] - m["close_total"]
    return None if v == 0 else (1 if v > 0 else 0)


def market_prob(r, fam, when="close"):
    m = r.get("mkt") or {}
    if fam == "ml":
        return novig(m.get(f"{when}_ml_home"), m.get(f"{when}_ml_away"))
    if fam == "spread":
        return novig(m.get(f"{when}_spread_price_home"), m.get(f"{when}_spread_price_away"))
    return novig(m.get(f"{when}_over_price"), m.get(f"{when}_under_price"))


def prices(r, fam, when="close"):
    m = r.get("mkt") or {}
    k = {"ml": ("ml_home", "ml_away"), "spread": ("spread_price_home", "spread_price_away"),
         "total": ("over_price", "under_price")}[fam]
    return m.get(f"{when}_{k[0]}"), m.get(f"{when}_{k[1]}")


# ---------------------------------------------------------------- metrics
def ece(pairs, bins=10):
    out, e, n = [], 0.0, len(pairs)
    for b in range(bins):
        sel = [(p, y) for p, y in pairs if (b / bins <= p < (b + 1) / bins) or (b == bins - 1 and p == 1)]
        if sel:
            mp, my = mean(p for p, _ in sel), mean(y for _, y in sel)
            e += len(sel) / n * abs(mp - my)
            out.append({"bin": b, "n": len(sel), "mean_p": mp, "freq": my})
    return e, out


def ll(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -math.log(p if y else 1 - p)


def max_drawdown(pnl):
    peak, cum, mdd = 0.0, 0.0, 0.0
    for x in pnl:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return mdd


def cluster_boot(days, values, reps=1000, seed=20261125):
    """Percentile 95% CI of a row MEAN, resampling whole game DATES with replacement."""
    import numpy as np
    if not values:
        return None, None
    keys = sorted(set(days))
    if len(keys) < 10:
        return None, None
    ix = {k: i for i, k in enumerate(keys)}
    d = np.array([ix[x] for x in days])
    v = np.asarray(values, dtype=float)
    sums = np.bincount(d, v, len(keys)); cnt = np.bincount(d, None, len(keys))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(keys), size=(reps, len(keys)))
    est = sums[draws].sum(1) / cnt[draws].sum(1)
    return float(np.quantile(est, .025)), float(np.quantile(est, .975))


def point_metrics(rows, name, key):
    es = [r["f"][name][key] - r[key] for r in rows]
    if not es:
        return {}
    mu = mean(es)
    return {"n": len(es), "mae": mean(abs(e) for e in es), "rmse": math.sqrt(mean(e * e for e in es)),
            "bias": mu, "residual_sd": math.sqrt(mean((e - mu) ** 2 for e in es))}


def bet_eval(rows, name, fam, w, when="close"):
    """Flat 1u on the side with positive blended EV at `when` prices; chronological order.

    p_blend = w * p_independent + (1-w) * p_market_novig(when). Push refunds.
    Returns ROI, n_bets, max drawdown (units), hit rate, CLV (open bets only).
    """
    pnl, bets = [], []
    for r in sorted(rows, key=lambda r: (r["day"], r["event_id"])):
        pr = r["p"][name].get(fam)
        pm = market_prob(r, fam, when)
        pa, pb = prices(r, fam, when)
        if pr is None or pm is None or pa is None or pb is None:
            continue
        if fam != "ml" and when == "open":
            # independent prob must be re-evaluated at the OPEN line
            m, f = r["mkt"], r["f"][name]
            line = m.get("open_spread_home") if fam == "spread" else m.get("open_total")
            if line is None:
                continue
            o, pp, u = (line_probs(f["margin"], f["sd_margin"], -line) if fam == "spread"
                        else line_probs(f["total"], f["sd_total"], line))
            pi, push = o, pp
        else:
            pi, push = pr
            line = None
        cond = pi / (1 - push) if push < 1 else .5
        pblend = w * cond + (1 - w) * pm
        pwin_a = pblend * (1 - push); pwin_b = (1 - pblend) * (1 - push)
        ev_a = pwin_a * (dec(pa) - 1) - pwin_b
        ev_b = pwin_b * (dec(pb) - 1) - pwin_a
        if max(ev_a, ev_b) <= 0:
            continue
        side = "a" if ev_a >= ev_b else "b"
        price = pa if side == "a" else pb
        if fam == "ml":
            res = 1 if r["margin"] > 0 else 0
        else:
            lv = (line if line is not None else (r["mkt"]["close_spread_home"] if fam == "spread" else r["mkt"]["close_total"]))
            v = r["margin"] + lv if fam == "spread" else r["total"] - lv
            res = None if v == 0 else (1 if v > 0 else 0)
        if res is None:
            p = 0.0
        else:
            won = (res == 1) == (side == "a")
            p = dec(price) - 1 if won else -1.0
        clv = None
        if when == "open":
            pc = market_prob(r, fam, "close")
            po = market_prob(r, fam, "open")
            if pc is not None and po is not None:
                if fam == "ml":
                    clv = (pc - po) if side == "a" else (po - pc)
                else:
                    cl = r["mkt"]["close_spread_home"] if fam == "spread" else r["mkt"]["close_total"]
                    if cl is not None:
                        # points CLV from bettor's side: home spread bettor gains if close line is more negative
                        d = (line - cl) if fam == "spread" else (cl - line)
                        clv = d if side == "a" else -d
        pnl.append(p)
        bets.append({"event_id": r["event_id"], "day": r["day"], "side": side, "price": price,
                     "ev": max(ev_a, ev_b), "pnl": p, "clv": clv, "fav": price < 0})
    n = len(pnl)
    clvs = [b["clv"] for b in bets if b["clv"] is not None]
    return {"n_bets": n, "roi": (sum(pnl) / n) if n else None, "units": sum(pnl), "max_drawdown_u": max_drawdown(pnl),
            "hit_rate": (sum(1 for x in pnl if x > 0) / sum(1 for x in pnl if x != 0)) if any(pnl) else None,
            "clv_mean": mean(clvs) if clvs else None, "clv_n": len(clvs)}, bets


def blend_ll(rows, name, fam, w):
    vals = []
    for r in rows:
        pr = r["p"][name].get(fam)
        pm = market_prob(r, fam)
        if pr is None or pm is None:
            continue
        y = outcome(r, fam)
        if y is None:
            continue
        pi, push = pr
        cond = pi / (1 - push)
        p = w * cond + (1 - w) * pm
        vals.append((ll(p, y), (p - y) ** 2))
    if not vals:
        return None
    return {"n": len(vals), "log_loss": mean(v[0] for v in vals), "brier": mean(v[1] for v in vals)}


# ---------------------------------------------------------------- driver
def run(root, odds_path, out_dir, seasons, extra_models=(), reps=1000):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    names = list(M.MODELS)
    for spec in extra_models:
        names.append(M.load_spec(spec))
    odds, odds_census = D.load_odds(odds_path) if odds_path else ({}, {"games": 0})
    leak = {"origins": 0, "violations": []}
    all_rows, coverage = [], []
    prev_games = None
    first = min(seasons)
    history = {}
    try:
        prev_games, _ = D.load_games(root, first - 1)
        history[first - 1] = prev_games
    except Exception:
        prev_games = None
    for s in seasons:
        games, census = D.load_games(root, s)
        carry = M.season_end_carry(prev_games) if prev_games else {}
        carry = dict(carry)
        carry["_history"] = {k: v for k, v in history.items() if k < s}   # earlier seasons only
        carry["_season"] = s
        d1_prev = M.d1_set(prev_games) if prev_games else set()
        if prev_games and any(g["day"] >= min(x["day"] for x in games) for g in prev_games):
            leak["violations"].append(f"carry_overlaps_season {s}")
        rows = forecast_season(games, carry, names, leak)
        for r in rows:
            r["mkt"] = D.quarantine(odds.get(r["event_id"]), s)
            r["d1_both"] = r["home"] in d1_prev and r["away"] in d1_prev
        all_rows.extend(rows)
        history[s] = games
        coverage.append({"season": s, "admitted_finals": census.get("admitted_schedule_finals"),
                         "with_possessions": census.get("complete_box_finals"), "rows": len(rows),
                         **{f"forecast_{n}": sum(1 for r in rows if n in r["f"]) for n in names},
                         "all_builtin_forecast": sum(1 for r in rows if all(n in r["f"] for n in M.BUILTIN)),
                         "market_any": sum(1 for r in rows if r["mkt"]),
                         "market_spread": sum(1 for r in rows if r["mkt"] and r["mkt"]["close_spread_home"] is not None),
                         "market_total": sum(1 for r in rows if r["mkt"] and r["mkt"]["close_total"] is not None),
                         "market_ml": sum(1 for r in rows if r["mkt"] and r["mkt"]["close_ml_home"] is not None and r["mkt"]["close_ml_away"] is not None),
                         "market_open_any": sum(1 for r in rows if r["mkt"] and (r["mkt"]["open_spread_home"] is not None or r["mkt"]["open_ml_home"] is not None)),
                         "providers": json.dumps(dict(sorted(_count(r["mkt"]["provider"] for r in rows if r["mkt"]).items())))})
        prev_games = games
        print(json.dumps(coverage[-1], default=str), flush=True)
    attach_sd_fast(all_rows, names)
    # leakage check 2: SD history strictly before origin
    for r in all_rows:
        for n, f in r["f"].items():
            if "sd_max_day" in f and f["sd_max_day"] >= r["origin"]:
                leak["violations"].append(f"sd_after_origin {r['event_id']} {n}")
    for r in all_rows:
        r["p"] = {n: (probabilities(r, n) if n in r["f"] else {}) for n in names}
    ident = [r for r in all_rows if all(n in r["f"] and "sd_margin" in r["f"][n] for n in names)]
    return _report(all_rows, ident, names, coverage, odds_census, leak, out_dir, seasons, reps)


def _count(it):
    c = defaultdict(int)
    for x in it:
        c[x] += 1
    return c


def _write(path, rows):
    if not rows:
        path.write_text("")
        return
    keys = list(rows[0].keys())
    for r in rows[1:]:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})


def _report(all_rows, ident, names, coverage, odds_census, leak, out, seasons, reps):
    res = {"point": [], "split": [], "prob": [], "calib": [], "boot": [], "blend": [], "select": [],
           "betsplit": [], "ev30": []}
    groups = {"ALL": ident, "D1_BOTH_PRIOR_SEASON": [r for r in ident if r.get("d1_both")], **{str(s): [r for r in ident if r["season"] == s] for s in seasons},
              **{k.upper(): [r for r in ident if r["season"] in v] for k, v in SPLITS.items()}}
    # --- point metrics
    for g, rows in groups.items():
        for n in names:
            for key in ("margin", "total", "home_points", "away_points"):
                pm = point_metrics(rows, n, key)
                if pm:
                    res["point"].append({"group": g, "model": n, "target": key, **pm})
    # --- bias splits (ALL identical rows)
    def fav_err(r, n):
        sp = r["mkt"]["close_spread_home"]
        sgn = 1 if sp < 0 else -1  # +1 => home is market favourite
        return sgn * (r["f"][n]["margin"] - r["margin"])
    def band(x):
        x = abs(x)
        return "0-3" if x <= 3 else "3.5-7" if x <= 7 else "7.5-12" if x <= 12 else "12.5-20" if x <= 20 else "20+"
    for n in names:
        cells = defaultdict(list)
        for r in ident:
            e_m = r["f"][n]["margin"] - r["margin"]; e_t = r["f"][n]["total"] - r["total"]
            cells[("venue", "neutral" if r["neutral"] else "home_court", "margin_home_persp")].append(e_m)
            cells[("venue", "neutral" if r["neutral"] else "home_court", "total")].append(e_t)
            cells[("model_fav", "home_fav" if r["f"][n]["margin"] > 0 else "away_fav", "margin_home_persp")].append(e_m)
            m = r["mkt"]
            if m and m.get("close_spread_home") not in (None, 0):
                cells[("market_fav_persp", "favorite", "margin")].append(fav_err(r, n))
                cells[("market_fav_persp", "underdog", "margin")].append(-fav_err(r, n))
                cells[("spread_band", band(m["close_spread_home"]), "margin_fav_persp")].append(fav_err(r, n))
            if m and m.get("close_total") is not None:
                side = "model_over" if r["f"][n]["total"] > m["close_total"] else "model_under"
                cells[("ou_vs_market", side, "total")].append(e_t)
                cells[("actual_ou", "went_over" if r["total"] > m["close_total"] else "went_under_or_push", "total")].append(e_t)
        for (dim, cell, tgt), es in sorted(cells.items()):
            mu = mean(es)
            res["split"].append({"model": n, "dimension": dim, "cell": cell, "target": tgt, "n": len(es),
                                 "bias_pred_minus_actual": mu, "mae": mean(abs(e) for e in es),
                                 "rmse": math.sqrt(mean(e * e for e in es)),
                                 "residual_sd": math.sqrt(mean((e - mu) ** 2 for e in es))})
    # --- probability metrics + calibration (ALL / split groups), incl. market benchmark
    for g in ["ALL", "D1_BOTH_PRIOR_SEASON"] + [k.upper() for k in SPLITS] + [str(s) for s in seasons]:
        rows = groups[g]
        for fam in FAMILIES:
            fam_rows = [r for r in rows if all(fam in r["p"][n] for n in names) and outcome(r, fam) is not None]
            mk_rows = [r for r in fam_rows if market_prob(r, fam) is not None]
            for n in names + ["MARKET_NOVIG_CLOSE"]:
                if n == "MARKET_NOVIG_CLOSE":
                    pairs = [(market_prob(r, fam), outcome(r, fam)) for r in mk_rows]
                    basis = "market rows"
                else:
                    pairs = [(r["p"][n][fam][0] / (1 - r["p"][n][fam][1]), outcome(r, fam)) for r in fam_rows]
                    basis = "identical rows" if fam == "ml" else "identical rows with close line"
                if not pairs:
                    continue
                e, bins = ece(pairs)
                res["prob"].append({"group": g, "family": fam, "model": n, "basis": basis, "n": len(pairs),
                                    "brier": mean((p - y) ** 2 for p, y in pairs),
                                    "log_loss": mean(ll(p, y) for p, y in pairs), "ece": e,
                                    "mean_p": mean(p for p, _ in pairs), "freq": mean(y for _, y in pairs)})
                if g == "ALL":
                    for b in bins:
                        res["calib"].append({"family": fam, "model": n, **b})
            # same-row model vs market comparison (market rows only)
            if mk_rows and g in ("ALL", "VALIDATION", "TEST"):
                for n in names:
                    pairs = [(r["p"][n][fam][0] / (1 - r["p"][n][fam][1]), market_prob(r, fam), outcome(r, fam)) for r in mk_rows]
                    res["prob"].append({"group": g, "family": fam, "model": n + "_ON_MARKET_ROWS", "basis": "market rows",
                                        "n": len(pairs), "brier": mean((p - y) ** 2 for p, _, y in pairs),
                                        "log_loss": mean(ll(p, y) for p, _, y in pairs),
                                        "ece": ece([(p, y) for p, _, y in pairs])[0],
                                        "mean_p": mean(p for p, _, _ in pairs), "freq": mean(y for _, _, y in pairs)})
    # --- clustered bootstrap CIs (by date): MAE deltas vs native_frozen, log-loss deltas vs market
    base = "native_frozen"
    days = [r["day"] for r in ident]
    for n in names:
        for key in ("margin", "total"):
            v = [abs(r["f"][n][key] - r[key]) for r in ident]
            dv = [abs(r["f"][n][key] - r[key]) - abs(r["f"][base][key] - r[key]) for r in ident]
            lo, hi = cluster_boot(days, v, reps)
            dlo, dhi = cluster_boot(days, dv, reps) if n != base else (None, None)
            e = [r["f"][n][key] - r[key] for r in ident]
            blo, bhi = cluster_boot(days, e, reps)
            res["boot"].append({"model": n, "metric": f"mae_{key}", "n": len(ident), "estimate": mean(v) if v else None,
                                "ci95_lo": lo, "ci95_hi": hi, "delta_vs_native": mean(dv) if n != base and dv else 0.0,
                                "delta_ci95_lo": dlo, "delta_ci95_hi": dhi})
            res["boot"].append({"model": n, "metric": f"bias_{key}", "n": len(ident), "estimate": mean(e) if e else None,
                                "ci95_lo": blo, "ci95_hi": bhi})
        for fam in FAMILIES:
            mk = [r for r in ident if fam in r["p"][n] and market_prob(r, fam) is not None and outcome(r, fam) is not None]
            dv = [ll(r["p"][n][fam][0] / (1 - r["p"][n][fam][1]), outcome(r, fam)) - ll(market_prob(r, fam), outcome(r, fam)) for r in mk]
            lo, hi = cluster_boot([r["day"] for r in mk], dv, reps)
            res["boot"].append({"model": n, "metric": f"logloss_minus_market_{fam}", "n": len(mk), "estimate": mean(dv) if dv else None,
                                "ci95_lo": lo, "ci95_hi": hi})
    # --- blends: every weight independently, per season and per split
    for n in names:
        for fam in FAMILIES:
            for w in BLEND_WEIGHTS:
                for g in [str(s) for s in seasons] + [k.upper() for k in SPLITS]:
                    rows = groups[g]
                    s1 = blend_ll(rows, n, fam, w)
                    bc, _ = bet_eval(rows, n, fam, w, "close")
                    bo = {"n_bets": None, "roi": None, "units": None, "max_drawdown_u": None, "clv_mean": D.OPEN_LINES_STATUS, "clv_n": 0}
                    res["blend"].append({"model": n, "family": fam, "w_independent": w, "w_market": 1 - w, "group": g,
                                         **({"n": s1["n"], "log_loss": s1["log_loss"], "brier": s1["brier"]} if s1 else {"n": 0}),
                                         "close_n_bets": bc["n_bets"], "close_roi": bc["roi"], "close_units": bc["units"],
                                         "close_max_dd_u": bc["max_drawdown_u"], "close_hit": bc["hit_rate"],
                                         "open_n_bets": bo["n_bets"], "open_roi": bo["roi"], "open_units": bo["units"],
                                         "open_max_dd_u": bo["max_drawdown_u"], "open_clv_mean": bo["clv_mean"], "open_clv_n": bo["clv_n"]})
    # --- selection: VALIDATION log loss only; one-shot TEST report
    leak["selection_seasons"] = list(SPLITS["validation"]); leak["test_seasons"] = list(SPLITS["test"])
    if set(SPLITS["validation"]) & set(SPLITS["test"]):
        leak["violations"].append("validation_test_overlap")
    for n in names:
        for fam in FAMILIES:
            cand = [b for b in res["blend"] if b["model"] == n and b["family"] == fam and b["group"] == "VALIDATION" and b.get("n")]
            if not cand:
                res["select"].append({"model": n, "family": fam, "status": "BLOCKED_NO_HISTORICAL_MARKET_IN_VALIDATION"})
                continue
            best = min(cand, key=lambda b: (b["log_loss"], -b["w_independent"]))
            test = [b for b in res["blend"] if b["model"] == n and b["family"] == fam and b["group"] == "TEST" and b["w_independent"] == best["w_independent"]]
            t = test[0] if test else {}
            mkt = [b for b in res["blend"] if b["model"] == n and b["family"] == fam and b["group"] == "TEST" and b["w_independent"] == 0.0]
            res["select"].append({"model": n, "family": fam, "status": "SELECTED_ON_VALIDATION_REPORTED_ONCE_ON_TEST" if t.get("n") else "SELECTED_BUT_NO_TEST_MARKET_ROWS",
                                  "selected_w_independent": best["w_independent"], "validation_n": best["n"],
                                  "validation_log_loss": best["log_loss"], "test_n": t.get("n"),
                                  "test_log_loss": t.get("log_loss"), "test_brier": t.get("brier"),
                                  "test_market_only_log_loss": mkt[0].get("log_loss") if mkt else None,
                                  "test_close_n_bets": t.get("close_n_bets"), "test_close_roi": t.get("close_roi"),
                                  "test_close_max_dd_u": t.get("close_max_dd_u"), "clv_status": D.OPEN_LINES_STATUS})
    # --- betting splits and EV>30% investigation (pure independent model, w=1, close prices, ALL)
    for n in names:
        for fam in FAMILIES:
            for w in (1.0,):
                _, bets = bet_eval(ident, n, fam, w, "close")
                cells = defaultdict(list)
                for b in bets:
                    if fam == "ml":
                        pb = "<=-300" if b["price"] <= -300 else "-299..-150" if b["price"] <= -150 else "-149..+149" if b["price"] < 150 else "+150..+299" if b["price"] < 300 else ">=+300"
                        cells[("price_band", pb)].append(b)
                        cells[("fav_dog", "favorite" if b["fav"] else "underdog")].append(b)
                    elif fam == "spread":
                        r = None
                        cells[("side", "home" if b["side"] == "a" else "away")].append(b)
                    else:
                        cells[("side", "over" if b["side"] == "a" else "under")].append(b)
                    eb = "ev>30%" if b["ev"] > .30 else "10-30%" if b["ev"] > .10 else "0-10%"
                    cells[("ev_band", eb)].append(b)
                for (dim, cell), bs in sorted(cells.items()):
                    pnl = [b["pnl"] for b in bs]
                    res["betsplit"].append({"model": n, "family": fam, "w_independent": w, "dimension": dim, "cell": cell,
                                            "n_bets": len(bs), "roi": sum(pnl) / len(bs), "units": sum(pnl),
                                            "max_drawdown_u": max_drawdown(pnl), "mean_claimed_ev": mean(b["ev"] for b in bs)})
    # spread fav/dog split needs market favourite; add explicitly
    for n in names:
        _, bets = bet_eval(ident, n, "spread", 1.0, "close")
        byid = {r["event_id"]: r for r in ident}
        cells = defaultdict(list)
        for b in bets:
            sp = byid[b["event_id"]]["mkt"]["close_spread_home"]
            if sp == 0:
                continue
            home_fav = sp < 0
            cells["favorite" if (b["side"] == "a") == home_fav else "underdog"].append(b)
        for cell, bs in sorted(cells.items()):
            pnl = [b["pnl"] for b in bs]
            res["betsplit"].append({"model": n, "family": "spread", "w_independent": 1.0, "dimension": "fav_dog", "cell": cell,
                                    "n_bets": len(bs), "roi": sum(pnl) / len(bs), "units": sum(pnl),
                                    "max_drawdown_u": max_drawdown(pnl), "mean_claimed_ev": mean(b["ev"] for b in bs)})
    # --- HCA diagnostics: applied home-court points by model and season (home-court identical rows)
    res["hca"] = []
    for n in names:
        for sname in [str(x) for x in seasons]:
            hc = [r for r in groups[sname] if not r["neutral"]]
            if hc:
                res["hca"].append({"model": n, "season": sname, "n_home_court_rows": len(hc),
                                   "mean_hca_applied": mean(r["f"][n].get("hca_applied", float("nan")) for r in hc),
                                   "mean_pred_margin": mean(r["f"][n]["margin"] for r in hc),
                                   "mean_actual_margin": mean(r["margin"] for r in hc)})
    _write(out / "hca_by_season.csv", res["hca"])
    # --- write
    for k, fn in (("point", "point_metrics.csv"), ("split", "bias_splits.csv"), ("prob", "probability_metrics.csv"),
                  ("calib", "calibration_bins.csv"), ("boot", "bootstrap_ci.csv"), ("blend", "blend_weights_all.csv"),
                  ("select", "blend_selection.csv"), ("betsplit", "betting_splits.csv")):
        _write(out / fn, res[k])
    _write(out / "coverage.csv", coverage)
    rowsout = []
    for r in all_rows:
        x = {"event_id": r["event_id"], "season": r["season"], "day": r["day"].isoformat(), "origin": r["origin"].isoformat(),
             "split": split_of(r["season"]), "home": r["home"], "away": r["away"], "neutral": r["neutral"],
             "home_points": r["home_points"], "away_points": r["away_points"], "identical_row": r in ident_set(ident),
             "d1_both_prior_season": r.get("d1_both")}
        for n in names:
            f = r["f"].get(n)
            x[f"{n}_margin"] = round(f["margin"], 3) if f else None
            x[f"{n}_total"] = round(f["total"], 3) if f else None
            x[f"{n}_sd_margin"] = round(f["sd_margin"], 3) if f and "sd_margin" in f else None
            x[f"{n}_hold"] = r["hold"].get(n)
        m = r.get("mkt") or {}
        for k in ("provider", "close_spread_home", "close_total", "close_ml_home", "close_ml_away", "close_spread_price_home",
                  "close_spread_price_away", "close_over_price", "close_under_price", "open_spread_home", "open_total",
                  "open_ml_home", "open_ml_away", "close_from_current_fallback"):
            x["mkt_" + k] = m.get(k)
        rowsout.append(x)
    _write(out / "rows_paired_forecasts.csv", rowsout)
    meta = {"schema": "CBB_ROLLING_ORIGIN_BACKTEST_V1", "status": "RESEARCH_PAPER_0U", "official_counted": 0,
            "approved_stake_u": 0, "label": "NON_COUNTED", "generated_utc": datetime.now(timezone.utc).isoformat(),
            "seasons": list(seasons), "splits": {k: list(v) for k, v in SPLITS.items()},
            "blend_weights": list(BLEND_WEIGHTS), "blend_weights_source": BLEND_SOURCE,
            "models": names, "identical_rows": len(ident), "total_rows": len(all_rows),
            "odds_census": odds_census, "market_quarantine": {str(k): list(v) for k, v in D.MARKET_QUARANTINE.items()},
            "clv_status": D.OPEN_LINES_STATUS, "leakage": {"origins_checked": leak["origins"], "violations": leak["violations"][:50],
            "violation_count": len(leak["violations"]), "selection_seasons": leak.get("selection_seasons"),
            "test_seasons": leak.get("test_seasons")}, "bootstrap": {"reps": reps, "cluster": "game date"},
            "native_model_sha256": _native_sha(), "code_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                                  for p in sorted(Path(__file__).parent.glob("*.py"))}}
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=str, sort_keys=True) + "\n")
    return meta, res


_IDENT = {}


def ident_set(ident):
    k = id(ident)
    if k not in _IDENT:
        _IDENT.clear(); _IDENT[k] = {id(r) for r in ident}
    return _IdentWrap(_IDENT[k])


class _IdentWrap:
    def __init__(self, s): self.s = s
    def __contains__(self, r): return id(r) in self.s


def _native_sha():
    try:
        import cbbd_native_score_model as native
        return native.MODEL_CODE_SHA256
    except Exception:
        return None


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--odds", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seasons", nargs="+", type=int, default=list(range(2019, 2027)))
    p.add_argument("--model", action="append", default=[], help="name=module:callable challenger")
    p.add_argument("--reps", type=int, default=1000)
    a = p.parse_args()
    run(a.root, a.odds, a.out, a.seasons, a.model, a.reps)
