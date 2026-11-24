"""Research-only CBBD original-byte regulation-half evidence adapter.

Provider schema: https://api.collegebasketballdata.com/api/games
Uses documented homePeriodPoints/awayPeriodPoints arrays. Does not infer
historical publication clocks or equate an overtime final to regulation.
No forecast certification, odds, stakes, or network access.
"""
from collections import Counter
from hashlib import sha256
import json
from cbbd_prospective_capture import BASE, Hold, decoded, utc, iso


def normalize(raw, manifest, *, asof_utc):
    if (not isinstance(manifest, dict)
            or manifest.get("format") != "CBBD_GAMES_CAPTURE_V1"
            or manifest.get("provider") != "collegebasketballdata"
            or manifest.get("documented_endpoint") != BASE):
        raise Hold("HALF_MANIFEST_INVALID")
    digest = sha256(raw).hexdigest()
    if manifest.get("source_sha256") != digest or manifest.get("source_bytes") != len(raw):
        raise Hold("HALF_ORIGINAL_HASH_MISMATCH")
    observed = utc(manifest.get("local_observed_utc"), "observation")
    if observed >= utc(asof_utc, "asof"):
        raise Hold("HALF_SOURCE_NOT_PRIOR")
    games = decoded(raw)
    if manifest.get("returned_rows") != len(games):
        raise Hold("HALF_SOURCE_CENSUS_MISMATCH")
    ids = Counter(g.get("id") for g in games if isinstance(g, dict)
                  and type(g.get("id")) is int)
    rows, rejected = [], []
    for i, g in enumerate(games):
        ident = g.get("id") if isinstance(g, dict) else None
        try:
            if type(ident) is not int or ident <= 0 or ids[ident] != 1:
                raise Hold("INVALID_OR_DUPLICATE_GAME_ID")
            if type(g.get("season")) is not int or g["season"] != manifest.get("season"):
                raise Hold("SEASON_MISMATCH")
            h, a = g.get("homeTeamId"), g.get("awayTeamId")
            if any(type(t) is not int or t <= 0 for t in (h, a)) or h == a:
                raise Hold("TEAM_IDENTITY_INVALID")
            tip = utc(g.get("startDate"), "tip")
            if g.get("startTimeTbd") is not False or tip >= observed or g.get("status") != "final":
                raise Hold("NOT_CONFIRMED_PRIOR_FINAL")
            hp, ap = g.get("homePeriodPoints"), g.get("awayPeriodPoints")
            if (not isinstance(hp, list) or not isinstance(ap, list)
                    or len(hp) != len(ap) or len(hp) < 2
                    or any(type(v) is not int or not 0 <= v <= 200 for v in hp + ap)):
                raise Hold("PERIOD_ARRAY_INVALID")
            hf, af = g.get("homePoints"), g.get("awayPoints")
            if (type(hf) is not int or type(af) is not int or hf == af
                    or sum(hp) != hf or sum(ap) != af):
                raise Hold("FINAL_PERIOD_TOTAL_MISMATCH")
            # Every extra period must follow a tied cumulative score.
            if any(sum(hp[:j]) != sum(ap[:j]) for j in range(2, len(hp))):
                raise Hold("OVERTIME_SEQUENCE_INVALID")
            rows.append({"sport": "CBB", "event_id": str(ident),
                         "game_start_utc": iso(tip), "final_published_utc": iso(observed),
                         "final_captured_utc": iso(observed),
                         "source_original_sha256": "sha256:" + digest,
                         "periods": {"H1": [hp[0], ap[0]], "H2": [hp[1], ap[1]]},
                         "regulation_home": sum(hp[:2]), "regulation_away": sum(ap[:2]),
                         "settlement_scope": "REGULATION_ONLY"})
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            rejected.append({"input_index": i, "game_id": str(ident), "reason": str(exc)})
    report = {"label": "PAPER_0U_UNAUTHENTICATED",
              "publication_basis": "UPPER_BOUND_LOCAL_OBSERVATION_NOT_PROVIDER_PUBLICATION",
              "source_sha256": digest, "input_rows": len(games), "admitted": len(rows),
              "rejected": rejected, "official_counted": 0, "approved_stake_u": 0}
    return ("".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in rows).encode(),
            report)


