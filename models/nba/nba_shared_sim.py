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

Integrity (audit round 2):
  * team draws use their own RNG stream; each player uses a stream keyed by
    (seed, player id), so adding/removing a player never changes team scores
    or other players' draws for the same seed.
  * listed players' points never exceed their team's points in any draw
    (deterministic trim: non-three points first, then threes).
  * players carry a stable 'id' (defaults to name); ids must be unique.
  * inputs, lines and EV arguments are range-checked; OT is capped.
  * scenario_sha256 hashes inputs; draws_sha256 hashes every generated draw.
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
MAX_N = 1_000_000
TEAM_MEAN_RANGE = (40.0, 200.0)
STAT_KEYS = ("pts", "reb", "ast", "fg3")

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


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _pid(p):
    return str(p.get("id", p.get("name")))


def _check_inputs(home_mean, away_mean, players, n, seed):
    for lbl, m in (("home_mean", home_mean), ("away_mean", away_mean)):
        if not _finite(m) or not TEAM_MEAN_RANGE[0] <= m <= TEAM_MEAN_RANGE[1]:
            raise ValueError(f"{lbl} must be finite in {TEAM_MEAN_RANGE}, got {m!r}")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_N:
        raise ValueError(f"n must be an int in 1..{MAX_N}")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an int")
    seen = set()
    team_pts = {"home": 0.0, "away": 0.0}
    for p in players:
        if not p.get("name") and p.get("id") is None:
            raise ValueError("player needs an id or name")
        pid = _pid(p)
        if p.get("team") not in SIDES:
            raise ValueError(f"player {pid!r}: team must be 'home' or 'away'")
        if pid in seen:
            raise ValueError(f"duplicate player id {pid!r}")
        seen.add(pid)
        for k in STAT_KEYS:
            v = p.get(k, 0)
            if not _finite(v) or v < 0:
                raise ValueError(f"player {pid!r}: {k} must be finite and >= 0")
        if p.get("pts", 0) < 3 * p.get("fg3", 0):
            raise ValueError(f"player {pid!r}: pts mean below 3 x fg3 mean")
        team_pts[p["team"]] += p.get("pts", 0)
    for t, mean in (("home", home_mean), ("away", away_mean)):
        if team_pts[t] > mean:
            raise ValueError(f"{t} players' pts means sum above team mean")


def _player_rng(seed, pid):
    h = hashlib.sha256(f"nba-player|{seed}|{pid}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _trim_to_team(rows, team_pts):
    """rows: list of [pts, fg3] for one team's players in one draw (mutated).
    Remove points deterministically until sum(pts) <= team_pts; keeps 3*fg3 <= pts."""
    excess = sum(r[0] for r in rows) - team_pts
    while excess > 0:
        # largest non-three points first
        r = max(rows, key=lambda r: (r[0] - 3 * r[1], r[0]))
        other = r[0] - 3 * r[1]
        if other > 0:
            cut = min(other, excess)
            r[0] -= cut
            excess -= cut
            continue
        r = max(rows, key=lambda r: r[1])
        if r[1] == 0:
            break
        r[1] -= 1
        r[0] -= 3
        excess -= 3


def simulate(home_mean, away_mean, players=(), n=20000, seed=7):
    """players: [{name, team: 'home'|'away', pts, reb, ast, fg3}] per-game means.
    Returns dict of per-draw arrays."""
    players = list(players)
    _check_inputs(home_mean, away_mean, players, n, seed)
    rng = random.Random(seed)                     # team stream only
    prng = {_pid(p): _player_rng(seed, _pid(p)) for p in players}
    H, A = [], []
    HQ = [[] for _ in range(4)]
    AQ = [[] for _ in range(4)]
    OT = []
    stats = {_pid(p): {k: [] for k in STAT_KEYS} for p in players}
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
            if ots >= MAX_OT:
                raise RuntimeError("OT cap reached; check inputs")
            ots += 1
            sh = rng.gauss(0, Q_SHARED_SD * math.sqrt(OT_SCALE))
            h += round(max(home_mean * 0.25 * OT_SCALE * g + sh + rng.gauss(0, Q_TEAM_SD * math.sqrt(OT_SCALE)), 0))
            a += round(max(away_mean * 0.25 * OT_SCALE * g + sh + rng.gauss(0, Q_TEAM_SD * math.sqrt(OT_SCALE)), 0))
        H.append(h); A.append(a); OT.append(ots)
        fac = {"home": h / home_mean, "away": a / away_mean}
        rows = {"home": [], "away": []}
        draw = {}
        for p in players:
            pid, f, r = _pid(p), fac[p["team"]], prng[_pid(p)]
            m3 = _poisson(r, p.get("fg3", 0) * f)
            other = _poisson(r, (p.get("pts", 0) - 3 * p.get("fg3", 0)) * f)
            row = [3 * m3 + other, m3]
            rows[p["team"]].append(row)
            draw[pid] = (row, _poisson(r, p.get("reb", 0) * g), _poisson(r, p.get("ast", 0) * g))
        _trim_to_team(rows["home"], h)
        _trim_to_team(rows["away"], a)
        for pid, (row, reb, ast) in draw.items():
            st = stats[pid]
            st["pts"].append(row[0]); st["fg3"].append(row[1])
            st["reb"].append(reb); st["ast"].append(ast)
    for st in stats.values():
        st["pra"] = [a + b + c for a, b, c in zip(st["pts"], st["reb"], st["ast"])]
    sig = json.dumps([home_mean, away_mean, players, n, seed], sort_keys=True, default=str)
    draws = json.dumps([H, A, HQ, AQ, OT, stats], sort_keys=True, separators=(",", ":"))
    return dict(home=H, away=A, hq=HQ, aq=AQ, ot=OT, players=stats, n=n, seed=seed,
                scenario_sha256=hashlib.sha256(sig.encode()).hexdigest(),
                draws_sha256=hashlib.sha256(draws.encode()).hexdigest())


def _wpl(vals, line, side_over=True):
    """(win, push, loss) for X over/under line."""
    n = len(vals)
    over = sum(v > line for v in vals) / n
    push = sum(v == line for v in vals) / n
    under = 1 - over - push
    return (over, push, under) if side_over else (under, push, over)


def _need_line(line, market):
    if not _finite(line) or abs(line) > 400:
        raise ValueError(f"{market}: finite numeric line required, got {line!r}")


def price(sim, market, selection, line=None, tie_rule=None, ot_rule=None):
    """Return (p_win, p_push, p_loss) from the shared draws.
    market: ML, SPREAD, TOTAL, TT_HOME, TT_AWAY, <SEG>_ML/SPREAD/TOTAL/TT_HOME/TT_AWAY
            for SEG in 1H, 2H, Q1..Q4, and PROP_<PTS|REB|AST|FG3|PRA>.
    selection: 'home'/'away' for ML/SPREAD; 'over'/'under' for totals;
               'over:<name>'/'under:<name>' for props.
    tie_rule: required for period ML ('push' or 'lose').
    ot_rule: required for 2H and Q4 markets ('include' or 'exclude')."""
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
    for lbl, v in (("win", win), ("push", push)):
        if not _finite(v) or not 0 <= v <= 1:
            raise ValueError(f"{lbl} must be a probability in [0, 1]")
    if win + push > 1 + 1e-9:
        raise ValueError("win + push exceeds 1")
    if not _finite(american) or -100 < american < 100:
        raise ValueError("american odds must be finite with |odds| >= 100")
    d = 1 + (american / 100 if american > 0 else 100 / -american)
    return win * (d - 1) - (1 - win - push)
