#!/usr/bin/env python3
"""Point-in-time backtest of the PINNED CBB game model on public ncaahoopR_data box scores.

The pinned model (models/cbb/sportsedge_cbb_model.py) is imported unchanged; only its
rating INPUTS are reconstructed here, from each team's PRIOR games in the same season:

  adjoe / adjde  one-pass opponent-adjusted offensive/defensive efficiency
                 (game OE * LEAGUE_oe / opponent's prior raw DE, averaged); Torvik's
                 adjoe uses an iterative full-season adjustment, so this is an
                 approximation, documented, not a reproduction of Torvik
  adj_t          possessions per 40 minutes (team minutes / 5 gives game length)
  four factors   efg_o/d, tov_o/d, orb_o/d, ftr_o/d, three_p_o/d, three_pa_rate (percent)
  pre_*          previous season's final adjoe/adjde/adj_t (none for the first season)
  games          prior games this season
  neutral        box-score location == 'N'
Not reconstructed (set to model defaults): venue_hca (HCA_DEFAULT 3.0), travel/back-to-back,
injuries. Altitude uses the pinned ALT_TEAMS names; box-score names that differ
(e.g. "Utah State" vs "Utah St.") get no altitude bump.

A game is scored only if both teams' box files exist (so D-I vs non-D-I games are
excluded) and each team has >= MIN_PRIOR prior games. Coefficients are NOT fitted.
"train" seasons are reported for comparison only; holdout seasons are never used to set
anything. Possessions = FGA - OREB + TO + 0.475*FTA (team), averaged with the opponent's.
PAPER research only.
"""
from __future__ import annotations
import argparse, csv, json, math, os, sys
from collections import defaultdict
from statistics import NormalDist

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "models", "cbb"))
import sportsedge_cbb_model as M  # noqa: E402  (pinned; never modified)

MIN_PRIOR = 3
REJECTED = {}  # season -> games dropped for implausible box totals
STATCOLS = ("FGM", "FGA", "3PTM", "3PTA", "FTM", "FTA", "OREB", "DREB", "TO", "PTS", "MIN")


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def team_name(dirname):
    return dirname.replace("_", " ")


def load_box(root, season):
    """Games where BOTH teams' box files exist, paired by game_id.

    Team identity = box_scores directory name (stable across seasons and schemas). Team
    totals come from the 'TEAM' row when present (older schema, includes team rebounds and
    turnovers), else from the sum of player rows (newer schema). Home/away/neutral comes
    from each file's location column (H/A/N); conflicting locations are dropped.
    """
    games = defaultdict(dict)
    base = os.path.join(root, season, "box_scores")
    for tdir in sorted(os.listdir(base)):
        p = os.path.join(base, tdir)
        if not os.path.isdir(p):
            continue
        team = team_name(tdir)
        for fn in sorted(os.listdir(p)):
            if not fn.endswith(".csv"):
                continue
            gid = fn[:-4]
            with open(os.path.join(p, fn), newline="") as f:
                rows = list(csv.DictReader(f))
            if not rows or team in games[gid]:
                continue
            trow = [r for r in rows if (r.get("player") or "").strip().upper() == "TEAM"]
            src = trow[:1] if trow else [r for r in rows if (r.get("player") or "").strip().upper() != "TEAM"]
            tot, ok = {c: 0.0 for c in STATCOLS}, True
            for r in src:
                for c in STATCOLS:
                    v = num(r.get(c))
                    if v is None and c != "MIN":
                        ok = False
                    tot[c] += v or 0.0
            if trow:  # minutes only exist on player rows
                tot["MIN"] = sum(num(r.get("MIN")) or 0.0 for r in rows if r is not trow[0])
            if not ok:
                continue
            games[gid][team] = {"s": tot, "date": rows[0].get("date"), "loc": (rows[0].get("location") or "").strip()}
    out = []
    for gid, sides in games.items():
        if len(sides) != 2:
            continue
        (ta, a), (tb, b) = sorted(sides.items())
        if a["date"] != b["date"] or not a["date"]:
            continue
        locs = {a["loc"], b["loc"]}
        if locs == {"N"}:
            neutral, home, away = True, ta, tb
        elif locs == {"H", "A"}:
            neutral = False
            home, away = (ta, tb) if a["loc"] == "H" else (tb, ta)
        else:
            continue  # missing or contradictory location
        h, aw = sides[home]["s"], sides[away]["s"]
        if not all(40 <= poss(t) <= 110 and 20 <= t["PTS"] <= 160 and t["FGA"] > 0 for t in (h, aw)):
            REJECTED[season] = REJECTED.get(season, 0) + 1
            continue  # empty or implausible box (counted, never silently used)
        out.append({"gid": gid, "date": a["date"], "season": season, "home": home, "away": away,
                    "neutral": neutral, "h": h, "a": aw})
    out.sort(key=lambda g: (g["date"], g["gid"]))
    return out


