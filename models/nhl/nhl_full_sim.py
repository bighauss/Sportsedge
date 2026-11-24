"""NHL full shared game simulation: one set of draws prices EVERY market. PAPER / 0u.

Mirrors the NFL standard. Extends the research team-scenario idea to full-game
settlement. Per draw:
  * game pace g ~ Gamma(mean 1, sd PACE_SD) shared by both teams
  * shots per team per period ~ Poisson(shots_mean * share * g); each shot scores
    with the team's shooting% (goals = Binomial thinning of shots)
  * empty-net goal when trailing by 1 / 2 after regulation goals (frozen model
    defaults en_p_lead1/en_p_lead2 read from sportsedge_nhl_model.W)
  * regulation tie -> 3v3 OT (P(goal) ~ 0.55, side by shot share) else shootout;
    the OT/SO winner gets +1 final goal (DK settlement); 3-way ML uses regulation
  * skater shots/goals/assists allocated from the SAME team shots/goals by each
    skater's share, so SOG, goals, assists and points props are consistent
Markets: ML (incl OT/SO), ML3 (regulation), PL, TOTAL, TT, P1-P3 ML2/ML3/TOTAL,
PROP_SOG/GOALS/ASSISTS/POINTS. Challenger only.
"""
from __future__ import annotations

import hashlib
import json
import math
import random

import sportsedge_nhl_model as NM

PERIOD_SHARE = (0.32, 0.33, 0.35)
PACE_SD = 0.08
OT_GOAL_P = 0.55


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def simulate(home_goals, away_goals, home_shots=31.0, away_shots=29.0, skaters=(), n=20000, seed=7):
    """skaters: [{name, team, shot_share, goal_share, assist_share}] shares of team shots/goals/assists."""
    rng = random.Random(seed)
    sp = {"home": home_goals / home_shots, "away": away_goals / away_shots}
    sh = {"home": home_shots, "away": away_shots}
    e1, e2 = NM.W["en_p_lead1"], NM.W["en_p_lead2"]
    out = dict(home=[], away=[], reg_home=[], reg_away=[], ot=[], so=[],
               hp=[[] for _ in range(3)], ap=[[] for _ in range(3)])
    sk = {s["name"]: {"sog": [], "goals": [], "assists": []} for s in skaters}
    for _ in range(n):
        shape = 1 / PACE_SD ** 2
        g = rng.gammavariate(shape, 1 / shape)
        tg = {"home": 0, "away": 0}; ts = {"home": 0, "away": 0}
        for i, s in enumerate(PERIOD_SHARE):
            for side, key in (("home", "hp"), ("away", "ap")):
                shots = _poisson(rng, sh[side] * s * g)
                goals = sum(rng.random() < sp[side] for _ in range(shots))
                out[key][i].append(goals); tg[side] += goals; ts[side] += shots
        out["reg_home"].append(tg["home"]); out["reg_away"].append(tg["away"])
        d = tg["home"] - tg["away"]
        if abs(d) in (1, 2) and rng.random() < (e1 if abs(d) == 1 else e2):
            tg["home" if d > 0 else "away"] += 1
        ot = so = 0
        if tg["home"] == tg["away"]:
            share_h = home_shots / (home_shots + away_shots)
            if rng.random() < OT_GOAL_P:
                ot = 1
            else:
                so = 1
            win_home = rng.random() < (share_h if ot else 0.5 + (share_h - 0.5) * 0.3)
            tg["home" if win_home else "away"] += 1
        out["ot"].append(ot); out["so"].append(so)
        out["home"].append(tg["home"]); out["away"].append(tg["away"])
        for s in skaters:
            side = s["team"]
            st = sk[s["name"]]
            goals_scored = tg[side] - (1 if so and tg[side] > tg["away" if side == "home" else "home"] else 0)
            st["sog"].append(sum(rng.random() < s["shot_share"] for _ in range(ts[side])))
            st["goals"].append(sum(rng.random() < s["goal_share"] for _ in range(goals_scored)))
            st["assists"].append(sum(rng.random() < s["assist_share"] for _ in range(goals_scored * 2)))
    for st in sk.values():
        st["points"] = [a + b for a, b in zip(st["goals"], st["assists"])]
    sig = json.dumps([home_goals, away_goals, home_shots, away_shots, list(skaters), n, seed, e1, e2], sort_keys=True, default=str)
    out.update(skaters=sk, n=n, seed=seed, scenario_sha256=hashlib.sha256(sig.encode()).hexdigest())
    return out


def _wpl(vals, line, over=True):
    n = len(vals)
    o = sum(v > line for v in vals) / n
    p = sum(v == line for v in vals) / n
    return (o, p, 1 - o - p) if over else (1 - o - p, p, o)


def price(sim, market, selection, line=None):
    """Returns (win, push, loss). selection 'home'/'away'/'draw' or 'over'/'under';
    props: market PROP_<SOG|GOALS|ASSISTS|POINTS>, selection 'over:<name>'."""
    if market.startswith("PROP_"):
        side, name = selection.split(":", 1)
        return _wpl(sim["skaters"][name][market[5:].lower()], line, side == "over")
    H, A = sim["home"], sim["away"]
    n = len(H)
    if market[:2] in ("P1", "P2", "P3"):
        k = int(market[1]) - 1
        h, a = sim["hp"][k], sim["ap"][k]
        base = market[3:]
        if base == "TOTAL":
            return _wpl([x + y for x, y in zip(h, a)], line, selection == "over")
        if base in ("ML2", "ML3"):
            if selection == "draw":
                w = sum(x == y for x, y in zip(h, a)) / n
                return w, 0.0, 1 - w
            w = sum((x > y) if selection == "home" else (y > x) for x, y in zip(h, a)) / n
            t = sum(x == y for x, y in zip(h, a)) / n
            return (w, t, 1 - w - t) if base == "ML2" else (w, 0.0, 1 - w)
    if market == "ML3":
        rh, ra = sim["reg_home"], sim["reg_away"]
        if selection == "draw":
            w = sum(x == y for x, y in zip(rh, ra)) / n
        else:
            w = sum((x > y) if selection == "home" else (y > x) for x, y in zip(rh, ra)) / n
        return w, 0.0, 1 - w
    if market in ("TOTAL", "TT_HOME", "TT_AWAY"):
        vals = [x + y for x, y in zip(H, A)] if market == "TOTAL" else H if market == "TT_HOME" else A
        return _wpl(vals, line, selection == "over")
    dm = [x - y for x, y in zip(H, A)] if selection == "home" else [y - x for x, y in zip(H, A)]
    if market == "ML":
        w = sum(v > 0 for v in dm) / n
        return w, 0.0, 1 - w
    if market == "PL":
        w = sum(v + line > 0 for v in dm) / n
        p = sum(v + line == 0 for v in dm) / n
        return w, p, 1 - w - p
    raise ValueError("unknown market " + market)


def ev(win, push, american):
    d = 1 + (american / 100 if american > 0 else 100 / -american)
    return win * (d - 1) - (1 - win - push)
