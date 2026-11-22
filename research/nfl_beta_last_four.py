"""Research-only NFL beta pricing. All output remains PAPER / 0u."""
from datetime import datetime, timezone
from math import isfinite, sqrt
from copy import deepcopy
import re

STATS = frozenset(("pass_yds", "rush_yds", "rec_yds", "receptions"))
KINDS = frozenset(("XPLUS", "FIRST_TD", "SGP"))


def _utc(s):
    if not isinstance(s, str):
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    return d.astimezone(timezone.utc)


def _implied(american):
    if type(american) is not int or abs(american) < 100:
        raise ValueError("INVALID_AMERICAN_ODDS")
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def _decimal(american):
    return 1 + (american / 100 if american > 0 else 100 / -american)


def _leg_hit(scenario, leg):
    if not isinstance(scenario, dict) or not isinstance(leg, dict):
        raise ValueError("INVALID_SCENARIO_OR_LEG")
    kind = leg["kind"]
    if kind == "XPLUS":
        if leg.get("stat") not in STATS or type(leg.get("threshold")) is not int or leg["threshold"] < 1:
            raise ValueError("INVALID_LADDER")
        player = leg.get("player_id")
        if not isinstance(player, str) or not player:
            raise ValueError("PLAYER_ID_REQUIRED")
        players = scenario["players"]
        if not isinstance(players, dict) or not isinstance(players.get(player), dict):
            raise ValueError("INVALID_PLAYER_SAMPLES")
        v = players[player][leg["stat"]]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v < 0:
            raise ValueError("INVALID_STAT_SAMPLE")
        return v >= leg["threshold"]
    if kind == "FIRST_TD":
        scorer = leg.get("player_id")
        if not isinstance(scorer, str) or not scorer:
            raise ValueError("PLAYER_ID_REQUIRED")
        events = scenario["ordered_touchdowns"]
        if not isinstance(events, list):
            raise ValueError("ORDERED_EVENTS_REQUIRED")
        if any(not isinstance(x, str) or not x for x in events):
            raise ValueError("INVALID_ORDERED_EVENT")
        return bool(events) and events[0] == scorer
    raise ValueError("UNSUPPORTED_LEG")


def _evaluate(scenario, offer):
    if offer["kind"] == "SGP":
        legs = offer.get("legs")
        if not isinstance(legs, list) or len(legs) < 2:
            raise ValueError("SGP_LEGS_REQUIRED")
        if any(not isinstance(leg, dict) or leg.get("kind") not in ("XPLUS", "FIRST_TD") for leg in legs):
            raise ValueError("UNSUPPORTED_SGP_LEG")
        outcomes = [_leg_hit(scenario, leg) for leg in legs]
        return all(outcomes)
    return _leg_hit(scenario, offer)


def price_beta(scenarios, offers, *, decision_utc, min_scenarios=1000):
    """Price exact joint offers; upstream provenance remains unverified."""
    decision = _utc(decision_utc)
    if not isinstance(scenarios, list) or not isinstance(offers, list):
        raise ValueError("INVALID_INPUT")
    if type(min_scenarios) is not int or min_scenarios < 100:
        raise ValueError("INVALID_SAMPLE_FLOOR")
    results = []
    seen = set()
    for offer in offers:
        if not isinstance(offer, dict):
            raise ValueError("INVALID_OFFER")
        identity = (offer.get("event_id"), offer.get("book"), offer.get("quote_id"))
        if not all(isinstance(x, str) and x for x in identity) or identity in seen:
            raise ValueError("MISSING_OR_DUPLICATE_QUOTE_ID")
        seen.add(identity)
        row = dict(offer_id=identity[2], event_id=identity[0], kind=offer.get("kind"),
                   status="PAPER_HOLD_0U", stake_u=0, official_counted=0,
                   beta_ev=None, beta_probability=None, reasons=[],
                   decision_utc=decision_utc, offer=deepcopy(offer))
        reasons = row["reasons"]
        if not isinstance(offer.get("kind"), str) or offer["kind"] not in KINDS:
            reasons.append("UNSUPPORTED_MARKET")
        if identity[1].casefold() != "draftkings":
            reasons.append("NOT_DRAFTKINGS")
        try:
            captured = _utc(offer["captured_at_utc"])
            kickoff = _utc(offer["kickoff_utc"])
            model_asof = _utc(offer["model_asof_utc"])
            if not (model_asof <= captured <= decision < kickoff):
                reasons.append("POINT_IN_TIME_OR_KICKOFF_VIOLATION")
            if (decision - captured).total_seconds() > 300:
                reasons.append("STALE_QUOTE")
        except (KeyError, ValueError, TypeError):
            reasons.append("TIMESTAMP_INVALID")
        if not all(isinstance(offer.get(k), str) and re.fullmatch(r"sha256:[0-9a-f]{64}", offer[k]) for k in ("source_sha256", "model_sha256")):
            reasons.append("PROVENANCE_HASH_INVALID")
        if len(scenarios) < min_scenarios:
            reasons.append("INSUFFICIENT_JOINT_SCENARIOS")
        if offer.get("kind") == "SGP" and offer.get("joint_simulation") is not True:
            reasons.append("JOINT_SIMULATION_NOT_ATTESTED")
        try:
            _implied(offer["odds_american"])
            d = _decimal(offer["odds_american"])
        except (KeyError, ValueError, TypeError, OverflowError):
            reasons.append("PRICE_INVALID")
        if not reasons:
            try:
                if any(not isinstance(s, dict) or s.get("event_id") != identity[0] for s in scenarios):
                    raise ValueError("MIXED_OR_INVALID_EVENT_SCENARIOS")
                hits = sum(bool(_evaluate(s, offer)) for s in scenarios)
                p = hits / len(scenarios)
                se = sqrt(p * (1 - p) / len(scenarios))
                row["beta_probability"] = round(p, 6)
                row["beta_ev"] = round(p * d - 1, 6)
                row["mc_se"] = round(se, 6)
                if hits == 0 or hits == len(scenarios):
                    reasons.append("EXTREME_MC_ESTIMATE")
                if se > 0.02:
                    reasons.append("MONTE_CARLO_UNCERTAINTY_HIGH")
            except (KeyError, TypeError, ValueError, IndexError, OverflowError):
                reasons.append("INCOMPLETE_OR_INVALID_JOINT_SCENARIOS")
        if not reasons:
            reasons.append("BETA_UNCALIBRATED_NO_VALIDATED_EV")
        results.append(row)
    return dict(status="RESEARCH_PAPER_0U", rows=results, official_bets=0)
