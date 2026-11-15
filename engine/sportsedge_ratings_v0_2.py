#!/usr/bin/env python3
"""SportsEdge own-ratings projector (v0, Nov 11 2026). Needs only numpy.

Builds OUR team ratings from game results, then writes home_proj / away_proj into a
board so sportsedge_v2/v5 price every market (full-game spread, ML, total, team totals,
halves, props) in PROJECTION mode instead of ANCHOR mode.

Run:  python sportsedge_ratings.py games.csv board.csv  [--prior priors.csv] [--blend 0.6]
Out:  board_proj.csv  (same board, projections filled)  +  ratings.csv

games.csv - one row per completed game (any sport that scores points/runs/goals):
  sport,date,home,away,home_pts,away_pts,neutral,poss
  poss = possessions (CBB/NBA) if known; blank -> estimated from points.
  neutral = 1 for neutral site, else blank/0.

priors.csv (optional, how early-season noise is tamed):
  sport,team,off,def,pace     off/def = points per 100 poss above/below league avg
  Any free source (last season's final ratings, preseason ratings, returning-minutes
  adjusted). Priors are shrunk toward as results come in; weight = PRIOR_GAMES.

Model, per sport:
  points(team A vs B) = pace(A,B) * (LG + off_A - def_B + hca*site) / 100
  pace(A,B)           = LG_PACE + pace_A + pace_B
  Fitted by ridge least squares on every game (each game = 2 observations),
  recency-weighted (half-life HALF_LIFE days), priors as pseudo-games.
"""
import csv, sys, math, datetime as dt
import numpy as np

CFG = {  # league average per-100 efficiency, pace, home edge (pts/100), shrink
    "CBB": dict(lg=104.0, pace=68.0, hca=3.2, ridge=4.0),
    "NBA": dict(lg=114.0, pace=99.0, hca=2.0, ridge=6.0),
    "CFB": dict(lg=28.0, pace=1.0, hca=2.8, ridge=3.0),   # football: pace=1, "poss" ignored, units = points/game
    "NFL": dict(lg=22.5, pace=1.0, hca=1.6, ridge=5.0),
    "NHL": dict(lg=3.05, pace=1.0, hca=0.12, ridge=8.0),
    "MLB": dict(lg=4.4, pace=1.0, hca=0.12, ridge=10.0),
}
HALF_LIFE, PRIOR_GAMES_DEFAULT = 45.0, 6.0
# prior weight in games: heavy early (CBB/NBA/NHL in Nov), light once a season is mostly played
PRIOR_W = {"CBB": 6.0, "NBA": 4.0, "NHL": 4.0, "CFB": 2.0, "NFL": 2.0, "MLB": 6.0}
# margin stretch: CBB fitted ~1.30 vs DK on Nov 11 2026 (37 games); 1.25 until backtested on results
MARGIN_K = {"CBB": 1.25}

def f(x):
    x = (x or "").strip()
    return float(x) if x else None

def poss_est(sport, hp, ap):
    c = CFG[sport]
    return c["pace"] if c["pace"] == 1.0 else (hp + ap) / (2 * c["lg"] / 100)

def fit(sport, games, priors, today):
    c = CFG[sport]
    PRIOR_GAMES = PRIOR_W.get(sport, PRIOR_GAMES_DEFAULT)
    teams = sorted({g["home"] for g in games} | {g["away"] for g in games} | set(priors))
    ix = {t: i for i, t in enumerate(teams)}; n = len(teams)
    # unknowns: off[n], def[n], pace[n]
    rows, ys, ws, prow, py, pw = [], [], [], [], [], []
    for g in games:
        age = (today - g["date"]).days
        w = 0.5 ** (age / HALF_LIFE)
        P = g["poss"] or poss_est(sport, g["hp"], g["ap"])
        site = 0 if g["neutral"] else 1
        for t, o, pts, s in ((g["home"], g["away"], g["hp"], site), (g["away"], g["home"], g["ap"], -site)):
            r = np.zeros(2 * n); r[ix[t]] = 1; r[n + ix[o]] = -1
            eff = pts / P * (100 if c["pace"] != 1.0 else 1) - c["lg"] - c["hca"] * s / 2
            rows.append(r); ys.append(eff); ws.append(w)
        if c["pace"] != 1.0:
            r = np.zeros(n); r[ix[g["home"]]] = 1; r[ix[g["away"]]] = 1
            prow.append(r); py.append(P - c["pace"]); pw.append(w)
    # ridge pulls toward the prior (not toward 0) for teams that have one
    A = np.array(rows) if rows else np.zeros((0, 2 * n)); y = np.array(ys); W = np.array(ws)
    reg = np.eye(2 * n) * c["ridge"]; tgt = np.zeros(2 * n)
    for t, (o, d, _) in priors.items():          # priors as pseudo-observations
        reg[ix[t], ix[t]] += PRIOR_GAMES; tgt[ix[t]] += (PRIOR_GAMES + c["ridge"]) * o
        reg[n + ix[t], n + ix[t]] += PRIOR_GAMES; tgt[n + ix[t]] += (PRIOR_GAMES + c["ridge"]) * d
    x = np.linalg.solve(A.T @ (A * W[:, None]) + reg, A.T @ (W * y) + tgt)
    pace = np.zeros(n)
    for t, (_, _, p) in priors.items():
        if p is not None: pace[ix[t]] = p
    if prow:
        B = np.array(prow); pw = np.array(pw); preg = np.eye(n) * c["ridge"]; ptg = np.zeros(n)
        for t, (_, _, p) in priors.items():
            if p is not None: preg[ix[t], ix[t]] += PRIOR_GAMES; ptg[ix[t]] += (PRIOR_GAMES + c["ridge"]) * p
        pace = np.linalg.solve(B.T @ (B * pw[:, None]) + preg, B.T @ (pw * np.array(py)) + ptg)
    gp = {t: 0 for t in teams}
    for g in games: gp[g["home"]] += 1; gp[g["away"]] += 1
    return {t: dict(off=x[ix[t]], dfn=x[n + ix[t]], pace=pace[ix[t]], gp=gp[t]) for t in teams}

