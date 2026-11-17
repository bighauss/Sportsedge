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
                key = _record_key(raw_key)
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
    return result
