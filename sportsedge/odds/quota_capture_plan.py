"""Offline budget preflight for prospective The Odds API event capture.

Read a private, hash-checked provider event catalog; produce a private,
create-only two-snapshot plan. Never contact the provider, schedule a task,
select bets, or automatically truncate the event universe to fit credits.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
import math
from pathlib import Path

from sportsedge.odds.event_discovery import COLS, clock
from sportsedge.odds.free_odds_aggregator_intake import (
    BOOKS, EVENT_RE, SPORTS, private_archive_root, strict_json, utc,
)
from sportsedge.odds.the_odds_api_clv_export import _write_private

ALLOWED_MARKETS = frozenset({"h2h", "spreads", "totals"})
CLOSE_OFFSET = timedelta(minutes=5)
TAKE_OFFSET = timedelta(minutes=60)
MIN_LEAD = timedelta(minutes=10)


class PlanningBlocked(ValueError):
    pass


def _original(root: Path, name: str) -> bytes:
    if (not isinstance(name, str) or not name or name != Path(name).name
            or name in (".", "..") or "\\" in name):
        raise PlanningBlocked("CATALOG_SOURCE_FILENAME_UNSAFE")
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise PlanningBlocked("CATALOG_SOURCE_FILE_UNAVAILABLE")
    if path.stat().st_size > 10_000_000:
        raise PlanningBlocked("CATALOG_SOURCE_FILE_OVERSIZE")
    return path.read_bytes()


def load_catalog(private_manifest: Path):
    path = Path(private_manifest).resolve()
    root = private_archive_root(path.parent)
    if path.is_symlink() or not path.is_file():
        raise PlanningBlocked("EVENT_MANIFEST_FILE_UNAVAILABLE")
    try:
        meta = strict_json(path.read_bytes())
    except (UnicodeError, json.JSONDecodeError):
        raise PlanningBlocked("EVENT_MANIFEST_NOT_STRICT_JSON") from None
    if (not isinstance(meta, dict) or
        meta.get("schema") != "sportsedge-oddsapi-provider-event-catalog-v1" or
        meta.get("sport") not in SPORTS):
        raise PlanningBlocked("EVENT_MANIFEST_SCHEMA_OR_SPORT_INVALID")
    raw = _original(root, meta.get("original_raw_filename"))
    catalog = _original(root, meta.get("catalog_filename"))
    if "sha256:" + sha256(raw).hexdigest() != meta.get("original_raw_sha256"):
        raise PlanningBlocked("EVENT_ORIGINAL_HASH_MISMATCH")
    if "sha256:" + sha256(catalog).hexdigest() != meta.get("catalog_sha256"):
        raise PlanningBlocked("EVENT_CATALOG_HASH_MISMATCH")
    created = utc(meta.get("captured_at_utc"))
    try:
        text = catalog.decode("utf-8-sig")
        reader = csv.DictReader(StringIO(text), restkey="__EXTRA__", strict=True)
        if not reader.fieldnames or tuple(reader.fieldnames) != COLS:
            raise PlanningBlocked("EVENT_CATALOG_HEADERS_UNEXPECTED")
        rows = list(reader)
    except (UnicodeError, csv.Error):
        raise PlanningBlocked("EVENT_CATALOG_CSV_MALFORMED") from None
    if len(rows) != meta.get("events_returned"):
        raise PlanningBlocked("EVENT_CATALOG_COUNT_MISMATCH")
    result = []
    seen = set()
    for row in rows:
        if "__EXTRA__" in row or None in row or any(v is None for v in row.values()):
            raise PlanningBlocked("EVENT_CATALOG_ROW_SHAPE_INVALID")
        ident = row.get("source_event_id")
        if not isinstance(ident, str) or not EVENT_RE.fullmatch(ident) or ident in seen:
            raise PlanningBlocked("EVENT_CATALOG_ID_MISSING_OR_DUPLICATED")
        seen.add(ident)
        if row["sport"] != meta["sport"] or utc(row["captured_at_utc"]) != created:
            raise PlanningBlocked("EVENT_CATALOG_SPORT_OR_CAPTURE_CHANGED")
        if not row["home_team"] or not row["away_team"] or row["home_team"] == row["away_team"]:
            raise PlanningBlocked("EVENT_CATALOG_TEAM_IDENTITIES_INVALID")
        kickoff = utc(row["kickoff_utc"])
        future = kickoff > created
        expected = "UPCOMING_PREGAME" if future else "ALREADY_STARTED_NO_PREGAME"
        close_string = (kickoff - CLOSE_OFFSET).isoformat() if future else ""
        if (row["capture_state"] != expected or
                row["suggested_close_capture_utc"] != close_string):
            raise PlanningBlocked("EVENT_CATALOG_TIMELINE_CHANGED")
        result.append((row, kickoff))
    if sum(r["capture_state"] == "UPCOMING_PREGAME" for r,_ in result) != meta.get("upcoming_pregame_events"):
        raise PlanningBlocked("EVENT_CATALOG_PREGAME_COUNT_MISMATCH")
    # A SHA-matched original plus a SHA-matched catalog is not sufficient:
    # one of them could have been rewritten and its manifest SHA updated.
    # Bind every catalog row to a provider event in the exact archived JSON.
    try:
        source_events = strict_json(raw)
    except (ValueError, UnicodeError, json.JSONDecodeError):
        raise PlanningBlocked("EVENT_ORIGINAL_JSON_INVALID") from None
    if not isinstance(source_events, list) or len(source_events) != len(result):
        raise PlanningBlocked("EVENT_RAW_CATALOG_CENSUS_DISAGREEMENT")
    canonical = {}
    for source_event in source_events:
        if not isinstance(source_event, dict):
            raise PlanningBlocked("EVENT_ORIGINAL_IDENTITY_INVALID")
        event_id = source_event.get("id")
        home, away = source_event.get("home_team"), source_event.get("away_team")
        if (not isinstance(event_id, str) or not EVENT_RE.fullmatch(event_id) or
            event_id in canonical or source_event.get("sport_key") != SPORTS[meta["sport"]] or
            not isinstance(home, str) or not home.strip() or
            not isinstance(away, str) or not away.strip() or home.strip() == away.strip()):
            raise PlanningBlocked("EVENT_ORIGINAL_IDENTITY_INVALID")
        try:
            start = utc(source_event.get("commence_time")).isoformat()
        except ValueError:
            raise PlanningBlocked("EVENT_ORIGINAL_KICKOFF_INVALID") from None
        canonical[event_id] = (home.strip(), away.strip(), start)
    catalog_identity = {row["source_event_id"]:
                        (row["home_team"], row["away_team"], kickoff.isoformat())
                        for row, kickoff in result}
    if canonical != catalog_identity:
        raise PlanningBlocked("EVENT_RAW_TO_CATALOG_IDENTITY_DRIFT")
    return meta, result, created


def build_plan(
    manifest: Path,
    output: Path,
    *,
    credits_remaining: int,
    reserve_credits: int = 0,
    markets=("h2h", "spreads", "totals"),
    bookmakers=("draftkings", "fanduel"),
    now=None,
    max_catalog_age_seconds: int = 3600,
):
    if (type(credits_remaining) is not int or type(reserve_credits) is not int or
        not 0 <= credits_remaining <= 1_000_000 or
        not 0 <= reserve_credits <= credits_remaining):
        raise PlanningBlocked("CREDIT_INPUT_INVALID")
    if not 1 <= max_catalog_age_seconds <= 86400:
        raise PlanningBlocked("CATALOG_AGE_LIMIT_INVALID")
    if (not markets or len(set(markets)) != len(markets) or
        any(m not in ALLOWED_MARKETS for m in markets)):
        raise PlanningBlocked("CAPTURE_MARKETS_NOT_SUPPORTED")
    if (not bookmakers or len(set(bookmakers)) != len(bookmakers) or
        any(b not in BOOKS for b in bookmakers)):
        raise PlanningBlocked("CAPTURE_BOOKS_NOT_SUPPORTED")
    destination = Path(output)
    if destination.suffix.lower() != ".json" or destination.exists() or destination.is_symlink():
        raise PlanningBlocked("OUTPUT_MUST_BE_NEW_PRIVATE_JSON")
    private_archive_root(destination.parent)
    current = clock(now)
    meta, events, catalog_created = load_catalog(manifest)
    age = (current - catalog_created).total_seconds()
    if not 0 <= age <= max_catalog_age_seconds:
        raise PlanningBlocked("EVENT_CATALOG_STALE_OR_FROM_FUTURE")
    # Official v4 advertised base quota: each market x region, with <=10
    # bookmakers equivalent to one region. Real charges can differ by plan.
    cost_per_snapshot = len(markets) * math.ceil(len(bookmakers) / 10)
    cost_per_event = 2 * cost_per_snapshot
    rows = []
    eligible = []
    for event, kickoff in events:
        row = {
            "source_event_id": event["source_event_id"],
            "sport": meta["sport"],
            "home_team": event["home_team"],
            "away_team": event["away_team"],
            "kickoff_utc": kickoff.isoformat(),
            "take_at_utc": None,
            "close_at_utc": None,
            "plan_status": "BLOCK_EVENT_ALREADY_STARTED",
            "estimate_credits_two_snapshots": 0,
        }
        if kickoff > current:
            if kickoff - current <= MIN_LEAD:
                row["plan_status"] = "BLOCK_TOO_LATE_FOR_DISTINCT_SNAPSHOTS"
            else:
                row["take_at_utc"] = max(current, kickoff - TAKE_OFFSET).isoformat()
                row["close_at_utc"] = (kickoff - CLOSE_OFFSET).isoformat()
                row["plan_status"] = "ELIGIBLE_NOT_YET_BUDGETED"
                row["estimate_credits_two_snapshots"] = cost_per_event
                eligible.append(row)
        rows.append(row)
    needed = len(eligible) * cost_per_event
    available = credits_remaining - reserve_credits
    full_coverage = bool(eligible) and needed <= available
    for row in eligible:
        row["plan_status"] = ("PLANNED_RESEARCH_ONLY" if full_coverage
                              else "BLOCK_QUOTA_INSUFFICIENT_FULL_COVERAGE")
    status = (
        "PAPER_0U_FULL_ELIGIBLE_CATALOG_PLAN_ONLY" if full_coverage else
        "BLOCK_NO_ELIGIBLE_UPCOMING_EVENTS" if not eligible else
        "BLOCK_INSUFFICIENT_CREDITS_FOR_COMPLETE_CATALOG"
    )
    report = {
        "schema": "sportsedge-oddsapi-quota-plan-v1",
        "state": status,
        "source_event_manifest_filename": Path(manifest).name,
        "source_event_original_sha256": meta["original_raw_sha256"],
        "source_event_catalog_sha256": meta["catalog_sha256"],
        "sport": meta["sport"],
        "planning_at_utc": current.isoformat(),
        "catalog_captured_at_utc": catalog_created.isoformat(),
        "catalog_event_denominator": len(rows),
        "eligible_upcoming_events": len(eligible),
        "planned_events": len(eligible) if full_coverage else 0,
        "not_planned_events": len(rows) - (len(eligible) if full_coverage else 0),
        "requested_markets": list(markets),
        "requested_bookmakers": list(bookmakers),
        "estimated_credits_per_snapshot": cost_per_snapshot,
        "estimated_credits_per_event_take_plus_close": cost_per_event,
        "estimated_credits_needed": needed,
        "operator_reported_credits_remaining": credits_remaining,
        "operator_reserved_credits": reserve_credits,
        "operator_available_credits_for_plan": available,
        "actual_provider_charge_not_verified": True,
        "no_scheduler_or_network_calls_created": True,
        "no_events_selected_on_model_edge_or_outcome": True,
        "no_provider_original_book_quote_authentication": True,
        "official_counted": 0,
        "approved_stake_u": 0,
        "events": rows,
    }
    payload = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    _write_private(destination, payload)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_event_manifest", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--credits-remaining", type=int, required=True)
    p.add_argument("--reserve-credits", type=int, default=0)
    p.add_argument("--markets", nargs="+", default=["h2h","spreads","totals"])
    p.add_argument("--bookmakers", nargs="+", default=["draftkings","fanduel"])
    p.add_argument("--max-catalog-age-seconds", type=int, default=3600)
    a = p.parse_args(argv)
    result = build_plan(
        a.private_event_manifest, a.output,
        credits_remaining=a.credits_remaining, reserve_credits=a.reserve_credits,
        markets=tuple(a.markets), bookmakers=tuple(a.bookmakers),
        max_catalog_age_seconds=a.max_catalog_age_seconds,
    )
    print(json.dumps({k:result[k] for k in (
        "state","sport","catalog_event_denominator","eligible_upcoming_events",
        "planned_events","estimated_credits_needed",
        "operator_available_credits_for_plan","official_counted")}, sort_keys=True))


if __name__ == "__main__":
    main()
