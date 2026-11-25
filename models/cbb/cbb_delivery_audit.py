"""CBB delivery-time safety and chronological residual diagnostics (research only).

Separate from the frozen forecast and ledger. Never changes a probability, quote,
stake, grade, or historic card. A delivery screen is not a release authorization.
"""
from datetime import datetime, timezone
import math
import statistics
import argparse
import hashlib
import json
from pathlib import Path

MAX_QUOTE_AGE_MINUTES = 20  # candidate research delivery policy, not a calibrated threshold
MIN_EV = 0.01


def utc(value):
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_REQUIRED")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return d.astimezone(timezone.utc)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def delivery_audit(card, delivery_utc, *, max_age_minutes=MAX_QUOTE_AGE_MINUTES):
    """Census every frozen row at delivery, including all rejection reasons.

    Even rows without these defects remain PAPER/0u, NOT_RELEASED.
    No correlation assumptions: report positive research candidates per game.
    """
    payload = {k: v for k, v in card.items() if k != "card_sha256"}
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if card.get("card_sha256") != expected:
        raise ValueError("CARD_DIGEST_MISMATCH")
    now = utc(delivery_utc)
    if not finite(max_age_minutes) or not 0 < max_age_minutes <= 60:
        raise ValueError("MAX_DELIVERY_QUOTE_AGE_INVALID")
    freeze = utc(card["freeze_utc"])
    if freeze > now:
        raise ValueError("FUTURE_CARD_FREEZE")
    game_map = {}
    for g in card["games"]:
        gid = g["game_id"]
        if gid in game_map:
            raise ValueError("DUPLICATE_GAME_ID")
        game_map[gid] = g
    counts, groups, rows = {}, {}, []
    for r in card["priced"]:
        why = []
        gid = r["game_id"]
        g = game_map.get(gid)
        advisory = []
        try:
            cap = utc(r.get("captured_utc"))
            tip = utc(g["tipoff_utc"] if g else None)
            if cap > freeze or cap > now:
                why.append("QUOTE_AFTER_FREEZE")
            if cap >= tip:
                why.append("LIVE_QUOTE")
            if tip <= now:
                why.append("GAME_STARTED")
            if (now - cap).total_seconds() > 60 * max_age_minutes:
                advisory.append("QUOTE_AGE_EXCEEDS_RESEARCH_TARGET")
        except (TypeError, ValueError, KeyError):
            why.append("CLOCK_OR_GAME_ID_UNVERIFIED")
        if r.get("provenance") != "AUTHENTICATED_DK_CAPTURE":
            why.append("ODDS_UNAUTHENTICATED")
        if card.get("projection_adapter") != "frozen_native_cbbd":
            why.append("PRODUCTION_RATINGS_UNAVAILABLE")
        period, market = r.get("period"), r.get("market")
        method = str(r.get("hybrid_method") or "")
        if period != "FG":
            why.append("HALF_BLEND_UNVALIDATED")
            if market == "ML":
                why.append("HALF_ML_SETTLEMENT_UNVERIFIED")
        if period == "FG" and ("UNVALIDATED" in method or "VALIDATION_SELECTED" not in method):
            why.append("BLEND_UNVALIDATED")
        if market in ("TT_HOME", "TT_AWAY"):
            why.append("TEAM_TOTAL_BLEND_UNVALIDATED")
        if str(market).startswith("PLAYER_"):
            why.append("PLAYER_CALIBRATION_UNVERIFIED")
        ev = r.get("ev_hybrid")
        if not finite(ev):
            why.append("EV_INVALID")
        elif ev < MIN_EV:
            why.append("BELOW_EV_FLOOR")
        else:
            groups[gid] = groups.get(gid, 0) + 1
        if any("EV_GT_30" in str(flag) for flag in (r.get("audit_flags") or [])):
            why.append("INFLATED_EV_REVIEW")
        for reason in set(why):
            counts[reason] = counts.get(reason, 0) + 1
        rows.append({"game_id": gid, "period": period, "market": market,
                     "line": r.get("line"), "side": r.get("side"),
                     "ev_hybrid": ev, "reasons": sorted(set(why)),
                     "advisories": advisory,
                     "status": "HOLD" if why else "RESEARCH_ONLY",
                     "approved_stake_u": 0})
    correlated = sorted(g for g, n in groups.items() if n > 1)
    return {"delivery_utc": delivery_utc, "freeze_utc": card["freeze_utc"],
            "card_sha256": card.get("card_sha256"), "max_quote_age_minutes": max_age_minutes,
            "min_ev": MIN_EV, "rows": rows, "reason_counts": counts,
            "age_advisory_count": sum(bool(r["advisories"]) for r in rows),
            "multi_candidate_games": correlated, "released": 0,
            "label": "PAPER_0U", "counted": "NON_COUNTED"}


def fit_prior_residuals(records, cutoff_utc, *, min_games=100):
    """Training-only diagnostic; requires genuinely archived pre-tip forecasts.

    The caller must authenticate archive timestamps and hashes independently.
    Do not use fitted residuals to evaluate the training rows or alter the freeze.
    """
    cutoff = utc(cutoff_utc)
    if type(min_games) is not int or min_games < 2:
        raise ValueError("MIN_GAMES_INVALID")
    errors, seen = {"margin": [], "total": []}, set()
    for r in records:
        forecast, tip, final = (utc(r[k]) for k in
                               ("forecast_observed_utc", "tip_utc", "final_observed_utc"))
        if not forecast < tip < final:
            raise ValueError("RESIDUAL_CLOCK_INVALID")
        if final >= cutoff:
            continue
        gid = r["game_id"]
        if not gid or gid in seen:
            raise ValueError("DUPLICATE_RESIDUAL_GAME")
        seen.add(gid)
        for k in errors:
            predicted, actual = r["predicted_" + k], r["actual_" + k]
            if not finite(predicted) or not finite(actual):
                raise ValueError("NONFINITE_RESIDUAL")
            errors[k].append(actual - predicted)
    if len(seen) < min_games:
        return {"status": "HOLD_INSUFFICIENT_PRIOR_RESIDUALS", "n": len(seen)}
    metrics = {k: {"bias_actual_minus_model": statistics.mean(v),
                   "sd": statistics.stdev(v),
                   "rmse": math.sqrt(statistics.mean(x*x for x in v))}
               for k, v in errors.items()}
    if any(v["sd"] <= 0 for v in metrics.values()):
        raise ValueError("DEGENERATE_RESIDUAL_SD")
    return {"status": "TRAINING_DIAGNOSTIC_ONLY", "n": len(seen),
            "cutoff_utc": cutoff_utc, "metrics": metrics}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("card", type=Path)
    p.add_argument("--delivery-utc", required=True)
    p.add_argument("--max-age-minutes", type=float, default=MAX_QUOTE_AGE_MINUTES)
    x = p.parse_args()
    result = delivery_audit(json.loads(x.card.read_text()), x.delivery_utc,
                            max_age_minutes=x.max_age_minutes)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
