#!/usr/bin/env python3
"""NFL margin challengers (items #4/#6) -- research only, PAPER, 0u.

Walk-forward weekly, pregame info only. Train 2018-2022 (fit maps/weights), test 2023-2025 once.
  A  points ridge  = engine/sportsedge_ratings_v0_2.fit/project (NFL cfg, unchanged, no priors)
  B  A + QB adj    = beta * (starter prior EPA/dropback - team season baseline), shrunk; beta fit on train
  C  EPA ridge     = models/nfl/epa_ridge_pit.build_ratings -> net EPA/play diff -> points (linear map, train)
  D  w*A + (1-w)*C, w fit on train
Data (free nflverse): schedules games.csv (scores, spread_line, home/away_qb_id) and
play_by_play_{2017..2025}.csv.gz. Usage:
  python research/nfl_margin_challengers/run_challengers.py DATA_DIR > report_numbers.txt
"""
import sys, os, json, datetime as dt
from collections import defaultdict
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(ROOT, "engine"), os.path.join(ROOT, "models", "nfl")]
import sportsedge_ratings_v0_2 as eng
import epa_ridge_pit as epa

D = sys.argv[1]
QB_K = 300.0            # dropbacks of shrinkage toward team baseline
WINDOW_DAYS = 400       # history passed to each weekly fit
PASS_SHARE = 0.58       # weight of pass unit in net EPA/play

s = pd.read_csv(os.path.join(D, "sched.csv"))
s = s[(s.season >= 2017) & (s.season <= 2025) & s.result.notna()].copy()
s["kick"] = pd.to_datetime(s.gameday + " " + s.gametime.fillna("13:00")) + pd.Timedelta(hours=5)  # ET->UTC approx
s["final"] = s.kick + pd.Timedelta(hours=4)
s["avail"] = s.final + pd.Timedelta(hours=1)
s = s.sort_values("kick")

cols = ["game_id", "play_id", "drive", "posteam", "defteam", "pass", "rush", "epa", "qb_dropback", "id", "season"]
pbp = pd.concat([pd.read_csv(os.path.join(D, f"pbp_{y}.csv.gz"), usecols=cols, low_memory=False) for y in range(2017, 2026)])
pbp = pbp[pbp.game_id.isin(set(s.game_id))]
fin = dict(zip(s.game_id, s.final)); pbp["final"] = pbp.game_id.map(fin)
team_fix = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
for c in ("posteam", "defteam"): pbp[c] = pbp[c].replace(team_fix)
for c in ("home_team", "away_team"): s[c] = s[c].replace(team_fix)
db = pbp[(pbp.qb_dropback == 1) & pbp.epa.notna()][["id", "posteam", "season", "epa", "final"]]

def iso(t): return t.strftime("%Y-%m-%dT%H:%M:%SZ")

rows = []
s["wk"] = s.season.astype(str) + "_" + s.week.astype(str).str.zfill(2)
for wk, g in s[s.season >= 2018].groupby("wk", sort=True):
    asof = g.kick.min() - pd.Timedelta(hours=1)
    hist = s[(s.final < asof) & (s.final > asof - pd.Timedelta(days=WINDOW_DAYS))]
    # A: engine points ridge
    games = [dict(date=r.kick.date(), home=r.home_team, away=r.away_team, hp=r.home_score, ap=r.away_score,
                  neutral=(r.location == "Neutral"), poss=None) for r in hist.itertuples()]
    R = eng.fit("NFL", games, {}, asof.date())
    # C: EPA ridge (repo code)
    ph = pbp[pbp.game_id.isin(set(hist.game_id))]
    man = {r.game_id: dict(kickoff_utc=iso(r.kick), final_utc=iso(r.final), data_available_utc=iso(r.avail)) for r in hist.itertuples()}
    plays = [dict(game_id=a, play_id=b, drive=c, posteam=d, defteam=e, epa=("" if pd.isna(f) else f),
                  **{"pass": str(int(p)) if not pd.isna(p) else "0", "rush": str(int(q)) if not pd.isna(q) else "0"})
             for a, b, c, d, e, f, p, q in zip(ph.game_id, ph.play_id, ph.drive, ph.posteam, ph.defteam, ph.epa, ph["pass"], ph.rush)
             if not (pd.isna(d) or pd.isna(c))]
    E = epa.build_ratings(plays, man, asof_utc=iso(asof), source_observed_utc=iso(asof))["units"]
    def net(t, o):
        v = 0.0
        for u, w in (("pass", PASS_SHARE), ("rush", 1 - PASS_SHARE)):
            U = E[u]; v += w * (U["offense_above_average_epa"].get(t, 0) + U["defense_allowed_above_average_epa"].get(o, 0))
        return v
    # B inputs: prior dropbacks only
    dbh = db[db.final < asof]
    season = int(g.season.iloc[0])
    def qb_adj(team, qb):
        if pd.isna(qb): return 0.0, 0
        q = dbh[dbh.id == qb]; n = len(q)
        tb = dbh[(dbh.posteam == team) & (dbh.season == season)]
        if len(tb) < 100: tb = dbh[(dbh.posteam == team) & (dbh.season == season - 1)]
        base = tb.epa.mean() if len(tb) else 0.0
        if n == 0: return 0.0, 0   # no NFL history -> neutral (logged)
        return (n / (n + QB_K)) * (q.epa.mean() - base), n
    for r in g.itertuples():
        p = eng.project("NFL", R, r.home_team, r.away_team, neutral=(r.location == "Neutral"))
        if p is None: continue
        qh, nh = qb_adj(r.home_team, r.home_qb_id); qa, na = qb_adj(r.away_team, r.away_qb_id)
        rows.append(dict(game_id=r.game_id, season=r.season, week=r.week, actual=r.result, spread=r.spread_line,
                         A=p[0] - p[1], epa_diff=net(r.home_team, r.away_team) - net(r.away_team, r.home_team),
                         hfa=0 if r.location == "Neutral" else 1, qb_diff=qh - qa, qb_n_min=min(nh, na)))
    print(wk, len(rows), file=sys.stderr)

