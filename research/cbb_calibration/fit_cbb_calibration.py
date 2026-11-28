#!/usr/bin/env python3
"""Walk-forward CBB calibration research on public ncaahoopR_data CSV box scores.

PAPER research only. Baselines are SIMPLE prior-games forecasts, clearly labeled; the
pinned CBB model (models/cbb/sportsedge_cbb_model.py) cannot be run point-in-time on
this data (it needs as-of Torvik ratings), so this measures distribution SHAPE/WIDTH
around a no-leakage baseline, not the pinned model's accuracy. No sportsbook lines:
thresholds are proxy offsets around the forecast, so nothing here is an edge claim.

(a) Player props pts/reb/ast/3pm: EWMA(alpha=0.35) of the player's prior games
    (>=3). Pinned pricing: normal, sd = max(0.8, PROP_SD_FRAC * max(mean, line)).
    Compared with an empirical discrete distribution (train-season counts of Y given
    forecast bin). Integer outcomes; .5 proxy lines.
(b) Games: baseline team points = 0.5*(team prior-game scored EWMA + opponent prior
    allowed EWMA) + home/neutral adjustment fitted on TRAIN residuals only. Margin,
    total and team-total residual width, skew, kurtosis, home bias, and calibration of
    the pinned SD_MARGIN/SD_TOTAL/SD_TT normals vs width fitted on train.
First halves: NOT_COVERED (box scores have no half scores).
"""
from __future__ import annotations
import argparse, bisect, csv, json, math, os, sys
from collections import defaultdict
from statistics import NormalDist

ALPHA, MIN_PRIOR = 0.35, 3
PROP_SD_FRAC = dict(pts=0.33, reb=0.40, ast=0.45, tpm=0.65)      # pinned CBB values
SD_MARGIN, SD_TOTAL, SD_TT = 11.0, 11.0, 8.0                       # pinned CBB values
PROP_COL = dict(pts="PTS", reb="REB", ast="AST", tpm="3PTM")
PROP_MIN_MEAN = dict(pts=5.0, reb=2.0, ast=1.0, tpm=0.5)          # prop-eligible players
PROP_OFFSETS = (-0.25, -0.10, 0.0, 0.10, 0.25)
GAME_OFFSETS = (-6.0, -3.0, 0.0, 3.0, 6.0)                         # points around forecast
ACTIVITY = ("FGA", "FTA", "REB", "AST", "TO", "PF", "STL", "BLK")


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def season_key(s):
    return int(s.split("-")[0])


# ---------------------------------------------------------------- loading
def load_players(root, seasons):
    """One row per (game_id, player_id). Rows with no activity at all are treated as
    DNP/garbage and dropped (MIN is 0 throughout this source, so it cannot be used)."""
    rows, seen, dup = [], set(), 0
    for s in seasons:
        base = os.path.join(root, s, "box_scores")
        for team in sorted(os.listdir(base)):
            for fn in sorted(os.listdir(os.path.join(base, team))):
                gid = fn[:-4]
                with open(os.path.join(base, team, fn), newline="") as f:
                    for r in csv.DictReader(f):
                        if r.get("player") == "TEAM" or not r.get("player_id") or r.get("player_id") == "NA":
                            continue
                        k = (gid, r["player_id"])
                        if k in seen:
                            dup += 1; continue
                        if not any((num(r.get(c)) or 0) > 0 for c in ACTIVITY + ("PTS",)):
                            continue
                        seen.add(k)
                        rows.append((season_key(s), r.get("date", ""), gid, r["player_id"], r))
    return rows, dup


