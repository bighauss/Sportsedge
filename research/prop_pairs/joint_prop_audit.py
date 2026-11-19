"""Strict point-in-time joint player-prop research, never a betting release.

Only complete, witnessed pregame predictions and postgame outcomes may be scored.
The source timestamps and SHA strings are *claims*: this module never
authenticates provider custody, offers, or actual sportsbook execution.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import math
import re
from statistics import mean, stdev

SPORTS = frozenset(("NFL", "NBA", "CFB", "CBB"))
PERIODS = frozenset(("FG", "1H", "1Q", "2H"))
SIDES = frozenset(("OVER", "UNDER", "YES", "NO"))
UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
HASH = re.compile(r"^[a-f0-9]{64}$")
LEG_FIELDS = frozenset(("player_id", "team_id", "market", "stat", "line", "side"))
CLOCKS = ("model_fitted_until_utc", "forecast_utc", "tipoff_utc",
          "a_published_utc", "a_captured_utc", "b_published_utc",
          "b_captured_utc", "final_published_utc", "final_captured_utc")
REQUIRED = frozenset(("sport", "event_id", "period", "settlement", "a", "b",
                      "pa", "pb", "ya", "yb", "a_source_sha256",
                      "b_source_sha256", "model_sha256", "final_sha256",
                      *CLOCKS))
OPTIONAL = frozenset(("joint_p",))


def _clock(value):
    if type(value) is not str or not UTC.fullmatch(value):
        raise ValueError("UTC_Z_TIMESTAMP_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("INVALID_UTC_TIMESTAMP") from exc


def _prob(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("INVALID_PROBABILITY:" + name)
    return float(value)


def _leg(value):
    if type(value) is not dict or set(value) != LEG_FIELDS:
        raise ValueError("EXACT_LEG_IDENTITY_REQUIRED")
    for k in ("player_id", "team_id", "market", "stat"):
        if type(value[k]) is not str or not value[k].strip():
            raise ValueError("LEG_IDENTITY_MISSING:" + k)
    if value["side"] not in SIDES:
        raise ValueError("INVALID_LEG_SIDE")
    try:
        line = Decimal(value["line"])
    except (TypeError, InvalidOperation, ValueError) as exc:
        raise ValueError("INVALID_PROP_LINE") from exc
    if not line.is_finite() or line < 0:
        raise ValueError("INVALID_PROP_LINE")
    if value["side"] in ("YES", "NO") and line != 0:
        raise ValueError("YES_NO_LINE_MUST_BE_ZERO")
    return (value["player_id"].strip(), value["team_id"].strip(),
            value["market"].strip().upper(), value["stat"].strip().upper(),
            format(line.normalize(), "f"), value["side"])


def _record(row):
    if type(row) is not dict or not REQUIRED.issubset(row) or set(row) - REQUIRED - OPTIONAL:
        raise ValueError("EXACT_PIT_PAIR_SCHEMA_REQUIRED")
    if row["sport"] not in SPORTS or row["period"] not in PERIODS:
        raise ValueError("UNSUPPORTED_SPORT_OR_PERIOD")
    if (row["period"] == "FG" and row["settlement"] != "INCLUDES_OT") or (
            row["period"] != "FG" and row["settlement"] != "REGULATION_PERIOD"):
        raise ValueError("PERIOD_SETTLEMENT_CONTRACT_INVALID")
    if type(row["event_id"]) is not str or not row["event_id"].strip():
        raise ValueError("EVENT_ID_REQUIRED")
    a, b = _leg(row["a"]), _leg(row["b"])
    if a == b:
        raise ValueError("SAME_SELECTION")
    for k in ("a_source_sha256", "b_source_sha256", "model_sha256", "final_sha256"):
        if type(row[k]) is not str or not HASH.fullmatch(row[k]):
            raise ValueError("UNVERIFIED_SHA_SHAPE:" + k)
    times = {k: _clock(row[k]) for k in CLOCKS}
    f, tip = times["forecast_utc"], times["tipoff_utc"]
    if not (
        times["model_fitted_until_utc"] < f < tip
        and times["a_published_utc"] <= times["a_captured_utc"] <= f
        and times["b_published_utc"] <= times["b_captured_utc"] <= f
        and tip < times["final_published_utc"] <= times["final_captured_utc"]
    ):
        raise ValueError("FUTURE_FEATURE_OR_RESULT_LOOKAHEAD")
    pa, pb = _prob(row["pa"], "pa"), _prob(row["pb"], "pb")
    if type(row["ya"]) is not int or row["ya"] not in (0, 1) or (
            type(row["yb"]) is not int or row["yb"] not in (0, 1)):
        raise ValueError("INVALID_OR_PUSHABLE_SETTLEMENT")
    has_joint = "joint_p" in row and row["joint_p"] is not None
    jp = _prob(row["joint_p"], "joint_p") if has_joint else None
    if jp is not None and not (max(0.0, pa + pb - 1.0) - 1e-12 <= jp <= min(pa, pb) + 1e-12):
        raise ValueError("INCOHERENT_JOINT_PROBABILITY")
    pair = tuple(sorted((a, b)))
    scope = (row["sport"], row["period"], row["settlement"], pair)
    return scope, (row["sport"], row["event_id"], row["period"], row["settlement"]), (
        pa, pb, row["ya"] * row["yb"], jp, has_joint
    )


def _ci(deltas):
    if len(deltas) < 30:
        return None
    mu = mean(deltas)
    delta = 1.96 * stdev(deltas) / math.sqrt(len(deltas))
    return [mu - delta, mu + delta]


def evaluate(rows):
    """Descriptive matched-pair Brier comparison, always non-counted/0u.

    A missing, disputed, or invalid source row refuses the entire comparison
    instead of silently selecting winners and changing its denominator.
    """
    if type(rows) is not list:
        raise ValueError("FULL_PAIRED_LEDGER_LIST_REQUIRED")
    if not rows:
        return {"status": "NO_DATA", "games": 0, "pair": None,
                "observed_joint_rate": None, "independence_expected_rate": None,
                "independence_brier": None, "joint_model_brier": None,
                "delta_brier_independence_minus_joint": None, "delta_ci95": None,
                "sample_warning": "NO_DATA", "certified": False,
                "source_authenticated": False, "official_counted": 0,
                "approved_stake_u": 0}
    seen = set()
    scope = None
    present = None
    actual, ind, joint = [], [], []
    for row in rows:
        key, event_key, (pa, pb, y, jp, has_joint) = _record(row)
        if scope is None:
            scope = key
        if scope != key:
            raise ValueError("MIXED_SPORT_PERIOD_SETTLEMENT_OR_PROP_PAIR")
        if event_key in seen:
            raise ValueError("DUPLICATE_EVENT_ALL_COPIES_REFUSED")
        seen.add(event_key)
        if present is None:
            present = has_joint
        if present != has_joint:
            raise ValueError("INCOMPLETE_JOINT_FORECASTS")
        actual.append(y)
        ind.append(pa * pb)
        if has_joint:
            joint.append(jp)
    n = len(rows)
    ind_losses = [(p - y) ** 2 for p, y in zip(ind, actual)]
    joint_losses = [(p - y) ** 2 for p, y in zip(joint, actual)] if present else []
    diff = [a - b for a, b in zip(ind_losses, joint_losses)]
    pair = [dict(zip(("player_id", "team_id", "market", "stat", "line", "side"), leg))
            for leg in scope[3]]
    return {
        "status": "PAPER_0U_CORRELATION_RESEARCH_UNAUTHENTICATED",
        "sport": scope[0], "period": scope[1], "settlement": scope[2],
        "games": n, "unique_events": len(seen), "pair": pair,
        "observed_joint_rate": mean(actual),
        "independence_expected_rate": mean(ind),
        "observed_bernoulli_covariance": mean(actual) - mean(
            (_prob(r["ya"], "ya") * _prob(r["yb"], "yb")) for r in rows
        ),
        "independence_brier": mean(ind_losses),
        "joint_model_brier": mean(joint_losses) if present else None,
        "delta_brier_independence_minus_joint": mean(diff) if present else None,
        "delta_ci95": _ci(diff) if present else None,
        "sample_warning": ("VERY_SMALL_SAMPLE" if n < 30 else
                           "EXPLORATORY_SAMPLE" if n < 100 else None),
        "source_authenticated": False, "certified": False,
        "official_counted": 0, "approved_stake_u": 0,
        "warning": "Source clocks/hashes are unverified claims; no true PIT attestation, no market quotes, no joint distribution admission, no automatic correlation or betting certification."
    }
