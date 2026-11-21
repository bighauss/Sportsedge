"""Uncertainty audits: Monte Carlo sim-count convergence + projection spread (dispersion).

1. Sim noise: SE of a simulated probability = sqrt(p(1-p)/N). A pick is flagged
   when sim noise exceeds `frac` (default 10%) of its edge; reports the N it needs.
2. Dispersion: a model whose SD is too small (e.g. using 61% of the true spread)
   produces too many extreme probabilities. Measures std of z = (actual-mean)/sd,
   interval coverage, extreme-probability share, and a RECOMMENDED SD multiplier
   fit on the earlier half and validated on the later half. Never applied (rule 4).
"""
from __future__ import annotations

import math
import random
from typing import Callable, Sequence

from . import stats


# ------------------------------------------------------------ Monte Carlo sim count

def sim_se(p: float, n: int) -> float:
    return math.sqrt(max(p * (1 - p), 1e-12) / n)


def required_sims(p: float, edge: float, frac: float = 0.10) -> int:
    """Smallest N with sim SE <= frac * |edge|."""
    target = frac * abs(edge)
    if target <= 0:
        return 10 ** 9
    return math.ceil(p * (1 - p) / target ** 2)


def sim_noise_check(rows: Sequence[dict], default_sims: int = 25000, frac: float = 0.10) -> dict:
    """rows: model_prob, odds (or edge), optional n_sims. Flags SIM_NOISE_GT_10PCT_EDGE."""
    from .odds import implied_prob
    out = []
    for r in rows:
        p = float(r["model_prob"])
        edge = float(r["edge"]) if r.get("edge") not in (None, "") else p - implied_prob(float(r["odds"]))
        n = int(r.get("n_sims") or default_sims)
        se = sim_se(p, n)
        need = required_sims(p, edge, frac)
        out.append({"pred_id": r.get("pred_id"), "p": p, "edge": edge, "n_sims": n, "sim_se": se,
                    "noise_to_edge": se / abs(edge) if edge else float("inf"), "sims_needed": need,
                    "flag": "SIM_NOISE_GT_10PCT_EDGE" if n < need else None})
    flagged = [o for o in out if o["flag"]]
    return {"n": len(out), "flagged": len(flagged), "max_sims_needed": max((o["sims_needed"] for o in out), default=0),
            "rows": sorted(out, key=lambda o: -o["noise_to_edge"])}


def sim_convergence(sim_fn: Callable[[int, int], float], counts=(10000, 25000, 50000),
                    seeds: Sequence[int] = range(10)) -> list[dict]:
    """Empirical test from the post: same inputs, different seeds, several counts.
    sim_fn(n_sims, seed) -> probability. Reports run-to-run SD vs theoretical SE and
    the marginal gain of each step."""
    out, prev = [], None
    for n in counts:
        vals = [sim_fn(n, s) for s in seeds]
        m = sum(vals) / len(vals)
        sd = (sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1)) ** .5
        row = {"n_sims": n, "mean": m, "run_sd": sd, "theory_se": sim_se(m, n),
               "gain_vs_prev": (prev - sd) / prev if prev else None, "cost_vs_prev": n / out[-1]["n_sims"] if out else None}
        out.append(row)
        prev = sd
    return out


# ------------------------------------------------------------ dispersion / spread audit

def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _over_prob(mean, sd, line):
    return 1 - _ncdf((line - mean) / sd)


def _dispersion_stats(rows, k=1.0):
    zs = [(float(r["actual"]) - float(r["projection"])) / (float(r["proj_sd"]) * k) for r in rows]
    n = len(zs)
    m = sum(zs) / n
    sd = (sum((z - m) ** 2 for z in zs) / max(1, n - 1)) ** .5
    cov = {f"{int(c * 100)}%": sum(abs(z) <= q for z in zs) / n
           for c, q in ((.5, .6745), (.8, 1.2816), (.9, 1.6449))}
    probs, outs = [], []
    for r in rows:
        if r.get("line") in (None, ""):
            continue
        p = _over_prob(float(r["projection"]), float(r["proj_sd"]) * k, float(r["line"]))
        probs.append(min(max(p, 1e-6), 1 - 1e-6))
        a, l = float(r["actual"]), float(r["line"])
        outs.append(None if a == l else int(a > l))
    pairs = [(p, o) for p, o in zip(probs, outs) if o is not None]
    res = {"n": n, "z_mean": m, "z_sd": sd, "coverage": cov,
           "extreme_share": sum(p < .2 or p > .8 for p in probs) / len(probs) if probs else None}
    if pairs:
        pp, oo = [p for p, _ in pairs], [o for _, o in pairs]
        res.update(brier=stats.brier(pp, oo), log_loss=stats.log_loss(pp, oo), ece=stats.ece(pp, oo))
    return res


def dispersion_audit(rows: Sequence[dict], time_key: str = "kickoff_ts", tol: float = 0.10) -> dict:
    """rows: projection (mean), proj_sd, actual, optional line + kickoff_ts.

    z_sd > 1 means the model's spread is too small: spread_used = 1/z_sd
    (z_sd 1.64 → model uses ~61% of the real spread). Recommendation is fit on the
    earlier half and checked on the later half; only RECOMMENDED if holdout improves.
    """
    rs = [r for r in rows if all(r.get(k) not in (None, "") for k in ("projection", "proj_sd", "actual"))
          and float(r["proj_sd"]) > 0]
    if len(rs) < 20:
        return {"n": len(rs), "status": "SMALL_SAMPLE"}
    rs = sorted(rs, key=lambda r: str(r.get(time_key, "")))
    full = _dispersion_stats(rs)
    half = len(rs) // 2
    fit, test = rs[:half], rs[half:]
    k = _dispersion_stats(fit)["z_sd"]
    before, after = _dispersion_stats(test), _dispersion_stats(test, k)
    # CI on z_sd via chi-square normal approx
    se = full["z_sd"] / math.sqrt(2 * (full["n"] - 1))
    status = ("UNDERDISPERSED_OVERCONFIDENT" if full["z_sd"] - 1.96 * se > 1 + tol else
              "OVERDISPERSED_UNDERCONFIDENT" if full["z_sd"] + 1.96 * se < 1 - tol else "OK")
    improved = after.get("brier") is not None and before.get("brier") is not None and after["brier"] < before["brier"]
    return {"n": full["n"], "status": status, "z_sd": full["z_sd"], "z_sd_ci": (full["z_sd"] - 1.96 * se, full["z_sd"] + 1.96 * se),
            "spread_used": 1 / full["z_sd"], "bias_z_mean": full["z_mean"], "coverage": full["coverage"],
            "extreme_share": full["extreme_share"],
            "recommendation": {"sd_multiplier": k, "fit_n": len(fit), "holdout_n": len(test),
                               "holdout_before": before, "holdout_after": after,
                               "verdict": "RECOMMEND (holdout improved; needs owner approval)" if status != "OK" and improved
                               else "NO_CHANGE"},
            "note": "Recommendation only. Engine SDs are never modified by this audit."}