def load_games(root, seasons):
    """Join both teams' schedule rows on game_id. Returns list of game dicts."""
    sides = defaultdict(list)
    for s in seasons:
        base = os.path.join(root, s, "schedules")
        for fn in sorted(os.listdir(base)):
            team = fn[: -len("_schedule.csv")]
            with open(os.path.join(base, fn), newline="") as f:
                for r in csv.DictReader(f):
                    ts, os_ = num(r.get("team_score")), num(r.get("opp_score"))
                    if ts is None or os_ is None or not r.get("game_id"):
                        continue
                    sides[r["game_id"]].append((season_key(s), r["date"], team, r.get("location"), ts, os_))
    games = []
    for gid, ss in sides.items():
        uniq = {x[2]: x for x in ss}
        if len(uniq) != 2:
            continue  # need both D-I sides, exactly once each
        a, b = sorted(uniq.values(), key=lambda x: x[2])
        if a[4] != b[5] or a[5] != b[4] or a[1] != b[1]:
            continue  # inconsistent scores/dates: refuse
        loc = {a[3], b[3]}
        if loc == {"H", "A"}:
            home, away, neutral = (a, b) if a[3] == "H" else (b, a), None, False
            home, away = home
        elif loc == {"N"}:
            home, away, neutral = a, b, True
        else:
            continue
        games.append({"season": a[0], "date": a[1], "gid": gid, "home": home[2], "away": away[2],
                      "neutral": neutral, "hs": home[4], "as": away[4]})
    games.sort(key=lambda g: (g["date"], g["gid"]))
    return games


# ---------------------------------------------------------------- scoring
def score(pairs):
    eps = 1e-6
    n = len(pairs)
    if not n:
        return {"n": 0}
    br = sum((p - o) ** 2 for p, o in pairs) / n
    ll = -sum(o * math.log(max(p, eps)) + (1 - o) * math.log(max(1 - p, eps)) for p, o in pairs) / n
    rel = defaultdict(lambda: [0, 0.0, 0])
    for p, o in pairs:
        k = min(int(p * 10), 9); rel[k][0] += 1; rel[k][1] += p; rel[k][2] += o
    ece = sum(abs(s / c - h / c) * c for c, s, h in rel.values()) / n
    return {"n": n, "brier": round(br, 5), "logloss": round(ll, 5), "ece": round(ece, 4)}


def moments(res):
    n = len(res); m = sum(res) / n
    v = sum((r - m) ** 2 for r in res) / n; sd = math.sqrt(v)
    sk = sum((r - m) ** 3 for r in res) / n / sd ** 3
    ku = sum((r - m) ** 4 for r in res) / n / v ** 2 - 3
    mae = sum(abs(r) for r in res) / n
    return {"n": n, "mean": round(m, 3), "sd": round(sd, 3), "mae": round(mae, 3),
            "skew": round(sk, 3), "excess_kurtosis": round(ku, 3)}


# ---------------------------------------------------------------- (a) props
def prop_forecasts(rows):
    by = defaultdict(list)
    for s, d, gid, pid, r in rows:
        by[pid].append((d, gid, s, r))
    out = []
    for pid, gs in by.items():
        gs.sort(key=lambda g: (g[0], g[1]))
        for stat, col in PROP_COL.items():
            ew, n = None, 0
            for d, gid, s, r in gs:
                y = num(r.get(col))
                if y is None:
                    continue
                if n >= MIN_PRIOR and ew is not None and ew >= PROP_MIN_MEAN[stat]:
                    out.append((s, stat, ew, y))
                ew = y if ew is None else ALPHA * y + (1 - ALPHA) * ew
                n += 1
    return out


def prop_bins(train):
    """Empirical P(Y > line) via train ratio Y/f within forecast bins (integer-aware)."""
    edges = (0, 1.5, 3, 5, 8, 12, 16, 20, 1e9)
    bins = defaultdict(list)
    for f, y in train:
        i = bisect.bisect_right(edges, f) - 1
        bins[i].append(y / f)
    return edges, {k: sorted(v) for k, v in bins.items() if len(v) >= 200}


def p_over_emp(model, f, line):
    edges, bins = model
    v = bins.get(bisect.bisect_right(edges, f) - 1)
    if not v:
        return None
    return (len(v) - bisect.bisect_right(v, line / f) + 0.5) / (len(v) + 1)


