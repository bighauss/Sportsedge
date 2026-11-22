"""Read-only, seven-sport, all-family attempt census. Never a betting signal.

Submitted offers are NOT an authenticated sportsbook universe. Every expected
sport/family appears in the report, even when the schedule, offers, forecasts,
results, or closing quotes have not been supplied. NHL and PGA do not inherit
the five-sport slate pricer. Do not pass private provider originals as inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

SCHEMA = "sportsedge-all-market-audit-v1"
SPORTS = ("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA")
COMMON = ("ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PERIOD", "ALTERNATE",
          "PLAYER_PROP", "SPECIAL", "SGP", "DFS", "OTHER")
FAMILIES = {
    "NFL": COMMON + ("ATTD", "FIRST_TD", "TD_2PLUS"),
    "CFB": COMMON + ("ATTD", "FIRST_TD", "TD_2PLUS"),
    "CBB": COMMON + ("FIRST_BASKET",),
    "NBA": COMMON + ("FIRST_BASKET",),
    "MLB": COMMON + ("NRFI", "YRFI", "PITCHER_PROP", "BATTER_PROP", "F5", "1IN"),
    "NHL": COMMON + ("GOALIE_SAVES", "FIRST_GOAL", "SHOTS", "GOALS", "POINTS"),
    "PGA": ("OUTRIGHT", "TOP5", "TOP10", "TOP20", "MAKE_CUT", "MISS_CUT",
            "MATCHUP", "THREE_BALL", "ROUND_LEADER", "FIRST_ROUND_LEADER",
            "ROUND_SCORE", "TOURNAMENT_SCORE", "BIRDIES", "BOGEYS",
            "EAGLES", "HOLE_IN_ONE", "DFS", "OTHER"),
}
MODEL_REFERENCE_PATHS = {
    "NFL": "models/nfl/score_walkforward_pit.py",
    "CFB": "models/cfb/sportsedge_cfb_model.py",
    "CBB": "models/cbb/sportsedge_cbb_model.py",
    "NBA": "models/nba/sportsedge_nba_model.py",
    "MLB": "models/mlb/sportsedge_mlb_model.py",
    "NHL": "models/nhl/sportsedge_nhl_model.py",
    "PGA": "models/pga/tournament_sim.py",
}
FIVE_SPORT_RESEARCH_PRICER = frozenset(("NFL", "CFB", "CBB", "NBA", "MLB"))
ROOT_FIELDS = {"schema", "events", "attempts"}
EVENT_FIELDS = {"sport", "event_id", "start_utc"}
ATTEMPT_FIELDS = {
    "sport", "event_id", "offer_id", "market_family", "period",
    "selection_id", "participant_id", "stat", "line", "book",
    "source_observed_utc", "source_captured_utc", "quote_sha256",
    "model_sha256", "close_sha256", "final_sha256",
}
OPTIONAL_ATTEMPT_FIELDS = {"settlement_rule", "joint_leg_ids"}
JOINT_FAMILIES = {"SGP", "MATCHUP", "THREE_BALL"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+~-]{0,127}$")
PERIOD = re.compile(r"^[A-Z0-9_]{1,24}$")
SHA = re.compile(r"^sha256:[0-9a-f]{64}$")


def _exact(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise ValueError("FIELDS_MISMATCH:" + label)


def _id(value, name, empty=False):
    if empty and value == "":
        return ""
    if type(value) is not str or ID.fullmatch(value) is None:
        raise ValueError("INVALID_ID:" + name)
    return value


def _utc(value, name):
    if type(value) is not str:
        raise ValueError("UTC_REQUIRED:" + name)
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_UTC:" + name) from exc
    if instant.utcoffset() != timedelta(0):
        raise ValueError("UTC_REQUIRED:" + name)
    return instant


def _line(value):
    if type(value) is not str or len(value) > 32:
        raise ValueError("INVALID_LINE")
    if value == "":
        return value
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("INVALID_LINE") from exc
    if not number.is_finite() or abs(number) > 1000000:
        raise ValueError("INVALID_LINE")
    return str(number.normalize())


def _hash(value, field):
    if value is not None and (type(value) is not str or SHA.fullmatch(value) is None):
        raise ValueError("INVALID_SHA256:" + field)


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def assess(data):
    """Inventory submitted event/offer identities without source or release claims."""
    _exact(data, ROOT_FIELDS, "root")
    if data["schema"] != SCHEMA:
        raise ValueError("INVALID_SCHEMA")
    events, attempts = data["events"], data["attempts"]
    if (type(events) is not list or type(attempts) is not list or
            len(events) > 2000 or len(attempts) > 100000):
        raise ValueError("INVALID_CENSUS_SIZE")
    event_start = {}
    by_sport = Counter()
    for row in events:
        _exact(row, EVENT_FIELDS, "event")
        sport = row["sport"]
        if type(sport) is not str or sport not in SPORTS:
            raise ValueError("UNKNOWN_SPORT")
        key = (sport, _id(row["event_id"], "event_id"))
        if key in event_start:
            raise ValueError("DUPLICATE_EVENT")
        event_start[key] = _utc(row["start_utc"], "start_utc")
        by_sport[sport] += 1
    seen_offers, seen_outcomes = set(), set()
    count, reason_count, rows = Counter(), Counter(), []
    for row in attempts:
        if type(row) is not dict or not ATTEMPT_FIELDS.issubset(row) or (
                set(row) - ATTEMPT_FIELDS - OPTIONAL_ATTEMPT_FIELDS):
            raise ValueError("FIELDS_MISMATCH:attempt")
        sport = row["sport"]
        if type(sport) is not str or sport not in SPORTS:
            raise ValueError("UNKNOWN_SPORT")
        key = (sport, _id(row["event_id"], "event_id"))
        if key not in event_start:
            raise ValueError("OFFER_OUTSIDE_SUPPLIED_SCHEDULE")
        family = row["market_family"]
        if type(family) is not str or family not in FAMILIES[sport]:
            raise ValueError("UNCLASSIFIED_FAMILY_USE_OTHER")
        period = row["period"]
        if type(period) is not str or PERIOD.fullmatch(period) is None:
            raise ValueError("INVALID_PERIOD")
        offer_id = _id(row["offer_id"], "offer_id")
        selection = _id(row["selection_id"], "selection_id")
        participant = _id(row["participant_id"], "participant_id", empty=True)
        stat = _id(row["stat"], "stat", empty=True)
        book = _id(row["book"], "book", empty=True)
        line = _line(row["line"])
        settlement = row.get("settlement_rule")
        if settlement is not None:
            _id(settlement, "settlement_rule")
        raw_legs = row.get("joint_leg_ids")
        if raw_legs is not None and (type(raw_legs) is not list or len(raw_legs) > 20 or
                any(type(x) is not str or ID.fullmatch(x) is None for x in raw_legs) or
                len(set(raw_legs)) != len(raw_legs)):
            raise ValueError("INVALID_JOINT_LEG_IDENTITIES")
        legs = tuple(raw_legs or ())
        offer_key = (sport, book, offer_id)
        if offer_key in seen_offers:
            raise ValueError("DUPLICATE_PROVIDER_OFFER_ID")
        seen_offers.add(offer_key)
        identity = (key, family, period, selection, participant, stat, line, book, settlement, legs)
        if identity in seen_outcomes:
            raise ValueError("DUPLICATE_EXACT_OUTCOME")
        seen_outcomes.add(identity)
        for field in ("quote_sha256", "model_sha256", "close_sha256", "final_sha256"):
            _hash(row[field], field)
        observed, captured = row["source_observed_utc"], row["source_captured_utc"]
        reasons = []
        if settlement is None:
            reasons.append("MARKET_SETTLEMENT_ID_MISSING")
        if family in JOINT_FAMILIES and (
                len(legs) < 2 or
                (family == "MATCHUP" and len(legs) != 2) or
                (family == "THREE_BALL" and len(legs) != 3)):
            reasons.append("JOINT_COMPONENT_IDENTITIES_MISSING")
        elif family not in JOINT_FAMILIES and legs:
            reasons.append("JOINT_COMPONENTS_ON_SINGLE_MARKET")
        if (observed is None) != (captured is None):
            reasons.append("INCOMPLETE_QUOTE_CLOCK_PAIR")
        elif observed is not None:
            try:
                if not _utc(observed, "observed") <= _utc(captured, "captured") < event_start[key]:
                    reasons.append("QUOTE_CLOCK_NOT_PREGAME")
            except ValueError:
                reasons.append("INVALID_QUOTE_CLOCK")
        if observed is None or row["quote_sha256"] is None:
            reasons.append("QUOTE_SOURCE_NOT_ATTESTED")
        if row["model_sha256"] is None:
            reasons.append("INDEPENDENT_MODEL_RECEIPT_MISSING")
        if row["close_sha256"] is None:
            reasons.append("CLOSING_QUOTE_NOT_CAPTURED")
        if row["final_sha256"] is None:
            reasons.append("FINAL_RESULT_NOT_CAPTURED")
        if family in ("PLAYER_PROP", "PITCHER_PROP", "BATTER_PROP", "GOALIE_SAVES",
                      "SHOTS", "GOALS", "POINTS", "ATTD", "FIRST_TD", "TD_2PLUS",
                      "FIRST_BASKET", "FIRST_GOAL") and not participant:
            reasons.append("PLAYER_ID_NOT_BOUND")
        if family == "PLAYER_PROP" and not stat:
            reasons.append("PLAYER_STAT_NOT_BOUND")
        if stat and not participant:
            reasons.append("STAT_MARKET_PARTICIPANT_MISSING")
        if family == "ALTERNATE" and not line:
            reasons.append("ALTERNATE_THRESHOLD_MISSING")
        if family == "PERIOD" and period == "FG":
            reasons.append("PERIOD_MARKET_PERIOD_MISSING")
        if sport == "PGA" and family in (
                "OUTRIGHT", "TOP5", "TOP10", "TOP20", "MAKE_CUT",
                "MISS_CUT", "ROUND_LEADER", "FIRST_ROUND_LEADER",
                "ROUND_SCORE", "TOURNAMENT_SCORE", "BIRDIES", "BOGEYS",
                "EAGLES", "HOLE_IN_ONE") and not participant:
            reasons.append("PGA_GOLFER_ID_MISSING")
        if not reasons:
            reasons.append("RECEIPT_METADATA_NOT_INDEPENDENTLY_AUTHENTICATED")
        count[(sport, family)] += 1
        reason_count.update(reasons)
        rows.append({
            "sport": sport, "event_id": key[1], "offer_id": offer_id,
            "market_family": family, "period": period, "selection_id": selection,
            "participant_id": participant, "stat": stat, "line": line,
            "book": book, "settlement_rule": settlement,
            "joint_leg_ids": list(legs),
            "status": "PAPER_0U_UNVERIFIED", "reasons": reasons,
            "source_authenticated": False, "model_calibrated": False,
            "clv_authenticated": False, "approved_stake_u": 0,
        })
    matrix = []
    for sport in SPORTS:
        for family in FAMILIES[sport]:
            n = count[(sport, family)]
            reason = ("NO_SCHEDULE_SUPPLIED" if by_sport[sport] == 0 else
                      "NOT_SUBMITTED_OFFERING_UNKNOWN" if not n else
                      "SUBMITTED_UNATTESTED_OFFERS")
            matrix.append({
                "sport": sport, "family": family,
                "scheduled_events_supplied": by_sport[sport],
                "submitted_outcomes": n,
                "state": reason,
                "native_model_reference": MODEL_REFERENCE_PATHS[sport],
                "model_code_presence_is_not_execution": True,
                "five_sport_research_pricer_path": sport in FIVE_SPORT_RESEARCH_PRICER,
                "model_validated": False, "market_offering_authenticated": False,
                "calibration_verified": False, "approved_stake_u": 0,
            })
    return {
        "schema": "sportsedge-all-market-audit-report-v1",
        "status": "RESEARCH_ONLY_NO_MARKET_CERTIFIED",
        "events_submitted": len(events), "attempted_outcomes": len(rows),
        "sport_family_partitions": len(matrix),
        "market_universe_complete": False,
        "model_releases_certified": 0, "official_counted": 0,
        "approved_stake_u": 0,
        "reasons_by_attempt": dict(sorted(reason_count.items())),
        "matrix": matrix, "attempts": rows,
        "limitations": [
            "A submitted event/offer list is not an authenticated complete sportsbook inventory",
            "SHA-shaped metadata is not proof of original provider bytes or source publication",
            "NHL/PGA are native research lanes, not supported by the five-sport pricer",
            "No odds, EV, profitable bets or model performance are computed",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", help="public/synthetic metadata only; no private originals")
    parser.add_argument("--out", help="optional new local output JSON")
    args = parser.parse_args(argv)
    raw = Path(args.json_file).read_bytes()
    if not 0 < len(raw) <= 20_000_000:
        raise ValueError("INVALID_INPUT_FILE_SIZE")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(
                          ValueError("NONFINITE_JSON:" + x)))
    result = assess(data)
    payload = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.out:
        out = Path(args.out)
        with out.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
