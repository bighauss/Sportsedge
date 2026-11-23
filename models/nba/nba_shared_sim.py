"""NBA shared game simulation: one set of draws prices EVERY market. PAPER / 0u.

Mirrors the NFL standard (showdown_mc -> markets.py): a single Monte Carlo per
game feeds ML, spread, total, team totals, 1H/2H/1Q-4Q markets, overtime, and
player PTS/REB/AST/3PM/PRA props, so every market is internally consistent.

Model per draw:
  * game pace factor  g ~ Normal(1, PACE_SD)            (shared by both teams)
  * team quarter points  Q_tq = mu_t*share_q*g + e_tq,  e ~ Normal(0, QSD)
    with a shared within-game shock (correlated totals) and team-specific noise
  * tied after regulation -> 5-min OT periods until decided (OT_SCALE of a quarter)
  * player 3PM ~ Poisson(fg3 * f) and non-three points ~ Poisson((pts - 3*fg3) * f),
    PTS = 3*3PM + non-three points, so 3*3PM <= PTS in every draw (f = team points
    drawn / team mean). REB, AST scale with pace. PRA is the sum of the SAME draws.
Constants are calibrated so full-game SDs match the existing analytic model
(margin ~12.5, total ~18); they are starting values, not fitted weights.

Settlement rules (must be stated by the caller, never assumed):
  * integer lines push; full-game ML includes OT (never ties).
  * period ML (1H/2H/Q1-Q4): caller passes tie_rule='push' (2-way, tie refunded)
    or tie_rule='lose' (3-way book, tie loses both sides). No default.
  * 2H and Q4 markets: caller passes ot_rule='include' or 'exclude'. No default.
    (Q1-Q3 and 1H can never contain OT, so ot_rule is ignored there.)
  * selections are validated; anything else raises ValueError.
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
MAX_OT = 12
MAX_DRAWS = 100000

SIDES = ("home", "away")
OU = ("over", "under")
PROP_STATS = ("pts", "reb", "ast", "fg3", "pra")
SEGMENTS = ("1H", "2H", "Q1", "Q2", "Q3", "Q4")


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


def _finite(v, label, low=None, high=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{label}: finite number required")
    if low is not None and v < low or high is not None and v > high:
        raise ValueError(f"{label}: out of range")
    return v


def _key(p):
    key = p.get("id", p.get("name"))
    if not isinstance(key, str) or not key.strip():
        raise ValueError("player ID/name required")
    return key


def _check_players(players):
    seen = set()
    for p in players:
        if p.get("team") not in SIDES:
            raise ValueError(f"player {p.get('name')!r}: team must be 'home' or 'away'")
        key = _key(p)
        if key in seen:
            raise ValueError(f"duplicate player key {key!r}")
        seen.add(key)
        for stat in ("pts", "reb", "ast", "fg3"):
            _finite(p.get(stat, 0), stat, 0, 300)
        if p.get("pts", 0) < 3 * p.get("fg3", 0):
            raise ValueError(f"player {p['name']!r}: pts mean below 3 x fg3 mean")


def simulate(home_mean, away_mean, players=(), n=20000, seed=7):
    """players: [{name, team: 'home'|'away', pts, reb, ast, fg3}] per-game means.
    Returns dict of per-draw arrays."""
    _finite(home_mean, "home_mean", 1, 300)
    _finite(away_mean, "away_mean", 1, 300)
    if type(n) is not int or not 1 <= n <= MAX_DRAWS:
        raise ValueError("n must be integer 1..100000")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("seed must be unsigned 64-bit integer")
    players = list(players)
    _check_players(players)
    rng = random.Random(seed)
    H, A = [], []
    HQ = [[] for _ in range(4)]
    AQ = [[] for _ in range(4)]
    OT = []
    stats = {_key(p): {k: [] for k in ("pts", "reb", "ast", "fg3")} for p in players}
    ordered = sorted(players, key=_key)
    for draw_index in range(n):
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
            if ots >= MAX_OT:
                raise ValueError("overtime cap exceeded")
            ots += 1
            sh = rng.gauss(0, Q_SHARED_SD * math.sqrt(OT_SCALE))
            h += round(max(home_mean * 0.25 * OT_SCALE * g + sh + rng.gauss(0, Q_TEAM_SD * math.sqrt(OT_SCALE)), 0))
            a += round(max(away_mean * 0.25 * OT_SCALE * g + sh + rng.gauss(0, Q_TEAM_SD * math.sqrt(OT_SCALE)), 0))
        H.append(h); A.append(a); OT.append(ots)
        fac = {"home": h / home_mean, "away": a / away_mean}
        remaining = {"home": int(h), "away": int(a)}
        for p in ordered:
            key = _key(p)
            f = fac[p["team"]]
            st = stats[key]
            digest = hashlib.sha256(f"{seed}|{draw_index}|{key}".encode()).digest()
            prng = random.Random(int.from_bytes(digest[:8], "big"))
            m3 = min(_poisson(prng, p.get("fg3", 0) * f), remaining[p["team"]] // 3)
            remaining[p["team"]] -= 3 * m3
            other = min(_poisson(prng, (p.get("pts", 0) - 3 * p.get("fg3", 0)) * f), remaining[p["team"]])
            remaining[p["team"]] -= other
            st["fg3"].append(m3)
            st["pts"].append(3 * m3 + other)
            st["reb"].append(_poisson(prng, p.get("reb", 0) * g))
            st["ast"].append(_poisson(prng, p.get("ast", 0) * g))
    for st in stats.values():
        st["pra"] = [a + b + c for a, b, c in zip(st["pts"], st["reb"], st["ast"])]
    sig = json.dumps([home_mean, away_mean, players, n, seed], sort_keys=True, default=str)
    result = dict(home=H, away=A, hq=HQ, aq=AQ, ot=OT, players=stats, n=n, seed=seed)
    result["config_sha256"] = hashlib.sha256(sig.encode()).hexdigest()
    result["scenario_sha256"] = draw_sha256(result)
    return result


def draw_sha256(sim):
    payload = {k: sim[k] for k in ("home", "away", "hq", "aq", "ot", "players")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _wpl(vals, line, side_over=True):
    """(win, push, loss) for X over/under line."""
    n = len(vals)
    over = sum(v > line for v in vals) / n
    push = sum(v == line for v in vals) / n
    under = 1 - over - push
    return (over, push, under) if side_over else (under, push, over)


def _need_line(line, market):
    if line is None or not isinstance(line, (int, float)) or isinstance(line, bool) or not math.isfinite(line):
        raise ValueError(f"{market}: numeric line required")


def price(sim, market, selection, line=None, tie_rule=None, ot_rule=None):
    """Return (p_win, p_push, p_loss) from the shared draws.
    market: ML, SPREAD, TOTAL, TT_HOME, TT_AWAY, <SEG>_ML/SPREAD/TOTAL/TT_HOME/TT_AWAY
            for SEG in 1H, 2H, Q1..Q4, and PROP_<PTS|REB|AST|FG3|PRA>.
    selection: 'home'/'away' for ML/SPREAD; 'over'/'under' for totals;
               'over:<name>'/'under:<name>' for props.
    tie_rule: required for period ML ('push' or 'lose').
    ot_rule: required for 2H and Q4 markets ('include' or 'exclude')."""
    if not isinstance(market, str):
        raise ValueError("market must be a string")
    H, A = sim["home"], sim["away"]
    if market.startswith("PROP_"):
        stat = market[5:].lower()
        if stat not in PROP_STATS:
            raise ValueError("unknown prop " + market)
        if not isinstance(selection, str) or ":" not in selection:
            raise ValueError("prop selection must be 'over:<name>' or 'under:<name>'")
        side, name = selection.split(":", 1)
        if side not in OU:
            raise ValueError(f"invalid prop side {side!r}")
        if name not in sim["players"]:
            raise ValueError(f"unknown player {name!r}")
        _need_line(line, market)
        return _wpl(sim["players"][name][stat], line, side == "over")
    seg, base = "FG", market
    for pre in SEGMENTS:
        if market.startswith(pre + "_"):
            seg, base = pre, market[len(pre) + 1:]
    if base not in ("ML", "SPREAD", "TOTAL", "TT_HOME", "TT_AWAY"):
        raise ValueError("unknown market " + market)
    if seg in ("2H", "Q4"):
        if ot_rule not in ("include", "exclude"):
            raise ValueError(f"{market}: ot_rule must be stated ('include' or 'exclude')")
    if seg == "FG":
        h, a = H, A
    elif seg == "1H":
        h = [x + y for x, y in zip(sim["hq"][0], sim["hq"][1])]
        a = [x + y for x, y in zip(sim["aq"][0], sim["aq"][1])]
    elif seg == "2H":
        h = [x + y for x, y in zip(sim["hq"][2], sim["hq"][3])]
        a = [x + y for x, y in zip(sim["aq"][2], sim["aq"][3])]
    else:
        q = int(seg[1]) - 1
        h, a = list(sim["hq"][q]), list(sim["aq"][q])
    if seg in ("2H", "Q4") and ot_rule == "include":
        reg_h = [sum(sim["hq"][q][i] for q in range(4)) for i in range(len(H))]
        reg_a = [sum(sim["aq"][q][i] for q in range(4)) for i in range(len(A))]
        h = [x + t - r for x, t, r in zip(h, H, reg_h)]
        a = [x + t - r for x, t, r in zip(a, A, reg_a)]
    n = len(h)
    if base in ("TOTAL", "TT_HOME", "TT_AWAY"):
        if selection not in OU:
            raise ValueError(f"{market}: selection must be 'over' or 'under', got {selection!r}")
        _need_line(line, market)
        vals = ([x + y for x, y in zip(h, a)] if base == "TOTAL" else h if base == "TT_HOME" else a)
        return _wpl(vals, line, selection == "over")
    if selection not in SIDES:
        raise ValueError(f"{market}: selection must be 'home' or 'away', got {selection!r}")
    d = [x - y for x, y in zip(h, a)] if selection == "home" else [y - x for x, y in zip(h, a)]
    if base == "ML":
        win = sum(v > 0 for v in d) / n
        tie = sum(v == 0 for v in d) / n
        if seg == "FG":                      # OT decides the game: never a tie
            return win, 0.0, 1 - win
        if tie_rule not in ("push", "lose"):
            raise ValueError(f"{market}: tie_rule must be stated ('push' or 'lose')")
        if tie_rule == "lose":
            return win, 0.0, 1 - win
        return win, tie, 1 - win - tie
    _need_line(line, market)
    win = sum(v + line > 0 for v in d) / n
    push = sum(v + line == 0 for v in d) / n
    return win, push, 1 - win - push


def ev(win, push, american):
    _finite(win, "win", 0, 1)
    _finite(push, "push", 0, 1)
    if win + push > 1 + 1e-12:
        raise ValueError("win plus push cannot exceed one")
    _finite(american, "american")
    if -100 < american < 100:
        raise ValueError("invalid American price")
    d = 1 + (american / 100 if american > 0 else 100 / -american)
    return win * (d - 1) - (1 - win - push)
