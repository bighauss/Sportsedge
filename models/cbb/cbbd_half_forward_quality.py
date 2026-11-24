"""Exact-original first-half forecast to final comparison, PAPER/0u.

Requires original frozen card, archived training bytes/manifest and archived
half report; recomputes the original fit rather than reconstructing history.
No market prices, calibrated probability, or release claim.
"""
from collections import Counter
import json
from statistics import mean, stdev
from cbbd_prospective_capture import Hold, decoded, utc
from cbbd_paper_card import card_digest, CARD_STATUS
from cbbd_half_evidence import normalize, fit_full_to_first_half, project_first_halves


def audit(card, half_report, training_raw, training_manifest, finals_raw,
          finals_manifest, *, evaluated_utc):
    if (card.get("status") != CARD_STATUS or card.get("official_counted") != 0
            or card.get("approved_stake_u") != 0 or card.get("card_sha256") != card_digest(card)):
        raise Hold("HALF_FROZEN_CARD_INVALID")
    if half_report.get("label") != "PAPER_0U":
        raise Hold("HALF_REPORT_LABEL_INVALID")
    freeze = utc(card["freeze_utc"], "freeze")
    fit = fit_full_to_first_half(training_raw, training_manifest, asof_utc=card["freeze_utc"])
    forecasts = project_first_halves(card, fit)
    if fit != half_report.get("fit") or forecasts != half_report.get("rows"):
        raise Hold("HALF_ORIGINAL_REPORT_REPLAY_MISMATCH")
    normalized, source = normalize(finals_raw, finals_manifest, asof_utc=evaluated_utc)
    observed = utc(finals_manifest["local_observed_utc"], "final_observed")
    admitted = {r["event_id"]: r for r in (json.loads(line) for line in normalized.splitlines())}
    original = {str(g["id"]): g for g in decoded(finals_raw) if isinstance(g, dict)
                and type(g.get("id")) is int and str(g["id"]) in admitted}
    ids = Counter(r["game_id"] for r in card["rows"])
    rows = []
    for r, f in zip(card["rows"], forecasts):
        gid = r["game_id"]
        row = {"game_id": gid, "state": "PASS", "reason": None}
        try:
            if ids[gid] != 1:
                raise Hold("HALF_DUPLICATE_FROZEN_GAME")
            tip = utc(r["tipoff_utc"], "tip")
            if not freeze < tip:
                raise Hold("HALF_FREEZE_NOT_PREGAME")
            if f["status"] != "PROJECTED_HALF_MEAN_RESEARCH":
                raise Hold("HALF_FORECAST_WITHHELD")
            g = original.get(gid)
            if g is None:
                raise Hold("HALF_FINAL_NOT_ADMITTED")
            if (tip != utc(g["startDate"], "source_tip") or not tip < observed
                    or str(g["season"]) != str(r["season"])
                    or str(g["homeTeamId"]) != r["home_team_id"]
                    or str(g["awayTeamId"]) != r["away_team_id"]):
                raise Hold("HALF_FINAL_IDENTITY_OR_CLOCK_MISMATCH")
            ah, aa = admitted[gid]["periods"]["H1"]
            ph, pa = f["home_points"], f["away_points"]
            row.update(state="GRADED", home_error=ah-ph, away_error=aa-pa,
                       total_error=(ah+aa)-(ph+pa), margin_error=(ah-aa)-(ph-pa),
                       actual_home=ah, actual_away=aa, predicted_home=ph, predicted_away=pa,
                       final_observed_utc=finals_manifest["local_observed_utc"])
        except (ValueError, KeyError, TypeError) as exc:
            row["reason"] = str(exc)
        rows.append(row)
    scored = [r for r in rows if r["state"] == "GRADED"]
    metrics = {}
    for k in ("home", "away", "total", "margin"):
        errors = [r[k+"_error"] for r in scored]
        metrics[k] = {"n": len(errors), "mae": mean(abs(x) for x in errors) if errors else None,
                      "bias_actual_minus_forecast": mean(errors) if errors else None,
                      "sample_residual_sd": stdev(errors) if len(errors) > 1 else None}
    return {"label": "PAPER_0U_FIRST_HALF_FORWARD_DIAGNOSTIC", "card_sha256": card["card_sha256"],
            "final_source_sha256": source["source_sha256"], "input_rows": len(rows),
            "graded": len(scored), "withheld": dict(Counter(r["reason"] for r in rows if r["state"] != "GRADED")),
            "metrics": metrics, "rows": rows, "holdout_calibrated": False, "approved_stake_u": 0}
