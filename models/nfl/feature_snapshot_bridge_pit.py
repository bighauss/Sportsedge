#!/usr/bin/env python3
"""Join one frozen NFL EPA rating artifact to exact event identities.

RESEARCH ONLY: emit score-model feature rows, never probabilities or bets.
The caller's timestamps and source metadata are not independently authenticated.
"""
from __future__ import annotations

import argparse
import csv
import io
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from epa_ridge_pit import utc
from score_walkforward_pit import FEATURE_COLUMNS, private_evidence_path, create_private_output


def _unique_json_object(pairs):
    """Fail closed: Python's default JSON decoder silently keeps last duplicates."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("DUPLICATE_JSON_KEY:" + key)
        obj[key] = value
    return obj


def _reject_nonfinite_json_literal(value):
    raise ValueError("NONFINITE_JSON_LITERAL:" + value)


def strict_original_json(payload):
    """Original input bytes/text; no duplicate keys or NaN/Infinity anywhere."""
    return json.loads(payload, object_pairs_hook=_unique_json_object,
                      parse_constant=_reject_nonfinite_json_literal)


EVENT_COLUMNS = frozenset((
    "game_id", "home_team", "away_team", "kickoff_utc", "forecast_asof_utc",
))


def _value(unit, kind, team):
    if not isinstance(unit, dict) or kind not in unit:
        raise ValueError("RATING_UNIT_MISSING:" + kind)
    values = unit[kind]
    if not isinstance(values, dict) or team not in values:
        raise ValueError("TEAM_NOT_IN_FROZEN_RATINGS:" + team)
    try:
        value = float(values[team])
    except (ValueError, TypeError) as exc:
        raise ValueError("INVALID_RATING:" + team) from exc
    if not isfinite(value):
        raise ValueError("NONFINITE_RATING:" + team)
    return value


def snapshots(ratings, events, *, ratings_sha256):
    if not isinstance(ratings, dict) or ratings.get("status") != "PAPER_HOLD_0U":
        raise ValueError("RATINGS_STATUS_NOT_RESEARCH")
    if ratings.get("approved_stake_u") != 0:
        raise ValueError("UNSAFE_UPSTREAM_RATINGS_STAKE")
    if not isinstance(ratings_sha256, str) or (
        len(ratings_sha256) != 71 or
        not ratings_sha256.startswith("sha256:") or
        any(c not in "0123456789abcdef" for c in ratings_sha256[7:])
    ):
        raise ValueError("RATINGS_SHA_REQUIRED")
    rated_at = utc(ratings["asof_utc"])
    observed = utc(ratings["source_observed_utc"])
    if observed > rated_at:
        raise ValueError("RATINGS_SOURCE_AFTER_RATING_TIME")
    units = ratings.get("units")
    if not isinstance(units, dict) or set(units) != {"pass", "rush"}:
        raise ValueError("PASS_AND_RUSH_RATINGS_REQUIRED")
    if not isinstance(events, list) or not events:
        raise ValueError("NO_MATCHUP_EVENTS")
    output = []
    used_ids = set()
    for event in events:
        if not isinstance(event, dict) or set(event) != EVENT_COLUMNS:
            raise ValueError("EVENT_SCHEMA_INVALID")
        game_id = event["game_id"]
        home = event["home_team"]
        away = event["away_team"]
        if not isinstance(game_id, str) or not game_id.strip() or (
            game_id in used_ids
        ):
            raise ValueError("DUPLICATE_OR_EMPTY_EVENT_ID")
        used_ids.add(game_id)
        if not all(isinstance(t, str) and t.strip() for t in (home, away)):
            raise ValueError("MISSING_EXACT_TEAM_IDS")
        if home == away:
            raise ValueError("HOME_AWAY_TEAM_COLLISION")
        kickoff = utc(event["kickoff_utc"])
        freeze = utc(event["forecast_asof_utc"])
        if not observed <= rated_at <= freeze < kickoff:
            raise ValueError("RATINGS_OR_FREEZE_LOOKAHEAD")
        row = {
            "game_id": game_id,
            "home_team": home,
            "away_team": away,
            "kickoff_utc": event["kickoff_utc"],
            "forecast_asof_utc": event["forecast_asof_utc"],
            "source_observed_utc": ratings["source_observed_utc"],
            "epa_ratings_sha256": ratings_sha256,
        }
        for side, team in (("home", home), ("away", away)):
            for play_kind in ("pass", "rush"):
                unit = units[play_kind]
                row[f"{side}_off_{play_kind}"] = _value(
                    unit, "offense_above_average_epa", team)
                row[f"{side}_def_allow_{play_kind}"] = _value(
                    unit, "defense_allowed_above_average_epa", team)
        if set(row) != FEATURE_COLUMNS:
            raise ValueError("SCORE_FEATURE_SCHEMA_DRIFT")
        output.append(row)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", required=True, help="archived EPA rating JSON")
    parser.add_argument("--events", required=True, help="exact matchup identities JSON list")
    parser.add_argument("--out", required=True, help="new create-only feature CSV")
    args = parser.parse_args()
    # Never load private source bytes from or write reconstructed features into
    # this public repository. Resolve symlinks and traversal before any reads.
    ratings_path = private_evidence_path(args.ratings)
    events_path = private_evidence_path(args.events)
    output_path = private_evidence_path(args.out)
    raw = ratings_path.read_bytes()
    ratings = strict_original_json(raw)
    events = strict_original_json(events_path.read_bytes())
    rows = snapshots(
        ratings, events,
        ratings_sha256="sha256:" + sha256(raw).hexdigest(),
    )
    buffer = io.StringIO(newline="")
    fields = sorted(FEATURE_COLUMNS)
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    create_private_output(args.out, buffer.getvalue().encode("utf-8"))
    print(json.dumps({
        "status": "PAPER_HOLD_0U", "event_rows": len(rows),
        "approved_stake_u": 0, "output": args.out,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
