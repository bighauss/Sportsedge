"""Private, prospective Firecrawl ESPN NFL injury-context intake (PAPER / 0u).

Consumes ORIGINAL saved Firecrawl Alexandria JSON bytes from an operator-owned
private archive. No network calls, sportsbook quotes, automatic player joins,
model feature admission, health assertions, or provider authentication.

ESPN's injuries endpoint can contain 'Active' records and dated game recaps.
It is NOT the official NFL practice/game designation feed. Neither raw row
count nor a successful HTTP 200 proves injuries or complete roster coverage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from sportsedge.validation.seven_sport_pit_freeze import _private_path, _raw_file

SCHEMA = "sportsedge-firecrawl-espn-injury-context-v1"
PROVIDER = "espn-com"
CAPABILITY = "sports-data/injuries"
SOURCE_ENDPOINT = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
MAX_BYTES = 10_000_000
TEAM = re.compile(r"^[A-Z]{2,4}$")
EVENT = re.compile(r"^[A-Za-z0-9_.:/-]{1,128}$")
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
# Listed statuses are *context*, not verified NFL final designations.
SIGNAL = frozenset({
    "OUT", "DOUBTFUL", "QUESTIONABLE", "DAY-TO-DAY", "DAY TO DAY",
    "INJURED RESERVE", "IR", "PUP", "PHYSICALLY UNABLE TO PERFORM",
    "SUSPENDED", "SUSPENSION", "INACTIVE",
})
NON_INJURY = frozenset({"ACTIVE", "HEALTHY", "AVAILABLE"})
UTC = timezone.utc


class InjuryEvidenceError(ValueError):
    """A malformed, stale or unsafe research export; never promote it."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InjuryEvidenceError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _nonfinite(_):
    raise InjuryEvidenceError("NONFINITE_JSON_NUMBER")


def _parse(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise InjuryEvidenceError("ORIGINAL_PROVIDER_BYTES_MISSING_OR_OVERSIZED")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, InjuryEvidenceError):
            raise
        raise InjuryEvidenceError("INVALID_OR_AMBIGUOUS_SOURCE_JSON") from exc
    if not isinstance(value, dict):
        raise InjuryEvidenceError("SOURCE_JSON_MUST_BE_OBJECT")
    return value


def _utc(raw, label):
    if type(raw) is not str:
        raise InjuryEvidenceError("TIMESTAMP_REQUIRED:" + label)
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise InjuryEvidenceError("INVALID_TIMESTAMP:" + label) from exc
    if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
        raise InjuryEvidenceError("UTC_TIMESTAMP_REQUIRED:" + label)
    return ts.astimezone(UTC)


def _positive_int(value, label, *, zero=False):
    if type(value) is not int or value < (0 if zero else 1):
        raise InjuryEvidenceError("INVALID_SOURCE_COUNT:" + label)
    return value


def _str(value, label, *, limit=256):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise InjuryEvidenceError("INVALID_SOURCE_STRING:" + label)
    return value


def _fetched(value):
    if type(value) is not int or not 1_000_000_000_000 <= value <= 9_999_999_999_999:
        raise InjuryEvidenceError("PROVIDER_OBSERVED_MS_INVALID")
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise InjuryEvidenceError("PROVIDER_OBSERVED_MS_INVALID") from exc


