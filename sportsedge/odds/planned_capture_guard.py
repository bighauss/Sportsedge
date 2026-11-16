"""Fail-closed pre-HTTP guard for OPTIONAL plan-bound prospective odds capture.

Local consistency checks, not provider attestation or live odds evidence.
The guard requires exact source catalog, event, markets, books and intended
phase/time. It NEVER requests provider data or pays any API credit.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import math

from sportsedge.odds.free_odds_aggregator_intake import (
    BOOKS, SPORTS, private_archive_root, strict_json, utc,
)
from sportsedge.odds.quota_capture_plan import (
    ALLOWED_MARKETS, CLOSE_OFFSET, MIN_LEAD, TAKE_OFFSET, load_catalog,
)

MAX_PLAN_BYTES = 10_000_000
TAKE_GRACE_SECONDS = 300


class CapturePlanBlocked(ValueError):
    pass


def _int(x):
    return type(x) is int and x >= 0


def guard_plan(
    plan_path: Path,
    *,
    sport: str,
    event_id: str,
    phase: str,
    markets: tuple[str, ...],
    bookmakers: tuple[str, ...],
    now: datetime | None = None,
):
    """Validate before an API request; return immutable expected event kickoff.

    The plan must live with its source catalog and original provider response.
    A plan's approved state is only research intent; it does not reserve
    provider quota, guarantee pricing, authorize wagers or prove a source.
    """
    p = Path(plan_path)
    if p.is_symlink() or not p.is_file():
        raise CapturePlanBlocked("CAPTURE_PLAN_NOT_REGULAR_PRIVATE_FILE")
    private_archive_root(p)  # Reject checkout even when caller supplies symlink path.
    if p.stat().st_size == 0 or p.stat().st_size > MAX_PLAN_BYTES:
        raise CapturePlanBlocked("CAPTURE_PLAN_EMPTY_OR_OVERSIZE")
    if p.stat().st_mode & 0o077:
        raise CapturePlanBlocked("CAPTURE_PLAN_PERMISSIONS_TOO_OPEN")
    try:
        content = p.read_bytes()
        plan = strict_json(content)
    except (ValueError, UnicodeError):
        raise CapturePlanBlocked("CAPTURE_PLAN_NOT_STRICT_JSON") from None
    if not isinstance(plan, dict) or plan.get("schema") != "sportsedge-oddsapi-quota-plan-v1":
        raise CapturePlanBlocked("CAPTURE_PLAN_SCHEMA_INVALID")
    if (plan.get("state") != "PAPER_0U_FULL_ELIGIBLE_CATALOG_PLAN_ONLY" or
        plan.get("official_counted") != 0 or
        plan.get("approved_stake_u") != 0 or
        plan.get("no_scheduler_or_network_calls_created") is not True):
        raise CapturePlanBlocked("CAPTURE_PLAN_NOT_APPROVED_FOR_RESEARCH")
    if sport not in SPORTS or plan.get("sport") != sport:
        raise CapturePlanBlocked("CAPTURE_PLAN_SPORT_MISMATCH")
    if (phase not in ("TAKE", "CLOSE") or
        not isinstance(event_id, str) or not event_id):
        raise CapturePlanBlocked("CAPTURE_PLAN_PHASE_OR_EVENT_INVALID")
    if (not isinstance(plan.get("requested_markets"),list) or
        plan["requested_markets"] != list(markets) or
        not markets or len(set(markets)) != len(markets) or
        any(x not in ALLOWED_MARKETS for x in markets)):
        raise CapturePlanBlocked("CAPTURE_PLAN_MARKET_SET_MISMATCH")
    if (not isinstance(plan.get("requested_bookmakers"),list) or
        plan["requested_bookmakers"] != list(bookmakers) or
        not bookmakers or len(set(bookmakers)) != len(bookmakers) or
        any(x not in BOOKS for x in bookmakers)):
        raise CapturePlanBlocked("CAPTURE_PLAN_BOOK_SET_MISMATCH")
    name = plan.get("source_event_manifest_filename")
    if (not isinstance(name,str) or not name or Path(name).name != name or
        name in (".","..") or "\\" in name):
        raise CapturePlanBlocked("CAPTURE_PLAN_CATALOG_MANIFEST_PATH_INVALID")
    source = p.parent / name
    if source.is_symlink() or not source.is_file():
        raise CapturePlanBlocked("CAPTURE_PLAN_CATALOG_MANIFEST_MISSING")
    try:
        catalog_meta, original_events, catalog_at = load_catalog(source)
    except ValueError:
        raise CapturePlanBlocked("CAPTURE_PLAN_CATALOG_INTEGRITY_INVALID") from None
    if (plan.get("source_event_original_sha256") != catalog_meta["original_raw_sha256"] or
        plan.get("source_event_catalog_sha256") != catalog_meta["catalog_sha256"] or
        catalog_meta.get("sport") != sport or
        plan.get("catalog_captured_at_utc") != catalog_at.isoformat()):
        raise CapturePlanBlocked("CAPTURE_PLAN_CATALOG_PROVENANCE_MISMATCH")
    try:
        planned_at = utc(plan["planning_at_utc"])
    except (KeyError, ValueError, TypeError):
        raise CapturePlanBlocked("CAPTURE_PLAN_CLOCK_INVALID") from None
    if not catalog_at <= planned_at:
        raise CapturePlanBlocked("CAPTURE_PLAN_CREATED_BEFORE_CATALOG")
    actual_now = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(actual_now,datetime) or actual_now.tzinfo is None or
        actual_now.utcoffset() != timedelta(0)):
        raise CapturePlanBlocked("CAPTURE_PLAN_NOW_NOT_UTC")
    actual_now = actual_now.astimezone(timezone.utc)
    if actual_now < planned_at:
        raise CapturePlanBlocked("CAPTURE_PLAN_FROM_FUTURE")
    original = {row["source_event_id"]: (row,kickoff)
                for row,kickoff in original_events}
    plan_rows = plan.get("events")
    if not isinstance(plan_rows,list) or len(plan_rows)!=len(original):
        raise CapturePlanBlocked("CAPTURE_PLAN_POPULATION_MISMATCH")
    observed_ids=set()
    planned_count=0
    for row in plan_rows:
        if not isinstance(row,dict):
            raise CapturePlanBlocked("CAPTURE_PLAN_ROW_INVALID")
        ident=row.get("source_event_id")
        if not isinstance(ident,str) or ident not in original or ident in observed_ids:
            raise CapturePlanBlocked("CAPTURE_PLAN_DUPLICATE_OR_UNKNOWN_EVENT")
        observed_ids.add(ident)
        original_row,kickoff=original[ident]
        if any(row.get(k)!=original_row[k] for k in ("sport","home_team","away_team","kickoff_utc")):
            raise CapturePlanBlocked("CAPTURE_PLAN_EVENT_IDENTITY_MISMATCH")
        remaining=kickoff-planned_at
        if remaining<=timedelta(0):
            expected="BLOCK_EVENT_ALREADY_STARTED"
        elif remaining<=MIN_LEAD:
            expected="BLOCK_TOO_LATE_FOR_DISTINCT_SNAPSHOTS"
        else:
            expected="PLANNED_RESEARCH_ONLY"
            planned_count+=1
            if (row.get("take_at_utc") != max(planned_at,kickoff-TAKE_OFFSET).isoformat() or
                row.get("close_at_utc") != (kickoff-CLOSE_OFFSET).isoformat()):
                raise CapturePlanBlocked("CAPTURE_PLAN_PHASE_CLOCK_MODIFIED")
        if row.get("plan_status") != expected:
            raise CapturePlanBlocked("CAPTURE_PLAN_EVENT_STATUS_MODIFIED")
    if observed_ids!=set(original):
        raise CapturePlanBlocked("CAPTURE_PLAN_POPULATION_MISMATCH")
    cost_per_snapshot = len(markets)*math.ceil(len(bookmakers)/10)
    per_event=2*cost_per_snapshot
    need=per_event*planned_count
    if (any(not _int(plan.get(k)) for k in (
            "operator_reported_credits_remaining","operator_reserved_credits",
            "operator_available_credits_for_plan","estimated_credits_per_snapshot",
            "estimated_credits_per_event_take_plus_close","estimated_credits_needed",
            "eligible_upcoming_events","planned_events","catalog_event_denominator")) or
        plan["operator_available_credits_for_plan"] !=
            plan["operator_reported_credits_remaining"]-plan["operator_reserved_credits"] or
        plan["operator_reserved_credits"]>plan["operator_reported_credits_remaining"] or
        plan["estimated_credits_per_snapshot"]!=cost_per_snapshot or
        plan["estimated_credits_per_event_take_plus_close"]!=per_event or
        plan["estimated_credits_needed"]!=need or
        plan["eligible_upcoming_events"]!=planned_count or
        plan["planned_events"]!=planned_count or
        plan["catalog_event_denominator"]!=len(original) or
        need>plan["operator_available_credits_for_plan"]):
        raise CapturePlanBlocked("CAPTURE_PLAN_QUOTA_OR_DENOMINATOR_INVALID")
    if not planned_count:
        raise CapturePlanBlocked("CAPTURE_PLAN_HAS_NO_ELIGIBLE_EVENTS")
    matched = next((r for r in plan_rows if r["source_event_id"]==event_id),None)
    if matched is None or matched.get("plan_status")!="PLANNED_RESEARCH_ONLY":
        raise CapturePlanBlocked("CAPTURE_EVENT_NOT_IN_APPROVED_PLAN")
    kickoff=original[event_id][1]
    if phase=="TAKE":
        take_target=utc(matched["take_at_utc"])
        if not take_target<=actual_now<=take_target+timedelta(seconds=TAKE_GRACE_SECONDS):
            raise CapturePlanBlocked("CAPTURE_TAKE_OUTSIDE_PLANNED_WINDOW")
        if not actual_now<kickoff-MIN_LEAD:
            raise CapturePlanBlocked("CAPTURE_TAKE_TOO_LATE_FOR_CLOSE")
    else:
        if not kickoff-timedelta(minutes=10)<=actual_now<kickoff:
            raise CapturePlanBlocked("CAPTURE_CLOSE_OUTSIDE_T_MINUS_TEN")
    return {
        "plan_sha256": "sha256:"+sha256(content).hexdigest(),
        "expected_kickoff_utc": kickoff.isoformat(),
        "plan_event_count":len(original),
        "plan_eligible_events":planned_count,
        "validation_state":"PAPER_0U_PLAN_GUARD_PASSED",
        "official_counted":0,
        "approved_stake_u":0,
    }
