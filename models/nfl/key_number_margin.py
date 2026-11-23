"""Research-only key-number NFL final-margin CHALLENGER. PAPER / 0u.

This discrete 3/7 reweighting never changes frozen v3 and is not a validated
pregame model. Unstamped fit_weights is exploratory; only fit_weights_asof
enforces a caller-supplied as-of cutoff. Claimed source timestamps still require
independent original-source review. Do not infer genuine +EV from this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from statistics import NormalDist

N = NormalDist()
SD_MARGIN = 13.5
KEYS = (3, 7)
SPAN = 70


def _num(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("INVALID_" + name)
    return float(v)


def _margin(v):
    if isinstance(v, bool) or not isinstance(v, int) or abs(v) > SPAN:
        raise ValueError("INVALID_FINAL_MARGIN")
    return v


def _sd(v):
    val = _num(v, "SD")
    if val <= 0:
        raise ValueError("INVALID_SD")
    return val


def _weights(weights):
    if weights is None:
        return {}
    if not isinstance(weights, dict):
        raise ValueError("INVALID_KEY_WEIGHTS")
    out = {}
    for key, v in weights.items():
        if isinstance(key, bool) or key not in KEYS or type(key) is not int:
            raise ValueError("INVALID_KEY_WEIGHT_ID")
        value = _num(v, "KEY_WEIGHT")
        if value < 1:
            raise ValueError("INVALID_KEY_WEIGHT")
        out[key] = value
    return out


def _utc(v, name):
    if not isinstance(v, str) or not v.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED:" + name)
    try:
        dt = datetime.fromisoformat(v[:-1] + "+00:00")
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_UTC:" + name) from exc
    if dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ValueError("INVALID_UTC:" + name)
    return dt


def pmf(mean, sd=SD_MARGIN, weights=None):
    """Signed integer margin PMF over [-70,70], with explicit tail truncation."""
    mu = _num(mean, "MEAN")
    sig = _sd(sd)
    w = _weights(weights)
    values = {}
    for k in range(-SPAN, SPAN + 1):
        base = N.cdf((k + .5 - mu) / sig) - N.cdf((k - .5 - mu) / sig)
        values[k] = max(0., base) * w.get(abs(k), 1.)
    total = sum(values.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("MARGIN_DISTRIBUTION_UNSUPPORTED")
    return {k: v / total for k, v in values.items()}


def fit_weights(margins, sd=SD_MARGIN, keys=KEYS):
    """EXPLORATORY fit on unstamped finals; not PIT validated. Never release."""
    _sd(sd)
    if not isinstance(margins, (list, tuple)):
        raise ValueError("MARGIN_HISTORY_REQUIRED")
    if not isinstance(keys, (list, tuple)) or not keys or len(set(keys)) != len(keys):
        raise ValueError("KEY_LIST_INVALID")
    if any(type(k) is not int or k not in KEYS for k in keys):
        raise ValueError("KEY_LIST_INVALID")
    vals = [_margin(m) for m in margins]
    if not vals:
        return {}
    base = pmf(0.0, sd)
    n = len(vals)
    return {k: max(1., ((sum(abs(m) == k for m in vals) + 1) / (n + 1))
                        / (base[k] + base[-k])) for k in keys}


def fit_weights_asof(records, *, asof_utc, sd=SD_MARGIN):
    """Strict source-clock gate; source authenticity is NOT established here.

    Each record must have event_id, margin (signed integer), completed_utc,
    and result_observed_utc. The *claimed* result observation must be after the
    final, and strictly before the declared as-of cutoff. Reject all duplicates
    or ineligible records rather than silently postdating a history.
    """
    cutoff = _utc(asof_utc, "ASOF")
    if not isinstance(records, (list, tuple)) or not records:
        raise ValueError("PIT_RECORDS_REQUIRED")
    seen, margins = set(), []
    for item in records:
        if not isinstance(item, dict) or set(item) != {
                "event_id", "margin", "completed_utc", "result_observed_utc"}:
            raise ValueError("PIT_SOURCE_SCHEMA_INVALID")
        event = item["event_id"]
        if not isinstance(event, str) or not event.strip():
            raise ValueError("PIT_EVENT_ID_INVALID")
        if event in seen:
            raise ValueError("PIT_DUPLICATE_EVENT_ID")
        seen.add(event)
        completed = _utc(item["completed_utc"], "COMPLETED")
        observed = _utc(item["result_observed_utc"], "RESULT_OBSERVED")
        if not completed <= observed < cutoff:
            raise ValueError("PIT_RESULT_NOT_AVAILABLE_BEFORE_ASOF")
        margins.append(_margin(item["margin"]))
    return {"weights": fit_weights(margins, sd), "eligible_events": len(seen),
            "asof_utc": asof_utc, "source_authenticated": False,
            "model_released": False}


def cover(mean, line, sd=SD_MARGIN, weights=None):
    """P(win), P(push), P(loss) for home-margin side with signed spread line."""
    spread = _num(line, "SPREAD_LINE")
    if abs(spread) > SPAN or abs(spread * 2 - round(spread * 2)) > 1e-8:
        raise ValueError("UNSUPPORTED_SPREAD_LINE")
    p = pmf(mean, sd, weights)
    threshold = -spread
    win = sum(v for k, v in p.items() if k > threshold + 1e-9)
    push = sum(v for k, v in p.items() if abs(k - threshold) < 1e-9)
    return win, push, max(0., 1. - win - push)


def log_loss(margins_with_means, sd=SD_MARGIN, weights=None):
    """Exact-margin descriptive NLL, not an odds or profitability score."""
    if not isinstance(margins_with_means, (list, tuple)) or not margins_with_means:
        raise ValueError("EVALUATION_ROWS_REQUIRED")
    total = 0.
    for item in margins_with_means:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("EVALUATION_ROW_INVALID")
        m, mu = item
        probability = pmf(mu, sd, weights).get(_margin(m), 0.)
        total -= math.log(max(probability, 1e-12))
    return total / len(margins_with_means)


def ev(p_win, p_push, american):
    """Push-refund expected return per unit for a valid nonzero American price."""
    win = _num(p_win, "WIN_PROBABILITY")
    push = _num(p_push, "PUSH_PROBABILITY")
    if win < 0 or push < 0 or win + push > 1 + 1e-10:
        raise ValueError("PROBABILITIES_OUT_OF_RANGE")
    if isinstance(american, bool) or type(american) is not int or not (
            100 <= abs(american) <= 100000):
        raise ValueError("INVALID_AMERICAN_ODDS")
    decimal = 1 + (american / 100 if american > 0 else 100 / -american)
    return win * (decimal - 1) - max(0., 1 - win - push)
