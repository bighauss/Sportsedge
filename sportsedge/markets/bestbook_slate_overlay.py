"""RUN IT BestBook research overlay: separate from price, EV and staking.

Only data already parsed from a permitted original BestBook public homepage is
accepted. A caller must explicitly map each displayed game label to an existing
SportsEdge scheduled event and its two displayed team abbreviations. Nothing
in this module creates DK PriceReceipts, a validated edge, or certified CLV.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import re

SCHEMA = "sportsedge-bestbook-public-reference-v1"
MAP_SCHEMA = "sportsedge-bestbook-slate-identity-map-v1"
SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
TEAM = re.compile(r"^[A-Z]{2,4}$")
FAMILIES = ("ML", "SPREAD", "TOTAL")


class BestBookSlateError(ValueError):
    pass


def _utc(value, field):
    if not isinstance(value, str) or not (
            value.endswith("Z") or value.endswith("+00:00")):
        raise BestBookSlateError("EXACT_UTC_OFFSET_REQUIRED:" + field)
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        raise BestBookSlateError("INVALID_UTC:" + field) from None
    if parsed.utcoffset() != timedelta(0):
        raise BestBookSlateError("NON_UTC:" + field)
    return parsed


def _line(value):
    try:
        x = Decimal(str(value))
        if not x.is_finite():
            return None
        return x
    except (ValueError, InvalidOperation, TypeError):
        return None


def _mapping(mapping):
    if not isinstance(mapping, dict) or set(mapping) != {"schema", "events"}:
        raise BestBookSlateError("INVALID_IDENTITY_MAP_FIELDS")
    if mapping["schema"] != MAP_SCHEMA:
        raise BestBookSlateError("UNSUPPORTED_IDENTITY_MAP_SCHEMA")
    entries = mapping["events"]
    if not isinstance(entries, list) or len(entries) > 500:
        raise BestBookSlateError("INVALID_OR_OVERSIZED_IDENTITY_MAP")
    by_public = {}
    by_event = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {
                "sport", "event_id", "public_event_label",
                "away_selection", "home_selection"}:
            raise BestBookSlateError("INVALID_EVENT_MAP_ROW")
        sport, event_id = item["sport"], item["event_id"]
        label = item["public_event_label"]
        if (sport != "NFL" or not isinstance(event_id, str)
                or not isinstance(label, str) or not 0 < len(label) <= 180):
            raise BestBookSlateError("UNSUPPORTED_OR_EMPTY_PUBLIC_EVENT_MAP")
        away, home = item["away_selection"], item["home_selection"]
        if (not isinstance(away, str) or not isinstance(home, str)
                or not TEAM.fullmatch(away) or not TEAM.fullmatch(home)
                or away == home):
            raise BestBookSlateError("INVALID_OR_DUPLICATE_TEAM_ALIAS")
        if label in by_public or (sport, event_id) in by_event:
            raise BestBookSlateError("DUPLICATE_MANUAL_EVENT_MAPPING")
        by_public[label] = item
        by_event[(sport, event_id)] = item
    return by_public, by_event


def _report(report):
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise BestBookSlateError("INVALID_BESTBOOK_PUBLIC_REPORT")
    if (report.get("status") != "PAPER_0U_PUBLIC_PAGE_RESEARCH_ONLY"
            or report.get("source_account_authenticated") is not False
            or report.get("gate_a_closed") is not False
            or report.get("gate_d_clv_closed") is not False
            or report.get("provider_original_quote_timestamps_verified") is not False
            or report.get("approved_stake_u") != 0
            or report.get("official_counted") != 0):
        raise BestBookSlateError("BESTBOOK_REPORT_MUST_REMAIN_UNVERIFIED_0U")
    if not isinstance(report.get("source_page_sha256"), str) or not SHA.fullmatch(
            report["source_page_sha256"]):
        raise BestBookSlateError("BESTBOOK_ORIGINAL_SOURCE_HASH_REQUIRED")
    if report.get("sports_scope_of_parser") != ["NFL"]:
        raise BestBookSlateError("UNVERIFIED_ADDITIONAL_SPORTS_IN_PAGE")
    if not isinstance(report.get("rows"), list) or len(report["rows"]) > 10000:
        raise BestBookSlateError("INVALID_PUBLIC_ROW_POPULATION")
    if not isinstance(report.get("missing_or_blocked_public_rows"), list):
        raise BestBookSlateError("MISSING_PUBLIC_GAP_CENSUS")
    for row in report["rows"]:
        if (not isinstance(row, dict)
                or row.get("approved_stake_u") != 0
                or row.get("official_counted") != 0
                or row.get("provider_original_quote_utc") is not None
                or row.get("book_direct_response_sha256") is not None
                or row.get("quote_status") not in (
                    "PUBLIC_PAGE_REFERENCE_UNVERIFIED", "BLOCKED_DUPLICATE_PUBLIC_OUTCOME")):
            raise BestBookSlateError("MALFORMED_OR_PROMOTED_PUBLIC_ROW")
        if (not isinstance(row.get("event_label"), str)
                or row.get("market_family") not in FAMILIES
                or not isinstance(row.get("selection_label"), str)
                or type(row.get("price_american")) is not int
                or not 100 <= abs(row["price_american"]) <= 100000
                or not isinstance(row.get("displayed_book_label"), str)):
            raise BestBookSlateError("PUBLIC_MARKET_IDENTITY_INVALID")


def _reference_match(market, map_item, offers):
    if not isinstance(market, (list, tuple)) or len(market) != 10:
        return None, "RESEARCH_MARKET_IDENTITY_UNKNOWN"
    sport, event_id, family, period, selection, line, *_ = market
    if sport != map_item["sport"] or event_id != map_item["event_id"]:
        return None, "RESEARCH_EVENT_IDENTITY_MISMATCH"
    if family not in FAMILIES or period != "FG":
        return None, "PUBLIC_HOMEPAGE_MARKET_NOT_CAPTURED"
    if family in ("ML", "SPREAD"):
        label = map_item["home_selection"] if selection == "HOME" else (
            map_item["away_selection"] if selection == "AWAY" else None)
    else:
        label = selection
    if label is None:
        return None, "INVALID_RESEARCH_SELECTION"
    same_side = [
        r for r in offers if r["market_family"] == family and
        r["selection_label"].upper() == label and
        r["quote_status"] == "PUBLIC_PAGE_REFERENCE_UNVERIFIED"
    ]
    if family == "ML":
        same_side = [r for r in same_side if line == ""]
    else:
        same_side = [r for r in same_side if _line(r["line"]) == _line(line)]
    if len(same_side) != 1:
        return None, "NO_UNIQUE_EXACT_PUBLIC_PRICE_REFERENCE"
    r = same_side[0]
    return {
        "displayed_book_label": r["displayed_book_label"],
        "displayed_price_american": r["price_american"],
        "displayed_line": r["line"],
        "market_family": family,
        "source_kind": "BESTBOOK_PUBLIC_BEST_PRICE_NOT_DK_ORIGINAL",
        "external_provider_quote_id": None,
        "provider_publication_utc": None,
        "source_authentication_verified": False,
        "official_counted": 0, "approved_stake_u": 0,
    }, "EXACT_MANUAL_IDENTITY_AND_LINE_REFERENCE_NOT_AUTHENTICATED"


def apply_bestbook_public_reference(slate, report, event_mapping, *, now_utc=None):
    """Return detached seven-sport slate with a strictly supplemental overlay.

    Both sources are local claims. Never alter candidate EV, quote IDs, state,
    risk or model inputs. Exact user mapping is not a verified provider mapping.
    """
    _report(report)
    public, mapped = _mapping(event_mapping)
    if not isinstance(slate, dict) or not isinstance(slate.get("events"), list):
        raise BestBookSlateError("INVALID_RUN_IT_SLATE_RESULT")
    if (slate.get("approved_stake_u") != 0 or slate.get("official_counted") != 0
            or slate.get("card") is not None
            or slate.get("issue10_release_certified") is not False):
        raise BestBookSlateError("RUN_IT_SLATE_NOT_PAPER_0U")
    when = _utc(slate["generated_at_utc"], "slate_generated")
    if now_utc is not None:
        if not isinstance(now_utc, datetime) or now_utc.tzinfo is None or now_utc.utcoffset() != timedelta(0):
            raise BestBookSlateError("NOW_MUST_BE_UTC")
        when = now_utc
    page_time = _utc(report.get("local_page_read_utc"), "bestbook_local_page")
    if page_time > when:
        raise BestBookSlateError("PUBLIC_PAGE_CAPTURE_IN_FUTURE")
    rows = report["rows"]
    labels = {r["event_label"] for r in rows}
    seen = {(e["sport"], e["event_id"]) for e in slate["events"]}
    if len(seen) != len(slate["events"]):
        raise BestBookSlateError("DUPLICATE_SCHEDULE_EVENT_IN_OUTPUT")
    for key in mapped:
        if key not in seen:
            raise BestBookSlateError("MAPPED_EVENT_NOT_ON_RUN_IT_SLATE")
    out = deepcopy(slate)
    totals = {
        "scheduled_events": len(out["events"]), "mapped_nfl_events": len(mapped),
        "public_displayed_quote_rows": len(rows), "matched_candidate_references": 0,
        "stale_or_poststart_mapped_games": 0, "unmapped_public_event_labels": len(labels-set(public)),
    }
    for event in out["events"]:
        key = (event["sport"], event["event_id"])
        mapped_item = mapped.get(key)
        family = event.get("families", {})
        statuses = {family_name: "NOT_CAPTURED_IN_PUBLIC_BESTBOOK_VIEW"
                    for family_name in family}
        overlay = {
            "status": "NO_EXACT_PUBLIC_EVENT_IDENTITY_MAPPING",
            "source": "BESTBOOK_PUBLIC_HOMEPAGE",
            "original_public_page_sha256": report["source_page_sha256"],
            "local_capture_utc": report["local_page_read_utc"],
            "source_original_book_quote_utc": None,
            "source_authenticated": False,
            "event_map_manually_verified_by_operator": False,
            "market_family_coverage": statuses,
            "quoted_references": [], "candidate_comparisons": [],
            "approved_stake_u": 0, "official_counted": 0,
        }
        if event["sport"] != "NFL":
            overlay["status"] = "SPORT_NOT_PRESENT_ON_PUBLIC_BESTBOOK_HOMEPAGE"
        elif mapped_item:
            label = mapped_item["public_event_label"]
            selected = [r for r in rows if r["event_label"] == label]
            if not selected:
                overlay["status"] = "MAPPED_LABEL_NOT_ON_PUBLIC_HOMEPAGE"
            else:
                start = _utc(event["start_utc"].replace("+00:00", "Z"), "scheduled_start")
                delayed = (when - page_time).total_seconds() > 300
                poststart = page_time >= start or when >= start
                if delayed or poststart:
                    overlay["status"] = ("PUBLIC_REFERENCE_POST_START_OR_LIVE"
                                         if poststart else "PUBLIC_REFERENCE_STALE_GT_300S")
                    totals["stale_or_poststart_mapped_games"] += 1
                else:
                    overlay["status"] = "PAPER_PUBLIC_REFERENCE_MATCHED_IDENTITY_UNVERIFIED"
                overlay["quoted_references"] = [
                    {**r, "reference_is_actionable": False}
                    for r in selected
                ]
                for family_name in FAMILIES:
                    if family_name in statuses and any(
                            r["market_family"] == family_name and
                            r["quote_status"] == "PUBLIC_PAGE_REFERENCE_UNVERIFIED"
                            for r in selected):
                        statuses[family_name] = "PUBLIC_RESEARCH_BEST_PRICE_NOT_BOOK_ORIGINAL"
                for candidate in event.get("research_rows", []):
                    market = candidate.get("market")
                    ref, reason = _reference_match(market, mapped_item, selected)
                    if delayed or poststart:
                        ref = None
                        reason = ("PUBLIC_REFERENCE_POST_START_OR_LIVE" if poststart
                                  else "PUBLIC_REFERENCE_STALE_GT_300S")
                    overlay["candidate_comparisons"].append({
                        "market": market, "reference": ref,
                        "reason": reason, "approved_stake_u": 0,
                        "official_counted": 0,
                    })
                    totals["matched_candidate_references"] += ref is not None
        event["bestbook_public_research"] = overlay
    out["bestbook_public_research"] = {
        "status": "SUPPLEMENTAL_ONLY_NOT_BOOK_ORIGINAL",
        "source_original_page_sha256": report["source_page_sha256"],
        "local_capture_utc": report["local_page_read_utc"],
        "published_quote_timestamps_verified": False,
        "book_independent_origins_verified": False,
        "manual_mapping_is_provider_verified": False,
        "unmapped_public_event_labels": sorted(labels-set(public)),
        "counts": totals, "approved_stake_u": 0, "official_counted": 0,
        "never_used_as_dk_quote_or_fair_model_probability": True,
    }
    return out