def eval_props(test, stat, emp):
    fixed, empi, gaps = [], [], {}
    for d in PROP_OFFSETS:
        pf, pe, ob = [], [], []
        for f, y in test:
            line = math.floor(f * (1 + d)) + 0.5
            if line <= 0:
                continue
            sd = max(0.8, PROP_SD_FRAC[stat] * max(f, line))
            p1 = 1 - NormalDist(f, sd).cdf(line)
            p2 = p_over_emp(emp, f, line)
            if p2 is None:
                continue
            o = 1 if y > line else 0
            fixed.append((p1, o)); empi.append((p2, o)); pf.append(p1); pe.append(p2); ob.append(o)
        if ob:
            gaps[f"{1+d:.2f}f"] = {"n": len(ob), "pinned_p_over": round(sum(pf) / len(pf), 3),
                                    "empirical_p_over": round(sum(pe) / len(pe), 3),
                                    "actual_over_rate": round(sum(ob) / len(ob), 3),
                                    "pinned_minus_actual": round(sum(pf) / len(pf) - sum(ob) / len(ob), 3)}
    return {"pinned_normal": score(fixed), "empirical": score(empi), "by_offset": gaps}


# ---------------------------------------------------------------- (b) games
def game_forecasts(games):
    off, de = {}, {}
    out = []
    cnt = defaultdict(int)
    for g in games:
        h, a = g["home"], g["away"]
        if cnt[h] >= MIN_PRIOR and cnt[a] >= MIN_PRIOR:
            fh = 0.5 * (off[h] + de[a]); fa = 0.5 * (off[a] + de[h])
            out.append(dict(g, fh=fh, fa=fa))
        for t, pts, allowed in ((h, g["hs"], g["as"]), (a, g["as"], g["hs"])):
            off[t] = pts if t not in off else ALPHA * pts + (1 - ALPHA) * off[t]
            de[t] = allowed if t not in de else ALPHA * allowed + (1 - ALPHA) * de[t]
            cnt[t] += 1
    return out


def fit_home(train):
    """Additive home-court shift for true-home games, fitted on train residuals only."""
    r = [((g["hs"] - g["fh"]) - (g["as"] - g["fa"])) / 2 for g in train if not g["neutral"]]
    return sum(r) / len(r)


