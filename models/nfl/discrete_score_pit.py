#!/usr/bin/env python3
"""NFL discrete final-score research from prior available paired residuals.

Each result distribution is a PAPER/0u diagnostic, NOT a calibrated betting
probability or inferred sportsbook offer. Requires real archived pregame
forecasts with independently checkable publication evidence upstream.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import floor, isfinite
from pathlib import Path

from score_walkforward_pit import utc, private_evidence_path, create_private_output
from feature_snapshot_bridge_pit import strict_original_json

HASH_PREFIX = "sha256:"
FORECAST_KEYS = frozenset({
    "game_id", "home_id", "away_id", "kickoff_utc", "forecast_asof_utc",
    "source_observed_utc", "model_sha256", "projected_home", "projected_away",
})
HISTORY_KEYS = FORECAST_KEYS | frozenset({
    "final_utc", "result_available_utc", "final_home", "final_away",
})
LINES_KEYS = frozenset({
    "game_id", "observed_at_utc", "home_spread", "game_total",
    "home_team_total", "away_team_total",
})
MARKET_FAMILIES_WITHOUT_MODEL = (
    "FIRST_HALF", "FIRST_QUARTER", "PLAYER_PROPS",
    "ANYTIME_TD", "FIRST_TD", "TD_2PLUS", "ALTERNATE_MARKET_LADDERS",
    "SAME_GAME_PARLAY",
)


def number(value, label):
    if isinstance(value, bool):
        raise ValueError("INVALID_NUMERIC:" + label)
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("INVALID_NUMERIC:" + label) from exc
    if not isfinite(v):
        raise ValueError("NONFINITE_NUMERIC:" + label)
    return v


def _exact_score(value, label):
    if type(value) is not int or value < 0 or value > 250:
        raise ValueError("INVALID_FINAL_SCORE:" + label)
    return value


def _forecast(raw):
    if not isinstance(raw, dict) or set(raw) != FORECAST_KEYS:
        raise ValueError("BAD_FROZEN_FORECAST_SCHEMA")
    gid = raw["game_id"]
    home, away = raw["home_id"], raw["away_id"]
    if (not isinstance(gid, str) or not gid.strip()
        or not isinstance(home, str) or not home.strip()
        or not isinstance(away, str) or not away.strip()
        or home == away):
        raise ValueError("EXACT_EVENT_AND_TEAM_IDS_REQUIRED")
    sha = raw["model_sha256"]
    if (not isinstance(sha, str) or not sha.startswith(HASH_PREFIX)
        or len(sha) != 71 or any(c not in "0123456789abcdef" for c in sha[7:])):
        raise ValueError("MODEL_SHA256_INVALID")
    start = utc(raw["kickoff_utc"])
    asof = utc(raw["forecast_asof_utc"])
    seen = utc(raw["source_observed_utc"])
    if not seen <= asof < start:
        raise ValueError("FROZEN_FORECAST_AFTER_SOURCE_OR_KICKOFF")
    hp = number(raw["projected_home"], "PROJECTED_HOME")
    ap = number(raw["projected_away"], "PROJECTED_AWAY")
    if not 0 <= hp <= 100 or not 0 <= ap <= 100:
        raise ValueError("PROJECTED_SCORE_OUT_OF_BOUNDS")
    return {"id": gid, "home": home, "away": away, "kickoff": start,
            "asof": asof, "seen": seen, "sha": sha, "hp": hp, "ap": ap}


def _history(raw):
    if not isinstance(raw, dict) or set(raw) != HISTORY_KEYS:
        raise ValueError("BAD_HISTORICAL_FORECAST_SCHEMA")
    entry = _forecast({k: raw[k] for k in FORECAST_KEYS})
    final = utc(raw["final_utc"])
    available = utc(raw["result_available_utc"])
    if not entry["kickoff"] < final <= available:
        raise ValueError("POSTGAME_OUTCOME_TIME_ORDER_INVALID")
    entry.update({
        "final": final, "available": available,
        "hs": _exact_score(raw["final_home"], "HOME"),
        "as": _exact_score(raw["final_away"], "AWAY"),
    })
    return entry


def _lines(raw, forecast):
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != LINES_KEYS:
        raise ValueError("BAD_MARKET_LINE_SCHEMA")
    if raw["game_id"] != forecast["id"]:
        raise ValueError("MARKET_EVENT_ID_MISMATCH")
    observed = utc(raw["observed_at_utc"])
    if not observed <= forecast["asof"]:
        raise ValueError("MARKET_LINES_AFTER_FROZEN_FORECAST")
    line = {}
    for key, bound in (
        ("home_spread", 90), ("game_total", 150),
        ("home_team_total", 100), ("away_team_total", 100),
    ):
        if raw[key] is None:
            line[key] = None
            continue
        value = number(raw[key], key)
        if (abs(value) > bound if key == "home_spread" else not 0 <= value <= bound):
            raise ValueError("MARKET_LINE_OUT_OF_REASONABLE_RANGE:" + key)
        line[key] = value
    return line


def _round_score(value):
    # Standard nonnegative half-up, not bankers' rounding at half points.
    return int(floor(max(0.0, value) + 0.5))


def _frequency(values):
    denom = len(values)
    return {k: round(v / denom, 8) for k, v in values.items()}


def _threeway(values):
    n = len(values)
    return {
        "over_or_home_cover": round(sum(x > 0 for x in values) / n, 8),
        "push": round(sum(x == 0 for x in values) / n, 8),
        "under_or_away_cover": round(sum(x < 0 for x in values) / n, 8),
        "sample_count": n,
    }


def _market_result(values, label, line, sign=1):
    if line is None:
        return {"status": "NOT_CAPTURED", "reason": "NO_SAME_EVENT_PREGAME_LINE"}
    x = _threeway([x + sign * line for x in values])
    x.update({"status": "PAPER_HOLD_0U", "line": line, "market_family": label,
              "source_authentication": False})
    return x


def score_distribution(target, history, *, lines=None, min_history=50):
    """Exact empirical paired-residual replay with explicit push probabilities.

    For each prior eligible event, shift its realized home/away forecast error
    onto the target's frozen mean; round both scores to integers. The pair of
    residuals remains intact, preserving observed score co-movement.

    Selection uses only results available at the target forecast as-of time.
    This has NO calibrated probability or source-authentication guarantee.
    """
    if type(min_history) is not int or min_history < 30:
        raise ValueError("MINIMUM_RESIDUAL_HISTORY_AT_LEAST_30_REQUIRED")
    f = _forecast(target)
    l = _lines(lines, f)
    if not isinstance(history, list):
        raise ValueError("HISTORICAL_FORECAST_LIST_REQUIRED")
    seen = set()
    pool = []
    census = Counter()
    for raw in history:
        h = _history(raw)
        census["history_rows_seen"] += 1
        if h["id"] == f["id"] or h["id"] in seen:
            raise ValueError("SELF_EVENT_OR_DUPLICATE_HISTORY_ROW")
        seen.add(h["id"])
        if h["sha"] != f["sha"]:
            census["excluded_different_model_version"] += 1
            continue
        if h["kickoff"] >= f["asof"] or h["available"] > f["asof"]:
            census["excluded_outcome_unavailable_at_forecast"] += 1
            continue
        pool.append((h["hs"] - h["hp"], h["as"] - h["ap"]))
    census["eligible_prior_residual_pairs"] = len(pool)
    output = {
        "status": "PAPER_HOLD_0U",
        "approved_stake_u": 0,
        "official_counted": 0,
        "event_id": f["id"],
        "forecast_asof_utc": f["asof"].isoformat(),
        "model_sha256": f["sha"],
        "cutoff_policy": "result_available_utc <= target_forecast_asof_utc",
        "source_authentication": "NOT_INDEPENDENTLY_ATTESTED",
        "calibration": "UNVERIFIED_EMPIRICAL_RESIDUALS",
        "census": dict(sorted(census.items())),
        "markets": {},
    }
    if len(pool) < min_history:
        output["reason"] = "INSUFFICIENT_MATCHED_PRIOR_RESIDUALS"
        for family in ("MONEYLINE", "SPREAD", "GAME_TOTAL",
                       "HOME_TEAM_TOTAL", "AWAY_TEAM_TOTAL"):
            output["markets"][family] = {"status": "NO_MODEL",
                                          "reason": "INSUFFICIENT_PRIOR_RESIDUALS"}
    else:
        pairs = [(_round_score(f["hp"] + he), _round_score(f["ap"] + ae))
                 for he, ae in pool]
        margins = [home - away for home, away in pairs]
        totals = [home + away for home, away in pairs]
        homes = [home for home, away in pairs]
        aways = [away for home, away in pairs]
        win = _threeway(margins)
        # In the NFL, an actual tie is possible. Two-way ML settlement is
        # book-specific and requires separate verified rules.
        output["markets"]["MONEYLINE"] = {
            "status": "PAPER_HOLD_0U",
            "home_win": win["over_or_home_cover"],
            "tie": win["push"],
            "away_win": win["under_or_away_cover"],
            "sample_count": len(pairs),
            "settlement_rule": "3_WAY_RESULTS_ONLY_NO_2_WAY_TIE_ASSUME",
        }
        home_spread = None if l is None else l["home_spread"]
        game_total = None if l is None else l["game_total"]
        htt = None if l is None else l["home_team_total"]
        att = None if l is None else l["away_team_total"]
        output["markets"]["SPREAD"] = _market_result(
            margins, "HOME_SPREAD", home_spread)
        output["markets"]["GAME_TOTAL"] = _market_result(
            totals, "GAME_TOTAL", game_total, sign=-1)
        output["markets"]["HOME_TEAM_TOTAL"] = _market_result(
            homes, "HOME_TEAM_TOTAL", htt, sign=-1)
        output["markets"]["AWAY_TEAM_TOTAL"] = _market_result(
            aways, "AWAY_TEAM_TOTAL", att, sign=-1)
        output["score_diagnostics"] = {
            "empirical_pairs": len(pairs),
            "mean_home": round(sum(homes) / len(homes), 5),
            "mean_away": round(sum(aways) / len(aways), 5),
            "exact_margin_frequency": _frequency(Counter(margins)),
            "exact_total_frequency": _frequency(Counter(totals)),
            "margin_3_frequency": round(margins.count(3) / len(margins), 8),
            "margin_7_frequency": round(margins.count(7) / len(margins), 8),
            "abs_margin_3_frequency": round(sum(abs(x) == 3 for x in margins) / len(margins), 8),
            "abs_margin_7_frequency": round(sum(abs(x) == 7 for x in margins) / len(margins), 8),
        }
    for family in MARKET_FAMILIES_WITHOUT_MODEL:
        output["markets"][family] = {
            "status": "NO_MODEL", "reason": "SEPARATE_PERIOD_PLAYER_OR_JOINT_MODEL_REQUIRED",
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="frozen pregame forecast JSON")
    parser.add_argument("--history", required=True, help="prior prediction+grade JSON array")
    parser.add_argument("--lines", help="optional exact event/pregame lines JSON")
    parser.add_argument("--min-history", type=int, default=50)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    # Validate ALL lexical and symlink-resolved locations before reading any
    # private source bytes. Only keep SHA of the exact bytes we just decoded:
    # double-reading each input would permit a hash/data mismatch under race.
    input_paths = {
        "target": private_evidence_path(args.target),
        "history": private_evidence_path(args.history),
    }
    if args.lines:
        input_paths["lines"] = private_evidence_path(args.lines)
    private_evidence_path(args.out)
    inputs = {kind: path.read_bytes() for kind, path in input_paths.items()}
    raw_target = strict_original_json(inputs["target"])
    raw_history = strict_original_json(inputs["history"])
    raw_line = strict_original_json(inputs["lines"]) if args.lines else None
    result = score_distribution(raw_target, raw_history,
                                lines=raw_line, min_history=args.min_history)
    result["local_input_sha256"] = {
        "target": HASH_PREFIX + sha256(inputs["target"]).hexdigest(),
        "history": HASH_PREFIX + sha256(inputs["history"]).hexdigest(),
        "lines": HASH_PREFIX + sha256(inputs["lines"]).hexdigest()
                 if args.lines else None,
    }
    payload = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    create_private_output(args.out, payload)
    print(json.dumps({"status": result["status"], "out": args.out,
                      "eligible_residuals": result["census"]["eligible_prior_residual_pairs"],
                      "approved_stake_u": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