def analyze(raw, *, team, event_id, event_start_utc, now_utc=None):
    """Analyze saved original provider JSON, never accept it as verified PIT data.

    The caller's event/team binding is REQUIRED; provider JSON is not proof a
    team really plays the given event or that an injury applies at kickoff.
    """
    if type(team) is not str or not TEAM.fullmatch(team):
        raise InjuryEvidenceError("EXPLICIT_NFL_TEAM_ABBREVIATION_REQUIRED")
    if type(event_id) is not str or not EVENT.fullmatch(event_id):
        raise InjuryEvidenceError("EXPLICIT_EVENT_ID_REQUIRED")
    event_start = _utc(event_start_utc, "event_start")
    now = datetime.now(UTC) if now_utc is None else now_utc
    if (not isinstance(now, datetime) or now.tzinfo is None
            or now.utcoffset() != timedelta(0)):
        raise InjuryEvidenceError("ACTUAL_CAPTURE_CLOCK_MUST_BE_UTC")
    now = now.astimezone(UTC)
    if not now < event_start:
        raise InjuryEvidenceError("POST_EVENT_INJURY_CAPTURE_REFUSED")

    root = _parse(raw)
    if root.get("success") is not True:
        raise InjuryEvidenceError("FIRECRAWL_RESPONSE_UNSUCCESSFUL")
    envelope = root.get("data")
    results = envelope.get("alexandria") if isinstance(envelope, dict) else None
    if not isinstance(results, list) or len(results) != 1:
        raise InjuryEvidenceError("ONE_ALEXANDRIA_SOURCE_RESULT_REQUIRED")
    result = results[0]
    if not isinstance(result, dict) or (result.get("provider"),
        result.get("capability")) != (PROVIDER, CAPABILITY):
        raise InjuryEvidenceError("WRONG_PROVIDER_OR_CAPABILITY")
    if result.get("error") is not None or result.get("upstreamStatus") != 200:
        raise InjuryEvidenceError("PROVIDER_RETURNED_ERROR_OR_NON_200")
    workflow = result.get("workflow")
    if not isinstance(workflow, dict):
        raise InjuryEvidenceError("WORKFLOW_VERSION_AND_DIGEST_REQUIRED")
    version = _str(workflow.get("version"), "workflow_version", limit=64)
    digest = workflow.get("digest")
    if type(digest) is not str or not DIGEST.fullmatch(digest):
        raise InjuryEvidenceError("WORKFLOW_DIGEST_INVALID")
    request_id = _str(result.get("providerRequestId"), "providerRequestId", limit=128)
    data = result.get("data")
    if not isinstance(data, dict) or data.get("sport") != "football" or data.get("league") != "nfl":
        raise InjuryEvidenceError("NOT_AN_NFL_INJURY_PAYLOAD")
    if data.get("team_filter") != team or data.get("status_filter") is not None:
        raise InjuryEvidenceError("UNFILTERED_ALL_STATUS_TEAM_REPORT_REQUIRED")
    observed = _fetched(data.get("observed_at_ms"))
    feed = _utc(data.get("feed_timestamp"), "upstream_feed")
    if not feed <= observed <= now < event_start:
        raise InjuryEvidenceError("PUBLICATION_OBSERVATION_CAPTURE_CHRONOLOGY_INVALID")
    if now - observed > timedelta(minutes=5):
        raise InjuryEvidenceError("SOURCE_CAPTURE_TOO_STALE_FOR_PREGAME")
    if observed - feed > timedelta(days=7):
        # A stale source-effective feed date cannot be substituted with the
        # later provider fetch timestamp to masquerade as fresh health news.
        raise InjuryEvidenceError("INJURY_FEED_DATE_OVER_SEVEN_DAYS_OLD")
    teams = data.get("teams")
    if (type(data.get("team_count")) is not int or data["team_count"] != 1
            or not isinstance(teams, list) or len(teams) != 1):
        raise InjuryEvidenceError("EXACT_ONE_REQUESTED_TEAM_REQUIRED")
    t = teams[0]
    if not isinstance(t, dict) or t.get("abbreviation") != team:
        raise InjuryEvidenceError("PROVIDER_TEAM_MISMATCH")
    team_id = _str(t.get("team_id"), "espn_team_id", limit=32)
    injuries = t.get("injuries")
    if not isinstance(injuries, list) or len(injuries) > 1000:
        raise InjuryEvidenceError("INVALID_OR_OVERSIZED_INJURY_CENSUS")
    rows = _positive_int(t.get("count"), "team_count", zero=True)
    total = _positive_int(data.get("player_count"), "player_count", zero=True)
    if rows != len(injuries) or total != rows:
        raise InjuryEvidenceError("PLAYER_CENSUS_COUNT_CONFLICT")

    active = unknown = signals = old_notes = 0
    seen_ids = set()
    for row in injuries:
        if not isinstance(row, dict):
            raise InjuryEvidenceError("NONOBJECT_INJURY_ROW")
        athlete = _str(row.get("athlete_id"), "athlete_id", limit=32)
        if athlete in seen_ids:
            raise InjuryEvidenceError("DUPLICATE_ESPN_ATHLETE")
        seen_ids.add(athlete)
        if row.get("current_team_id") != team_id:
            raise InjuryEvidenceError("ATHLETE_CURRENT_TEAM_MISMATCH")
        date = _utc(row.get("date"), "injury_note_date")
        if date > observed:
            raise InjuryEvidenceError("INJURY_NOTE_IN_FUTURE_OF_SOURCE_OBSERVATION")
        if observed - date > timedelta(days=7):
            old_notes += 1
        status = _str(row.get("status"), "injury_status", limit=80).upper()
        normalized = " ".join(status.replace("_", " ").split())
        if normalized in NON_INJURY:
            active += 1
        elif normalized in SIGNAL:
            signals += 1
        else:
            unknown += 1
    reasons = [
        "SOURCE_TRANSPORT_AND_PUBLICATION_NOT_INDEPENDENTLY_ATTESTED",
        "ESPN_CONTEXT_IS_NOT_OFFICIAL_NFL_GAME_DESIGNATION",
        "TEAM_GAME_IDENTITY_AND_ROSTER_MAPPING_NOT_VERIFIED",
        "NO_AUTHORIZED_DK_OR_INDEPENDENT_BOOK_QUOTES",
    ]
    if not rows:
        reasons.append("EMPTY_PROVIDER_REPORT_CANNOT_PROVE_HEALTH_OR_ROSTER_COMPLETENESS")
    if active:
        reasons.append("ACTIVE_ROWS_ARE_NOT_INJURY_DESIGNATIONS")
    if old_notes:
        reasons.append("SOME_STATUS_NOTES_OLDER_THAN_SEVEN_DAYS")
    if unknown:
        reasons.append("UNRECOGNIZED_STATUS_ROWS_EXCLUDED")
    if not signals:
        reasons.append("NO_RECOGNIZED_NON_ACTIVE_INJURY_STATUS_FOUND")
    state = ("PAPER_0U_UNAUTHENTICATED_INJURY_CONTEXT"
             if signals and not unknown and not old_notes else
             "BLOCK_INJURY_CONTEXT_INCOMPLETE_OR_STALE")
    return {
        "schema": SCHEMA, "state": state,
        "source_provider_claim": PROVIDER,
        "source_capability_claim": CAPABILITY,
        "source_endpoint_contract": SOURCE_ENDPOINT,
        "source_workflow_version_claim": version,
        "source_workflow_digest_claim": digest,
        "provider_request_id_claim": request_id,
        "original_response_sha256": "sha256:" + sha256(raw).hexdigest(),
        "original_response_bytes": len(raw),
        "sport": "NFL", "team": team, "event_id_claim": event_id,
        "event_start_utc_claim": event_start.isoformat(),
        "feed_timestamp_claim": feed.isoformat(),
        "provider_observed_utc_claim": observed.isoformat(),
        "local_receipt_created_utc": now.isoformat(),
        "provider_rows_received": rows,
        "reported_nonactive_status_rows": signals,
        "non_injury_active_rows_excluded": active,
        "unsupported_status_rows_excluded": unknown,
        "older_than_seven_days_notes": old_notes,
        "exclusion_reasons": reasons,
        "raw_player_records_redacted_from_receipt": True,
        "source_independently_authenticated": False,
        "team_roster_coverage_verified": False,
        "published_asof_kickoff_authenticated": False,
        "official_game_designations_verified": False,
        "model_feature_admissible": False,
        "gate_b_pit_certified": False,
        "gate_a_book_coverage_certified": False,
        "release_certified": False,
        "official_counted": 0, "approved_stake_u": 0, "card": None,
    }


def archive(original, report_path, *, team, event_id, event_start_utc,
            now_utc=None):
    """Preserve original raw input in private storage; create sanitized report."""
    original = _private_path(original, "firecrawl_original")
    output = _private_path(report_path, "firecrawl_report", output=True)
    if original == output:
        raise InjuryEvidenceError("ORIGINAL_AND_REPORT_PATH_COLLIDE")
    raw = _raw_file(original, "firecrawl_original")
    result = analyze(raw, team=team, event_id=event_id,
                     event_start_utc=event_start_utc, now_utc=now_utc)
    encoded = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)
               + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(output, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--team", required=True)
    p.add_argument("--event-id", required=True)
    p.add_argument("--event-start-utc", required=True)
    args = p.parse_args(argv)
    report = archive(args.original, args.report, team=args.team,
                     event_id=args.event_id, event_start_utc=args.event_start_utc)
    print(json.dumps({
        "state": report["state"],
        "rows": report["provider_rows_received"],
        "signals_unverified": report["reported_nonactive_status_rows"],
        "active_rows_excluded": report["non_injury_active_rows_excluded"],
        "gate_b_pit_certified": False,
        "official_counted": 0, "approved_stake_u": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