def poss(t):
    return t["FGA"] - t["OREB"] + t["TO"] + 0.475 * t["FTA"]


class Book:
    """Running per-team accumulators for ONE season; updated only after a game is forecast."""

    def __init__(self, pre):
        self.g = defaultdict(list)
        self.pre = pre

    def raw_de(self, team):
        xs = self.g.get(team)
        if not xs:
            return M.LEAGUE["oe"]
        return 100 * sum(x["pa"] for x in xs) / sum(x["p"] for x in xs)

    def raw_oe(self, team):
        xs = self.g.get(team)
        if not xs:
            return M.LEAGUE["oe"]
        return 100 * sum(x["pf"] for x in xs) / sum(x["p"] for x in xs)

    def ratings(self, team):
        xs = self.g.get(team, [])
        pre = self.pre.get(team, {})
        r = {"team": team, "games": len(xs), "pre_adjoe": pre.get("adjoe"),
             "pre_adjde": pre.get("adjde"), "pre_adj_t": pre.get("adj_t")}
        if not xs:
            return r
        lg = M.LEAGUE["oe"]
        r["adjoe"] = sum(100 * x["pf"] / x["p"] * lg / self.raw_de(x["opp"]) for x in xs) / len(xs)
        r["adjde"] = sum(100 * x["pa"] / x["p"] * lg / self.raw_oe(x["opp"]) for x in xs) / len(xs)
        r["adj_t"] = sum(x["p40"] for x in xs) / len(xs)
        S = lambda k: sum(x[k] for x in xs)
        o_fga, d_fga = S("fga"), S("ofga")
        r.update({
            "efg_o": 100 * (S("fgm") + 0.5 * S("tpm")) / o_fga, "efg_d": 100 * (S("ofgm") + 0.5 * S("otpm")) / d_fga,
            "tov_o": 100 * S("to") / S("p"), "tov_d": 100 * S("oto") / S("p"),
            "orb_o": 100 * S("orb") / max(1.0, S("orb") + S("odrb")),
            "orb_d": 100 * S("oorb") / max(1.0, S("oorb") + S("drb")),
            "ftr_o": 100 * S("fta") / o_fga, "ftr_d": 100 * S("ofta") / d_fga,
            "three_pa_rate": 100 * S("tpa") / o_fga,
            "three_p_o": 100 * S("tpm") / max(1.0, S("tpa")), "three_p_d": 100 * S("otpm") / max(1.0, S("otpa")),
        })
        return r

    def add(self, team, opp, me, them):
        p = (poss(me) + poss(them)) / 2
        mins = me["MIN"] / 5 if me["MIN"] > 0 else 40.0
        self.g[team].append({"opp": opp, "p": p, "p40": p * 40 / max(40.0, mins), "pf": me["PTS"], "pa": them["PTS"],
                             "fgm": me["FGM"], "fga": me["FGA"], "tpm": me["3PTM"], "tpa": me["3PTA"],
                             "fta": me["FTA"], "to": me["TO"], "orb": me["OREB"], "drb": me["DREB"],
                             "ofgm": them["FGM"], "ofga": them["FGA"], "otpm": them["3PTM"], "otpa": them["3PTA"],
                             "ofta": them["FTA"], "oto": them["TO"], "oorb": them["OREB"], "odrb": them["DREB"]})


