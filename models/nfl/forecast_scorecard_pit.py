#!/usr/bin/env python3
"""NFL forecast scorecard: strict same-game, pregame paired evaluation.

Read-only RESEARCH/PAPER/0u. Scores three *existing pregame forecasts*;
does not fabricate a score model from NFL EPA ridge features. No sportsbooks,
bets, stakes, live odds or network access. All predictions must be archived
before kickoff with source and model custody records.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

MODELS = ("ridge", "elo", "epa")
GAME_FIELDS = ("game_id", "season", "week", "home", "away",
               "kickoff_utc", "final_available_utc", "home_score", "away_score")
FORECAST_FIELDS = ("game_id", "model", "forecast_utc", "source_available_utc",
                   "training_cutoff_utc", "model_version_sha256",
                   "input_sha256", "home_margin", "total", "home_win_prob")


class Inadmissible(ValueError):
    pass


def utc(value, label):
    if not value:
        raise Inadmissible(label + "_MISSING")
    try:
        v = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise Inadmissible(label + "_INVALID") from exc
    if v.tzinfo is None or v.utcoffset() is None:
        raise Inadmissible(label + "_NAIVE")
    return v.astimezone(timezone.utc)


def finite(text, label):
    try:
        x = float(text)
    except (ValueError, TypeError) as exc:
        raise Inadmissible(label + "_NOT_NUMERIC") from exc
    if not math.isfinite(x):
        raise Inadmissible(label + "_NONFINITE")
    return x


def rows_from_csv(path, required, label):
    raw = Path(path).read_bytes()
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        header = [c.strip() for c in next(reader, [])]
        if not header or not all(header) or len(header) != len(set(header)):
            raise Inadmissible(label + "_AMBIGUOUS_HEADER")
        if set(required).difference(header):
            raise Inadmissible(label + "_MISSING_COLUMN:" +
                               ",".join(sorted(set(required).difference(header))))
        rows = []
        for line_no, values in enumerate(reader, 2):
            if len(values) != len(header) or not any(str(v).strip() for v in values):
                raise Inadmissible(label + "_MALFORMED_ROW:" + str(line_no))
            rows.append(dict(zip(header, (v.strip() for v in values))))
    except (UnicodeError, csv.Error) as exc:
        raise Inadmissible(label + "_INVALID_CSV") from exc
    return rows, hashlib.sha256(raw).hexdigest()


def require_hex(text, key):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(text or "")):
        raise Inadmissible(key + "_MISSING_OR_NOT_SHA256")


def valid_game(row):
    if not row["game_id"] or not row["home"] or not row["away"] or row["home"] == row["away"]:
        raise Inadmissible("BAD_GAME_IDENTITY")
    if not str(row["season"]).isdigit() or not (2000 <= int(row["season"]) <= 2100):
        raise Inadmissible("BAD_SEASON")
    if not str(row["week"]).isdigit() or not (1 <= int(row["week"]) <= 22):
        raise Inadmissible("BAD_WEEK")
    kickoff = utc(row["kickoff_utc"], "KICKOFF")
    final_at = utc(row["final_available_utc"], "FINAL_AVAILABLE")
    if final_at <= kickoff:
        raise Inadmissible("OUTCOME_AVAILABLE_BEFORE_KICKOFF")
    h, a = finite(row["home_score"], "HOME_SCORE"), finite(row["away_score"], "AWAY_SCORE")
    if not (h >= 0 and a >= 0 and h <= 100 and a <= 100 and int(h) == h and int(a) == a):
        raise Inadmissible("INVALID_FINAL_SCORE")
    return kickoff, h, a


def valid_forecast(row, kickoff):
    try:
        if row["model"] not in MODELS:
            raise Inadmissible("UNKNOWN_FORECAST_MODEL")
        forecast = utc(row["forecast_utc"], "FORECAST")
        source = utc(row["source_available_utc"], "SOURCE_AVAILABLE")
        trained = utc(row["training_cutoff_utc"], "TRAINING_CUTOFF")
        if not trained <= source <= forecast < kickoff:
            raise Inadmissible("NOT_STRICTLY_PREGAME")
        require_hex(row["model_version_sha256"], "MODEL_VERSION")
        require_hex(row["input_sha256"], "INPUT")
        margin = finite(row["home_margin"], "MARGIN")
        total = finite(row["total"], "TOTAL")
        prob = finite(row["home_win_prob"], "HOME_WIN_PROB")
        if not (-100 <= margin <= 100 and 0 <= total <= 180 and 0 < prob < 1):
            raise Inadmissible("FORECAST_OUT_OF_RANGE")
        if abs(margin) > total:
            raise Inadmissible("IMPOSSIBLE_POINTS_GEOMETRY")
        return {"home_margin": margin, "total": total, "home_win_prob": prob}
    except Inadmissible as exc:
        return {"rejected": str(exc)}


def _round(x):
    return round(x, 6)


def summarize(rows):
    if not rows:
        return None
    n = len(rows)
    margin_errors = [r["margin"] - r["actual_margin"] for r in rows]
    total_errors = [r["total"] - r["actual_total"] for r in rows]
    briers = [(r["prob"] - r["home_win"]) ** 2 for r in rows]
    logs = [-r["home_win"] * math.log(r["prob"]) -
            (1 - r["home_win"]) * math.log1p(-r["prob"]) for r in rows]
    mae = lambda seq: sum(abs(x) for x in seq) / n
    rmse = lambda seq: math.sqrt(sum(x * x for x in seq) / n)
    cal = []
    for i in range(10):
        b = [r for r in rows if min(9, int(r["prob"] * 10)) == i]
        cal.append({"range": f"{i * 10}-{(i + 1) * 10}%",
                    "n": len(b),
                    "mean_predicted": _round(sum(r["prob"] for r in b) / len(b)) if b else None,
                    "actual_home_win_rate": _round(sum(r["home_win"] for r in b) / len(b)) if b else None})
    return {"n": n, "margin_mae": _round(mae(margin_errors)),
            "margin_rmse": _round(rmse(margin_errors)),
            "total_mae": _round(mae(total_errors)),
            "total_rmse": _round(rmse(total_errors)),
            "brier": _round(sum(briers) / n),
            "log_loss": _round(sum(logs) / n),
            "calibration": cal}


def score(games, forecasts, min_paired=100, model_names=MODELS):
    """Paired-only metrics, no retrospective selection or changing denominator."""
    if not games:
        raise Inadmissible("EMPTY_GAMES")
    if min_paired < 1:
        raise Inadmissible("MIN_PAIRED_MUST_BE_POSITIVE")
    if set(model_names) != set(MODELS):
        raise Inadmissible("THREE_BASELINES_REQUIRED")
    by_game = {}
    for row in games:
        if row["game_id"] in by_game:
            raise Inadmissible("DUPLICATE_GAME")
        valid_game(row)
        by_game[row["game_id"]] = row
    by_forecast = {}
    for row in forecasts:
        key = (row["game_id"], row["model"])
        if row["game_id"] not in by_game:
            raise Inadmissible("ORPHAN_FORECAST")
        if row["model"] not in MODELS:
            raise Inadmissible("UNKNOWN_FORECAST_MODEL")
        if key in by_forecast:
            raise Inadmissible("DUPLICATE_FORECAST")
        by_forecast[key] = row
    rejections, eligible, per_model_eligible = [], [], {m: 0 for m in MODELS}
    for g in games:
        gid = g["game_id"]
        ko, home, away = valid_game(g)
        reasons = {}
        normalized = {}
        for m in MODELS:
            row = by_forecast.get((gid, m))
            if row is None:
                reasons[m] = "MISSING_FORECAST"
                continue
            f = valid_forecast(row, ko)
            if "rejected" in f:
                reasons[m] = f["rejected"]
            else:
                normalized[m] = f
                per_model_eligible[m] += 1
        if home == away:
            reasons["outcome"] = "TIED_NFL_RESULT_NO_BINARY_HOME_WIN"
        if reasons:
            rejections.append({"game_id": gid, "reasons": reasons})
            continue
        eligible.append({"game_id": gid, "season": g["season"], "week": g["week"],
                         "actual_margin": home - away, "actual_total": home + away,
                         "home_win": int(home > away), "forecasts": normalized})
    scores = {}
    for m in MODELS:
        metrics = [{"margin": x["forecasts"][m]["home_margin"],
                    "total": x["forecasts"][m]["total"],
                    "prob": x["forecasts"][m]["home_win_prob"],
                    "actual_margin": x["actual_margin"],
                    "actual_total": x["actual_total"],
                    "home_win": x["home_win"]} for x in eligible]
        scores[m] = summarize(metrics)
    reason_counts = dict(Counter(f"{m}:{r}" for x in rejections
                                 for m, r in x["reasons"].items()))
    n = len(eligible)
    return {"status": "RESEARCH_PAPER_0U",
            "interpretation": "INSUFFICIENT_PAIRED_SAMPLE" if n < min_paired
                              else "PAIRED_RESEARCH_DESCRIPTIVE_ONLY",
            "official_model_admitted": False, "betting_authorized": False,
            "stake_u": 0, "models": list(MODELS), "slate_n": len(games),
            "paired_n": n, "blocked_n": len(rejections),
            "per_model_pregame_eligible": per_model_eligible,
            "blocked_reasons": reason_counts, "blocked_games": rejections,
            "paired_game_ids": [x["game_id"] for x in eligible],
            "scores": scores,
            "limitations": [
                "No independent authentication of the source/provider publication clock",
                "SHA256 verifies archived bytes, not that those bytes existed before kickoff",
                "Ridge feature stage is NOT a points/probability forecaster",
                "No automatic nflverse downloads, refitting, or actual betting approvals",
                "Elo or EPA forecasts must be separately frozen before kickoff",
                "No market-price or closing-line validation performed"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("games", "forecasts", "out"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--min-paired", type=int, default=100)
    a = p.parse_args()
    g, ghash = rows_from_csv(a.games, GAME_FIELDS, "GAMES")
    f, fhash = rows_from_csv(a.forecasts, FORECAST_FIELDS, "FORECASTS")
    result = score(g, f, min_paired=a.min_paired)
    result["inputs_sha256"] = {"games": ghash, "forecasts": fhash}
    with open(a.out, "x", encoding="utf-8") as file:
        json.dump(result, file, sort_keys=True, indent=2)
        file.write("\n")
    print(f"{result['interpretation']}: matched {result['paired_n']}/{result['slate_n']}, "
          f"BLOCKED={result['blocked_n']}, official units=0")


if __name__ == "__main__":
    main()
