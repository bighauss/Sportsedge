"""NFL totals challenger backtest (research only; does not touch engine files).

Data (free): nflverse nfldata games.csv (scores, total_line, roof, temp, wind)
and nflverse-data stats_team_week_{season}.csv (plays = attempts+carries+sacks).
Strict walk-forward: every projection for a game uses only games completed on
earlier dates. Tuning on 2018-2022 only; test 2023-2025 once; 2026 reported apart.

Usage: python3 nfl_totals_backtest.py GAMES_CSV TEAMSTATS_DIR
"""
import sys, glob
import numpy as np, pandas as pd

LG = 22.5
games = pd.read_csv(sys.argv[1])
games = games[(games.season >= 2016) & games.total.notna()].copy()
games["date"] = pd.to_datetime(games.gameday)
games = games.sort_values(["date", "game_id"]).reset_index(drop=True)

ts = pd.concat([pd.read_csv(f) for f in glob.glob(sys.argv[2] + "/ts_*.csv")])
ts["plays"] = ts.attempts.fillna(0) + ts.carries.fillna(0) + ts.sacks_suffered.fillna(0)
plays = ts.groupby(["game_id", "team"]).plays.sum().to_dict()

# team-game long table
rows = []
for g in games.itertuples():
    for t, o, pf, pa, home in ((g.home_team, g.away_team, g.home_score, g.away_score, 1),
                               (g.away_team, g.home_team, g.away_score, g.home_score, 0)):
        rows.append(dict(game_id=g.game_id, date=g.date, season=g.season, team=t, opp=o,
                         pf=pf, pa=pa, home=home * (g.location == "Home"),
                         plays=plays.get((g.game_id, t), np.nan)))
long = pd.DataFrame(rows)
teams = sorted(set(long.team))
ti = {t: i for i, t in enumerate(teams)}
NT = len(teams)


def pfpa(prior, season, team, k):
    s = prior[(prior.season == season) & (prior.team == team)]
    n = len(s)
    return (s.pf.sum() + k * LG) / (n + k), (s.pa.sum() + k * LG) / (n + k)


def method_pf(prior, g, k):
    hpf, hpa = pfpa(prior, g.season, g.home_team, k)
    apf, apa = pfpa(prior, g.season, g.away_team, k)
    return (hpf + apa) / 2 + (apf + hpa) / 2


def ridge_fit(prior, date, lam, hl=45.0, window=400):
    p = prior[prior.date > date - pd.Timedelta(days=window)]
    if len(p) < 40:
        return None
    w = 0.5 ** ((date - p.date).dt.days.values / hl)
    X = np.zeros((len(p), 2 * NT + 2))
    X[:, 0] = 1
    X[:, 1] = p.home.values
    X[np.arange(len(p)), 2 + p.team.map(ti).values] = 1          # offence
    X[np.arange(len(p)), 2 + NT + p.opp.map(ti).values] = 1      # defence (pts allowed)
    y = p.pf.values
    R = np.diag([0, 0] + [lam] * 2 * NT)
    WX = X * w[:, None]
    return np.linalg.solve(X.T @ WX + R, WX.T @ y)


def ridge_total(b, g):
    h, a = ti[g.home_team], ti[g.away_team]
    hf = 1.0 if g.location == "Home" else 0.0
    ph = b[0] + b[1] * hf + b[2 + h] + b[2 + NT + a]
    pa = b[0] + b[2 + a] + b[2 + NT + h]
    return ph + pa


def pace(prior, date, team, k=6, hl=120.0):
    p = prior[(prior.team == team) & prior.plays.notna() & (prior.date > date - pd.Timedelta(days=400))]
    lg = prior.plays.mean()
    if len(p) == 0:
        return 0.0
    w = 0.5 ** ((date - p.date).dt.days.values / hl)
    return (np.sum(w * p.plays.values) + k * lg) / (w.sum() + k) - lg


KS = [4, 8, 12, 16, 24, 32]
LAMS = [2, 5, 10, 20, 40]
out = []
for date, day in games.groupby("date"):
    prior = long[long.date < date]
    if prior.empty:
        continue
    fits = {lam: ridge_fit(prior, date, lam) for lam in LAMS}
    for g in day.itertuples():
        r = dict(game_id=g.game_id, season=g.season, actual=g.total, line=g.total_line,
                 roof=g.roof, temp=g.temp, wind=g.wind)
        for k in KS:
            r[f"pf_k{k}"] = method_pf(prior, g, k)
        for lam, b in fits.items():
            r[f"rd_l{lam}"] = ridge_total(b, g) if b is not None else np.nan
        r["pace_h"] = pace(prior, date, g.home_team)
        r["pace_a"] = pace(prior, date, g.away_team)
        out.append(r)
