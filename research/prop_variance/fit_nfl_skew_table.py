#!/usr/bin/env python3
"""Fit models/nfl/prop_skew_v1_table.json from nflverse TRAIN seasons only, and validate on
untouched HOLDOUT seasons vs the frozen v3 normal (runit_ledger PROP_MARKETS cv).

Usage: python fit_nfl_skew_table.py ps_*.csv.gz --fit-out TABLE.json --report REPORT.json
"""
from __future__ import annotations
import argparse, json, math, os, sys
from statistics import NormalDist

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "models", "nfl"))
import fit_nfl_prop_variance as V  # noqa: E402
import prop_skew_v1 as S  # noqa: E402

TRAIN, HOLDOUT = range(2018, 2023), range(2023, 2026)
STATS = ("pass_yds", "rush_yds", "rec_yds", "receptions")
NBINS = 5  # forecast-size bins at TRAIN forecast quintiles
V3_CV = {"pass_yds": .28, "rec_yds": .65, "rush_yds": .5, "receptions": .45}  # runit_ledger v3
NQ = 200
OFFSETS = (0.6, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5)


def quantiles(v):
    v = sorted(v); n = len(v)
    return [v[min(n - 1, max(0, round(i * (n - 1) / NQ)))] for i in range(NQ + 1)]


def fit(fc):
    out = {"schema": "sportsedge-nfl-prop-skew-table-v1", "version": S.VERSION,
           "train_seasons": list(TRAIN), "nq": NQ, "stats": {}}
    if any(s not in TRAIN for s, *_ in fc):
        raise ValueError("HOLDOUT_ROW_PASSED_TO_FIT")
    for stat in STATS:
        pairs = [(f, y) for s, st, f, y in fc if st == stat]
        fs = sorted(f for f, _ in pairs)
        cuts = [fs[len(fs) * i // NBINS] for i in range(1, NBINS)]
        edges = (0.0, *cuts, 1e9)
        bins = []
        for lo, hi in zip(edges, edges[1:]):
            r = [y / f for f, y in pairs if lo <= f < hi]
            if len(r) < 150:
                raise ValueError(f"THIN_BIN {stat} {lo}-{hi} n={len(r)}")
            bins.append({"lo": lo, "hi": hi, "n": len(r), "q": quantiles(r)})
        out["stats"][stat] = {"train_n": len(pairs), "bins": bins}
    return out


def v3_p_ge(stat, m, k):
    return 1 - NormalDist(m, V3_CV[stat] * m).cdf(k - 0.5)


def validate(fc, tab):
    rep = {}
    for stat in STATS:
        test = [(f, y) for s, st, f, y in fc if st == stat and s in HOLDOUT]
        res = {"holdout_n": len(test), "by_offset": [], "methods": {}}
        pairs = {"v3_normal": [], "skew_v1": []}
        for off in OFFSETS:
            agg = {"v3_normal": [0.0, 0], "skew_v1": [0.0, 0]}; hit = 0; n = 0
            for f, y in test:
                k = math.floor(f * off) + 1  # milestone k+ (integer), as on DK milestone ladders
                if k <= 0:
                    continue
                o = 1 if y >= k else 0
                for name, p in (("v3_normal", v3_p_ge(stat, f, k)), ("skew_v1", S.p_ge(stat, f, k, tab))):
                    p = min(max(p, 1e-6), 1 - 1e-6)
                    agg[name][0] += p; pairs[name].append((p, o))
                hit += o; n += 1
            res["by_offset"].append({"k_over_f": off, "n": n, "actual_p_ge": round(hit / n, 4),
                                     **{f"{m}_pred": round(a[0] / n, 4) for m, a in agg.items()},
                                     **{f"{m}_signed_bias": round(a[0] / n - hit / n, 4) for m, a in agg.items()}})
        for name, pr in pairs.items():
            res["methods"][name] = V.score(pr)
        rep[stat] = res
    return {"schema": "sportsedge-nfl-prop-skew-validation-v1", "train": list(TRAIN),
            "holdout": list(HOLDOUT), "line_source": "PROXY_MILESTONES_NOT_SPORTSBOOK",
            "status": "PAPER_RESEARCH_ONLY", "stats": rep}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--fit-out", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args(argv)
    fc = V.forecasts(V.load(a.files))
    train_only = [r for r in fc if r[0] in TRAIN]
    tab = fit(train_only)  # holdout rows are never passed to fit()
    with open(a.fit_out, "w") as f:
        json.dump(tab, f, separators=(",", ":"))
        f.write("\n")
    rep = validate(fc, tab)
    with open(a.report, "w") as f:
        json.dump(rep, f, indent=1)
    for stat, r in rep["stats"].items():
        m = r["methods"]
        print(stat, r["holdout_n"], "v3", m["v3_normal"]["brier"], m["v3_normal"]["logloss"], m["v3_normal"]["ece"],
              "| skew", m["skew_v1"]["brier"], m["skew_v1"]["logloss"], m["skew_v1"]["ece"])
        for o in r["by_offset"]:
            print(f"   k/f={o['k_over_f']:.2f} n={o['n']} actual={o['actual_p_ge']:.3f} v3={o['v3_normal_pred']:.3f} ({o['v3_normal_signed_bias']:+.3f}) skew={o['skew_v1_pred']:.3f} ({o['skew_v1_signed_bias']:+.3f})")


if __name__ == "__main__":
    main()
