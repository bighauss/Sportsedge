"""Calibrated full-game pricing for the CHALLENGER (PAPER / 0u, NON_COUNTED). Stdlib only.

* Predictive distributions are fitted on CHRONOLOGICAL FORECAST RESIDUALS (actual - forecast from a
  strictly-prior walk-forward), never on realized score SDs, separately per early-season phase
  (min current-season games of the two teams) because early forecasts are much less certain.
* Tails: margin / total / team-points residuals use a location-scale Student-t whose degrees of
  freedom are matched to the residual excess kurtosis (normal when kurtosis <= 0). The location term
  is the residual mean of the fitting window (de-biasing), recorded, never tuned on evaluation rows.
* Push-aware: integer lines get P(push) = P(line - 1/2 < X < line + 1/2) (scores are integers);
  half-point lines never push. Moneyline: ties are impossible (overtime), so P(home) = P(X > 0) with
  the half-integer mass at 0 split evenly.
* NO EV caps. ``ev_audit`` flags rows over a threshold (default 30%) with diagnostic reason codes but
  never alters probabilities or EV; the fix for inflated EV is the projection and calibration.
"""
from __future__ import annotations
import math
from statistics import mean

import cbb_pricing as _PR

PHASES = ((0, 0), (1, 1), (2, 4), (5, 9), (10, 19), (20, 10 ** 6))
MIN_PHASE_N = 200


def phase_of(n_home, n_away):
    n = min(n_home, n_away)
    for i, (lo, hi) in enumerate(PHASES):
        if lo <= n <= hi:
            return i
    return len(PHASES) - 1


# ---------------------------------------------------------------- Student-t CDF (stdlib)
def _betacf(a, b, x):
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(c) > tiny else 1 + aa / tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(c) > tiny else 1 + aa / tiny
        de = d * c
        h *= de
        if abs(de - 1) < 1e-14:
            break
    return h


def _ibeta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def t_cdf(t, df):
    if df is None or df > 1e6:
        return 0.5 * math.erfc(-t / math.sqrt(2))
    x = df / (df + t * t)
    p = 0.5 * _ibeta(df / 2, 0.5, x)
    return 1 - p if t > 0 else p


class Dist:
    """Location-scale distribution of the target given a forecast: X = forecast + loc + scale * T_df."""

    def __init__(self, loc, sd, df=None):
        if not (math.isfinite(sd) and sd > 0):
            raise ValueError("SD_INVALID")
        if df is not None and df <= 2:
            raise ValueError("DF_INVALID")
        self.loc, self.sd, self.df = loc, sd, df
        self.scale = sd * math.sqrt((df - 2) / df) if df else sd

    def cdf(self, x, mu):
        return t_cdf((x - mu - self.loc) / self.scale, self.df)

    def as_dict(self):
        return {"loc": self.loc, "sd": self.sd, "df": self.df}


def fit_dist(residuals, *, min_n=MIN_PHASE_N, df_floor=4.0):
    """Moments of chronological forecast residuals -> Dist (t df from excess kurtosis)."""
    r = [x for x in residuals if math.isfinite(x)]
    if len(r) < min_n:
        raise ValueError("INSUFFICIENT_RESIDUALS")
    m = mean(r)
    v = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    k4 = sum((x - m) ** 4 for x in r) / len(r) / (v * v) - 3
    df = None if k4 <= 0.05 else max(df_floor, 6 / k4 + 4)
    return Dist(m, math.sqrt(v), df)


def fit_phase_dists(rows, target):
    """rows: dicts with 'phase' and target residual. Phases short of data borrow the nearest later phase."""
    by = {}
    for r in rows:
        by.setdefault(r["phase"], []).append(r[target])
    allr = [x for v in by.values() for x in v]
    out = {"all": fit_dist(allr)}
    for i in range(len(PHASES)):
        try:
            out[i] = fit_dist(by.get(i, []))
        except ValueError:
            out[i] = None
    for i in range(len(PHASES)):
        if out[i] is None:
            nxt = next((out[j] for j in range(i + 1, len(PHASES)) if out[j] is not None), out["all"])
            out[i] = nxt
    return out


