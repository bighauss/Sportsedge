#!/usr/bin/env python3
"""Dedicated CBB first-half (1H) distributions vs the pinned scaled-full-game approach.

Inputs
  halves.csv  derived from ncaahoopR_data pbp_logs (extract_cbb_halves.py): last half-1 play
              score = halftime score; last play = final. Raw pbp is not committed.
  box root    ncaahoopR_data (for the pinned-model point-in-time forecast, via
              cbb_pit_model_backtest.run_season, prior games only).

Validation: a game is used only if its pbp final equals the box-score final for both teams
(both orientations checked) and the halftime score is <= final; mismatches are counted.

Models compared on untouched holdout seasons:
  pinned_scaled  1H total mean = H1_FRAC * pinned full total, SD_H1; 1H margin mean =
                 H1_FRAC * pinned margin, SD_H1*0.85 (exactly the pinned model_prob)
  pinned_scaled_recalibrated  same mean as pinned_scaled plus a train-fitted bias; SDs fitted on train
  dedicated      team 1H points = 0.5*(team prior 1H scored EWMA + opp prior 1H allowed EWMA)
                 + train-fitted 1H home shift; SD fitted on train residuals only
Prior-only: EWMAs are updated after each game is forecast; within-season (reset each
season, like the pinned model's in-season ratings). PAPER research only.
"""
from __future__ import annotations
import argparse, csv, json, math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cbb_pit_model_backtest as B  # noqa: E402
M = B.M

ALPHA, MIN_PRIOR = 0.25, 3


def load_halves(path):
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                v = {k: int(r[k]) for k in ("h1_home", "h1_away", "final_home", "final_away")}
            except (KeyError, ValueError):
                continue
            out[r["game_id"]] = v
    return out


def join(games, halves):
    """Attach validated halftime scores (in box home/away orientation)."""
    stats = {"no_pbp": 0, "final_mismatch": 0, "ok": 0}
    out = []
    for g in games:
        h = halves.get(g["gid"])
        if h is None:
            stats["no_pbp"] += 1; continue
        bh, ba = g["h"]["PTS"], g["a"]["PTS"]
        if (h["final_home"], h["final_away"]) == (bh, ba):
            h1h, h1a = h["h1_home"], h["h1_away"]
        elif (h["final_away"], h["final_home"]) == (bh, ba):
            h1h, h1a = h["h1_away"], h["h1_home"]
        else:
            stats["final_mismatch"] += 1; continue
        if not (0 <= h1h <= bh and 0 <= h1a <= ba):
            stats["final_mismatch"] += 1; continue
        stats["ok"] += 1
        out.append({**g, "h1h": h1h, "h1a": h1a})
    return out, stats


def dedicated(games):
    """Prior-only 1H forecasts per game (within season)."""
    sc, al, n = {}, {}, defaultdict(int)
    out = []
    for g in games:
        H, A = g["home"], g["away"]
        if n[H] >= MIN_PRIOR and n[A] >= MIN_PRIOR:
            out.append((g, 0.5 * (sc[H] + al[A]), 0.5 * (sc[A] + al[H])))
        for t, o, pf, pa in ((H, A, g["h1h"], g["h1a"]), (A, H, g["h1a"], g["h1h"])):
            sc[t] = pf if t not in sc else ALPHA * pf + (1 - ALPHA) * sc[t]
            al[t] = pa if t not in al else ALPHA * pa + (1 - ALPHA) * al[t]
            n[t] += 1
    return out