def run_season(games, pre):
    """Forecast each game from prior games only, then update. Returns forecasts + final ratings."""
    book, out = Book(pre), []
    for g in games:
        h, a = book.ratings(g["home"]), book.ratings(g["away"])
        if h["games"] >= MIN_PRIOR and a["games"] >= MIN_PRIOR:
            pj = M.project_game({"home": g["home"], "away": g["away"], "neutral": int(g["neutral"])},
                                {g["home"]: h, g["away"]: a}, {}, {})
            out.append({**{k: g[k] for k in ("gid", "date", "season", "home", "away", "neutral")},
                        "f_home": pj["home_pts"], "f_away": pj["away_pts"], "poss": pj["poss"],
                        "y_home": g["h"]["PTS"], "y_away": g["a"]["PTS"]})
        book.add(g["home"], g["away"], g["h"], g["a"])
        book.add(g["away"], g["home"], g["a"], g["h"])
    final = {}
    for t in book.g:
        r = book.ratings(t)
        final[t] = {k: r.get(k) for k in ("adjoe", "adjde", "adj_t")}
    return out, final


def moments(xs):
    n = len(xs); m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    sk = sum((x - m) ** 3 for x in xs) / n / sd ** 3
    ku = sum((x - m) ** 4 for x in xs) / n / sd ** 4 - 3
    return {"n": n, "mean": round(m, 3), "sd": round(sd, 3), "mae": round(sum(abs(x) for x in xs) / n, 3),
            "rmse": round(math.sqrt(sum(x * x for x in xs) / n), 3), "skew": round(sk, 3), "excess_kurtosis": round(ku, 3)}


def ece_over(fs, ys, sd, offsets=(-6, -3, 0, 3, 6), scales=None):
    """Calibration of P(Y > f+k) under Normal(f, sd*scale) at proxy lines (half-point)."""
    pairs = []
    for i, (f, y) in enumerate(zip(fs, ys)):
        sdi = sd * (scales[i] if scales else 1.0)
        for k in offsets:
            line = math.floor(f + k) + 0.5
            p = 1 - NormalDist(f, sdi).cdf(line)
            pairs.append((p, 1 if y > line else 0, k))
    n = len(pairs)
    bins = defaultdict(lambda: [0, 0.0, 0])
    for p, o, _ in pairs:
        b = bins[min(int(p * 10), 9)]; b[0] += 1; b[1] += p; b[2] += o
    ece = sum(abs(s - h) for c, s, h in bins.values()) / n
    brier = sum((p - o) ** 2 for p, o, _ in pairs) / n
    by = {}
    for k in offsets:
        sel = [(p, o) for p, o, kk in pairs if kk == k]
        by[str(k)] = round(sum(p for p, _ in sel) / len(sel) - sum(o for _, o in sel) / len(sel), 4)
    return {"n": n, "ece": round(ece, 4), "brier": round(brier, 5), "pred_minus_actual_by_offset": by}


