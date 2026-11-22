"""Seven-sport exact-offer/model research comparison; NO certified wagering.

Consumes a supplied census, independent-model assertions and quoted prices.
Does not infer probabilities from point projection gaps or bookmaker odds.
Every submitted exact offer remains visible, even without a projection/price.
Metadata alone never authenticates sources, calibration or posted odds.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from research.audit import all_sports_market_census as universe

SCHEMA = "sportsedge-seven-sport-beta-comparison-v1"
ROOT_FIELDS = {"schema", "census", "forecasts", "prices"}
MODEL_FIELDS = {
    "sport", "event_id", "market_family", "period", "selection_id",
    "participant_id", "stat", "line", "settlement_rule", "origin",
    "model_sha256", "distribution_sha256", "model_asof_utc",
    "p_win", "p_push", "period_distribution_sha256",
    "ordered_events_sha256", "count_distribution_sha256",
    "joint_distribution_sha256",
}
PRICE_FIELDS = {"sport", "book", "offer_id", "price_american"}
EVENT_CLASSES_ORDERED = frozenset(("FIRST_TD", "FIRST_BASKET", "FIRST_GOAL"))
EVENT_CLASSES_COUNT = frozenset(("TD_2PLUS",))
EVENT_CLASSES_JOINT = frozenset(("SGP", "MATCHUP", "THREE_BALL"))


def _forecast_key(row):
    return (row["sport"], row["event_id"], row["market_family"],
            row["period"], row["selection_id"], row["participant_id"],
            row["stat"], universe._line(row["line"]), row["settlement_rule"])


def _prob(v, label):
    if type(v) not in (float, int) or not (0 <= v <= 1):
        raise ValueError("INVALID_PROBABILITY:" + label)
    return float(v)


def _price(v):
    if type(v) is not int or abs(v) < 100 or abs(v) > 100000:
        raise ValueError("INVALID_AMERICAN_ODDS")
    return v


def _ev(p_win, p_push, price):
    win_profit = (price / 100 if price > 0 else 100 / -price)
    return p_win * win_profit - (1 - p_win - p_push)


def evaluate(data, *, max_quote_age_minutes=30):
    universe._exact(data, ROOT_FIELDS, "root")
    if data["schema"] != SCHEMA:
        raise ValueError("INVALID_BETA_SCHEMA")
    if type(max_quote_age_minutes) is not int or not 0 <= max_quote_age_minutes <= 1440:
        raise ValueError("INVALID_MAX_QUOTE_AGE")
    census = data["census"]
    universe_report = universe.assess(census)
    forecasts, prices = data["forecasts"], data["prices"]
    if (type(forecasts) is not list or type(prices) is not list or
            len(forecasts) > 100000 or len(prices) > 100000):
        raise ValueError("BETA_INPUTS_INVALID")
    events = {(e["sport"], e["event_id"]): universe._utc(e["start_utc"], "event_start")
              for e in census["events"]}
    predicted = {}
    for p in forecasts:
        universe._exact(p, MODEL_FIELDS, "forecast")
        if type(p["sport"]) is not str or p["sport"] not in universe.SPORTS:
            raise ValueError("UNKNOWN_SPORT")
        if type(p["market_family"]) is not str or p["market_family"] not in universe.FAMILIES[p["sport"]]:
            raise ValueError("UNKNOWN_MODEL_MARKET_FAMILY")
        if (p["sport"], p["event_id"]) not in events:
            raise ValueError("FORECAST_OUTSIDE_EXPECTED_EVENTS")
        if p["origin"] != "SPORTSEDGE_INDEPENDENT":
            # Explicitly refuse third-party, book-anchored or unlabeled forecasts.
            raise ValueError("NOT_AN_ASSERTED_INDEPENDENT_MODEL")
        for f in ("model_sha256", "distribution_sha256", "period_distribution_sha256",
                  "ordered_events_sha256", "count_distribution_sha256", "joint_distribution_sha256"):
            universe._hash(p[f], f)
        if p["model_sha256"] is None or p["distribution_sha256"] is None:
            raise ValueError("MODEL_DISTRIBUTION_HASH_REQUIRED")
        pw, pp = _prob(p["p_win"], "p_win"), _prob(p["p_push"], "p_push")
        if pw + pp > 1 + 1e-12:
            raise ValueError("WIN_PUSH_TOTAL_GT_ONE")
        model_asof = universe._utc(p["model_asof_utc"], "model_asof")
        if model_asof >= events[(p["sport"], p["event_id"])]:
            raise ValueError("MODEL_NOT_PREGAME")
        key = _forecast_key(p)
        if key in predicted:
            raise ValueError("DUPLICATED_EXACT_MARKET_FORECAST")
        predicted[key] = (p, model_asof, pw, pp)
    offered = {}
    for p in prices:
        universe._exact(p, PRICE_FIELDS, "price")
        if type(p["sport"]) is not str or p["sport"] not in universe.SPORTS:
            raise ValueError("UNKNOWN_SPORT")
        key = (p["sport"], universe._id(p["book"], "price_book"),
               universe._id(p["offer_id"], "price_offer"))
        if key in offered:
            raise ValueError("DUPLICATED_EXACT_OFFER_PRICE")
        offered[key] = _price(p["price_american"])
    market_keys = set()
    price_keys = set()
    rows, reasons = [], Counter()
    for entry, censused in zip(census["attempts"], universe_report["attempts"], strict=True):
        key = (
            censused["sport"], censused["event_id"], censused["market_family"],
            censused["period"], censused["selection_id"], censused["participant_id"],
            censused["stat"], censused["line"], censused["settlement_rule"],
        )
        offer_key = (censused["sport"], censused["book"], censused["offer_id"])
        market_keys.add(key)
        if offer_key in offered:
            price_keys.add(offer_key)
        errors = list(censused["reasons"])
        # A missing closing or final receipt does not invalidate a pregame
        # research comparison; retain the gaps, but don't use them as a gate.
        errors = [x for x in errors if x not in (
            "CLOSING_QUOTE_NOT_CAPTURED", "FINAL_RESULT_NOT_CAPTURED",
            "RECEIPT_METADATA_NOT_INDEPENDENTLY_AUTHENTICATED")]
        model = predicted.get(key)
        quote = offered.get(offer_key)
        if model is None:
            errors.append("NO_EXACT_MODEL_FORECAST_FOR_OUTCOME")
        if quote is None:
            errors.append("NO_EXACT_PRICE_FOR_OFFER")
        if model is not None and entry["model_sha256"] != model[0]["model_sha256"]:
            errors.append("MODEL_RECEIPT_HASH_MISMATCH")
        if model is not None:
            p, asof, pw, pp = model
            if censused["period"] != "FG" and p["period_distribution_sha256"] is None:
                errors.append("NO_PERIOD_DISTRIBUTION")
            if key[2] in EVENT_CLASSES_ORDERED and p["ordered_events_sha256"] is None:
                errors.append("NO_ORDERED_EVENT_DISTRIBUTION")
            if key[2] in EVENT_CLASSES_COUNT and p["count_distribution_sha256"] is None:
                errors.append("NO_COUNT_EVENT_DISTRIBUTION")
            if key[2] in EVENT_CLASSES_JOINT and p["joint_distribution_sha256"] is None:
                errors.append("NO_JOINT_DISTRIBUTION")
            observed = entry["source_observed_utc"]
            captured = entry["source_captured_utc"]
            if observed is not None and captured is not None:
                clock = universe._utc(captured, "quote_capture")
                if (asof - clock).total_seconds() > max_quote_age_minutes * 60:
                    errors.append("QUOTE_STALE_RELATIVE_TO_MODEL")
        critical = list(dict.fromkeys(errors))
        # Only positive/nonpositive research hypotheses for structurally
        # matched models + prices. Never a verified or official selection.
        ev = _ev(pw, pp, quote) if not critical else None
        status = ("BLOCKED_NO_PREGAME_COMPARISON" if ev is None else
                  "UNVERIFIED_RESEARCH_POSITIVE_EV" if ev > 0 else
                  "UNVERIFIED_RESEARCH_NONPOSITIVE_EV")
        reasons.update(critical)
        rows.append({
            "sport": censused["sport"], "event_id": censused["event_id"],
            "book": censused["book"], "offer_id": censused["offer_id"],
            "market_family": censused["market_family"], "period": censused["period"],
            "selection_id": censused["selection_id"],
            "participant_id": censused["participant_id"], "stat": censused["stat"],
            "line": censused["line"], "settlement_rule": censused["settlement_rule"],
            "status": status, "reasons": critical,
            "claimed_model_p_win": pw if model is not None else None,
            "claimed_model_p_push": pp if model is not None else None,
            "posted_price_unverified": quote,
            "research_ev_per_unit_unverified": ev,
            "source_authenticated": False, "calibration_verified": False,
            "certified_positive_ev": False, "official_counted": 0,
            "approved_stake_u": 0, "bet_eligible": False,
        })
    if set(predicted) - market_keys:
        raise ValueError("ORPHAN_FORECAST_OUTSIDE_ATTEMPTED_MARKETS")
    if set(offered) - price_keys:
        raise ValueError("ORPHAN_OFFER_PRICE")
    return {
        "schema": "sportsedge-seven-sport-beta-comparison-report-v1",
        "state": "PAPER_0U_ALL_MARKETS_RESEARCH_ONLY",
        "submitted_outcomes": len(rows),
        "research_comparisons": sum(r["research_ev_per_unit_unverified"] is not None for r in rows),
        "research_positive_ev": sum(r["status"] == "UNVERIFIED_RESEARCH_POSITIVE_EV" for r in rows),
        "blocked": sum(r["status"] == "BLOCKED_NO_PREGAME_COMPARISON" for r in rows),
        "reason_counts": dict(sorted(reasons.items())),
        "market_universe_complete": False, "certified_positive_ev": False,
        "official_counted": 0, "approved_stake_u": 0,
        "rows": rows, "sport_family_matrix": universe_report["matrix"],
        "limitations": [
            "Model win/push chances are supplied assertions, not independently verified",
            "Posted odds and quote hashes are not authenticated provider originals",
            "No market-specific calibration, closing-line, execution or release proof",
            "Research expected values are hypotheses only, not bets or certified edges",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", help="normalized research metadata only, not private originals")
    parser.add_argument("--out", help="new JSON report; will not overwrite")
    args = parser.parse_args(argv)
    raw = Path(args.input_json).read_bytes()
    if not 0 < len(raw) <= 20_000_000:
        raise ValueError("INVALID_INPUT_SIZE")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=universe._pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(
                          ValueError("NONFINITE_JSON:" + x)))
    result = evaluate(data)
    payload = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.out:
        with Path(args.out).open("x", encoding="utf-8") as f:
            f.write(payload)
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
