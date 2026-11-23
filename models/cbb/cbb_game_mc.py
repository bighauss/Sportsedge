"""CBB shared-possession Monte Carlo from the incumbent projection. PAPER / research only.

One simulated game feeds ML, spread, total, team totals, first-half markets and overtime. Player props are
BLOCKED. The per-possession PMF is MODELED (moment-matching device), not empirical: variance is anchored to the
incumbent margin SD (NOT fitted), pace SD is an explicit assumption, and the 3-point share is approximate.
Do not treat output as calibrated. Use only after projections pass validation against real finals.
"""
from __future__ import annotations
import bisect, hashlib, json, math, random

CODE_VERSION = "cbb_game_mc/1"
SIDES = {"ML": ("home", "away"), "SPREAD": ("home", "away"), "H1_SPREAD": ("home", "away"), "H1_ML": ("home", "away"),
         "TOTAL": ("over", "under"), "H1_TOTAL": ("over", "under"), "TT_HOME": ("over", "under"), "TT_AWAY": ("over", "under")}
TIE_RULES = ("LOSE_3WAY", "REFUND")

class Blocked(ValueError):
    pass

def _fin(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x): raise Blocked(f"{name} must be finite number")
    return float(x)

def pmf_from_moments(mean, var, p3):
    two_p2 = (var + mean * mean - 9 * p3) - (mean - 3 * p3); p2 = two_p2 / 2
    p1 = mean - 3 * p3 - 2 * p2; p0 = 1 - p1 - p2 - p3; pmf = (p0, p1, p2, p3)
    if min(pmf) < -1e-12 or abs(sum(pmf) - 1) > 1e-9: raise Blocked("infeasible per-possession PMF for supplied mean/variance/3pt share")
    return tuple(max(0.0, x) for x in pmf)

def simulate(game_id, home_pts, away_pts, poss, p3_home, p3_away, margin_sd, pace_sd, n=20000, seed=7, max_ot=10):
    for v, nme in ((home_pts, "home_pts"), (away_pts, "away_pts"), (poss, "poss"), (p3_home, "p3_home"), (p3_away, "p3_away"),
                   (margin_sd, "margin_sd"), (pace_sd, "pace_sd")): _fin(v, nme)
    if not game_id or type(n) is not int or not 100 <= n <= 100000 or type(seed) is not int: raise Blocked("bad game_id, n or seed")
    if not (45 <= poss <= 90 and 40 <= home_pts <= 130 and 40 <= away_pts <= 130 and 0 <= pace_sd <= 8 and 4 <= margin_sd <= 20):
        raise Blocked("input outside plausible range")
    var = margin_sd ** 2 / (2 * poss); caps = {}
    def _p3(mean, req, who):
        cap = 0.98 * (var + mean * mean - mean) / 6
        if cap <= 0: raise Blocked("variance too small for any 3-point share")
        used = min(req, cap); caps[who] = dict(requested=round(req, 4), used=round(used, 4), capped=used < req); return used
    pm_h = pmf_from_moments(home_pts / poss, var, _p3(home_pts / poss, p3_home, "home"))
    pm_a = pmf_from_moments(away_pts / poss, var, _p3(away_pts / poss, p3_away, "away"))
    ch = [sum(pm_h[:i + 1]) for i in range(4)]; ca = [sum(pm_a[:i + 1]) for i in range(4)]
    rng = random.Random(seed); rnd = rng.random; bl = bisect.bisect_right
    def pts(cum, k):
        s = 0
        for _ in range(k): s += min(3, bl(cum, rnd()))
        return s
    H, A, H1h, H1a, OT, UN = [], [], [], [], [], 0
    for _ in range(n):
        N = max(45, min(95, round(rng.gauss(poss, pace_sd)))); k1 = round(N / 2)
        h1, a1 = pts(ch, k1), pts(ca, k1); h, a = h1 + pts(ch, N - k1), a1 + pts(ca, N - k1); ot = 0
        while h == a and ot < max_ot:
            ot += 1; kk = max(1, round(N * 5 / 40)); h += pts(ch, kk); a += pts(ca, kk)
        if h == a: UN += 1
        H.append(h); A.append(a); H1h.append(h1); H1a.append(a1); OT.append(ot)
    arrays = dict(home=H, away=A, h1_home=H1h, h1_away=H1a, ot=OT)
    sig = json.dumps(dict(v=CODE_VERSION, g=game_id, i=[home_pts, away_pts, poss, p3_home, p3_away, margin_sd, pace_sd, n, seed]), sort_keys=True)
    return dict(game_id=game_id, n=n, seed=seed, unresolved=UN, status="PAPER_NON_COUNTED_UNCALIBRATED", pmf_home=pm_h, pmf_away=pm_a,
                p3_caps=caps, config_sha256=hashlib.sha256(sig.encode()).hexdigest(),
                scenario_sha256=hashlib.sha256(json.dumps(arrays, separators=(",", ":")).encode()).hexdigest(),
                blocked={"PLAYER_PROPS": "NO_PLAYER_FORECAST"}, **arrays)