def summarize(rows, sd_fit=None):
    m = [(r["y_home"] - r["y_away"]) - (r["f_home"] - r["f_away"]) for r in rows]
    t = [(r["y_home"] + r["y_away"]) - (r["f_home"] + r["f_away"]) for r in rows]
    tt = [r["y_home"] - r["f_home"] for r in rows] + [r["y_away"] - r["f_away"] for r in rows]
    nn = [r for r in rows if not r["neutral"]]
    fav = []
    for r in rows:
        fm = r["f_home"] - r["f_away"]
        if abs(fm) >= 0.5:
            s = 1 if fm > 0 else -1
            fav.append(s * ((r["y_home"] - r["y_away"]) - fm))
    out = {"games": len(rows), "neutral_games": len(rows) - len(nn),
           "margin": moments(m), "total": moments(t), "team_total": moments(tt),
           "home_margin_bias_nonneutral": moments([(r["y_home"] - r["y_away"]) - (r["f_home"] - r["f_away"]) for r in nn])["mean"],
           "favorite_margin_bias": moments(fav)["mean"] if fav else None,
           "favorite_cover_rate_vs_model": round(sum(x > 0 for x in fav) / len(fav), 4) if fav else None}
    pinned = {"margin": M.SD_MARGIN, "total": M.SD_TOTAL, "team_total": M.SD_TT}
    out["pinned_sd"] = pinned
    fs_t = [r["f_home"] + r["f_away"] for r in rows]; ys_t = [r["y_home"] + r["y_away"] for r in rows]
    tempo = [math.sqrt(r["poss"] / M.LEAGUE["tempo"]) for r in rows]  # pinned model_prob tempo scaling
    out["total_over_calibration_pinned_sd"] = ece_over(fs_t, ys_t, M.SD_TOTAL, scales=tempo)
    if sd_fit:
        out["total_over_calibration_train_fitted_sd"] = ece_over(fs_t, ys_t, sd_fit["total"])
        fs_tt = [r["f_home"] for r in rows] + [r["f_away"] for r in rows]
        ys_tt = [r["y_home"] for r in rows] + [r["y_away"] for r in rows]
        out["team_total_over_calibration_pinned_sd"] = ece_over(fs_tt, ys_tt, M.SD_TT, (-4, -2, 0, 2, 4))
        out["team_total_over_calibration_train_fitted_sd"] = ece_over(fs_tt, ys_tt, sd_fit["team_total"], (-4, -2, 0, 2, 4))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--train", default="2021-22,2022-23")
    ap.add_argument("--holdout", default="2023-24,2024-25")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    tr, ho = a.train.split(","), a.holdout.split(",")
    seasons = sorted(set(tr + ho))
    pre, fc, audit = {}, {}, {}
    for s in seasons:
        g = load_box(a.root, s)
        audit[s] = {"games_with_both_sides": len(g), "rejected_implausible_box": REJECTED.get(s, 0), "first_date": g[0]["date"], "last_date": g[-1]["date"],
                    "game_ids": {x["gid"] for x in g}}
        fc[s], pre = run_season(g, pre)
    ids_tr = set().union(*(audit[s]["game_ids"] for s in tr)); ids_ho = set().union(*(audit[s]["game_ids"] for s in ho))
    leak = {"train_last_date": max(audit[s]["last_date"] for s in tr),
            "holdout_first_date": min(audit[s]["first_date"] for s in ho),
            "game_id_overlap": len(ids_tr & ids_ho)}
    leak["train_before_holdout"] = leak["train_last_date"] < leak["holdout_first_date"]
    train = [r for s in tr for r in fc[s]]; hold = [r for s in ho for r in fc[s]]
    st = summarize(train)
    sd_fit = {"total": st["total"]["sd"], "team_total": st["team_total"]["sd"]}
    rep = {"schema": "sportsedge-cbb-pit-pinned-model-backtest-v1", "status": "PAPER_RESEARCH_ONLY",
           "model": "models/cbb/sportsedge_cbb_model.py project_game (unchanged)",
           "inputs": "RECONSTRUCTED_FROM_PRIOR_BOX_SCORES (see module docstring for differences)",
           "min_prior_games": MIN_PRIOR, "train": tr, "holdout": ho, "leakage_audit": leak,
           "season_audit": {s: {k: v for k, v in audit[s].items() if k != "game_ids"} for s in seasons},
           "train_summary": st, "train_fitted_sd": sd_fit, "holdout_summary": summarize(hold, sd_fit)}
    js = json.dumps(rep, indent=1)
    if a.out:
        open(a.out, "w").write(js)
    print(js)


if __name__ == "__main__":
    sys.exit(main())
