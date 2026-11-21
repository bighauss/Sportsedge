"""Replay the 2026-11-21 CBB league-scale comparison from committed files only (stdlib, no network).

Inputs (same folder): torvik_2027_slate.csv (frozen Torvik ratings), cbb_replay_51.csv (DK lines captured
07:33-07:34 CT plus the projections produced at run time). Recomputes every projection with the
ratings-leg formula from models/cbb/sportsedge_cbb_model.py, checks them against the committed values,
and prints the old-vs-new summary.

Run: python research/runs/2026-11-21_cbb/replay_league_compare.py
"""
import csv, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
HCA = 3.0
SCALES = {"old": (105.0, 67.5), "new": (107.0, 69.0)}


def main():
    teams = {r["dk"]: r for r in csv.DictReader(open(os.path.join(HERE, "torvik_2027_slate.csv"), encoding="utf-8"))}
    games = list(csv.DictReader(open(os.path.join(HERE, "cbb_replay_51.csv"), encoding="utf-8")))
    assert len(games) == 51, len(games)
    summary = {}
    for tag, (oe, tempo) in SCALES.items():
        dt, dm = [], []
        for g in games:
            h, a = teams[g["home"]], teams[g["away"]]
            f = lambda r, k: float(r[k])
            poss = f(h, "adj_t") * f(a, "adj_t") / tempo
            hp = f(h, "adjoe") * f(a, "adjde") / oe / 100 * poss
            ap = f(a, "adjoe") * f(h, "adjde") / oe / 100 * poss
            if g["neutral"] != "1":
                hp += HCA / 2; ap -= HCA / 2
            assert abs(hp + ap - float(g[f"{tag}_total"])) < 0.01, (tag, g["away"], g["home"])
            assert abs(hp - ap - float(g[f"{tag}_margin"])) < 0.01, (tag, g["away"], g["home"])
            dt.append(hp + ap - float(g["dk_total"]))
            dm.append(hp - ap + float(g["dk_home_spread"]))
        summary[tag] = dict(n=len(dt), mean_total_minus_dk=round(st.mean(dt), 2), sd=round(st.stdev(dt), 2),
                            over_dk=sum(x > 0 for x in dt), mean_margin_minus_dk=round(st.mean(dm), 2))
    for tag, s in summary.items():
        print(tag, s)
    assert summary["old"]["mean_total_minus_dk"] == 7.88 and summary["new"]["mean_total_minus_dk"] == 1.65
    print("REPLAY MATCHES COMMITTED RESULTS")


if __name__ == "__main__":
    main()