df = pd.DataFrame(rows); df.to_csv(os.path.join(os.path.dirname(__file__), "predictions.csv"), index=False)
tr, te = df[df.season <= 2022], df[df.season >= 2023]
# C map: actual ~ a*hfa + b*epa_diff (train only)
X = np.c_[tr.hfa, tr.epa_diff]; cC = np.linalg.lstsq(X, tr.actual, rcond=None)[0]
df["C"] = cC[0] * df.hfa + cC[1] * df.epa_diff
# B: residual of A on qb_diff (train only)
beta = float(np.linalg.lstsq(np.c_[tr.qb_diff], tr.actual - tr.A, rcond=None)[0][0])
df["B"] = df.A + beta * df.qb_diff
tr = df[df.season <= 2022]
ws = np.linspace(0, 1, 101); w = ws[np.argmin([((x * tr.A + (1 - x) * tr.C - tr.actual) ** 2).mean() for x in ws])]
df["D"] = w * df.A + (1 - w) * df.C
te = df[df.season >= 2023]

def stats(pred, d):
    e = d.actual - pred; sl = np.polyfit(pred, d.actual, 1)[0]
    return f"MAE {e.abs().mean():.2f} | bias {e.mean():+.2f} | slope {sl:.2f} | RMSE {np.sqrt((e**2).mean()):.2f}"
print(f"n_train={len(df[df.season<=2022])} n_test={len(te)}  C_map hfa={cC[0]:.2f} pts_per_epa={cC[1]:.1f}  QB beta={beta:.1f} pts/EPA-db  D w_A={w:.2f}")
print("| model | test MAE | bias (act-pred) | slope act~pred | RMSE |")
for m in ["spread", "A", "B", "C", "D"]:
    print("| " + m + " | " + stats(te[m], te).replace(" | ", " | ").replace("MAE ", "").replace("bias ", "").replace("slope ", "").replace("RMSE ", "") + " |")
print("\nATS vs closing spread_line, test 2023-2025 (pushes excluded)")
print("| model | edge 3-5 | edge 5-7 | edge >7 | all >3 |")
for m in ["A", "B", "C", "D"]:
    edge = te[m] - te.spread; cover = te.actual - te.spread
    out = []
    for lo, hi in ((3, 5), (5, 7), (7, 99), (3, 99)):
        sel = (edge.abs() > lo) & (edge.abs() <= hi) & (cover != 0)
        win = (np.sign(edge[sel]) == np.sign(cover[sel])).sum(); n = int(sel.sum())
        out.append(f"{win}-{n-win} ({win/n*100:.1f}%)" if n else "0-0")
    print(f"| {m} | " + " | ".join(out) + " |")
print(f"\nQB rows with a starter lacking NFL dropback history (adj=0): {(te.qb_n_min==0).sum()} of {len(te)} test games")