def project(sport, R, home, away, neutral=False):
    c = CFG[sport]; h, a = R.get(home), R.get(away)
    if h is None or a is None: return None
    s = 0 if neutral else 1
    P = c["pace"] + h["pace"] + a["pace"] if c["pace"] != 1.0 else 1.0
    k = 100 if c["pace"] != 1.0 else 1
    hp = P * (c["lg"] + h["off"] - a["dfn"] + c["hca"] * s / 2) / k
    ap = P * (c["lg"] + a["off"] - h["dfn"] - c["hca"] * s / 2) / k
    k_m = MARGIN_K.get(sport, 1.0)               # efficiency margins run compressed vs real blowouts
    mid, half = (hp + ap) / 2, (hp - ap) / 2 * k_m
    return mid + half, mid - half

def main():
    args = sys.argv[1:]
    prior_path = args[args.index("--prior") + 1] if "--prior" in args else None
    blend = float(args[args.index("--blend") + 1]) if "--blend" in args else 1.0
    games_path, board_path = [a for a in args if not a.startswith("--") and a not in (prior_path, str(blend))][:2]
    games, priors = {}, {}
    for r in csv.DictReader(open(games_path, encoding="utf-8-sig")):
        sp = r["sport"].upper()
        games.setdefault(sp, []).append(dict(date=dt.date.fromisoformat(r["date"]), home=r["home"], away=r["away"],
            hp=float(r["home_pts"]), ap=float(r["away_pts"]), neutral=(r.get("neutral") or "0").strip() == "1", poss=f(r.get("poss"))))
    if prior_path:
        for r in csv.DictReader(open(prior_path, encoding="utf-8-sig")):
            priors.setdefault(r["sport"].upper(), {})[r["team"]] = (float(r["off"]), float(r["def"]), f(r.get("pace")))
    today = dt.date.today()
    R = {sp: fit(sp, g, priors.get(sp, {}), today) for sp, g in games.items()}
    for sp in priors:
        if sp not in R: R[sp] = fit(sp, [], priors[sp], today)
    with open("ratings.csv", "w", newline="") as fo:
        w = csv.writer(fo); w.writerow(["sport", "team", "off", "def", "pace", "games"])
        for sp, tr in R.items():
            for t, v in sorted(tr.items(), key=lambda kv: -(kv[1]["off"] + kv[1]["dfn"])):
                w.writerow([sp, t, f"{v['off']:.2f}", f"{v['dfn']:.2f}", f"{v['pace']:.2f}", v["gp"]])
    rows = list(csv.DictReader(open(board_path, encoding="utf-8-sig")))
    miss = set()
    for r in rows:
        sp = r["sport"].upper()
        if sp not in R or r.get("home_proj"): continue
        pj = project(sp, R[sp], r["home"], r["away"])
        if pj is None: miss.add((sp, r["home"], r["away"])); continue
        # blend < 1 leaves room for the engine's market anchor: written as-is, the engine
        # treats these as the projection; blending vs the book is done by the caller.
        r["home_proj"], r["away_proj"] = f"{pj[0]:.2f}", f"{pj[1]:.2f}"
        r["proj_blend"] = str(blend)
    fields = list(rows[0].keys()) + (["proj_blend"] if "proj_blend" not in rows[0] else [])
    with open("board_proj.csv", "w", newline="") as fo:
        w = csv.DictWriter(fo, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    print(f"ratings.csv + board_proj.csv written; {len(miss)} games had a team with no data:")
    for m in sorted(miss): print("  ", *m)

if __name__ == "__main__":
    main()
