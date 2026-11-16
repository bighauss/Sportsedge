#!/usr/bin/env python3
"""NFL point-in-time paired model-vs-market research evaluator.

Given externally archived *pregame* model forecasts and two-sided prices,
grade original odds and compare conditional Brier/log loss with the market.
This is not source authentication, CLV, unit authorization or validated EV.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import re

from score_walkforward_pit import utc, private_evidence_path, create_private_output

def _unique_json_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("DUPLICATE_JSON_KEY:" + key)
        data[key] = value
    return data


def _reject_nonfinite_json(value):
    raise ValueError("NONFINITE_JSON_LITERAL:" + value)


def strict_json_payload(raw):
    """Reject duplicate fields, including nested IDs and prices, before grading."""
    return json.loads(raw, object_pairs_hook=_unique_json_keys,
                      parse_constant=_reject_nonfinite_json)


HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
MARKETS = frozenset({
    "MONEYLINE_2WAY", "SPREAD", "TOTAL", "HOME_TEAM_TOTAL",
    "AWAY_TEAM_TOTAL",
})
FIELDS = frozenset({
    "sport", "game_id", "home_id", "away_id", "market", "selection",
    "period", "provider_event_id", "provider_market_id",
    "provider_outcome_id", "provider_opposite_outcome_id", "quote_receipt_id",
    "book", "home_spread_or_total_line", "american_taken",
    "american_opposite", "model_p_win", "model_p_push", "model_p_loss",
    "model_sha256", "model_forecast_sha256", "provider_quote_sha256",
    "kickoff_utc", "model_features_observed_utc", "model_asof_utc",
    "quote_observed_utc", "quote_captured_utc", "decision_utc",
    "final_utc", "result_available_utc", "final_home", "final_away",
    "tie_settlement",
})


def _numeric(v, name):
    if isinstance(v, bool):
        raise ValueError("INVALID_"+name)
    try:
        x = float(v)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_"+name) from exc
    if not math.isfinite(x):
        raise ValueError("NONFINITE_"+name)
    return x


def _american(value, label):
    if type(value) is not int or (-100 < value < 100) or value == -100:
        raise ValueError("INVALID_AMERICAN_PRICE:"+label)
    if abs(value) > 100000:
        raise ValueError("UNREASONABLE_AMERICAN_PRICE")
    return value


def _implied(price):
    if price > 0:
        return 100 / (price + 100)
    return -price / (-price + 100)


def _decimal_profit(price):
    return price / 100 if price > 0 else 100 / -price


def _score(value):
    if type(value) is not int or not 0 <= value <= 250:
        raise ValueError("INVALID_FINAL_SCORE")
    return value


def _validate(raw, *, freshness_seconds):
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise ValueError("MARKET_EVALUATION_SCHEMA_MISMATCH")
    if raw["sport"] != "NFL" or raw["market"] not in MARKETS:
        raise ValueError("UNSUPPORTED_SPORT_OR_MARKET")
    if raw["period"] != "FG":
        raise ValueError("EXPLICIT_FULL_GAME_PERIOD_REQUIRED")
    for field in (
        "game_id", "home_id", "away_id", "book",
        "provider_event_id", "provider_market_id",
        "provider_outcome_id", "provider_opposite_outcome_id", "quote_receipt_id",
    ):
        value = raw[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("EVENT_OR_BOOK_ID_MISSING:"+field)
    if raw["home_id"] == raw["away_id"]:
        raise ValueError("INVALID_HOME_AWAY_MAPPING")
    if raw["provider_outcome_id"] == raw["provider_opposite_outcome_id"]:
        raise ValueError("SAME_PROVIDER_OUTCOME_ID_BOTH_SIDES")
    market = raw["market"]
    selection = raw["selection"]
    if selection not in (
        ("HOME", "AWAY") if market in ("MONEYLINE_2WAY", "SPREAD")
        else ("OVER", "UNDER")
    ):
        raise ValueError("WRONG_SELECTION_FOR_MARKET")
    if market == "MONEYLINE_2WAY":
        if raw["home_spread_or_total_line"] is not None or raw["tie_settlement"] != "TIE_PUSH":
            raise ValueError("MONEYLINE_TIE_SETTLEMENT_NOT_EXPLICIT")
        line = None
    else:
        if raw["tie_settlement"] != "PUSH_ON_EXACT_LINE":
            raise ValueError("LINE_PUSH_SETTLEMENT_NOT_EXPLICIT")
        line = _numeric(raw["home_spread_or_total_line"], "LINE")
        if not (-90 <= line <= 90 if market == "SPREAD" else 0 <= line <= 150):
            raise ValueError("LINE_OUT_OF_BOUNDS")
    for field in ("model_sha256", "model_forecast_sha256", "provider_quote_sha256"):
        if not isinstance(raw[field], str) or not HASH.fullmatch(raw[field]):
            raise ValueError("BAD_SOURCE_OR_MODEL_HASH:"+field)
    kickoff = utc(raw["kickoff_utc"])
    seen = utc(raw["model_features_observed_utc"])
    model_asof = utc(raw["model_asof_utc"])
    quote_seen = utc(raw["quote_observed_utc"])
    quote_saved = utc(raw["quote_captured_utc"])
    decision = utc(raw["decision_utc"])
    final = utc(raw["final_utc"])
    published = utc(raw["result_available_utc"])
    if not (seen <= model_asof <= decision < kickoff
            and quote_seen <= quote_saved <= decision
            and kickoff < final <= published):
        raise ValueError("POINT_IN_TIME_OR_FINAL_CHRONOLOGY_BROKEN")
    if (decision - quote_saved).total_seconds() > freshness_seconds or (
        decision - quote_seen).total_seconds() > freshness_seconds:
        raise ValueError("STALE_PROVIDER_OR_LOCAL_QUOTE")
    taken = _american(raw["american_taken"], "TAKEN")
    opposite = _american(raw["american_opposite"], "OPPOSITE")
    pwin = _numeric(raw["model_p_win"], "PWIN")
    ppush = _numeric(raw["model_p_push"], "PPUSH")
    ploss = _numeric(raw["model_p_loss"], "PLOSS")
    if min(pwin, ppush, ploss) < 0 or max(pwin, ppush, ploss) > 1 or (
        abs(pwin + ppush + ploss - 1) > 1e-6):
        raise ValueError("MODEL_PROBABILITY_SIMPLEX_INVALID")
    if pwin + ploss <= 0:
        raise ValueError("NO_NONPUSH_MODEL_MASS")
    home = _score(raw["final_home"])
    away = _score(raw["final_away"])
    if market == "MONEYLINE_2WAY":
        margin = home - away
        sign = 1 if selection == "HOME" else -1
    elif market == "SPREAD":
        margin = (home - away) + line
        sign = 1 if selection == "HOME" else -1
    elif market == "TOTAL":
        margin = home + away - line
        sign = 1 if selection == "OVER" else -1
    elif market == "HOME_TEAM_TOTAL":
        margin = home - line
        sign = 1 if selection == "OVER" else -1
    else:
        margin = away - line
        sign = 1 if selection == "OVER" else -1
    outcome = "P" if margin == 0 else "W" if sign * margin > 0 else "L"
    q_taken, q_opposite = _implied(taken), _implied(opposite)
    market_conditional_p = q_taken / (q_taken + q_opposite)
    model_conditional_p = pwin / (pwin + ploss)
    profit = _decimal_profit(taken) if outcome == "W" else (
        -1.0 if outcome == "L" else 0.0)
    return {
        "game_id": raw["game_id"],
        "period": raw["period"],
        "provider_event_id": raw["provider_event_id"],
        "provider_market_id": raw["provider_market_id"],
        "provider_outcome_id": raw["provider_outcome_id"],
        "provider_opposite_outcome_id": raw["provider_opposite_outcome_id"],
        "quote_receipt_id": raw["quote_receipt_id"],
        "market": market,
        "book": raw["book"],
        "selection": selection,
        "line": line,
        "decision_utc": decision.isoformat(),
        "outcome": outcome,
        "profit_one_hypothetical_unit": profit,
        "model_conditional_win": model_conditional_p,
        "market_novig_conditional_win": market_conditional_p,
        "model_push_mass": ppush,
        "book_overround": q_taken + q_opposite - 1.0,
        "implied_taken": q_taken,
        "raw_model_ev_per_unit": pwin * _decimal_profit(taken) - ploss,
        "american_taken": taken,
        "american_opposite": opposite,
    }


def _summarize(items, *, resamples=400):
    graded = [r for r in items if r["outcome"] in ("W", "L")]
    n = len(graded)
    total = len(items)
    event_ids = sorted({r["game_id"] for r in graded})
    def brier(p, y):
        return (p-y) ** 2
    def nll(p, y):
        clipped = min(max(p, 1e-10), 1-1e-10)
        return -(y * math.log(clipped) + (1-y) * math.log(1-clipped))
    deltas, model_bs, market_bs, model_ll, market_ll = [], [], [], [], []
    for r in graded:
        y = 1 if r["outcome"] == "W" else 0
        pm = r["model_conditional_win"]
        pk = r["market_novig_conditional_win"]
        mb, kb = brier(pm,y), brier(pk,y)
        model_bs.append(mb); market_bs.append(kb)
        model_ll.append(nll(pm,y)); market_ll.append(nll(pk,y))
        deltas.append(kb-mb)  # Positive means model better.
    def mean(a):
        return round(sum(a)/len(a), 8) if a else None
    result = {
        "evaluated_nonpush_rows": n,
        "evaluated_distinct_games": len(event_ids),
        "push_rows_excluded_from_conditional_metrics": total-n,
        "all_original_outcome_rows": total,
        "wins": sum(r["outcome"]=="W" for r in items),
        "losses": sum(r["outcome"]=="L" for r in items),
        "pushes": sum(r["outcome"]=="P" for r in items),
        "model_conditional_brier": mean(model_bs),
        "market_novig_conditional_brier": mean(market_bs),
        "model_conditional_logloss": mean(model_ll),
        "market_novig_conditional_logloss": mean(market_ll),
        "paired_brier_gain_market_minus_model": mean(deltas),
        "net_units_at_original_prices_hypothetical_1u_each": round(
            sum(r["profit_one_hypothetical_unit"] for r in items), 8),
        "roi_original_prices_hypothetical_1u_each": mean([
            r["profit_one_hypothetical_unit"] for r in items]),
        "has_30_independent_games": len(event_ids) >= 30,
        "paired_brier_gain_cluster_95pct_ci": None,
    }
    if len(event_ids) >= 30:
        by_event = defaultdict(list)
        for r in graded:
            y = 1 if r["outcome"] == "W" else 0
            by_event[r["game_id"]].append(
                brier(r["market_novig_conditional_win"],y) -
                brier(r["model_conditional_win"],y))
        # Re-sample EVENTS rather than independently resampling every
        # correlated market/alt-line selection in the same game.
        rng = random.Random(20261115)
        values = []
        for _ in range(resamples):
            drawn = [event_ids[rng.randrange(len(event_ids))]
                     for _ in event_ids]
            diffs = [x for event in drawn for x in by_event[event]]
            values.append(sum(diffs)/len(diffs))
        values.sort()
        result["paired_brier_gain_cluster_95pct_ci"] = [
            round(values[int(.025*(resamples-1))],8),
            round(values[int(.975*(resamples-1))],8),
        ]
    return result


def evaluate_market_rows(rows, *, freshness_seconds=300):
    """Preserve invalid rows in the rejection census, never silently delete."""
    if (type(freshness_seconds) is not int or
        not 1 <= freshness_seconds <= 300):
        raise ValueError("INVALID_PREGAME_FRESHNESS_LIMIT")
    if not isinstance(rows, list):
        raise ValueError("ROWS_ARRAY_REQUIRED")
    qualified = []
    rejected = []
    for i, raw in enumerate(rows, 1):
        try:
            row = _validate(raw, freshness_seconds=freshness_seconds)
            # Preserve original source-row identity BEFORE grouping, even when
            # contradictory copies would otherwise each pass individual gates.
            row["source_row"] = i
            qualified.append(row)
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            rejected.append({"source_row": i, "reason": str(exc)})

    def same_selection_key(row):
        # Quote ID and price are NOT part of identity: repeated or conflicting
        # copies of one offered selection must both be quarantined.
        return (row["game_id"].strip(), row["period"], row["market"],
                " ".join(row["book"].casefold().split()),
                row["provider_event_id"].strip(), row["provider_market_id"].strip(),
                row["provider_outcome_id"].strip(), row["selection"], row["line"],
                row["decision_utc"])

    counts = Counter(same_selection_key(row) for row in qualified)
    accepted = []
    for row in qualified:
        if counts[same_selection_key(row)] > 1:
            rejected.append({"source_row": row["source_row"],
                             "reason": "DUPLICATE_SAME_MARKET_OUTCOME_PRICE_ALL_COPIES"})
        else:
            accepted.append(row)
    rejected.sort(key=lambda item: item["source_row"])
    by_market = {}
    for m in sorted(MARKETS):
        subset = [r for r in accepted if r["market"] == m]
        by_market[m] = (
            {"status": "NOT_CAPTURED", "count": 0}
            if not subset else {
                "status": "PAPER_HOLD_0U",
                **_summarize(subset),
            }
        )
    return {
        "status": "PAPER_HOLD_0U",
        "official_counted": 0,
        "approved_stake_u": 0,
        "source_authentication": False,
        "market_quotes_verified": False,
        "closing_line_verified": False,
        "market_baseline_description": (
            "TWO_SIDED_SAME_LINE_NO_VIG_CONDITIONAL_TO_NONPUSH"
        ),
        "quote_freshness_limit_seconds": freshness_seconds,
        "input_rows": len(rows),
        "accepted_research_rows": len(accepted),
        "rejected_rows": rejected,
        "rejection_reasons": dict(sorted(Counter(
            r["reason"] for r in rejected).items())),
        "research_rows": accepted,
        "market_evaluations": by_market,
        "notes": [
            "HYPOTHETICAL_1U_EACH_NOT_A_PORTFOLIO_OR_BETTING_LEDGER",
            "SELF_ASSERTED_PROVIDER_RECEIPTS_NO_INDEPENDENT_AUTHENTICATION",
            "NOT_CLV_WITHOUT_INDEPENDENT_MATCHED_CLOSING_QUOTES",
            "CONFIDENCE_INTERVALS_BOOTSTRAP_CLUSTER_BY_GAME",
            "NO_FINAL_TEST_FOLD_OR_CALIBRATION_PROMOTION_AUTHORIZED",
            "DO_NOT_USE_HOLDOUT_FOR_COEFFICIENT_OR_THRESHOLD_SELECTION",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", required=True, help="source-preserved candidate array JSON")
    parser.add_argument("--out", required=True)
    parser.add_argument("--freshness-seconds", type=int, default=300)
    args = parser.parse_args()
    # Both original input and detailed output contain sensitive quote prices.
    # Check paths before touching source bytes, including outward aliases.
    input_path = private_evidence_path(args.rows)
    private_evidence_path(args.out)
    raw = input_path.read_bytes()
    rows = strict_json_payload(raw)
    report = evaluate_market_rows(rows, freshness_seconds=args.freshness_seconds)
    report["local_original_input_sha256"] = "sha256:" + sha256(raw).hexdigest()
    payload = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    create_private_output(args.out, payload)
    print(json.dumps({"status": report["status"],
                      "input_rows": report["input_rows"],
                      "accepted": report["accepted_research_rows"],
                      "rejected": len(report["rejected_rows"]),
                      "out": args.out}, sort_keys=True))


if __name__ == "__main__":
    main()
