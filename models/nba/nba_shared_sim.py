"""NBA shared game simulation: one set of draws prices EVERY market. PAPER / 0u.

Mirrors the NFL standard (showdown_mc -> markets.py): a single Monte Carlo per
game feeds ML, spread, total, team totals, 1H/2H/1Q-4Q markets, overtime, and
player PTS/REB/AST/3PM/PRA props, so every market is internally consistent.

Model per draw:
  * game pace factor  g ~ Normal(1, PACE_SD)            (shared by both teams)
  * team quarter points  Q_tq = mu_t*share_q*g + e_tq,  e ~ Normal(0, QSD)
    with a shared within-game shock (correlated totals) and team-specific noise
  * tied after regulation -> 5-min OT periods until decided (OT_SCALE of a quarter)
  * player stat X ~ Poisson(rate * team_factor) where team_factor = team points
    drawn / team mean (PTS and 3PM) or pace factor (REB, AST); PRA is the sum of
    the SAME draws (never inferred from separate means).
Constants are calibrated so full-game SDs match the existing analytic model
(margin ~12.5, total ~18); they are starting values, not fitted weights.
Settlement: integer lines push; 2-way period moneylines refund a tied period;
full-game ML includes OT.
"""
from __future__ import annotations

import hashlib
import json
import math
import random

QUARTER_SHARE = (0.252, 0.250, 0.250, 0.248)
PACE_SD = 0.035
Q_SHARED_SD = 2.7      # within-quarter shock common to both teams (total variance)
Q_TEAM_SD = 4.3        # team-specific quarter noise (margin variance)
OT_SCALE = 5 / 12


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


def simulate(home_mean, away_mean, players=(), n=20000, seed=7):
    """players: [{name, team: 'home'|'away', pts, reb, ast, fg3}] per-game means.
    Returns dict of per-draw arrays."""
    rng = random.Random(seed)
    H, A = [], []
    HQ = [[] for _ in range(4)]
    AQ = [[] for _ in range(4)]
    OT = []
    stats = {p["name"]: {k: [] for k in ("pts", "reb", "ast", "fg3")} for p in players}
    for _ in range(n):
        g = rng.gauss(1.0, PACE_SD)
        h = a = 0.0
        for q, s in enumerate(QUARTER_SHARE):
            shared = rng.gauss(0, Q_SHARED_SD)
            hq = home_mean * s * g + shared + rng.gauss(0, Q_TEAM_SD)
            aq = away_mean * s * g + shared + rng.gauss(0, Q_TEAM_SD)
            hq, aq = round(max(hq, 0)), round(max(aq, 0))
            HQ[q].append(hq); AQ[q].append(aq)
            h += hq; a += aq
        ots = 0
        while h == a:
            ots += 1
            sh = rng.gauss(0, Q_SHARED_SD * math.sqrt(OT_SCALE))
            h += round(max(home_mean * 0.25 * OT_SCALE * g + sh + rng.gauss(0, Q_TEAM_SD * math.sqrt(OT_SCALE)), 0))
            a += round(max(away_mean * 0.25 * OT_SCALE * g + sh + rng.gauss(0, Q_TEAM_SD * math.sqrt(OT_SCALE)), 0))
        H.append(h); A.append(a); OT.append(ots)
        fac = {"home": h / home_mean, "away": a / away_mean}
        for p in players:
            f = fac[p["team"]]
            st = stats[p["name"]]
            st["pts"].append(_poisson(rng, p.get("pts", 0) * f))
            st["fg3"].append(_poisson(rng, p.get("fg3", 0) * f))
            st["reb"].append(_poisson(rng, p.get("reb", 0) * g))
            st["ast"].append(_poisson(rng, p.get("ast", 0) * g))
    for st in stats.values():
        st["pra"] = [a + b + c for a, b, c in zip(st["pts"], st["reb"], st["ast"])]
    sig = json.dumps([home_mean, away_mean, list(players), n, seed], sort_keys=True, default=str)
    return dict(home=H, away=A, hq=HQ, aq=AQ, ot=OT, players=stats, n=n, seed=seed,
                scenario_sha256=hashlib.sha256(sig.encode()).hexdigest())


def _wpl(vals, line, side_over=True):
    """(win, push, loss) for X over/under line."""
    n = len(vals)
    over = sum(v > line for v in vals) / n
    push = sum(v == line for v in vals) / n
    under = 1 - over - push
    return (over, push, under) if side_over else (under, push, over)


def price(sim, market, selection, line=None):
    """Return (p_win, p_push, p_loss) from the shared draws.
    market: ML, SPREAD, TOTAL, TT_HOME, TT_AWAY, 1H_ML, 1H_SPREAD, 1H_TOTAL,
            2H_*, Q1..Q4_ML/SPREAD/TOTAL, PROP_<PTS|REB|AST|FG3|PRA>.
    selection: 'home'/'away' for sides, 'over'/'under' for totals and props;
    props also need sim['players'] key via selection 'over:<name>'."""
    H, A = sim["home"], sim["away"]
    if market.startswith("PROP_"):
        side, name = selection.split(":", 1)
        vals = sim["players"][name][market[5:].lower()]
        return _wpl(vals, line, side == "over")
    seg, base = "FG", market
    for pre in ("1H_", "2H_", "Q1_", "Q2_", "Q3_", "Q4_"):
        if market.startswith(pre):
            seg, base = pre[:-1], market[len(pre):]
    if seg == "FG":
        h, a = H, A
    elif seg == "1H":
        h = [x + y for x, y in zip(sim["hq"][0], sim["hq"][1])]
        a = [x + y for x, y in zip(sim["aq"][0], sim["aq"][1])]
    elif seg == "2H":   # 2H markets include OT at most books
        h = [t - x - y for t, x, y in zip(H, sim["hq"][0], sim["hq"][1])]
        a = [t - x - y for t, x, y in zip(A, sim["aq"][0], sim["aq"][1])]
    else:
        q = int(seg[1]) - 1
        h, a = sim["hq"][q], sim["aq"][q]
    n = len(h)
    if base in ("TOTAL", "TT_HOME", "TT_AWAY"):
        vals = ([x + y for x, y in zip(h, a)] if base == "TOTAL" else h if base == "TT_HOME" else a)
        return _wpl(vals, line, selection == "over")
    d = [x - y for x, y in zip(h, a)] if selection == "home" else [y - x for x, y in zip(h, a)]
    if base == "ML":
        win = sum(v > 0 for v in d) / n
        tie = sum(v == 0 for v in d) / n     # 0 for full game (OT); refunded for 2-way periods
        return win, tie, 1 - win - tie
    if base == "SPREAD":
        win = sum(v + line > 0 for v in d) / n
        push = sum(v + line == 0 for v in d) / n
        return win, push, 1 - win - push
    raise ValueError("unknown market " + market)


def ev(win, push, american):
    d = 1 + (american / 100 if american > 0 else 100 / -american)
    return win * (d - 1) - (1 - win - push)
