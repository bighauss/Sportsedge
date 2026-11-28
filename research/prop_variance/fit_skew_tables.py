#!/usr/bin/env python3
"""Fit sport-specific skew tables (CFB, CBB) on TRAIN seasons only; report untouched holdout.

Forecasts come from each sport's own walk-forward script (prior games only):
  CFB: research/prop_variance/fit_cfb_prop_variance.py  (cfbfastR-data player_stats CSVs)
  CBB: research/cbb_calibration/fit_cbb_calibration.py  (ncaahoopR_data box scores)
No coefficient is shared across sports. Holdout bias is REPORTED, never tuned by hand.
Usage:
  fit_skew_tables.py cfb <player_stats_dir> --table OUT.json --report REPORT.json
  fit_skew_tables.py cbb <ncaahoopR_data_root> --table OUT.json --report REPORT.json
"""
from __future__ import annotations
import argparse, json, math, os, sys
from statistics import NormalDist

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.join(ROOT, "research", "cbb_calibration"), ROOT]
from sportsedge.markets import prop_skew as PS  # noqa: E402

NQ, NBINS, MIN_BIN_N = 200, 8, 300
DELTAS = (-0.25, -0.10, 0.0, 0.10, 0.25)


def quantiles(xs, nq):
    xs = sorted(xs); n = len(xs)
    out = []
    for i in range(nq + 1):
        pos = i / nq * (n - 1); lo = int(math.floor(pos)); hi = min(lo + 1, n - 1)
        out.append(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))
    for i in range(1, len(out)):  # enforce non-decreasing
        out[i] = max(out[i], out[i - 1])
    return out


def build_stat(train, min_mean):
    train = [(f, y) for f, y in train if f >= min_mean]
    fs = sorted(f for f, _ in train)
    edges = [min_mean] + [fs[int(len(fs) * i / NBINS)] for i in range(1, NBINS)] + [float("inf")]
    edges = sorted(set(edges))
    bins = []
    for lo, hi in zip(edges, edges[1:]):
        r = [y / f for f, y in train if lo <= f < hi]
        if len(r) < MIN_BIN_N and bins:  # merge thin bin into previous
            prev = bins[-1]; prev["hi"] = hi; prev["_r"] += r; continue
        bins.append({"lo": lo, "hi": hi, "_r": r})
    for b in bins:
        b["n"] = len(b["_r"]); b["q"] = quantiles(b.pop("_r"), NQ)
        if b["hi"] == float("inf"):
            b["hi"] = 1e12
    return {"train_n": len(train), "min_mean": min_mean, "bins": bins}


def normal_three(mean, sd, line):
    nd = NormalDist(mean, max(sd, 1e-9))
    if float(line).is_integer():
        lo, hi = nd.cdf(line - 0.5), nd.cdf(line + 0.5)
        return 1 - hi, hi - lo, lo
    p = 1 - nd.cdf(line); return p, 0.0, 1 - p


def evaluate(tab, stat, test, frac, sd_floor):
    out = {}
    for kind in ("half", "integer"):
        for d in DELTAS:
            rows = {"skew": [], "pinned_normal": []}; push_obs = 0; n = 0
            for f, y in test:
                if f < tab["stats"][stat]["min_mean"]:
                    continue
                L = math.floor(f * (1 + d)) + 0.5 if kind == "half" else float(max(1, round(f * (1 + d))))
                if L <= 0:
                    continue
                o = 1 if y > L else 0; push_obs += int(y == L); n += 1
                rows["skew"].append((PS.three_way(tab, stat, f, L), o, y == L))
                rows["pinned_normal"].append((normal_three(f, max(sd_floor, frac * f), L), o, y == L))
            key = f"{kind}:{1 + d:.2f}f"; out[key] = {"n": n, "actual_over": round(sum(o for _, o, _ in rows["skew"]) / n, 4),
                                                      "actual_push": round(push_obs / n, 4)}
            for name, rs in rows.items():
                po = sum(p[0] for p, _, _ in rs) / n; pp = sum(p[1] for p, _, _ in rs) / n
                br = sum((p[0] - o) ** 2 for p, o, _ in rs) / n
                out[key][name] = {"pred_over": round(po, 4), "signed_over_bias": round(po - out[key]["actual_over"], 4),
                                  "pred_push": round(pp, 4), "brier_over": round(br, 5)}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("sport", choices=("cfb", "cbb"))
    ap.add_argument("src")
    ap.add_argument("--table", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args(argv)
    if a.sport == "cfb":
        import fit_cfb_prop_variance as S
        train_s, hold_s = range(2014, 2022), range(2022, 2026)
        games = {}
        for s in range(2014, 2026):
            p = os.path.join(a.src, f"player_stats_{s}.csv")
            if os.path.exists(p):
                games.update(S.aggregate(p))
        fc = S.forecasts(games); stats = list(S.ELIG); frac = S.CFB_PINNED_FRAC; floor = 1.0
        mins = {"pass_yds": 60.0, "rush_yds": 10.0, "rec_yds": 10.0, "receptions": 1.0}
        version, train_lab, hold_lab = "cfb-prop-skew-v1", "2014-2021", "2022-2025"
        tr = lambda s: s in train_s; ho = lambda s: s in hold_s
    else:
        import fit_cbb_calibration as S
        tr_l, ho_l = ["2021-22", "2022-23"], ["2023-24", "2024-25"]
        players, _ = S.load_players(a.src, tr_l + ho_l)
        fc = S.prop_forecasts(players); stats = list(S.PROP_COL); frac = S.PROP_SD_FRAC; floor = 0.8
        mins = dict(S.PROP_MIN_MEAN)
        version, train_lab, hold_lab = "cbb-prop-skew-v1", ",".join(tr_l), ",".join(ho_l)
        trk = {S.season_key(s) for s in tr_l}; hok = {S.season_key(s) for s in ho_l}
        tr = lambda s: s in trk; ho = lambda s: s in hok
    tab = {"schema": "sportsedge-prop-skew-table-v1", "version": version, "sport": a.sport.upper(),
           "train_seasons": train_lab, "nq": NQ, "fit": "train-season outcome/forecast ratio quantiles by forecast bin",
           "status": "PAPER_RESEARCH_ONLY", "stats": {}}
    for st in stats:
        tab["stats"][st] = build_stat([(f, y) for s, k, f, y in fc if k == st and tr(s)], mins[st])
    rep = {"version": version, "train": train_lab, "holdout": hold_lab,
           "line_source": "PROXY_LINES_NOT_SPORTSBOOK", "bias_tuning": "NONE (reported only)", "stats": {}}
    for st in stats:
        test = [(f, y) for s, k, f, y in fc if k == st and ho(s)]
        rep["stats"][st] = {"holdout_n": len(test), "by_line": evaluate(tab, st, test, frac[st], floor)}
    json.dump(tab, open(a.table, "w"), separators=(",", ":"))
    json.dump(rep, open(a.report, "w"), indent=1)
    for st, d in rep["stats"].items():
        bl = d["by_line"]
        print(st, d["holdout_n"], " ".join(f"{k}:skew{v['skew']['signed_over_bias']:+.3f}/pin{v['pinned_normal']['signed_over_bias']:+.3f}" for k, v in bl.items() if k.startswith("half")))


if __name__ == "__main__":
    main()