# ---------------------------------------------------------------- push-aware line probabilities
def line_probs(dist, mu, line):
    """(P(X > line), P(push), P(X < line)) for target X; integer lines push on the integer."""
    line = float(line)
    if line.is_integer():
        lo, hi = dist.cdf(line - 0.5, mu), dist.cdf(line + 0.5, mu)
        return 1 - hi, hi - lo, lo
    b = dist.cdf(line, mu)
    return 1 - b, 0.0, b


def ml_probs(dist, mu):
    """P(home wins) with the [-1/2, 1/2] tie mass split evenly (games cannot end tied)."""
    lo, hi = dist.cdf(-0.5, mu), dist.cdf(0.5, mu)
    p = 1 - hi + 0.5 * (hi - lo)
    return p, 1 - p


def parse_american(value, *, min_abs=100, max_abs=100000):
    """Delegate to the canonical quote contract in ``cbb_pricing.parse_american``."""
    return _PR.parse_american(value, min_abs=min_abs, max_abs=max_abs)


def decimal_odds(american):
    a = parse_american(american)
    return 1 + (a / 100 if a > 0 else 100 / -a)


def no_vig(pa, pb):
    a, b = 1 / decimal_odds(pa), 1 / decimal_odds(pb)
    return a / (a + b), b / (a + b), a + b - 1


def ev(p_win, p_push, price):
    return p_win * (decimal_odds(price) - 1) - (1 - p_win - p_push)


def fair_american(p):
    if not 0 < p < 1:
        return None
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


# ---------------------------------------------------------------- audit (flags only, no caps)
def ev_audit(row, *, threshold=0.30, z_disagree=1.5):
    """Return reason codes for an EV above ``threshold``. Never modifies the row.

    row: ev, price, p_model, p_novig, and optionally model_mean / market_mean / sd (same target).
    """
    if row["ev"] <= threshold:
        return []
    codes = ["EV_GT_%d_PCT" % round(threshold * 100)]
    if decimal_odds(row["price"]) >= 6.0:
        codes.append("LONGSHOT_PRICE_GE_PLUS500")
    if row.get("p_novig") and row["p_model"] / row["p_novig"] >= 2.0:
        codes.append("MODEL_PROB_GE_2X_NOVIG")
    mm, km, sd = row.get("model_mean"), row.get("market_mean"), row.get("sd")
    if None not in (mm, km, sd) and sd > 0 and abs(mm - km) / sd >= z_disagree:
        codes.append("MODEL_MARKET_MEAN_GAP_GE_%.1f_SD" % z_disagree)
    return codes


# ---------------------------------------------------------------- moneyline tail calibration
def _lg(p):
    p = min(1 - 1e-12, max(1e-12, p)); return math.log(p / (1 - p))


def fit_logit_recal(pairs, iters=50):
    """Fit logit(p_cal) = a + b * logit(p) by maximum likelihood (Newton/IRLS) on (p, y) pairs taken
    from STRICTLY EARLIER seasons. b < 1 thins over-fat tails; a = 0 keeps home/away symmetric."""
    a, b = 0.0, 1.0
    xs = [(_lg(p), y) for p, y in pairs]
    for _ in range(iters):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in xs:
            q = 1 / (1 + math.exp(-(a + b * x)))
            w = q * (1 - q)
            g0 += y - q; g1 += (y - q) * x
            h00 += w; h01 += w * x; h11 += w * x * x
        det = h00 * h11 - h01 * h01
        if det <= 0:
            break
        da = (h11 * g0 - h01 * g1) / det; db = (h00 * g1 - h01 * g0) / det
        a += da; b += db
        if abs(da) + abs(db) < 1e-10:
            break
    return {"a": a, "b": b, "n": len(xs)}


def apply_logit_recal(p, recal):
    if not recal:
        return p
    z = recal["a"] + recal["b"] * _lg(p)
    return 1 / (1 + math.exp(-z))
