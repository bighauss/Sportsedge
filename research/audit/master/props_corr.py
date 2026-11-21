"""P3 — prop distributions, usage redistribution, correlation / joint probability,
portfolio exposure (Theo 22, 36-39, 46; Rusty T1#3, T2#6, joint-probability prompt).
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Sequence

from .odds import ev_per_unit, implied_prob
from . import stats


# ------------------------------------------------------------ distributions

def _norm_cdf(x, mu, sd):
    return 0.5 * (1 + math.erf((x - mu) / (sd * math.sqrt(2))))


def _pois_pmf(k, lam):
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1)) if lam > 0 else float(k == 0)


def _negbin_pmf(k, mean, var):
    if var <= mean:
        return _pois_pmf(k, mean)
    p = mean / var
    r = mean * p / (1 - p)
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                    + r * math.log(p) + k * math.log(1 - p))


def over_under(line: float, mean: float, sd: float | None = None, dist: str = "auto") -> dict:
    """P(over), P(under), P(push) from the projected DISTRIBUTION, not mean-minus-line.

    dist: normal (yards), poisson (TDs, goals, Ks), negbin (over-dispersed counts), auto.
    sd must come from history; if missing for a continuous stat we refuse (no invented inputs).
    """
    if dist == "auto":
        dist = "poisson" if mean < 8 and sd is None else ("negbin" if sd and mean < 15 else "normal")
    if dist == "normal":
        if not sd:
            raise ValueError("sd required for normal — never invent missing inputs")
        if float(line).is_integer():
            pu = _norm_cdf(line - .5, mean, sd)
            pp = _norm_cdf(line + .5, mean, sd) - pu
        else:
            pu, pp = _norm_cdf(line, mean, sd), 0.0
        return {"over": 1 - pu - pp, "under": pu, "push": pp, "dist": dist}
    pmf = (lambda k: _pois_pmf(k, mean)) if dist == "poisson" else (lambda k: _negbin_pmf(k, mean, sd * sd))
    top = int(mean * 6 + 30)
    pu = sum(pmf(k) for k in range(0, math.ceil(line)) if k < line)
    pp = pmf(int(line)) if float(line).is_integer() else 0.0
    po = max(0.0, 1 - pu - pp) if top else 0
    return {"over": po, "under": pu, "push": pp, "dist": dist}


def prop_projection(game_log: Sequence[float], minutes_hist: Sequence[float], proj_minutes: float,
                    opp_factor: float = 1.0, opp_factor_n: int = 0, shrink_k: int = 20) -> dict:
    """Rate × opportunity × opponent adjustment, opponent factor shrunk toward 1 by sample size."""
    if not game_log or not minutes_hist or sum(minutes_hist) == 0:
        raise ValueError("game log required — never invent missing inputs")
    rate = sum(game_log) / sum(minutes_hist)
    w = opp_factor_n / (opp_factor_n + shrink_k)
    adj = 1 + (opp_factor - 1) * w
    mean = rate * proj_minutes * adj
    m = sum(game_log) / len(game_log)
    sd = (sum((x - m) ** 2 for x in game_log) / max(1, len(game_log) - 1)) ** .5
    srt = sorted(game_log)
    return {"mean": mean, "sd_hist": sd, "median_hist": srt[len(srt) // 2], "rate_per_min": rate,
            "opp_adj_applied": adj, "n_games": len(game_log)}


def usage_redistribution(out_player_usage: float, teammates: dict[str, float],
                         hist_with_without: dict[str, tuple[float, float, int]] | None = None,
                         min_n: int = 5) -> dict:
    """Theo 37. With historical with/without splits (usage_with, usage_without, n_without) use
    them; otherwise proportional share — labelled PROPORTIONAL_PRIOR (not evidence)."""
    out = {}
    tot = sum(teammates.values())
    for name, u in teammates.items():
        h = (hist_with_without or {}).get(name)
        if h and h[2] >= min_n:
            out[name] = {"new_usage": h[1], "delta": h[1] - h[0], "basis": f"HISTORICAL_n={h[2]}"}
        else:
            nu = u + out_player_usage * u / tot
            out[name] = {"new_usage": nu, "delta": nu - u, "basis": "PROPORTIONAL_PRIOR"}
    return out


# ------------------------------------------------------------ correlation

def joint_hit_rates(rows: Sequence[dict], pair_key=("game_id",), min_n: int = 30) -> list[dict]:
    """Empirical P(A and B) vs P(A)P(B) for market-pairs sharing a game (or player).
    rows need: game_id, market, side, result. Brier of independence vs empirical joint.
    """
    by_group = defaultdict(dict)
    for r in rows:
        if r.get("result") not in ("W", "L"):
            continue
        g = tuple(r.get(k) for k in pair_key)
        by_group[g][(r.get("market"), r.get("side"), r.get("player"))] = (r["result"] == "W", float(r.get("model_prob", .5)))
    pairs = defaultdict(list)
    for legs in by_group.values():
        ks = sorted(legs, key=str)
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                a, b = ks[i], ks[j]
                typ = (a[0], a[1], b[0], b[1], "same_player" if a[2] and a[2] == b[2] else "same_game")
                pairs[typ].append((legs[a], legs[b]))
    out = []
    for typ, obs in pairs.items():
        n = len(obs)
        pa = sum(o[0][0] for o in obs) / n
        pb = sum(o[1][0] for o in obs) / n
        pab = sum(o[0][0] and o[1][0] for o in obs) / n
        hits = [int(o[0][0] and o[1][0]) for o in obs]
        ind = [o[0][1] * o[1][1] for o in obs]
        denom = math.sqrt(pa * (1 - pa) * pb * (1 - pb)) or 1e-9
        out.append({"pair": typ, "n": n, "p_a": pa, "p_b": pb, "p_joint": pab,
                    "p_indep": pa * pb, "lift": pab / (pa * pb) if pa * pb else None,
                    "phi": (pab - pa * pb) / denom,
                    "brier_independence": stats.brier(ind, hits),
                    "supported": n >= min_n, "note": "SMALL_SAMPLE" if n < min_n else ""})
    return sorted(out, key=lambda x: -abs(x["phi"]))


def effective_n(n: int, avg_corr: float, cluster_size: float) -> float:
    """Design effect: n_eff = n / (1 + (m-1)·rho). Shows why correlated wins look too convincing."""
    return n / (1 + (cluster_size - 1) * max(0.0, avg_corr))


def portfolio_exposure(bets: Sequence[dict], corr: dict[tuple, float] | None = None,
                       default_same_game: float = 0.0, iters: int = 20000, seed: int = 5) -> dict:
    """Today's slate (Theo 22). bets: [{id, game_id, model_prob, odds, stake}].
    Simulates with a Gaussian copula using supplied correlations (pairs by id);
    unknown same-game pairs use default_same_game (0 = assume none, flagged)."""
    rng = random.Random(seed)
    n = len(bets)
    C = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    unknown = []
    for i in range(n):
        for j in range(i + 1, n):
            key = (bets[i]["id"], bets[j]["id"])
            c = (corr or {}).get(key, (corr or {}).get(key[::-1]))
            if c is None and bets[i].get("game_id") == bets[j].get("game_id"):
                c = default_same_game
                unknown.append(key)
            C[i][j] = C[j][i] = c or 0.0
    L = _cholesky(C)
    inv = [_norm_ppf(float(b["model_prob"])) for b in bets]
    from .odds import american_to_decimal
    pnl = []
    for _ in range(iters):
        z = [rng.gauss(0, 1) for _ in range(n)]
        x = [sum(L[i][k] * z[k] for k in range(i + 1)) for i in range(n)]
        tot = 0.0
        for i, b in enumerate(bets):
            s = float(b.get("stake", 1))
            tot += s * (american_to_decimal(float(b["odds"])) - 1) if x[i] < inv[i] else -s
        pnl.append(tot)
    pnl.sort()
    ev = sum(ev_per_unit(float(b["model_prob"]), float(b["odds"])) * float(b.get("stake", 1)) for b in bets)
    return {"expected_units": ev, "p5_units": pnl[len(pnl) // 20], "worst_case": -sum(float(b.get("stake", 1)) for b in bets),
            "p_all_lose": sum(p == pnl[0] for p in pnl) / iters, "sd_units": stats_sd(pnl),
            "unknown_same_game_pairs": unknown}


def stats_sd(xs):
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** .5


def _cholesky(A):
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                L[i][j] = math.sqrt(max(A[i][i] - s, 1e-12))
            else:
                L[i][j] = (A[i][j] - s) / L[j][j]
    return L


def _norm_ppf(p):
    lo, hi = -10.0, 10.0
    for _ in range(80):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if 0.5 * (1 + math.erf(m / math.sqrt(2))) < p else (lo, m)
    return (lo + hi) / 2


def sgp_check(legs: Sequence[dict], offered_odds: float, joint_prob: float | None = None) -> dict:
    """Theo 39. legs: [{model_prob, odds}]. Without an empirical joint prob we only report
    the independence number and mark the parlay UNPRICED_CORRELATION."""
    ind = math.prod(float(l["model_prob"]) for l in legs)
    p = joint_prob if joint_prob is not None else ind
    return {"independence_prob": ind, "used_prob": p, "book_implied": implied_prob(offered_odds),
            "ev_per_unit": ev_per_unit(p, offered_odds),
            "status": "PRICED" if joint_prob is not None else "UNPRICED_CORRELATION"}
