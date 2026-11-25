"""CBB first-half / second-half projection and discrete score distributions (PAPER/0u, NON_COUNTED).

Stdlib only; no network. Coefficients come from ``coefficients_halves_v1.json``, produced by
``research/cbb_halves/fit_halves.py`` from chronological out-of-sample (rolling-origin) residuals
of pregame projections on the public ESPN/sportsdataverse halves dataset.

Two distinct second-half products, never mixed:
  * PREGAME second half (``H2`` / ``H2REG``): uses only pregame full-game projections.
  * HALFTIME-ADJUSTED second half (``HT_H2`` / ``HT_H2REG``): additionally conditions on the
    realized first-half score (and optionally first-half possessions). Only valid at halftime.

Scopes: ``H2``/``HT_H2`` include overtime (sportsbook "2nd half" convention, verify per book);
``H2REG``/``HT_H2REG`` are regulation-only second halves.

Every distribution is a probability mass function over integer outcomes, so integer lines get
explicit push probabilities and half-point lines get none. Nothing here caps EV.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_COEFFICIENTS = HERE / "coefficients_halves_v1.json"
LABEL = "PAPER_0U"
COUNTING = "NON_COUNTED"
PERIODS = ("H1", "H2", "H2REG", "HT_H2", "HT_H2REG")
HALFTIME_PERIODS = ("HT_H2", "HT_H2REG")


class HalvesHold(ValueError):
    """Explicit withhold reason (input invalid or outside the fitted domain)."""


def _finite(x, code):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise HalvesHold(code)
    return float(x)


def load_coefficients(path=None):
    p = Path(path) if path else DEFAULT_COEFFICIENTS
    raw = p.read_bytes()
    coef = json.loads(raw)
    if coef.get("label") != LABEL or coef.get("counting") != COUNTING:
        raise HalvesHold("COEFFICIENTS_LABEL_INVALID")
    coef["_sha256"] = hashlib.sha256(raw).hexdigest()
    return coef


# ----------------------------------------------------------------------------- features
def feature_value(name, ctx):
    """Feature registry shared by the fitter and the runtime (one definition, no drift)."""
    if name == "1":
        return 1.0
    if name == "M":
        return ctx["M"]
    if name == "T":
        return ctx["T"]
    if name == "abs_M10":
        return abs(ctx["M"]) / 10.0
    if name == "T140_20":
        return (ctx["T"] - 140.0) / 20.0
    if name == "poss_dev":
        return ctx["poss"] - 68.0
    if name == "early":
        return ctx["early"]
    if name == "m1":
        return ctx["m1"]
    if name == "t1":
        return ctx["t1"]
    if name == "abs_m1_10":
        return abs(ctx["m1"]) / 10.0
    if name == "poss1_dev":
        return ctx["poss1"] - 34.0
    if name == "mu_team_dev10":
        return (ctx["mu_team"] - 35.0) / 10.0
    raise HalvesHold("UNKNOWN_FEATURE:" + name)


def linear(spec, ctx):
    return sum(c * feature_value(f, ctx) for f, c in zip(spec["features"], spec["coef"]))


# ----------------------------------------------------------------------------- shapes
def _norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def shape_cdf(shape, z):
    """CDF of the standardized residual. 'normal' or an 'empirical' monotone quantile table
    (linear interpolation; Gaussian tails beyond the outermost knots, matched in probability)."""
    if shape["kind"] == "normal":
        return _norm_cdf(z)
    zs, ps = shape["z_knots"], shape["p_knots"]
    if z <= zs[0]:
        # Gaussian-shaped tail anchored at (zs[0], ps[0])
        return ps[0] * _norm_cdf(z) / max(_norm_cdf(zs[0]), 1e-300)
    if z >= zs[-1]:
        return 1.0 - (1.0 - ps[-1]) * (1.0 - _norm_cdf(z)) / max(1.0 - _norm_cdf(zs[-1]), 1e-300)
    i = bisect.bisect_right(zs, z)
    z0, z1, p0, p1 = zs[i - 1], zs[i], ps[i - 1], ps[i]
    return p0 + (p1 - p0) * (z - z0) / (z1 - z0) if z1 > z0 else p1


class IntegerPMF:
    """PMF over integers ``lo..hi`` built by discretizing mu + sigma * Z on unit bins."""

    def __init__(self, mu, sigma, shape, span=9.0):
        mu = _finite(mu, "MEAN_INVALID")
        sigma = _finite(sigma, "SD_INVALID")
        if sigma <= 0:
            raise HalvesHold("SD_INVALID")
        self.mu, self.sigma = mu, sigma
        self.lo = int(math.floor(mu - span * sigma))
        self.hi = int(math.ceil(mu + span * sigma))
        cdf = [shape_cdf(shape, (k + 0.5 - mu) / sigma) for k in range(self.lo - 1, self.hi + 1)]
        pm = [max(0.0, cdf[i + 1] - cdf[i]) for i in range(len(cdf) - 1)]
        s = sum(pm)
        self.p = [x / s for x in pm]

    def pmf(self, k):
        return self.p[k - self.lo] if self.lo <= k <= self.hi else 0.0

    def prob_gt(self, x):
        """P(Y > x) for any real x."""
        return sum(p for k, p in zip(range(self.lo, self.hi + 1), self.p) if k > x + 1e-9)

    def prob_eq(self, x):
        return self.pmf(int(round(x))) if abs(x - round(x)) < 1e-9 else 0.0

    def prob_lt(self, x):
        return max(0.0, 1.0 - self.prob_gt(x) - self.prob_eq(x))

    def mean(self):
        return sum(k * p for k, p in zip(range(self.lo, self.hi + 1), self.p))


# ----------------------------------------------------------------------------- projection
def _context(fg_home, fg_away, *, min_games=None, fg_poss=None, h1_home=None, h1_away=None,
             h1_poss=None):
    fh = _finite(fg_home, "FG_PROJECTION_INVALID")
    fa = _finite(fg_away, "FG_PROJECTION_INVALID")
    if not (20 <= fh <= 140 and 20 <= fa <= 140):
        raise HalvesHold("FG_PROJECTION_OUT_OF_DOMAIN")
    ctx = {"M": fh - fa, "T": fh + fa}
    if min_games is None:
        ctx["early"] = None
    else:
        g = _finite(min_games, "MIN_GAMES_INVALID")
        if g < 0:
            raise HalvesHold("MIN_GAMES_INVALID")
        ctx["early"] = 1.0 / (1.0 + g)
    ctx["poss"] = None if fg_poss is None else _finite(fg_poss, "FG_POSS_INVALID")
    if h1_home is not None or h1_away is not None:
        a = _finite(h1_home, "H1_SCORE_INVALID"); b = _finite(h1_away, "H1_SCORE_INVALID")
        if a < 0 or b < 0 or a != int(a) or b != int(b):
            raise HalvesHold("H1_SCORE_INVALID")
        ctx["m1"], ctx["t1"] = a - b, a + b
    ctx["poss1"] = None if h1_poss is None else _finite(h1_poss, "H1_POSS_INVALID")
    return ctx


def _pick_variant(tspec, ctx):
    """Use the richest fitted variant whose inputs are all present."""
    for v in tspec["variants"]:
        if all(ctx.get(k) is not None for k in v["requires"]):
            return v
    raise HalvesHold("NO_VARIANT_FOR_INPUTS")


def _sigma(v, ctx, fg_sd_override):
    s = math.exp(linear(v["sd"], ctx))
    if fg_sd_override is not None and v.get("beta_fg") is not None:
        # Re-scale for a full-game model whose residual SD differs from the fitting model's:
        # var_H = var_fit + beta^2 * (sd_new^2 - sd_fit^2), floored at the conditional noise.
        b, sfit = v["beta_fg"], v["fg_resid_sd_fit"]
        var = s * s + b * b * (fg_sd_override ** 2 - sfit ** 2)
        s = math.sqrt(max(var, v["cond_resid_sd"] ** 2))
    return s


def project_period(period, fg_home, fg_away, *, coefficients=None, min_games=None, fg_poss=None,
                   h1_home=None, h1_away=None, h1_poss=None, fg_margin_sd=None, fg_total_sd=None):
    """Distributions for one period.

    Inputs are the *pregame full-game* expected points (home, away) from whatever full-game
    model the runner uses (home-court already applied, neutral sites without HCA), optional
    pregame possessions, optional ``min_games`` (fewest games either team has played this season)
    and, for halftime periods only, the realized first-half score.

    Returns dict with means, SDs and IntegerPMF objects for margin (home minus away), total,
    home points and away points, plus provenance.
    """
    if period not in PERIODS:
        raise HalvesHold("PERIOD_INVALID")
    coef = coefficients or load_coefficients()
    ctx = _context(fg_home, fg_away, min_games=min_games, fg_poss=fg_poss,
                   h1_home=h1_home, h1_away=h1_away, h1_poss=h1_poss)
    if period in HALFTIME_PERIODS and "m1" not in ctx:
        raise HalvesHold("HALFTIME_REQUIRES_H1_SCORE")
    if period not in HALFTIME_PERIODS and "m1" in ctx:
        raise HalvesHold("PREGAME_PERIOD_MUST_NOT_SEE_H1_SCORE")
    if ctx["early"] is None:
        ctx["early"] = coef["default_early"]
    T = coef["targets"]
    vm = _pick_variant(T[period + "_MARGIN"], ctx)
    vt = _pick_variant(T[period + "_TOTAL"], ctx)
    mu_m, mu_t = linear(vm["mean"], ctx), linear(vt["mean"], ctx)
    sd_m = _sigma(vm, ctx, fg_margin_sd)
    sd_t = _sigma(vt, ctx, fg_total_sd)
    vteam = _pick_variant(T[period + "_TEAM"], ctx)
    mu_h, mu_a = (mu_t + mu_m) / 2.0, (mu_t - mu_m) / 2.0
    sd_h = math.exp(linear(vteam["sd"], {**ctx, "mu_team": mu_h}))
    sd_a = math.exp(linear(vteam["sd"], {**ctx, "mu_team": mu_a}))
    return {
        "period": period, "label": LABEL, "counting": COUNTING,
        "model_version": coef["model_version"], "coefficients_sha256": coef["_sha256"],
        "kind": "HALFTIME_ADJUSTED" if period in HALFTIME_PERIODS else "PREGAME",
        "overtime_included": period in ("H2", "HT_H2"),
        "variants": {"margin": vm["name"], "total": vt["name"], "team": vteam["name"]},
        "mean": {"margin": mu_m, "total": mu_t, "home": mu_h, "away": mu_a},
        "sd": {"margin": sd_m, "total": sd_t, "home": sd_h, "away": sd_a},
        "pmf": {"margin": IntegerPMF(mu_m, sd_m, vm["shape"]),
                "total": IntegerPMF(mu_t, sd_t, vt["shape"]),
                "home": IntegerPMF(mu_h, sd_h, vteam["shape"]),
                "away": IntegerPMF(mu_a, sd_a, vteam["shape"])},
    }