def _wpl(vals, line, over):
    n = len(vals); o = sum(v > line for v in vals) / n; p = sum(v == line for v in vals) / n; u = 1 - o - p
    return (o, p, u) if over else (u, p, o)

def price(sim, market, side, line=None, tie_rule=None):
    if sim["unresolved"]: raise Blocked("unresolved overtime scenarios present")
    if market not in SIDES: raise Blocked("unsupported market " + str(market))
    if side not in SIDES[market]: raise Blocked("invalid side for market")
    H, A = sim["home"], sim["away"]
    if market == "ML":
        d = [x - y for x, y in zip(H, A)]; d = d if side == "home" else [-x for x in d]
        w = sum(v > 0 for v in d) / len(d); return dict(win=w, push=0.0, loss=1 - w)
    if market == "H1_ML":
        if tie_rule not in TIE_RULES: raise Blocked("H1_ML requires explicit tie_rule LOSE_3WAY or REFUND")
        d = [x - y for x, y in zip(sim["h1_home"], sim["h1_away"])]; d = d if side == "home" else [-x for x in d]
        w = sum(v > 0 for v in d) / len(d); t = sum(v == 0 for v in d) / len(d); pu = t if tie_rule == "REFUND" else 0.0
        return dict(win=w, push=pu, loss=1 - w - pu, tie=t)
    _fin(line, "line")
    if market in ("SPREAD", "H1_SPREAD"):
        h, a = (H, A) if market == "SPREAD" else (sim["h1_home"], sim["h1_away"])
        d = [x - y for x, y in zip(h, a)]; d = d if side == "home" else [-x for x in d]
        w = sum(v + line > 0 for v in d) / len(d); p = sum(v + line == 0 for v in d) / len(d)
        return dict(win=w, push=p, loss=1 - w - p)
    vals = {"TOTAL": [x + y for x, y in zip(H, A)], "H1_TOTAL": [x + y for x, y in zip(sim["h1_home"], sim["h1_away"])], "TT_HOME": H, "TT_AWAY": A}[market]
    w, p, l = _wpl(vals, line, side == "over"); return dict(win=w, push=p, loss=l)

def summary(sim):
    n = sim["n"]; H, A = sim["home"], sim["away"]; mean = lambda v: sum(v) / n
    marg = [x - y for x, y in zip(H, A)]; tot = [x + y for x, y in zip(H, A)]
    sd = lambda v: math.sqrt(sum((x - mean(v)) ** 2 for x in v) / n)
    return dict(home_mean=mean(H), away_mean=mean(A), margin_mean=mean(marg), margin_sd=sd(marg), total_mean=mean(tot),
                total_sd=sd(tot), p_home=sum(x > 0 for x in marg) / n, ot_rate=sum(o > 0 for o in sim["ot"]) / n)

def p3_share(three_pa_rate, three_p_pct):
    return 0.85 * (three_pa_rate / 100) * (three_p_pct / 100)
