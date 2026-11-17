"""CBB prospective availability and disagreement preflight — PAPER/0u only.

Checks identities, point-in-time release/capture chronology, and missing roster
observations. Never estimates injury impact or overrides the frozen CBB model.
No hash supplied by a caller proves external source authenticity.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import math
import re

HASH = re.compile(r"^[a-f0-9]{64}$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
STATES = {"ACTIVE", "OUT", "DOUBTFUL", "QUESTIONABLE", "UNKNOWN"}


class CBBBlocked(ValueError):
    pass


def _time(s, label):
    if not isinstance(s, str) or not STAMP.fullmatch(s):
        raise CBBBlocked(label + ":UTC_Z_REQUIRED")
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise CBBBlocked(label + ":INVALID_TIME") from exc


def _hash(s, label):
    if not isinstance(s, str) or not HASH.fullmatch(s):
        raise CBBBlocked(label + ":ORIGINAL_SHA256_REQUIRED")


def _identity(s, label):
    if not isinstance(s, str) or not s.strip() or s != s.strip():
        raise CBBBlocked(label + ":CANONICAL_ID_REQUIRED")
    return s


def audit_cbb_availability(event: dict, roster: list, observations: list) -> dict:
    """All roster players need one frozen status observation; no name matching.

    Source-reported times and digest strings establish only internal shape.
    Injury-adjusted projected points require a separately fitted coefficient
    model, so this gate NEVER authorizes an availability score adjustment.
    """
    if not isinstance(event, dict) or not isinstance(roster, list) or not isinstance(observations, list):
        raise CBBBlocked("EVENT_ROSTER_OBSERVATIONS_REQUIRED")
    event_id = _identity(event.get("event_id"), "event_id")
    home = _identity(event.get("home_team_id"), "home_team_id")
    away = _identity(event.get("away_team_id"), "away_team_id")
    if home == away:
        raise CBBBlocked("SAME_TEAM_ON_BOTH_SIDES")
    freeze = _time(event.get("freeze_utc"), "freeze_utc")
    tip = _time(event.get("tipoff_utc"), "tipoff_utc")
    if freeze >= tip:
        raise CBBBlocked("FROZEN_AT_OR_AFTER_TIPOFF")
    _hash(event.get("roster_sha256"), "roster")
    published = _time(event.get("roster_published_utc"), "roster_published_utc")
    captured = _time(event.get("roster_captured_utc"), "roster_captured_utc")
    if not published <= captured <= freeze:
        raise CBBBlocked("ROSTER_NOT_POINT_IN_TIME")
    if not roster:
        raise CBBBlocked("EMPTY_ROSTER")
    bound = {}
    problems = []
    for i, p in enumerate(roster):
        try:
            player = _identity(p.get("player_id"), "player_id")
            team = _identity(p.get("team_id"), "team_id")
            if team not in (home, away):
                raise CBBBlocked("NON_EVENT_TEAM")
            if player in bound:
                raise CBBBlocked("DUPLICATE_ROSTER_PLAYER_ALL_COPIES")
            bound[player] = team
        except (AttributeError, CBBBlocked) as exc:
            problems.append({"input":"roster", "row":i, "reason":str(exc)})
    seen = Counter(o.get("player_id") for o in observations if isinstance(o, dict))
    statuses = {}
    for i, o in enumerate(observations):
        try:
            player = _identity(o.get("player_id"), "player_id")
            team = _identity(o.get("team_id"), "team_id")
            if player not in bound or bound[player] != team:
                raise CBBBlocked("UNBOUND_OR_TRANSFERRED_PLAYER")
            if seen[player] > 1:
                raise CBBBlocked("DUPLICATE_PLAYER_STATUS_ALL_COPIES")
            status = o.get("status")
            if status not in STATES:
                raise CBBBlocked("UNKNOWN_AVAILABILITY_STATE")
            _hash(o.get("source_sha256"), "status_source")
            pub = _time(o.get("published_utc"), "published_utc")
            obs = _time(o.get("captured_utc"), "captured_utc")
            if not pub <= obs <= freeze:
                raise CBBBlocked("STATUS_AFTER_FREEZE_OR_RELEASE_CONFLICT")
            statuses[player] = status
        except (AttributeError, CBBBlocked) as exc:
            problems.append({"input":"observation", "row":i, "reason":str(exc)})
    for player in sorted(set(bound) - set(statuses)):
        problems.append({"input":"roster", "player_id":player,
                         "reason":"NO_VALID_FROZEN_STATUS"})
    uncertain = sorted(p for p, state in statuses.items() if state != "ACTIVE")
    if uncertain:
        problems.append({"reason":"NO_FITTED_INJURY_OR_MINUTES_EFFECT",
                         "affected_player_count":len(uncertain)})
    return {
        "sport":"CBB", "event_id":event_id,
        "state":"BLOCK" if problems else "PIT_SHAPE_ONLY_UNAUTHENTICATED",
        "problems":problems, "roster_players":len(roster),
        "observations":len(observations), "valid_statuses":len(statuses),
        "availability_counts":dict(sorted(Counter(statuses.values()).items())),
        "independent_source_attested":False,
        "fitted_player_impact":False, "may_change_frozen_projection":False,
        "official_counted":0, "approved_stake_u":0,
    }


def screen_cbb_disagreement(signal: dict | None, *, availability: dict | None) -> tuple[bool, list[str]]:
    """Symmetric *research display* quarantine, not an optimized EV filter.

    15 pp / 25% raw-EV thresholds are conservative audit triggers; they
    are not a fitted calibration rule or evidence of an edge.
    """
    reasons = []
    if not isinstance(availability, dict) or availability.get("state") != "PIT_SHAPE_ONLY_UNAUTHENTICATED":
        reasons.append("CBB_AVAILABILITY_OR_ROSTER_INCOMPLETE")
    if signal is None:
        reasons.append("NO_TWO_SIDED_RESEARCH_SIGNAL")
    else:
        try:
            gap = float(signal["model_minus_market_pp"])
            ev = float(signal["raw_ev_unverified"])
            if not math.isfinite(gap) or not math.isfinite(ev):
                raise ValueError("NONFINITE_DISAGREEMENT")
            if abs(gap) >= 15 or ev >= 0.25:
                reasons.append("MODEL_DOUBTED_EXTREME_DISAGREEMENT")
        except (ValueError, TypeError, KeyError) as exc:
            reasons.append("INVALID_CBB_DISAGREEMENT:" + str(exc))
    return not reasons, reasons


def cbb_direction_diagnostic(rows: list[dict]) -> dict:
    """Inspect candidate shortlist directions without inventing balanced picks."""
    counts = Counter()
    for x in rows:
        if x.get("quality_state") != "RESEARCH_SCREEN_ONLY":
            continue
        market = x.get("market", ())
        if len(market) < 6 or market[0] != "CBB":
            continue
        kind, side, line = market[2], market[4], market[5]
        if kind in ("TOTAL", "TEAM_TOTAL"):
            counts["OVER" if side == "OVER" else "UNDER"] += 1
        elif kind == "SPREAD":
            try:
                value = float(line)
            except (TypeError, ValueError):
                continue
            counts["UNDERDOG" if value > 0 else "FAVORITE" if value < 0 else "PICKEM"] += 1
    total = sum(counts.values())
    return {"direction_counts":dict(sorted(counts.items())), "n":total,
            "one_sided_warning":total >= 10 and any(n/total >= .85 for n in counts.values()),
            "warning_is_not_fitted_bias_correction":True}
