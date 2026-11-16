#!/usr/bin/env python3
"""Prequential, research-only NFL final-score probability audit (PAPER / 0u).

Replay each frozen forecast only against SAME-MODEL historical outcomes already
available by that forecast's UTC freeze. Compare 3-way Brier/log loss against
a simple training-only raw-result base rate. NO sportsbook authentication,
actual EV, probability promotion, CLV, or approved bets.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import random

from discrete_score_pit import (
    FORECAST_KEYS, LINES_KEYS, _forecast, _history, _lines,
    _load_original_bytes, _refuse_json_numeric_overflow, score_distribution,
)
from feature_snapshot_bridge_pit import strict_original_json
from score_walkforward_pit import (
    create_private_output, private_evidence_path, utc,
)

FAMILIES = (
    "MONEYLINE", "SPREAD", "GAME_TOTAL", "HOME_TEAM_TOTAL", "AWAY_TEAM_TOTAL",
)
FAMILY_LINE = {
    "SPREAD": "home_spread",
    "GAME_TOTAL": "game_total",
    "HOME_TEAM_TOTAL": "home_team_total",
    "AWAY_TEAM_TOTAL": "away_team_total",
}


def _score_sign(home, away, market, line):
    if market == "MONEYLINE":
        return home-away
    if market == "SPREAD":
        return home-away+line
    if market == "GAME_TOTAL":
        return home+away-line
    if market == "HOME_TEAM_TOTAL":
        return home-line
    if market == "AWAY_TEAM_TOTAL":
        return away-line
    raise ValueError("UNKNOWN_MARKET_FAMILY")


def _category(home, away, market, line):
    # 0: home win/cover or over, 1: tie/push, 2: away win/cover or under
    x = _score_sign(home, away, market, line)
    return 0 if x > 0 else 1 if x == 0 else 2


def _probability_triplet(market, result):
    if market == "MONEYLINE":
        keys = ("home_win", "tie", "away_win")
    else:
        keys = ("over_or_home_cover", "push", "under_or_away_cover")
    p = tuple(result[k] for k in keys)
    if (any(not isinstance(v, (int, float)) or not math.isfinite(v)
            or v < 0 or v > 1 for v in p)
        or abs(sum(p)-1) > 1e-6):
        raise ValueError("INVALID_DISCRETE_PROBABILITY_TRIPLET")
    return p


def _brier(p, actual):
    return sum((p[k]-(1 if k == actual else 0))**2 for k in range(3))


def _logloss(p, actual):
    return -math.log(max(1e-12, p[actual]))


def _summary(rows, *, bootstrap_samples=400):
    n = len(rows)
    def mean(key):
        return round(sum(r[key] for r in rows)/n, 8) if n else None
    out = {
        "evaluated_distinct_games": n,
        "has_30_independent_games": n >= 30,
        "model_3way_brier": mean("model_brier"),
        "train_only_raw_result_baseline_3way_brier": mean("baseline_brier"),
        "model_3way_logloss": mean("model_logloss"),
        "train_only_raw_result_baseline_3way_logloss": mean("baseline_logloss"),
        "paired_brier_gain_baseline_minus_model": (
            round(mean("baseline_brier")-mean("model_brier"), 8)
            if n else None),
        "paired_brier_gain_game_bootstrap_95pct_ci": None,
    }
    if n >= 30:
        # Each family contributes AT MOST one selection per source game.
        # For joint multisport/market portfolios, bootstrap game blocks across
        # markets instead of treating correlated choices as independent.
        rng = random.Random(20261115)
        diffs = [r["baseline_brier"]-r["model_brier"] for r in rows]
        sampled = []
        for _ in range(bootstrap_samples):
            draw = [diffs[rng.randrange(n)] for _ in range(n)]
            sampled.append(sum(draw)/n)
        sampled.sort()
        out["paired_brier_gain_game_bootstrap_95pct_ci"] = [
            round(sampled[int(.025*(bootstrap_samples-1))], 8),
            round(sampled[int(.975*(bootstrap_samples-1))], 8),
        ]
    return out


def evaluate_frozen_distributions(
    historical, *, lines=None, audit_asof_utc,
    min_history=50,
):
    """Read-only research grade, with target's own result NEVER in its model.

    historical: original immutable frozen score+final rows, exact HISTORY_KEYS.
    lines: optional list of original prefreeze line observations, LINES_KEYS.
    audit_asof_utc: actual audit-time UTC; CLI supplies real current UTC.
    """
    if type(min_history) is not int or min_history < 30:
        raise ValueError("MINIMUM_RESIDUAL_HISTORY_AT_LEAST_30_REQUIRED")
    if not isinstance(historical, list) or not historical:
        raise ValueError("NONEMPTY_FROZEN_HISTORY_ARRAY_REQUIRED")
    audit = utc(audit_asof_utc)
    seen = set()
    events = []
    for raw in historical:
        h = _history(raw)
        if h["id"] in seen:
            raise ValueError("DUPLICATE_FROZEN_EVENT_ID")
        seen.add(h["id"])
        if h["available"] > audit:
            raise ValueError("RESULT_NOT_AVAILABLE_BY_AUDIT_TIME")
        events.append((h, raw))
    by_id = {h["id"]: (h, raw) for h, raw in events}
    if lines is None:
        lines = []
    if not isinstance(lines, list):
        raise ValueError("LINES_MUST_BE_LIST")
    line_map = {}
    for row in lines:
        if not isinstance(row, dict) or set(row) != LINES_KEYS:
            raise ValueError("UNEXPECTED_PREGAME_LINE_SCHEMA")
        gid = row["game_id"]
        if gid not in by_id:
            raise ValueError("UNKNOWN_LINE_EVENT_ID")
        if gid in line_map:
            raise ValueError("DUPLICATE_PREGAME_LINE_EVENT")
        _lines(row, _forecast({k: by_id[gid][1][k] for k in FORECAST_KEYS}))
        line_map[gid] = row

    events.sort(key=lambda t: (t[0]["asof"], t[0]["kickoff"], t[0]["id"]))
    ledger = []
    per_market = {m: [] for m in FAMILIES}
    withheld = Counter()
    for h, raw in events:
        # Precompute strict prior pool. Never feed this event or any future
        # event's final score into its own probability denominator.
        prior = [(older, original) for older, original in events
                 if older["id"] != h["id"] and older["sha"] == h["sha"]
                 and older["kickoff"] < h["asof"]
                 and older["available"] <= h["asof"]]
        forecast = {k: raw[k] for k in FORECAST_KEYS}
        prediction = score_distribution(
            forecast, [source for _, source in prior],
            lines=line_map.get(h["id"]), min_history=min_history,
        )
        event = {
            "game_id": h["id"],
            "forecast_asof_utc": h["asof"].isoformat(),
            "model_sha256": h["sha"],
            "training_only_prior_game_count": len(prior),
            "outcome_available_utc": h["available"].isoformat(),
            "status": "PAPER_HOLD_0U",
            "market_diagnostics": {},
            "approved_stake_u": 0,
        }
        for market in FAMILIES:
            obj = prediction["markets"][market]
            if obj["status"] != "PAPER_HOLD_0U":
                reason = obj["status"]
                event["market_diagnostics"][market] = {
                    "status": reason, "reason": obj["reason"],
                }
                withheld[(market, reason)] += 1
                continue
            line = None
            if market in FAMILY_LINE:
                line = obj["line"]
            p = _probability_triplet(market, obj)
            category = _category(h["hs"], h["as"], market, line)
            baseline_count = Counter(
                _category(past["hs"], past["as"], market, line)
                for past, _ in prior
            )
            n = len(prior)
            baseline = tuple(baseline_count.get(i, 0)/n for i in range(3))
            audit_row = {
                "game_id": h["id"],
                "market_family": market,
                "train_only_prior_games": n,
                "original_line_or_null": line,
                "model_threeway_probabilities": list(p),
                "baseline_threeway_probabilities": list(baseline),
                "observed_class_0_home_or_over_1_push_2_away_or_under": category,
                "model_brier": _brier(p, category),
                "baseline_brier": _brier(baseline, category),
                "model_logloss": _logloss(p, category),
                "baseline_logloss": _logloss(baseline, category),
                "status": "PAPER_HOLD_0U",
            }
            per_market[market].append(audit_row)
            event["market_diagnostics"][market] = audit_row
        ledger.append(event)
    summaries = {market: _summary(rows) for market, rows in per_market.items()}
    return {
        "status": "PAPER_HOLD_0U",
        "official_counted": 0,
        "approved_stake_u": 0,
        "audit_asof_utc": audit.isoformat(),
        "history_rows_seen": len(historical),
        "unique_games_seen": len(events),
        "market_line_event_count": len(line_map),
        "independently_authenticated_inputs": False,
        "source_publication_time_verified": False,
        "score_probability_calibration_approved": False,
        "market_bookmaker_quotes_verified": False,
        "exact_betting_ev": None,
        "min_history_for_diagnostics_only": min_history,
        "market_summaries": summaries,
        "withheld_census": {f"{k[0]}:{k[1]}":v
                            for k,v in sorted(withheld.items())},
        "event_ledger": ledger,
        "notes": [
            "FROZEN_MODEL_AND_SOURCE_DATES_ARE_CALLER_ASSERTIONS",
            "ALL_ACTUAL_RESULTS_USED_FOR_GRADING_ONLY_AFTER_PREDICTION",
            "TRAINING_POOL_REQUIRES_PRE_FORECAST_RESULT_AVAILABILITY",
            "BASELINE_IS_PRIOR_SAME_VERSION_RAW_GAME_RESULT_RATE_NOT_SPORTSBOOK",
            "BOTH_MARKET_SIDES_AND_BOOK_SPECIFIC_SETTLEMENT_NOT_VERIFIED",
            "NO_CALIBRATION_THRESHOLD_OR_MODEL_WEIGHT_WAS_FIT_HERE",
            "NO_PROSPECTIVE_VALIDATION_OR_WAGER_ADMISSION_GRANTED",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True, help="private frozen scores + final results JSON array")
    parser.add_argument("--lines", help="optional private pregame lines JSON array")
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-history", type=int, default=50)
    args = parser.parse_args()
    paths = {"history": private_evidence_path(args.history)}
    if args.lines:
        paths["lines"] = private_evidence_path(args.lines)
    private_evidence_path(args.out)
    raw = {kind: _load_original_bytes(path) for kind,path in paths.items()}
    loaded = {kind: strict_original_json(content) for kind,content in raw.items()}
    for value in loaded.values():
        _refuse_json_numeric_overflow(value)
    # Never accept an operator-backdated audit clock in the CLI.
    report = evaluate_frozen_distributions(
        loaded["history"],
        lines=loaded.get("lines"),
        audit_asof_utc=datetime.now(timezone.utc).isoformat(),
        min_history=args.min_history,
    )
    report["local_original_input_sha256"] = {
        kind: "sha256:" + sha256(content).hexdigest()
        for kind,content in raw.items()
    }
    payload = (json.dumps(report, sort_keys=True, indent=2,
                          allow_nan=False) + "\n").encode("utf-8")
    create_private_output(args.out, payload)
    print(json.dumps({
        "status": "PAPER_HOLD_0U",
        "unique_games_seen": report["unique_games_seen"],
        "approved_stake_u": 0, "out": args.out,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
