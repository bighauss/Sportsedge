"""Replay the 2026-11-21 CFB SP+ ratings-leg run from committed files only (stdlib, no network).

Inputs (same folder):
  sp_plus_2026_wk11.csv  ESPN SP+ table, updated through 2026-11-15 (138 FBS teams; offense = points
                         scored vs an average defense, defense = points allowed vs an average offense).
  cfb_replay_58.csv      all 58 games on the DK 1st-half board at 07:32 CT: DK full-game lines, SP+ team
                         mapping, run status, and the projections that were produced.

Scoring units (centered, NOT the repo's 28 + offense + defense):
  baseline   = (mean SP+ offense + mean SP+ defense) / 2 over all 138 teams
  team pts   = baseline + (team offense - mean offense) + (opponent defense - mean defense) +/- HFA/2
             = team offense + opponent defense - (mean offense + mean defense - baseline) +/- HFA/2
HFA 2.5 (repo default); every game treated as campus (no neutral-site audit yet). FCS teams have no
SP+ row and are BLOCKED, not imputed.

Run: python research/runs/2026-11-21_cfb/replay_cfb_sp.py
"""
import csv, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
HFA = 2.5


def main():
    sp = {r["team"]: r for r in csv.DictReader(open(os.path.join(HERE, "sp_plus_2026_wk11.csv"), encoding="utf-8"))}
    assert len(sp) == 138, len(sp)
    avg_o = st.mean(float(r["offense"]) for r in sp.values())
    avg_d = st.mean(float(r["defense"]) for r in sp.values())
    base = (avg_o + avg_d) / 2
    games = list(csv.DictReader(open(os.path.join(HERE, "cfb_replay_58.csv"), encoding="utf-8")))
    assert len(games) == 58, len(games)
    priced, blocked, dt, dm = 0, 0, [], []
    for g in games:
        if g["status"] != "PRICED":
            assert not (g["sp_home"] and g["sp_away"]), g
            blocked += 1
            continue
        h, a = sp[g["sp_home"]], sp[g["sp_away"]]
        hfa = 0.0 if g["neutral"] == "1" else HFA
        hp = base + (float(h["offense"]) - avg_o) + (float(a["defense"]) - avg_d) + hfa / 2
        ap = base + (float(a["offense"]) - avg_o) + (float(h["defense"]) - avg_d) - hfa / 2
        hp, ap = max(hp, 3.0), max(ap, 3.0)
        for got, want in ((hp, g["home_pts"]), (ap, g["away_pts"]), (hp + ap, g["total"]), (hp - ap, g["home_margin"])):
            assert abs(got - float(want)) < 0.06, (g["away"], g["home"], got, want)
        priced += 1
        dt.append(hp + ap - float(g["dk_total"]))
        dm.append(hp - ap + float(g["dk_home_spread"]))
    print(f"baseline {base:.3f} (mean off {avg_o:.3f}, mean def {avg_d:.3f})")
    print(f"priced {priced}, blocked {blocked}")
    print(f"mean(model total - DK) {st.mean(dt):+.2f} sd {st.stdev(dt):.2f}; mean(model margin - DK) {st.mean(dm):+.2f} sd {st.stdev(dm):.2f}")
    assert priced == 54 and blocked == 4
    print("REPLAY MATCHES COMMITTED PROJECTIONS")


if __name__ == "__main__":
    main()