def fit_full_to_first_half(raw, manifest, *, asof_utc):
    """Current-snapshot training only: aggregate first-half/full-final ratio.

    Full-game model predicts final scores, so denominator includes OT, unlike
    regulation-only period-share fitting. No fitted predictive distribution.
    This fit cannot be applied retrospectively before the snapshot observation.
    """
    normalized, census = normalize(raw, manifest, asof_utc=asof_utc)
    source = decoded(raw)
    admitted = {int(json.loads(line)["event_id"]) for line in normalized.splitlines()}
    training = [g for g in source if isinstance(g, dict) and g.get("id") in admitted]
    days = {utc(g["startDate"], "tip").date() for g in training}
    first = sum(g["homePeriodPoints"][0] + g["awayPeriodPoints"][0] for g in training)
    full = sum(g["homePoints"] + g["awayPoints"] for g in training)
    ready = len(training) >= 50 and len(days) >= 7 and 0 < first < full
    return {"status": "TRAIN_ONLY_HALF_MEAN_UNVALIDATED" if ready else "BLOCK_HALF_TRAINING",
            "source_sha256": census["source_sha256"], "source_observed_utc": manifest["local_observed_utc"],
            "fit_asof_utc": asof_utc, "input_rows": census["input_rows"], "admitted": len(training),
            "rejected": len(census["rejected"]), "rejected_reasons": dict(Counter(r["reason"] for r in census["rejected"])),
            "distinct_dates": len(days), "share_of_final_points": first / full if ready else None,
            "source_authenticated": False, "holdout_calibrated": False, "approved_stake_u": 0}


def project_first_halves(card, fit):
    """Expected scores only; do not price H1 contracts without a fitted variance."""
    share = fit.get("share_of_final_points")
    return [{"game_id": r["game_id"],
             "status": "PROJECTED_HALF_MEAN_RESEARCH" if r["status"] == "PROJECTED" and share is not None else "PASS",
             "reason": None if r["status"] == "PROJECTED" and share is not None else
                       (r.get("pass_reason") or fit["status"]),
             "home_points": r["projection"]["home_points"] * share if r["status"] == "PROJECTED" and share is not None else None,
             "away_points": r["projection"]["away_points"] * share if r["status"] == "PROJECTED" and share is not None else None}
            for r in card["rows"]]


def fit_full_to_second_half(raw, manifest, *, asof_utc):
    """Train a regulation H2/full-final mean share independently from H1.

    The final denominator includes overtime; the numerator contains only
    regulation H2. The H1 historical report contract stays byte-compatible.
    """
    normalized, census = normalize(raw, manifest, asof_utc=asof_utc)
    admitted = {int(json.loads(line)["event_id"]) for line in normalized.splitlines()}
    training = [g for g in decoded(raw) if isinstance(g, dict) and g.get("id") in admitted]
    days = {utc(g["startDate"], "tip").date() for g in training}
    second = sum(g["homePeriodPoints"][1] + g["awayPeriodPoints"][1] for g in training)
    full = sum(g["homePoints"] + g["awayPoints"] for g in training)
    ready = len(training) >= 50 and len(days) >= 7 and 0 < second < full
    return {"status": "TRAIN_ONLY_H2_MEAN_UNVALIDATED" if ready else "BLOCK_H2_TRAINING",
            "source_sha256": census["source_sha256"], "source_observed_utc": manifest["local_observed_utc"],
            "fit_asof_utc": asof_utc, "input_rows": census["input_rows"], "admitted": len(training),
            "distinct_dates": len(days), "share_of_final_points": second / full if ready else None,
            "scope": "REGULATION_SECOND_HALF_ONLY", "source_authenticated": False,
            "holdout_calibrated": False, "approved_stake_u": 0}


def project_second_halves(card, fit):
    """Pregame expected regulation H2 score only, not a live halftime model."""
    rows = project_first_halves(card, fit)
    for r in rows:
        if r["status"] == "PROJECTED_HALF_MEAN_RESEARCH":
            r["status"] = "PROJECTED_H2_MEAN_RESEARCH"
    return rows