def sd(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("halves")
    ap.add_argument("--train", default="2021-22,2022-23")
    ap.add_argument("--holdout", default="2023-24,2024-25")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    tr, ho = a.train.split(","), a.holdout.split(",")
    halves = load_halves(a.halves)
    pre, rows, join_stats, share = {}, {"train": [], "holdout": []}, {}, {}
    for s in sorted(set(tr + ho)):
        games = B.load_box(a.root, s)
        pin, pre = B.run_season(games, pre)
        pin = {r["gid"]: r for r in pin}
        jg, join_stats[s] = join(games, halves)
        share[s] = round(sum(g["h1h"] + g["h1a"] for g in jg) / sum(g["h"]["PTS"] + g["a"]["PTS"] for g in jg), 4)
        for g, fh, fa in dedicated(jg):
            p = pin.get(g["gid"])
            if p is None:
                continue  # score both methods on the identical game set
            rows["train" if s in tr else "holdout"].append({
                "neutral": g["neutral"], "y_tot": g["h1h"] + g["h1a"], "y_mar": g["h1h"] - g["h1a"],
                "pin_tot": M.H1_FRAC * (p["f_home"] + p["f_away"]), "pin_mar": M.H1_FRAC * (p["f_home"] - p["f_away"]),
                "ded_tot": fh + fa, "ded_mar": fh - fa})
    trn = rows["train"]
    hca = sum(r["y_mar"] - r["ded_mar"] for r in trn if not r["neutral"]) / max(1, sum(not r["neutral"] for r in trn))
    for part in rows.values():
        for r in part:
            if not r["neutral"]:
                r["ded_mar"] += hca
    fit = {"total_sd": sd([r["y_tot"] - r["ded_tot"] for r in trn]),
           "margin_sd": sd([r["y_mar"] - r["ded_mar"] for r in trn]),
           "total_bias": sum(r["y_tot"] - r["ded_tot"] for r in trn) / len(trn)}
    for part in rows.values():  # train-fitted mean correction (train seasons only)
        for r in part:
            r["ded_tot"] += fit["total_bias"]
    # Recalibrated pinned: keep the pinned scaled mean, refit only its bias and SDs on train.
    pb = sum(r["y_tot"] - r["pin_tot"] for r in trn) / len(trn)
    pfit = {"total_bias": pb, "total_sd": sd([r["y_tot"] - r["pin_tot"] for r in trn]),
            "margin_sd": sd([r["y_mar"] - r["pin_mar"] for r in trn])}
    for part in rows.values():
        for r in part:
            r["pinr_tot"] = r["pin_tot"] + pb
    hold = rows["holdout"]
    res = {}
    for name, mt, mm, st, sm in (("pinned_scaled", "pin_tot", "pin_mar", M.SD_H1, M.SD_H1 * 0.85),
                                 ("pinned_scaled_recalibrated", "pinr_tot", "pin_mar", pfit["total_sd"], pfit["margin_sd"]),
                                 ("dedicated", "ded_tot", "ded_mar", fit["total_sd"], fit["margin_sd"])):
        et = [r["y_tot"] - r[mt] for r in hold]; em = [r["y_mar"] - r[mm] for r in hold]
        res[name] = {"total_resid": B.moments(et), "margin_resid": B.moments(em), "assumed_total_sd": round(st, 3),
                     "assumed_margin_sd": round(sm, 3),
                     "total_over_calibration": B.ece_over([r[mt] for r in hold], [r["y_tot"] for r in hold], st,
                                                          (-4, -2, 0, 2, 4))}
    rep = {"schema": "sportsedge-cbb-first-half-v1", "status": "PAPER_RESEARCH_ONLY",
           "train": tr, "holdout": ho, "holdout_games": len(hold), "train_games": len(trn),
           "join_validation": join_stats, "observed_h1_share_of_total": share, "pinned_H1_FRAC": M.H1_FRAC,
           "dedicated_train_fit": {k: round(v, 3) for k, v in fit.items()} | {"h1_home_shift": round(hca, 3)},
           "pinned_recalibration_train_fit": {k: round(v, 3) for k, v in pfit.items()},
           "holdout": res}
    js = json.dumps(rep, indent=1)
    if a.out:
        open(a.out, "w").write(js)
    print(js)


if __name__ == "__main__":
    sys.exit(main())
