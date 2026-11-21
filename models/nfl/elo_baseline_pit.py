#!/usr/bin/env python3
"""Research-only Elo-style NFL baseline from earlier *observed* final games.

Not an implementation or endorsement of the FiveThirtyEight proprietary
forecast, not a calibrated scoring model. Research-only K20, HFA65, 25 Elo
per margin point and historical mean total are unvalidated starting choices.
Produces source-time-stamped forecast rows for forecast_scorecard_pit.py,
and an explicit blocked-row audit, never betting recommendations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from forecast_scorecard_pit import (Inadmissible, GAME_FIELDS, rows_from_csv,
                                    utc, valid_game, require_hex)

TARGET_FIELDS = ("game_id", "season", "week", "home", "away",
                 "kickoff_utc", "forecast_utc")
FORECAST_FIELDS = ("game_id", "model", "forecast_utc", "source_available_utc",
                   "training_cutoff_utc", "model_version_sha256",
                   "input_sha256", "home_margin", "total", "home_win_prob")


def generate(history, targets, source_observed_utc, source_sha256,
             model_version_sha256, min_history=64, k=20.0, hfa_elo=65.0,
             elo_per_margin_point=25.0):
    observed = utc(source_observed_utc, "SOURCE_OBSERVED")
    require_hex(source_sha256, "SOURCE")
    require_hex(model_version_sha256, "VERSION")
    if min_history < 1 or k <= 0 or elo_per_margin_point <= 0:
        raise Inadmissible("INVALID_ELO_CONFIGURATION")
    if not history or not targets:
        raise Inadmissible("EMPTY_HISTORY_OR_TARGETS")
    target_ids, observed_games = set(), set()
    for h in history:
        if h["game_id"] in observed_games:
            raise Inadmissible("DUPLICATE_HISTORY_GAME")
        observed_games.add(h["game_id"])
        ko, _, _ = valid_game(h)
        available = utc(h["final_available_utc"], "FINAL")
        if available > observed:
            raise Inadmissible("HISTORICAL_RESULT_NOT_AVAILABLE_WHEN_SNAPSHOT_OBSERVED")
    for g in targets:
        if g["game_id"] in target_ids or g["game_id"] in observed_games:
            raise Inadmissible("DUPLICATE_OR_HISTORICAL_TARGET")
        target_ids.add(g["game_id"])
        if g["home"] == g["away"] or not g["home"] or not g["away"]:
            raise Inadmissible("BAD_TARGET_TEAMS")
        if not str(g["season"]).isdigit() or not str(g["week"]).isdigit():
            raise Inadmissible("BAD_TARGET_SEASON_WEEK")
        ko = utc(g["kickoff_utc"], "TARGET_KICKOFF")
        fr = utc(g["forecast_utc"], "TARGET_FORECAST")
        if not observed <= fr < ko:
            raise Inadmissible("TARGET_NOT_STRICTLY_PREGAME")
    # Source archive is observed before the EARLIEST target; no retrospective
    # filtering of later results can turn a new download into a past snapshot.
    start = min(utc(g["forecast_utc"], "TARGET_FORECAST") for g in targets)
    if observed > start:
        raise Inadmissible("POSTHOC_SOURCE_ARCHIVE")
    ordered = sorted(history, key=lambda x:
                     (utc(x["final_available_utc"], "FINAL"), x["game_id"]))
    rating = {}
    totals = []
    last_final = None
    for h in ordered:
        home, away = h["home"], h["away"]
        rh, ra = rating.get(home, 1500), rating.get(away, 1500)
        diff = rh + hfa_elo - ra
        probability = 1 / (1 + 10 ** (-diff / 400))
        gh, ga = float(h["home_score"]), float(h["away_score"])
        observed_home_win = 1 if gh > ga else (0.5 if gh == ga else 0)
        change = k * (observed_home_win - probability)
        rating[home] = rh + change
        rating[away] = ra - change
        totals.append(gh + ga)
        last_final = utc(h["final_available_utc"], "FINAL")
    outputs, blocked = [], []
    total_mean = sum(totals) / len(totals)
    for g in targets:
        errors = []
        home, away = g["home"], g["away"]
        if len(history) < min_history:
            errors.append("INSUFFICIENT_PRIOR_HISTORY")
        if home not in rating or away not in rating:
            errors.append("TEAM_UNSEEN_IN_PIT_HISTORY")
        if errors:
            blocked.append({"game_id": g["game_id"], "reasons": errors})
            continue
        diff = rating[home] + hfa_elo - rating[away]
        prob = 1 / (1 + 10 ** (-diff / 400))
        outputs.append({"game_id": g["game_id"], "model": "elo",
                        "forecast_utc": utc(g["forecast_utc"], "FORECAST").isoformat(),
                        "source_available_utc": observed.isoformat(),
                        "training_cutoff_utc": last_final.isoformat(),
                        "model_version_sha256": model_version_sha256,
                        "input_sha256": source_sha256,
                        "home_margin": round(diff / elo_per_margin_point, 5),
                        "total": round(total_mean, 5),
                        "home_win_prob": round(prob, 9)})
    return outputs, {"status": "RESEARCH_PAPER_0U", "games_requested": len(targets),
                     "games_emitted": len(outputs), "games_blocked": len(blocked),
                     "blocked_games": blocked, "history_games": len(history),
                     "source_observed_utc": observed.isoformat(),
                     "source_sha256": source_sha256,
                     "model_version_sha256": model_version_sha256,
                     "unvalidated_config": {"k": k, "hfa_elo": hfa_elo,
                                            "elo_per_margin_point": elo_per_margin_point,
                                            "total_method": "mean_prior_final_total"},
                     "wager_eligible": False, "official_units": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("history", "targets", "source-observed-utc", "out"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--min-history", type=int, default=64)
    a = parser.parse_args()
    history, sha = rows_from_csv(a.history, GAME_FIELDS, "HISTORY")
    targets, _ = rows_from_csv(a.targets, TARGET_FIELDS, "TARGETS")
    version_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows, report = generate(history, targets, a.source_observed_utc,
                            sha, version_sha, min_history=a.min_history)
    path = Path(a.out)
    with path.open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FORECAST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with Path(str(path) + ".audit.json").open("x", encoding="utf-8") as f:
        json.dump(report, f, sort_keys=True, indent=2)
        f.write("\n")
    print(f"ELO_STYLE_RESEARCH: {len(rows)} baseline forecasts; {len(report['blocked_games'])} blocked; official=0u")


if __name__ == "__main__":
    main()