df = pd.DataFrame(out)
df.to_csv("walkforward_preds.csv", index=False)

train = df[df.season.between(2018, 2022)].dropna(subset=["rd_l5"])
test = df[df.season.between(2023, 2025)]
cur = df[df.season == 2026]

mae = lambda d, c: np.mean(np.abs(d.actual - d[c]))
bk = min(KS, key=lambda k: mae(train, f"pf_k{k}"))
bl = min(LAMS, key=lambda l: mae(train, f"rd_l{l}"))
B, C = f"pf_k{bk}", f"rd_l{bl}"
base = B if mae(train, B) < mae(train, C) else C


def feats(d):
    outdoor = d.roof.isin(["outdoors", "open"]).astype(float)
    wind = d.wind.fillna(0) * outdoor
    temp = d.temp.fillna(65)
    return np.column_stack([np.ones(len(d)), d.pace_h + d.pace_a,
                            wind, (temp < 32).astype(float) * outdoor, 1 - outdoor])


# D: OLS on train residuals of the chosen base
Xtr = feats(train)
coef = np.linalg.lstsq(Xtr, (train.actual - train[base]).values, rcond=None)[0]
# D_pace: pace only (fully pregame-knowable)
coefp = np.linalg.lstsq(Xtr[:, :2], (train.actual - train[base]).values, rcond=None)[0]
for d in (df,):
    d["D_full"] = d[base] + feats(d) @ coef
    d["D_pace"] = d[base] + feats(d)[:, :2] @ coefp
# E: market-anchored blend line + w*(D_full-line), w tuned on train
tr0 = df[df.season.between(2018, 2022)].dropna(subset=["rd_l5", "line"])
WS = np.round(np.arange(0, 0.51, 0.05), 2)
bw = min(WS, key=lambda w: np.mean(np.abs(tr0.actual - (tr0.line + w * (tr0.D_full - tr0.line)))))
df["E_blend"] = df.line + bw * (df.D_full - df.line)
train, test, cur = (df[df.season.between(2018, 2022)].dropna(subset=["rd_l5"]),
                    df[df.season.between(2023, 2025)], df[df.season == 2026])

methods = [("A current k=8 PF/PA", "pf_k8"), (f"B PF/PA k={bk}", B),
           (f"C ridge lam={bl}", C), ("D base+pace", "D_pace"),
           ("D base+pace+weather*", "D_full"), (f"E market+{bw}*(D-mkt)", "E_blend"), ("MARKET close", "line")]


def table(d, label):
    d = d.dropna(subset=["line"])
    L = [f"\n### {label} (n={len(d)})\n", "| method | MAE | bias (pred-act) | slope act~pred | sd(pred) |",
         "|---|---|---|---|---|"]
    for name, c in methods:
        e = d[c] - d.actual
        sl = np.polyfit(d[c], d.actual, 1)[0]
        L.append(f"| {name} | {np.mean(np.abs(e)):.2f} | {e.mean():+.2f} | {sl:.2f} | {d[c].std():.2f} |")
    L += ["\nO/U vs closing line at -110 (pushes excluded); edge = model - line\n",
          "| method | bucket | n | hit% | ROI% |", "|---|---|---|---|---|"]
    for name, c in methods[:-1]:
        edge = d[c] - d.line
        for lo, hi in ((3, 5), (5, 7), (7, 99), (3, 99)):
            m = edge.abs().between(lo, hi, inclusive="left") & (d.actual != d.line)
            if m.sum() == 0:
                L.append(f"| {name} | {lo}-{hi} | 0 | - | - |"); continue
            win = np.sign(edge[m]) == np.sign(d.actual[m] - d.line[m])
            hr = win.mean()
            L.append(f"| {name} | {lo}-{hi if hi<99 else '+'} | {m.sum()} | {100*hr:.1f} | {100*(hr*1.9091-1):+.1f} |")
    return "\n".join(L)


rep = [f"Tuned on 2018-22: best k={bk}, best ridge lam={bl}, D base={base}",
       f"D coefs [int, pace_sum, wind_mph, freezing_outdoor, dome]: {np.round(coef,3).tolist()}",
       f"D_pace coefs [int, pace_sum]: {np.round(coefp,3).tolist()}",
       "Train MAE: " + ", ".join(f"{c}={mae(train,c):.2f}" for _, c in methods[:-1] + [("", "line")]),
       table(test, "TEST 2023-2025"), table(cur, "2026 to date")]
print("\n".join(rep))
open("results.md", "w").write("\n".join(rep))
