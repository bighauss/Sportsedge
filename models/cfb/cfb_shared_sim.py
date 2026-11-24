"""CFB shared drive simulation: one set of draws prices EVERY market. PAPER / 0u.

Mirrors the NFL standard (showdown_mc -> markets.py). Per draw:
  * game tempo g ~ Normal(1, TEMPO_SD) sets drives per team (Poisson ~ DRIVES*g)
  * each drive -> TD (7, with 2% missed PAT -> 6), FG (3) or no score; TD/FG
    probabilities are solved so the team's expected points equal its projection
  * drives are spread evenly across the 4 quarters (quarter = drive index bucket)
  * tied after regulation -> college OT rounds (each team: TD p, FG p) until decided
  * team plays ~ Normal(PLAYS*g); player yards = share * team plays * ypp *
    (team points / mean) ** 0.5 with lognormal noise; receptions/attempts Poisson.
Every game, half, quarter, team-total and player-prop market is priced from the
same draws. Constants are starting values (CFB scale), not fitted.
"""
from __future__ import annotations

import hashlib
import json
import math
import random

DRIVES = 12.5
TEMPO_SD = 0.08
PLAYS = 70.0
FG_SHARE = 0.30          # share of scoring drives that are FGs
PAT_MISS = 0.02


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def _drive_probs(mean_pts):
    """Per-drive (p_td, p_fg) so that DRIVES*(6.86*p_td + 3*p_fg) = mean_pts."""
    per = mean_pts / DRIVES
    pts_per_score = (1 - FG_SHARE) * (7 - PAT_MISS) + FG_SHARE * 3
    p_score = min(0.9, per / pts_per_score)
    return p_score * (1 - FG_SHARE), p_score * FG_SHARE


def simulate(home_mean, away_mean, players=(), n=20000, seed=7):
    """players: [{name, team, stat in rush_yds|rec_yds|pass_yds|receptions|pass_att|rush_att, mean}]"""
    rng = random.Random(seed)
    probs = {"home": _drive_probs(home_mean), "away": _drive_probs(away_mean)}
    means = {"home": home_mean, "away": away_mean}
    out = {"home": [], "away": [], "hq": [[] for _ in range(4)], "aq": [[] for _ in range(4)], "ot": []}
    pstats = {(p["name"], p["stat"]): [] for p in players}
    for _ in range(n):
        g = rng.gauss(1.0, TEMPO_SD)
        tot = {}
        # possessions alternate, so both teams share the drive count (+/-1 for who
        # gets the extra drive); drive count is tightly bounded, not Poisson.
        nd_game = max(6, int(round(rng.gauss(DRIVES * g - 0.5, 1.0))))
        extra = "home" if rng.random() < 0.5 else "away"
        for side, key in (("home", "hq"), ("away", "aq")):
            td, fg = probs[side]
            nd = nd_game + (side == extra)
            q = [0, 0, 0, 0]
            for i in range(nd):
                r = rng.random()
                pts = (6 if rng.random() < PAT_MISS else 7) if r < td else 3 if r < td + fg else 0
                q[min(3, i * 4 // nd)] += pts
            for k in range(4):
                out[key][k].append(q[k])
            tot[side] = sum(q)
        ots = 0
        while tot["home"] == tot["away"]:
            ots += 1
            for side in ("home", "away"):
                td, fg = probs[side]
                s = td / (td + fg) * 0.55
                r = rng.random()
                tot[side] += 7 if r < s else 3 if r < s + 0.25 else 0
        out["home"].append(tot["home"]); out["away"].append(tot["away"]); out["ot"].append(ots)
        for p in players:
            f = max(0.2, tot[p["team"]] / max(means[p["team"]], 1)) ** 0.5 * g
            m = p["mean"] * f
            if p["stat"] in ("receptions", "pass_att", "rush_att"):
                v = _poisson(rng, m)
            else:
                v = max(0.0, m * math.exp(rng.gauss(-0.5 * 0.45 ** 2, 0.45)))
                v = int(round(v))
            pstats[(p["name"], p["stat"])].append(v)
    sig = json.dumps([home_mean, away_mean, list(players), n, seed], sort_keys=True, default=str)
    out.update(players=pstats, n=n, seed=seed, scenario_sha256=hashlib.sha256(sig.encode()).hexdigest())
    return out


def _wpl(vals, line, over=True):
    n = len(vals)
    o = sum(v > line for v in vals) / n
    p = sum(v == line for v in vals) / n
    return (o, p, 1 - o - p) if over else (1 - o - p, p, o)


def price(sim, market, selection, line=None):
    """Same interface as nba_shared_sim.price. Props: market 'PROP', selection 'over:<name>:<stat>'."""
    if market == "PROP":
        side, name, stat = selection.split(":")
        return _wpl(sim["players"][(name, stat)], line, side == "over")
    H, A = sim["home"], sim["away"]
    seg, base = "FG", market
    for pre in ("1H_", "2H_", "Q1_", "Q2_", "Q3_", "Q4_"):
        if market.startswith(pre):
            seg, base = pre[:-1], market[len(pre):]
    if seg == "FG":
        h, a = H, A
    elif seg == "1H":
        h = [x + y for x, y in zip(sim["hq"][0], sim["hq"][1])]
        a = [x + y for x, y in zip(sim["aq"][0], sim["aq"][1])]
    elif seg == "2H":
        h = [t - x - y for t, x, y in zip(H, sim["hq"][0], sim["hq"][1])]
        a = [t - x - y for t, x, y in zip(A, sim["aq"][0], sim["aq"][1])]
    else:
        k = int(seg[1]) - 1
        h, a = sim["hq"][k], sim["aq"][k]
    n = len(h)
    if base in ("TOTAL", "TT_HOME", "TT_AWAY"):
        vals = [x + y for x, y in zip(h, a)] if base == "TOTAL" else h if base == "TT_HOME" else a
        return _wpl(vals, line, selection == "over")
    d = [x - y for x, y in zip(h, a)] if selection == "home" else [y - x for x, y in zip(h, a)]
    if base == "ML":
        w = sum(v > 0 for v in d) / n
        t = sum(v == 0 for v in d) / n
        return w, t, 1 - w - t
    if base == "SPREAD":
        w = sum(v + line > 0 for v in d) / n
        p = sum(v + line == 0 for v in d) / n
        return w, p, 1 - w - p
    raise ValueError("unknown market " + market)


def ev(win, push, american):
    d = 1 + (american / 100 if american > 0 else 100 / -american)
    return win * (d - 1) - (1 - win - push)
