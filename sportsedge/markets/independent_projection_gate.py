"""Fail-closed, PAPER-only inventory gate for SportsEdge's *own* projections.

This gate validates model/source assertions and market identity; it does not
authenticate the upstream source, calibrate a probability, or certify EV.
It never reads sportsbook odds or fills a missing projection from a line.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import math
import re


SPORTS = frozenset({"NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"})
SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
FAMILY = re.compile(r"[A-Z][A-Z0-9_:]{0,63}\Z")
PERIODS = frozenset({
    "FG", "1H", "2H", "1Q", "2Q", "3Q", "4Q",
    "1P", "2P", "3P", "F5", "1IN", "R1", "R2", "R3", "R4",
})
# Source roles describe the actual feature content, not the vendor name.
# Original bookmaker prices and other services' finished predictions are not
# independent model features even if the owner possesses a permitted copy.
FEATURE_KINDS = frozenset({
    "HISTORICAL_GAME_STATS", "OFFICIAL_ROSTER", "OFFICIAL_INJURY",
    "OFFICIAL_LINEUP", "SCHEDULE", "WEATHER", "VENUE",
    "PUBLIC_EFFICIENCY_STATS", "PLAY_BY_PLAY", "TRACKING_STATS",
    "HISTORICAL_PLAYER_LOG", "STROKES_GAINED_STATS",
})
PLAYER_FAMILIES = frozenset({
    "ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET", "FIRST_GOAL",
    "GOALIE_SAVES", "BIRDIES", "BOGEYS", "EAGLES", "HOLE_IN_ONE",
    "OUTRIGHT", "TOP5", "TOP10", "TOP20", "MAKE_CUT", "MISS_CUT",
    "ROUND_SCORE", "TOURNAMENT_SCORE", "ROUND_LEADER",
    "FIRST_ROUND_LEADER",
})
ORDERED_FAMILIES = frozenset({"FIRST_TD", "FIRST_BASKET", "FIRST_GOAL"})
COUNT_FAMILIES = frozenset({"TD_2PLUS"})
JOINT_FAMILIES = frozenset({"SGP", "MATCHUP", "THREE_BALL"})


def _sha(value: object) -> bool:
    return type(value) is str and SHA.fullmatch(value) is not None


def _utc(value: object) -> datetime | None:
    if type(value) is not str:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        return None
    return timestamp


def _unit(value: object) -> bool:
    return type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1


def audit_projection(candidate: dict, frozen_roster: dict[str, str] | None = None) -> dict:
    """Never infer a missing player-team binding or turn an anchor into EV.

    `candidate` has a `market` identity and a `forecast` receipt.
    `frozen_roster` must originate from a separate pregame source; a team
    label asserted by the odds feed alone does not supply roster proof.
    """
    reasons: list[str] = []

    def block(code: str) -> None:
        if code not in reasons:
            reasons.append(code)

    if not isinstance(candidate, dict):
        raise ValueError("CANDIDATE_OBJECT_REQUIRED")
    market = candidate.get("market")
    if not isinstance(market, dict):
        raise ValueError("MARKET_IDENTITY_REQUIRED")
    sport, event_id = market.get("sport"), market.get("event_id")
    family, period = market.get("family"), market.get("period")
    if type(sport) is not str or sport not in SPORTS or type(event_id) is not str or IDENT.fullmatch(event_id) is None:
        block("UNKNOWN_SPORT_OR_EVENT")
    if type(family) is not str or FAMILY.fullmatch(family) is None:
        block("UNKNOWN_MARKET_FAMILY")
    if type(period) is not str or period not in PERIODS:
        block("UNKNOWN_PERIOD")
    if type(market.get("settlement_id")) is not str or not market["settlement_id"].strip():
        block("MARKET_SETTLEMENT_UNKNOWN")

    forecast = candidate.get("forecast")
    if not isinstance(forecast, dict):
        block("NO_INDEPENDENT_MODEL_PROJECTION")
        forecast = {}
    origin = forecast.get("origin")
    if origin == "MARKET_ANCHOR":
        block("SPORTSBOOK_ANCHOR_NOT_INDEPENDENT")
    elif origin == "THIRD_PARTY_PROJECTION":
        block("THIRD_PARTY_FORECAST_NOT_SPORTSEDGE")
    elif origin != "SPORTSEDGE_INDEPENDENT":
        block("OWN_MODEL_ORIGIN_UNVERIFIED")

    for field in ("model_sha256", "feature_sha256", "distribution_sha256"):
        if not _sha(forecast.get(field)):
            block("MODEL_LINEAGE_MISSING_" + field.upper())
    frozen = _utc(forecast.get("feature_frozen_utc"))
    generated = _utc(forecast.get("generated_utc"))
    start = _utc(forecast.get("event_start_utc"))
    if frozen is None or generated is None or start is None:
        block("MODEL_UTC_CLOCKS_MISSING")
    elif not frozen <= generated < start:
        block("MODEL_NOT_FROZEN_BEFORE_START")

    source_rows = forecast.get("feature_sources")
    if not isinstance(source_rows, list) or not source_rows:
        block("INDEPENDENT_FEATURE_RECEIPTS_MISSING")
    else:
        for row in source_rows:
            if not isinstance(row, dict) or type(row.get("kind")) is not str or row.get("kind") not in FEATURE_KINDS:
                block("BOOKMAKER_OR_FOREIGN_FORECAST_FEATURE_FORBIDDEN")
                continue
            published = _utc(row.get("published_utc"))
            if not _sha(row.get("sha256")) or published is None:
                block("FEATURE_PROVENANCE_INCOMPLETE")
            elif frozen is not None and published > frozen:
                block("FEATURE_PUBLISHED_AFTER_MODEL_FREEZE")

    win = forecast.get("p_win")
    push = forecast.get("p_push")
    if not _unit(win) or not _unit(push) or win + push > 1 + 1e-12:
        block("MODEL_WIN_PUSH_PROBABILITIES_INVALID")
    if "projected_mean" in forecast:
        mean = forecast["projected_mean"]
        if type(mean) not in (int, float) or not math.isfinite(mean):
            block("PROJECTED_MEAN_INVALID")

    if isinstance(family, str):
        if family.startswith("PLAYER_PROP") or family in PLAYER_FAMILIES:
            player_id, team_id = market.get("player_id"), market.get("team_id")
            if (type(player_id) is not str or not player_id or
                    type(team_id) is not str or not team_id or
                    not isinstance(frozen_roster, dict) or
                    frozen_roster.get(player_id) != team_id):
                block("PLAYER_TEAM_PIT_ROSTER_UNBOUND")
            if family.startswith("PLAYER_PROP") and (
                type(market.get("stat")) is not str or not market["stat"]):
                block("PLAYER_STAT_IDENTITY_MISSING")
        if family in JOINT_FAMILIES and not _sha(forecast.get("joint_distribution_sha256")):
            block("CORRELATED_EVENT_DISTRIBUTION_MISSING")
        if family in ORDERED_FAMILIES and not _sha(forecast.get("ordered_events_sha256")):
            block("ORDERED_SCORING_EVENTS_MISSING")
        if family in COUNT_FAMILIES and not _sha(forecast.get("count_distribution_sha256")):
            block("MULTI_EVENT_COUNT_DISTRIBUTION_MISSING")
    if period != "FG" and period in PERIODS and not _sha(forecast.get("period_distribution_sha256")):
        block("INDEPENDENT_PERIOD_DISTRIBUTION_MISSING")

    return {
        "status": "BLOCK" if reasons else "PAPER_0U_MODEL_PROJECTION_UNVERIFIED",
        "reasons": reasons if reasons else ["MODEL_ORIGINALITY_AND_CALIBRATION_NOT_EXTERNALLY_VERIFIED"],
        "sport": sport if sport in SPORTS else None,
        "event_id": event_id if type(event_id) is str else None,
        "market_family": family if type(family) is str else None,
        "period": period if type(period) is str else None,
        "research_projection_usable": not reasons,
        "source_authenticated": False,
        "calibration_verified": False,
        "positive_ev_verified": False,
        "official_counted": 0,
        "approved_stake_u": 0,
    }


def census(candidates: list[dict], roster_by_event: dict[tuple[str, str], dict[str, str]] | None = None) -> dict:
    """Preserve the full attempted denominator, including unsupported markets."""
    if not isinstance(candidates, list):
        raise ValueError("CANDIDATE_LIST_REQUIRED")
    roster_by_event = roster_by_event or {}
    rows = []
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError("CANDIDATE_OBJECT_REQUIRED")
        market = item.get("market")
        if not isinstance(market, dict):
            raise ValueError("MARKET_IDENTITY_REQUIRED")
        sport, event_id = market.get("sport"), market.get("event_id")
        key = (sport, event_id) if type(sport) is str and type(event_id) is str else None
        rows.append(audit_projection(item, roster_by_event.get(key)))
    reasons = Counter(code for row in rows for code in row["reasons"])
    return {
        "status": "PAPER_0U_PROJECTION_COVERAGE_ONLY",
        "submitted": len(rows),
        "research_projections_with_valid_shape": sum(r["research_projection_usable"] for r in rows),
        "blocked": sum(r["status"] == "BLOCK" for r in rows),
        "reason_counts": dict(sorted(reasons.items())),
        "rows": rows,
        "official_counted": 0,
        "approved_stake_u": 0,
    }
