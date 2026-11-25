"""Prospective conditional-player mean errors, PAPER/0u, no market grading.

Replay the exact original forecast from original training bytes and compare
with independently captured later final player boxes. Missing participation
is withheld, not interpreted as zero, DNP, or a settlement result.
"""
from collections import Counter
from hashlib import sha256
import json
import math
from statistics import mean, stdev
from cbbd_prospective_capture import Hold, utc, decoded
from cbbd_player_history import collect_batches, conditional_player_means


def audit(card, report_raw, training_batches, training_finals_raw, training_finals_receipt,
          final_batches, finals_raw, finals_receipt, *, season, evaluated_utc, report_sha256):
    freeze = utc(card["freeze_utc"], "freeze")
    final_batches = tuple(final_batches)
    if utc(finals_receipt["observed_utc"], "final_observed") <= freeze:
        raise Hold("PLAYER_EVALUATION_NOT_AFTER_FREEZE")
    for _, receipt in final_batches:
        if utc(receipt["observed_utc"], "player_observed") <= freeze:
            raise Hold("PLAYER_EVALUATION_NOT_AFTER_FREEZE")
    training = collect_batches(training_batches, training_finals_raw, training_finals_receipt,
                               season=season, asof_utc=card["freeze_utc"])
    expected = conditional_player_means(card, training)
    if type(report_raw) is not bytes or sha256(report_raw).hexdigest() != report_sha256:
        raise Hold("PLAYER_ORIGINAL_REPORT_DIGEST_MISMATCH")
    canonical = json.dumps(expected, sort_keys=True, allow_nan=False).encode("utf-8")
    if canonical != report_raw:
        raise Hold("PLAYER_ORIGINAL_REPORT_REPLAY_MISMATCH")
    actual = collect_batches(final_batches, finals_raw, finals_receipt,
                             season=season, asof_utc=evaluated_utc, include_records=True)
    games = {r["game_id"]: r for r in card["rows"]}
    source_games = decoded(finals_raw)
    counts = Counter(g.get("id") for g in source_games if isinstance(g, dict)
                     and type(g.get("id")) is int)
    source = {str(g["id"]): g for g in source_games if isinstance(g, dict)
              and type(g.get("id")) is int and counts[g["id"]] == 1 and g.get("status") == "final"}
    records = {(r["game_id"], r["team_id"], r["player_id"]): r for r in actual["accepted_records"]}
    rows = []
    for f in expected["rows"]:
        gid, tid, pid = f["game_id"], f["team_id"], f["player_id"]
        row = {"game_id": gid, "team_id": tid, "player_id": pid, "state": "PASS"}
        try:
            g = games[gid]
            s = source.get(gid)
            if s is None:
                raise Hold("PLAYER_FINAL_NOT_ADMITTED")
            tip = utc(g["tipoff_utc"], "tip")
            if (not freeze < tip or tip != utc(s.get("startDate"), "source_tip")
                    or str(s.get("season")) != str(g["season"])
                    or str(s.get("homeTeamId")) != g["home_team_id"]
                    or str(s.get("awayTeamId")) != g["away_team_id"]):
                raise Hold("PLAYER_FINAL_IDENTITY_OR_CLOCK_MISMATCH")
            a = records.get((gid, tid, pid))
            if a is None:
                raise Hold("PLAYER_PARTICIPATION_UNOBSERVED_OR_REJECTED")
            observed = {"MINUTES": a["minutes"], **a["stats"]}
            predicted = {"MINUTES": f["minutes_if_participating"], **f["means_if_participating"]}
            row.update(state="GRADED_CONDITIONAL", actual=observed, predicted=predicted,
                       errors={k: observed[k] - v for k, v in predicted.items()})
        except (ValueError, TypeError, KeyError) as exc:
            row["reason"] = str(exc)
        rows.append(row)
    graded = [r for r in rows if r["state"] == "GRADED_CONDITIONAL"]
    metrics = {}
    for k in ("MINUTES", "POINTS", "REBOUNDS", "ASSISTS", "THREES", "PRA"):
        errors = [r["errors"][k] for r in graded]
        metrics[k] = {"n": len(errors), "mae": mean(abs(v) for v in errors) if errors else None,
                      "rmse": math.sqrt(mean(v*v for v in errors)) if errors else None,
                      "bias_actual_minus_forecast": mean(errors) if errors else None,
                      "sample_residual_sd": stdev(errors) if len(errors) > 1 else None}
    return {"label": "PAPER_0U_CONDITIONAL_PLAYER_FORWARD_DIAGNOSTIC",
            "card_sha256": card["card_sha256"], "original_player_report_sha256": report_sha256,
            "training_finals_receipt": expected["training_finals_receipt"], "input_rows": len(rows), "graded": len(graded),
            "withheld": dict(Counter(r["reason"] for r in rows if r["state"] == "PASS")),
            "evaluated_utc": utc(evaluated_utc, "evaluated").isoformat(),
            "finals_receipt": {k: finals_receipt[k] for k in ("source", "sha256", "bytes", "observed_utc")},
            "final_player_receipts": [{k: receipt[k] for k in ("source", "sha256", "bytes", "observed_utc")}
                                      for _, receipt in final_batches],
            "metrics": metrics, "rows": rows, "holdout_calibrated": False,
            "official_counted": 0, "approved_stake_u": 0}
