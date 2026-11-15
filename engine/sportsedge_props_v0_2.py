#!/usr/bin/env python3
"""SportsEdge player-prop projection layer (numpy + stdlib).
Usage: python sportsedge_props.py board.csv players.csv [--out board_props.csv]
       [--outlist out.csv] [--teams teams.csv] [--rosters rosters.csv]
players.csv: sport,player,team,games,minutes,pts,reb,ast,threes
  optional last5 cols: l5_minutes,l5_pts,l5_reb,l5_ast,l5_threes; optional proj_minutes
teams.csv (optional): team,avg_total  (team's season avg game total) -> pace factor
Pace factor = game projected total (home_proj+away_proj, else 'total' line col) / team avg_total; 1.0 if unknown.
"""
import csv, sys, argparse, unicodedata
import numpy as np

STATS = {"POINTS": ["pts"], "REBOUNDS": ["reb"], "ASSISTS": ["ast"], "THREES": ["threes"],
         "PRA": ["pts", "reb", "ast"]}
W_SEASON, W_L5, REDIST, USAGE_CAP = 0.6, 0.4, 0.7, 0.25
MAX_MIN = 40.0

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())

def f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def rates(p):
    mins = f(p["minutes"]) or 0.0
    l5m = f(p.get("l5_minutes"))
    out = {}
    for s in ("pts", "reb", "ast", "threes"):
        r = (f(p.get(s)) or 0.0) / mins if mins else 0.0
        l5 = f(p.get("l5_" + s))
        if l5 is not None and l5m:
            r = W_SEASON * r + W_L5 * (l5 / l5m)
        out[s] = r
    m = f(p.get("proj_minutes"))
    if m is None:
        m = W_SEASON * mins + W_L5 * l5m if l5m else mins
    return out, m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board"); ap.add_argument("players")
    ap.add_argument("--out", default="board_props.csv")
    ap.add_argument("--outlist"); ap.add_argument("--teams")
    ap.add_argument("--rosters", help="team,player,minutes,pts,reb,ast,threes (season per-game)")
    a = ap.parse_args()
    players = {norm(r["player"]): r for r in csv.DictReader(open(a.players))}
    outs = set()
    if a.outlist:
        outs = {norm(r[0]) for r in csv.reader(open(a.outlist)) if r and r[0].lower() != "player"}
    team_avg = {}
    if a.teams:
        team_avg = {r["team"]: f(r["avg_total"]) for r in csv.DictReader(open(a.teams))}
    rows = list(csv.DictReader(open(a.board)))
    fields = list(rows[0].keys()) if rows else []
    for c in ("proj", "proj_minutes", "pace"):
        if c not in fields: fields.append(c)
    # per-player rates/minutes
    model = {}
    for k, p in players.items():
        model[k] = list(rates(p)) + [p["team"]]
    # injury redistribution: REDIST (70%) of each OUT player's minutes and output is spread
    # over the WHOLE team rotation (rosters.csv) by minutes share; board players get only
    # their share. Per-minute usage boost capped at +USAGE_CAP; minutes capped at MAX_MIN.
    roster = {}
    if a.rosters:
        for r in csv.DictReader(open(a.rosters)):
            roster.setdefault(r["team"], {})[norm(r["player"])] = r
    on_board = {norm(r["player"]) for r in rows}
    base = {k: (dict(v[0]), v[1]) for k, v in model.items()}
    for o in outs:
        if o in model:
            r_o, m_o, team = model.pop(o)
        else:
            team = next((t for t, rs in roster.items() if o in rs), None)
            if team is None: continue
            rp = roster[team][o]; m_o = f(rp["minutes"]) or 0.0
            r_o = {s: (f(rp[s]) or 0.0) / m_o if m_o else 0.0 for s in ("pts", "reb", "ast", "threes")}
        if team in roster:
            pool = {k: (model[k][1] if k in model else f(rp["minutes"]) or 0.0)
                    for k, rp in roster[team].items() if k not in outs}
            for k in on_board:  # board players missing from roster file still get a share
                if k in model and model[k][2] == team and k not in outs: pool.setdefault(k, model[k][1])
        else:  # fallback: board teammates only (old behaviour)
            pool = {k: model[k][1] for k in on_board if k in model and model[k][2] == team}
        tot = sum(pool.values())
        if not tot: continue
        for k, mk in pool.items():
            if k not in model: continue  # non-board rotation player absorbs its share
            wi = mk / tot
            r, m, t = model[k]
            new_m = min(m + REDIST * m_o * wi, MAX_MIN)
            for s in r:
                nr = (r[s] * m + REDIST * r_o[s] * m_o * wi) / new_m
                r[s] = min(nr, base[k][0][s] * (1 + USAGE_CAP)) if base[k][0][s] else nr
            model[k] = [r, new_m, t]
    for row in rows:
        k = norm(row.get("player"))
        if row.get("sport", "").upper() != "NBA" or k in outs or k not in model:
            row.setdefault("proj", ""); continue
        mkt = row.get("market", "").upper()
        if mkt not in STATS: continue
        r, m, team = model[k]
        gt = None
        hp, apj = f(row.get("home_proj")), f(row.get("away_proj"))
        if hp and apj: gt = hp + apj
        elif f(row.get("total")): gt = f(row.get("total"))
        avg = team_avg.get(team) or team_avg.get(row.get("team"))
        pace = gt / avg if gt and avg else 1.0
        row["proj"] = round(sum(r[s] for s in STATS[mkt]) * m * pace, 2)
        row["proj_minutes"] = round(m, 1); row["pace"] = round(pace, 3)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"wrote {a.out}: {sum(1 for r in rows if r.get('proj') not in ('', None))}/{len(rows)} rows projected")

if __name__ == "__main__":
    main()
