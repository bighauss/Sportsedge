"""CBB paper-card display gate: EV is not verified five-star confidence.

Frozen v5 and all historic selections stay untouched. This presentation-only
overlay uses the operative POWER_V1/Lane A research path unchanged; the separate
30/70 v2.1 risk diagnostic is NOT introduced as a price adjustment.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import argparse
import re
from pathlib import Path


class CardConfidenceError(ValueError):
    pass


SHA = re.compile(r"^[0-9a-f]{64}$")
UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _time(value, name):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise CardConfidenceError(name + "_UTC_REQUIRED")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CardConfidenceError(name + "_INVALID") from exc


def _float(value, label):
    try:
        v = Decimal(str(value))
        if not v.is_finite():
            raise InvalidOperation
        return float(v)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CardConfidenceError(label + "_INVALID") from exc


def _odds(value):
    n = _float(value, "PRICE")
    if n != int(n) or not (100 <= abs(n) <= 100000):
        raise CardConfidenceError("INVALID_AMERICAN_PRICE")
    return n


def _implied(o):
    return 100 / (100 + o) if o > 0 else -o / (100 - o)


def decorate_research_card(card: dict) -> dict:
    """Create a distinct display object; do not mutate the original card.

    In absence of verified independent forward calibration, remove stars from
    display. Original model stars stay in a clearly named legacy field solely
    for research traceability. A quoted opposite side is needed for a simple
    no-vig diagnostic, never as a substitute for the operative POWER_V1 fit.
    """
    if not isinstance(card, dict) or card.get("release") != "PAPER_0U":
        raise CardConfidenceError("PAPER_0U_SOURCE_REQUIRED")
    src = card.get("source")
    if not isinstance(src, dict):
        raise CardConfidenceError("SOURCE_METADATA_REQUIRED")
    for name in ("model_sha256", "feature_sha256"):
        if not isinstance(src.get(name), str) or not SHA.fullmatch(src[name]):
            raise CardConfidenceError(name.upper() + "_REQUIRED")
    frozen = _time(src.get("frozen_utc"), "MODEL_FROZEN")
    plays = card.get("plays")
    if not isinstance(plays, list):
        raise CardConfidenceError("PLAYS_ARRAY_REQUIRED")
    result, seen = [], set()
    for p in plays:
        if not isinstance(p, dict):
            raise CardConfidenceError("MALFORMED_PLAY")
        for key in ("bet_id", "event_id", "market", "side"):
            if not isinstance(p.get(key), str) or not p[key].strip():
                raise CardConfidenceError(key.upper() + "_REQUIRED")
        if p["bet_id"] in seen:
            raise CardConfidenceError("DUPLICATE_SELECTION")
        seen.add(p["bet_id"])
        if p.get("status") != "PAPER_0U":
            raise CardConfidenceError("PLAY_PAPER_0U_REQUIRED")
        cap = _time(p.get("captured_utc"), "QUOTE_CAPTURED")
        tip = _time(p.get("tipoff_utc"), "TIPOFF")
        if not frozen <= cap < tip:
            raise CardConfidenceError("NOT_PREGAME_OR_FEATURE_AFTER_QUOTE")
        pmodel = _float(p.get("model_p"), "MODEL_P")
        if not 0 < pmodel < 1:
            raise CardConfidenceError("MODEL_P_OUT_OF_RANGE")
        odds = _odds(p.get("price_american"))
        raw_ev = pmodel * (1 + (odds / 100 if odds > 0 else 100 / -odds)) - 1
        if "raw_ev" in p and abs(_float(p["raw_ev"], "RAW_EV") - raw_ev) > .0015:
            raise CardConfidenceError("MODEL_EV_ARITHMETIC_MISMATCH")
        other, market_p = p.get("opposite_american"), None
        if other is not None:
            op = _odds(other)
            market_p = _implied(odds) / (_implied(odds) + _implied(op))
        elif p.get("market_p") is not None:
            raise CardConfidenceError("MARKET_PROB_WITHOUT_OPPOSING_QUOTE")
        output = {**p,
                  "legacy_raw_ev_stars": p.get("stars"),
                  "stars": None, "show_five_stars": False,
                  "confidence_label": "UNVALIDATED",
                  "raw_ev_recomputed": round(raw_ev, 6),
                  "market_p_simple_novig_diagnostic": (
                      round(market_p, 6) if market_p is not None else None),
                  "model_minus_market_pp_diagnostic": (
                      round(100 * (pmodel - market_p), 3)
                      if market_p is not None else None),
                  "reasons": ["EV_NOT_CALIBRATED_CONFIDENCE",
                              "NO_FORWARD_CERTIFICATION",
                              "PAPER_0U_ONLY"] + (
                              ["OPPOSING_QUOTE_NOT_SUPPLIED"] if market_p is None else []),
                  "approved_stake_u": 0, "official_counted": 0}
        result.append(output)
    return {"release": "PAPER_0U", "source": dict(src),
            "plays": result, "rating_policy": "SUPPRESS_UNVALIDATED_CBB_STARS",
            "pricing_policy": "POWER_V1_LANE_A_UNCHANGED",
            "approved_stake_u": 0, "official_counted": 0}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_card_json", type=Path)
    p.add_argument("output_display_json", type=Path)
    a = p.parse_args(argv)
    if a.input_card_json.resolve() == a.output_display_json.resolve():
        p.error("MUST_NOT_OVERWRITE_ORIGINAL_CARD")
    raw = json.loads(a.input_card_json.read_text(encoding="utf-8"))
    try:
        result = decorate_research_card(raw)
    except CardConfidenceError as exc:
        p.exit(2, "CBB_DISPLAY_BLOCKED:" + str(exc) + "\n")
    # Create-only; no archive or previous display may be overwritten.
    with a.output_display_json.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
