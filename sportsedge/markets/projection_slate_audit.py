"""Annotate every RUN IT research row with a separate own-projection verdict.

An existing simulated research price stays unchanged, but cannot masquerade
as a validated independent edge. Evidence is optional and strictly private,
matched to the complete exact market identity, never position or name.
No bookmaker odds are used as model features. PAPER / 0u on every path.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from .independent_projection_gate import audit_projection, _utc

IDENTITY_WIDTH = 10
RECEIPT_KEYS = frozenset({"market_identity", "forecast", "frozen_roster"})


def _record_key(value: object) -> tuple[str, ...]:
    if (type(value) is not list or len(value) != IDENTITY_WIDTH
            or any(type(v) is not str for v in value)):
        raise ValueError("PROJECTION_EVIDENCE_MARKET_IDENTITY_INVALID")
    return tuple(value)


def _reason(reason: str) -> dict:
    return {
        "status": "BLOCK",
        "reasons": [reason],
        "research_projection_usable": False,
        "source_authenticated": False,
        "calibration_verified": False,
        "positive_ev_verified": False,
        "official_counted": 0,
        "approved_stake_u": 0,
    }



# An explicit five-family coverage contract for the three owner-priority sports.
# An absent market is UNKNOWN offering coverage, not evidence of no DK offering.
THREE_SPORT_FAMILIES = {
    "CBB": ("ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP"),
    "CFB": ("ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP"),
    "NFL": ("ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP"),
}


def _three_sport_projection_matrix(result: dict) -> dict:
    """Report missing own-model receipts for every game/market family.

    Never infer independently modeled player props from a score projection.
    A valid receipt shape is not authenticated input or calibrated EV.
    """
    requested = result.get("sport_coverage", {})
    report = {}
    for sport, families in THREE_SPORT_FAMILIES.items():
        games = [e for e in result["events"] if e["sport"] == sport]
        family_report = {}
        for family in families:
            submitted = sum(e.get("families", {}).get(family, {}).get(
                "submitted_research_candidates", 0) for e in games)
            matched_rows = []
            for event in games:
                for row in event.get("research_rows", []):
                    market = row.get("market")
                    if (type(market) in (tuple, list) and len(market) >= 3
                            and market[2] == family):
                        matched_rows.append(row)
            valid = sum(row.get("independent_projection", {}).get(
                "research_projection_usable") is True for row in matched_rows)
            missing_rows = max(0, submitted - len(matched_rows))
            blocked = len(matched_rows) - valid
            no_family_rows_games = sum(
                e.get("families", {}).get(family, {}).get(
                    "submitted_research_candidates", 0) == 0 for e in games)
            if sport not in requested:
                status = "SPORT_NOT_REQUESTED"
            elif not games:
                status = "NO_SCHEDULED_EVENTS_SUPPLIED"
            elif submitted == 0:
                status = "MARKET_NOT_SUBMITTED_OFFERING_UNVERIFIED"
            elif missing_rows:
                status = "BLOCK_MISSING_RESEARCH_OUTPUT_ROWS"
            elif blocked:
                status = "BLOCK_MISSING_OR_INVALID_INDEPENDENT_MODEL_RECEIPTS"
            elif no_family_rows_games:
                status = "PARTIAL_EVENT_MARKET_CENSUS_UNVERIFIED"
            else:
                status = "PAPER_MODEL_RECEIPT_SHAPE_ONLY"
            family_report[family] = {
                "submitted_candidates": submitted,
                "rows_with_projection_audit": len(matched_rows),
                "valid_model_receipt_shape_unverified": valid,
                "blocked_or_invalid_model_receipts": blocked,
                "missing_research_output_rows": missing_rows,
                "events_without_submitted_family": no_family_rows_games,
                "status": status,
                "source_authenticated": False,
                "calibration_verified": False,
                "official_counted": 0,
            }
        report[sport] = {
            "scheduled_events_supplied": len(games),
            "families": family_report,
            "all_market_families_verified": False,
            "approved_stake_u": 0,
        }
    return report


def attach_independent_projection_audit(result: dict, evidence: list[dict]) -> dict:
    """Attach a source-UNVERIFIED metadata audit to the existing research rows.

    This does not reprice, alter the model or turn a model assertion into a
    verified edge. Every submitted row is retained, including SGP placeholders.
    Unknown/duplicate evidence blocks the intake rather than silently matching
    a different selection. Forecast IDs and clocks are bound to actual run
    model hashes, game kickoff and report time.
    """
    if not isinstance(result, dict) or not isinstance(result.get("events"), list):
        raise ValueError("PROJECTION_SLATE_OUTPUT_REQUIRED")
    if type(evidence) is not list or len(evidence) > 500_000:
        raise ValueError("PROJECTION_EVIDENCE_LIST_REQUIRED")
    records = {}
    for entry in evidence:
        if type(entry) is not dict or set(entry) - RECEIPT_KEYS or "market_identity" not in entry:
            raise ValueError("PROJECTION_EVIDENCE_FIELDS_INVALID")
        key = _record_key(entry["market_identity"])
        if key in records:
            raise ValueError("PROJECTION_EVIDENCE_DUPLICATE_MARKET")
        records[key] = entry

    generated = _utc(result.get("generated_at_utc"))
    if generated is None:
        raise ValueError("PROJECTION_SLATE_GENERATED_CLOCK_INVALID")
    matched = set()
    counts = Counter()
    for event in result["events"]:
        event_start = _utc(event.get("start_utc"))
        if event_start is None:
            raise ValueError("PROJECTION_EVENT_START_MISSING")
        event_counts = Counter()
        for row in event.get("research_rows", []):
            raw_key = row.get("market")
            # SGP inventory-only markers have no real posted leg-market identity.
            if type(raw_key) is list and len(raw_key) == 4 and raw_key[2] == "SGP":
                verdict = _reason("SGP_INVENTORY_ONLY_NO_POSTED_LEGS")
            else:
                # Internal Market.identity() is a tuple; JSON evidence is a list.
                key = _record_key(list(raw_key) if type(raw_key) is tuple else raw_key)
                if key[0:2] != (event["sport"], event["event_id"]):
                    raise ValueError("PROJECTION_RESEARCH_ROW_EVENT_MISMATCH")
                entry = records.get(key)
                if entry is None:
                    verdict = _reason("NO_INDEPENDENT_PROJECTION_RECEIPT")
                else:
                    matched.add(key)
                    forecast = entry.get("forecast")
                    if not isinstance(forecast, dict):
                        verdict = _reason("NO_INDEPENDENT_MODEL_PROJECTION")
                    elif (_utc(forecast.get("event_start_utc")) != event_start
                          or _utc(forecast.get("generated_utc")) is None
                          or _utc(forecast["generated_utc"]) > generated):
                        verdict = _reason("PROJECTION_RECEIPT_GAME_OR_RUN_CLOCK_MISMATCH")
                    elif (forecast.get("model_sha256") != event.get("research_model_sha256")
                          or forecast.get("feature_sha256") != event.get("research_feature_sha256")):
                        verdict = _reason("PROJECTION_RECEIPT_NOT_BOUND_TO_PRICED_MODEL")
                    else:
                        market = {
                            "sport": key[0], "event_id": key[1],
                            "family": key[2], "period": key[3],
                            "settlement_id": key[9],
                            "player_id": key[7], "team_id": key[6], "stat": key[8],
                        }
                        roster = entry.get("frozen_roster")
                        if roster is not None and (
                            type(roster) is not dict or
                            any(type(k) is not str or type(v) is not str
                                for k, v in roster.items())
                        ):
                            verdict = _reason("PROJECTION_FROZEN_ROSTER_INVALID")
                        else:
                            verdict = audit_projection(
                                {"market": market, "forecast": forecast}, roster
                            )
            row["independent_projection"] = verdict
            row["verified_model_ev"] = False
            event_counts["rows"] += 1
            counts["rows"] += 1
            if verdict["status"] == "BLOCK":
                counts["blocked"] += 1
                event_counts["blocked"] += 1
            else:
                counts["valid_shape_unverified"] += 1
                event_counts["valid_shape_unverified"] += 1
        event["independent_projection_coverage"] = {
            "rows": event_counts["rows"],
            "blocked": event_counts["blocked"],
            "valid_shape_unverified": event_counts["valid_shape_unverified"],
            "official_counted": 0, "approved_stake_u": 0,
        }

    if set(records) != matched:
        raise ValueError("PROJECTION_EVIDENCE_NOT_IN_SUBMITTED_MARKET_CENSUS")
    result["independent_projection_coverage"] = {
        "submitted_research_rows": counts["rows"],
        "receipts_matched": len(matched),
        "blocked": counts["blocked"],
        "valid_shape_unverified": counts["valid_shape_unverified"],
        "source_authenticated": False,
        "calibration_verified": False,
        "verified_model_ev_count": 0,
        "official_counted": 0, "approved_stake_u": 0,
    }
    result["cbb_cfb_nfl_projection_matrix"] = _three_sport_projection_matrix(result)
    return result