def eval_games(train, test):
    hca = fit_home(train)

    def adj(g):
        k = 0.0 if g["neutral"] else hca
        return g["fh"] + k, g["fa"] - k

    def resid(rows):
        m, t, tt = [], [], []
        for g in rows:
            fh, fa = adj(g)
            m.append((g["hs"] - g["as"]) - (fh - fa)); t.append((g["hs"] + g["as"]) - (fh + fa))
            tt += [g["hs"] - fh, g["as"] - fa]
        return m, t, tt

    mtr, ttr, tttr = resid(train)
    mte, tte, ttte = resid(test)
    fit_sd = {"margin": moments(mtr)["sd"], "total": moments(ttr)["sd"], "team_total": moments(tttr)["sd"]}

    def calib(kind, pinned_sd):
        out = {}
        for name, sd in (("pinned", pinned_sd), ("train_fitted", fit_sd[kind])):
            pairs, gaps = [], {}
            for off_ in GAME_OFFSETS:
                pp, oo = [], []
                for g in test:
                    fh, fa = adj(g)
                    if kind == "margin":
                        f, y = fh - fa, g["hs"] - g["as"]
                    elif kind == "total":
                        f, y = fh + fa, g["hs"] + g["as"]
                    else:
                        for f2, y2 in ((fh, g["hs"]), (fa, g["as"])):
                            line = math.floor(f2 + off_) + 0.5
                            p = 1 - NormalDist(f2, sd).cdf(line); pp.append(p); oo.append(1 if y2 > line else 0)
                        continue
                    line = math.floor(f + off_) + 0.5
                    p = 1 - NormalDist(f, sd).cdf(line); pp.append(p); oo.append(1 if y > line else 0)
                pairs += list(zip(pp, oo))
                gaps[f"{off_:+.0f}"] = {"n": len(oo), "p_over": round(sum(pp) / len(pp), 3),
                                        "actual": round(sum(oo) / len(oo), 3),
                                        "gap": round(sum(pp) / len(pp) - sum(oo) / len(oo), 3)}
            out[name] = dict(score(pairs), sd=sd, by_offset=gaps)
        return out

    # favorite/underdog: by sign of forecast margin, does the favorite cover the forecast?
    fav = [(1 if ((g["hs"] - g["as"]) - (adj(g)[0] - adj(g)[1])) * (1 if adj(g)[0] >= adj(g)[1] else -1) > 0 else 0)
           for g in test if abs(adj(g)[0] - adj(g)[1]) >= 1]
    # key numbers: share of final margins at each |margin|
    km = defaultdict(int)
    for g in test:
        km[abs(int(g["hs"] - g["as"]))] += 1
    top = sorted(km.items(), key=lambda kv: -kv[1])[:8]
    return {
        "baseline": "PRIOR_GAMES_EWMA_TEAM_POINTS_PLUS_TRAIN_HCA (not the pinned CBB model)",
        "hca_points_per_team_train": round(hca, 3),
        "train_n": len(train), "holdout_n": len(test),
        "holdout_true_home_share": round(sum(not g["neutral"] for g in test) / len(test), 3),
        "residuals_holdout": {"margin": moments(mte), "total": moments(tte), "team_total": moments(ttte)},
        "train_fitted_sd": fit_sd,
        "home_bias_holdout_margin_mean": moments([r for r, g in zip(mte, test) if not g["neutral"]])["mean"],
        "favorite_beats_forecast_rate": {"n": len(fav), "rate": round(sum(fav) / len(fav), 3)},
        "most_common_abs_final_margins": [{"margin": k, "share": round(v / len(test), 4)} for k, v in top],
        "margin": calib("margin", SD_MARGIN), "total": calib("total", SD_TOTAL),
        "team_total": calib("team_total", SD_TT),
        "first_half": {"state": "NOT_COVERED", "reason": "box scores have no half scores"},
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--train", default="2021-22,2022-23")
    ap.add_argument("--holdout", default="2023-24,2024-25")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    tr, ho = a.train.split(","), a.holdout.split(",")
    trk, hok = {season_key(s) for s in tr}, {season_key(s) for s in ho}
    players, dup = load_players(a.root, tr + ho)
    pf = prop_forecasts(players)
    rep = {"schema": "sportsedge-cbb-calibration-v1", "status": "PAPER_RESEARCH_ONLY",
           "line_source": "PROXY_LINES_NOT_SPORTSBOOK", "train": tr, "holdout": ho,
           "duplicate_player_rows_dropped": dup, "props": {}}
    for stat in PROP_COL:
        train = [(f, y) for s, st, f, y in pf if st == stat and s in trk]
        test = [(f, y) for s, st, f, y in pf if st == stat and s in hok]
        emp = prop_bins(train)
        mf = sum(f for f, _ in test) / len(test)
        rmse = math.sqrt(sum((y - f) ** 2 for f, y in test) / len(test))
        rep["props"][stat] = dict(train_n=len(train), holdout_n=len(test), mean_forecast=round(mf, 2),
                                  rmse=round(rmse, 3), pinned_frac=PROP_SD_FRAC[stat],
                                  implied_frac_at_mean=round(rmse / mf, 3),
                                  median_ratio=round(sorted(y / f for f, y in test)[len(test) // 2], 3),
                                  **eval_props(test, stat, emp))
    games = load_games(a.root, tr + ho)
    gf = game_forecasts(games)
    rep["games"] = eval_games([g for g in gf if g["season"] in trk], [g for g in gf if g["season"] in hok])
    js = json.dumps(rep, indent=1)
    if a.out:
        open(a.out, "w").write(js)
    print(js)


if __name__ == "__main__":
    sys.exit(main())
