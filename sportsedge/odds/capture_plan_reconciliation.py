"""Offline full-slate TAKE/CLOSE source-to-normalized quote coverage audit.

Never consumes an API credit, takes a wager, authenticates the upstream
bookmakers, changes model history or infers a missing quote. Required input is
a private all-eligible event plan, plus actual separately archived original
provider response manifests and corresponding normalized quote CSVs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import timedelta
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path

from ledger.historical_clv_bridge import FIELDS, Blocked, utc
from sportsedge.odds.free_odds_aggregator_intake import (
    private_archive_root, strict_json,
)
from sportsedge.odds.planned_capture_guard import guard_plan
from sportsedge.odds.the_odds_api_clv_export import (
    convert, load_evidence, _write_private,
)

MAX_SOURCE_BYTES = 10_000_000
MAX_QUOTE_BYTES = 20_000_000


class ReconciliationBlocked(ValueError):
    pass


def _file(path: Path, limit=MAX_SOURCE_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ReconciliationBlocked("SOURCE_FILE_NOT_REGULAR_OR_MISSING")
    if path.stat().st_size == 0 or path.stat().st_size > limit:
        raise ReconciliationBlocked("SOURCE_FILE_EMPTY_OR_OVERSIZE")
    return path.read_bytes()


def _json(path: Path) -> dict:
    try:
        raw = _file(path)
        data = strict_json(raw)
    except (ValueError, UnicodeError, json.JSONDecodeError):
        raise ReconciliationBlocked("SOURCE_JSON_MALFORMED") from None
    if not isinstance(data,dict):
        raise ReconciliationBlocked("SOURCE_JSON_NOT_OBJECT")
    return data


def _csv(path: Path) -> list[dict]:
    try:
        raw = _file(path,MAX_QUOTE_BYTES).decode("utf-8-sig")
        reader = csv.DictReader(StringIO(raw),restkey="__EXTRA__",strict=True)
        if reader.fieldnames != list(FIELDS):
            raise ReconciliationBlocked("NORMALIZED_CSV_HEADER_MISMATCH")
        rows=list(reader)
    except (UnicodeError, csv.Error):
        raise ReconciliationBlocked("NORMALIZED_CSV_MALFORMED") from None
    if any(None in r or "__EXTRA__" in r or any(v is None for v in r.values()) for r in rows):
        raise ReconciliationBlocked("NORMALIZED_CSV_ROW_SHAPE_INVALID")
    return rows


def _check_snapshot(manifest: Path, role: str, expected: dict, markets: list, books: list):
    try:
        m, events, captured, digest = load_evidence(manifest)
    except (ValueError, UnicodeError, KeyError, OSError):
        return "BLOCK_ORIGINAL_HASH_OR_SCHEMA", None
    if (m.get("sport")!=expected["sport"] or
        m.get("requested_event_id")!=expected["source_event_id"] or
        m.get("requested_markets")!=markets or
        m.get("requested_books")!=books or
        len(events)!=1 or events[0].get("id")!=expected["source_event_id"]):
        return "BLOCK_ORIGINAL_EVENT_OR_REQUEST_MISMATCH", None
    try:
        start=utc(events[0]["commence_time"])
    except (KeyError,TypeError,ValueError):
        return "BLOCK_ORIGINAL_START_TIME_INVALID", None
    if start.isoformat()!=expected["kickoff_utc"]:
        return "BLOCK_CHANGED_PROVIDER_KICKOFF", None
    if role=="CLOSE":
        if not timedelta(0)<start-captured<=timedelta(minutes=10):
            return "BLOCK_CLOSE_OUTSIDE_T_MINUS_TEN", None
    elif not captured < start-timedelta(minutes=10):
        return "BLOCK_TAKE_TOO_LATE", None
    stem=manifest.name[:-len(".manifest.json")]
    suffix=".take.csv" if role=="TAKE" else ".close.csv"
    path=manifest.with_name(stem+suffix)
    sidecar=path.with_name(path.name+".audit.json")
    if not path.is_file() or not sidecar.is_file() or path.is_symlink() or sidecar.is_symlink():
        return "BLOCK_MISSING_NORMALIZED_CSV_OR_AUDIT", None
    try:
        audit=_json(sidecar)
        actual=_csv(path)
        normalized_raw=_file(path,MAX_QUOTE_BYTES)
        expected_rows, regenerated=convert(manifest,"TAKE" if role=="TAKE" else "HISTORY")
    except (ValueError, OSError, KeyError, UnicodeError):
        return "BLOCK_NORMALIZED_OR_PROVIDER_REPLAY_INVALID", None
    if (audit.get("schema")!="sportsedge-oddsapi-to-clv-archive-v1" or
        audit.get("phase")!=("TAKE" if role=="TAKE" else "HISTORY") or
        audit.get("original_raw_sha256")!="sha256:"+digest or
        audit.get("normalized_csv_sha256")!="sha256:"+sha256(normalized_raw).hexdigest() or
        audit.get("rows_generated")!=len(actual) or
        audit.get("official_counted")!=0 or
        audit.get("approved_stake_u")!=0):
        return "BLOCK_NORMALIZED_AUDIT_PROVENANCE_INVALID", None
    if actual!=expected_rows or len(actual)!=regenerated["rows_generated"]:
        return "BLOCK_NORMALIZED_QUOTES_DISAGREE_WITH_ORIGINAL", None
    if not actual:
        return "BLOCK_NO_TWO_SIDED_QUOTES", None
    return "PAPER_0U_SOURCE_CONSISTENT_CAPTURE", {
        "original_sha256":"sha256:"+digest,
        "normalized_sha256":audit["normalized_csv_sha256"],
        "captured_at_utc":captured.isoformat(),
        "quote_rows":len(actual),
        "source_manifest_filename":manifest.name,
        "normalized_csv_filename":path.name,
    }


def reconcile(plan_path: Path, output_path: Path):
    plan_path=Path(plan_path)
    output_path=Path(output_path)
    archive_root=private_archive_root(plan_path.parent)
    private_archive_root(output_path)
    if plan_path.is_symlink() or not plan_path.is_file():
        raise ReconciliationBlocked("PLAN_NOT_PRIVATE_REGULAR_FILE")
    if output_path.suffix!=".json" or output_path.exists() or output_path.is_symlink():
        raise ReconciliationBlocked("OUTPUT_MUST_BE_NEW_JSON")
    plan=_json(plan_path)
    if not isinstance(plan.get("events"),list):
        raise ReconciliationBlocked("PLAN_EVENT_LIST_MISSING")
    pending=[r for r in plan["events"] if isinstance(r,dict) and
             r.get("plan_status")=="PLANNED_RESEARCH_ONLY"]
    if not pending:
        raise ReconciliationBlocked("NO_APPROVED_ELIGIBLE_EVENTS")
    representative=pending[0]
    # Reuse the full deep validation of original catalog, census and quota,
    # but evaluate at the precommitted TAKE time (replay only, no HTTP).
    checked=guard_plan(plan_path,sport=plan.get("sport"),
                       event_id=representative["source_event_id"],phase="TAKE",
                       markets=tuple(plan.get("requested_markets",[])),
                       bookmakers=tuple(plan.get("requested_bookmakers",[])),
                       now=utc(representative["take_at_utc"]))
    if plan_path.parent.resolve()!=archive_root:
        raise ReconciliationBlocked("PLAN_ARCHIVE_ROOT_INVALID")
    grouped=defaultdict(lambda:{"TAKE":[],"CLOSE":[],"UNLABELED":[]})
    unassigned=[]
    sport=plan["sport"]
    for mpath in sorted(archive_root.glob("aggregator_"+sport+"_*.manifest.json")):
        try:
            record=_json(mpath)
        except ReconciliationBlocked:
            unassigned.append({"manifest_filename":mpath.name,"reason":"INVALID_ORIGIN_MANIFEST"})
            continue
        event_id=record.get("requested_event_id")
        if (event_id not in {r["source_event_id"] for r in pending} or
            record.get("sport")!=sport):
            unassigned.append({"manifest_filename":mpath.name,"reason":"UNPLANNED_EVENT_OR_SPORT"})
            continue
        stem=mpath.name[:-len(".manifest.json")]
        take=mpath.with_name(stem+".take.csv").is_file()
        close=mpath.with_name(stem+".close.csv").is_file()
        if take and close:
            grouped[event_id]["UNLABELED"].append(mpath)
            continue
        if take:
            grouped[event_id]["TAKE"].append(mpath)
        elif close:
            grouped[event_id]["CLOSE"].append(mpath)
        else:
            grouped[event_id]["UNLABELED"].append(mpath)
    results=[]
    status_counts=Counter()
    for expected in plan["events"]:
        row={
            "source_event_id":expected["source_event_id"],
            "sport":sport,
            "kickoff_utc":expected["kickoff_utc"],
            "plan_status":expected["plan_status"],
            "take_status":"NOT_PLANNED",
            "close_status":"NOT_PLANNED",
            "take":None,
            "close":None,
            "unlabeled_original_manifests":[],
        }
        if expected["plan_status"]=="PLANNED_RESEARCH_ONLY":
            matches=grouped[expected["source_event_id"]]
            row["unlabeled_original_manifests"]=[p.name for p in matches["UNLABELED"]]
            for role in ("TAKE","CLOSE"):
                items=matches[role]
                if len(items)==0:
                    status="BLOCK_MISSING_"+role
                    detail=None
                elif len(items)>1:
                    status="BLOCK_DUPLICATE_"+role+"_ALL_COPIES"
                    detail=None
                else:
                    status, detail=_check_snapshot(
                        items[0],role,expected,
                        plan["requested_markets"],plan["requested_bookmakers"])
                row[role.lower()+"_status"]=status
                row[role.lower()]=detail
                status_counts[status]+=1
            if matches["UNLABELED"]:
                status_counts["UNLABELED_OR_DUPLICATE_PHASE_ORIGINAL_MANIFEST"]+=len(matches["UNLABELED"])
        results.append(row)
    full=all(
        row["take_status"]=="PAPER_0U_SOURCE_CONSISTENT_CAPTURE" and
        row["close_status"]=="PAPER_0U_SOURCE_CONSISTENT_CAPTURE"
        for row in results if row["plan_status"]=="PLANNED_RESEARCH_ONLY"
    )
    if unassigned:
        status_counts["UNASSIGNED_OR_INVALID_ORIGINAL_MANIFEST"]+=len(unassigned)
    if any(row["unlabeled_original_manifests"] for row in results):
        full=False
    if unassigned:
        full=False
    output={
        "schema":"sportsedge-prospective-plan-reconciliation-v1",
        "state":"PAPER_0U_ALL_PLAN_CAPTURE_FILES_CONSISTENT" if full
                else "BLOCK_INCOMPLETE_OR_INVALID_PLAN_CAPTURE_COVERAGE",
        "plan_sha256":checked["plan_sha256"],
        "source_plan_file_name":plan_path.name,
        "source_plan_event_denominator":plan["catalog_event_denominator"],
        "planned_event_denominator":plan["planned_events"],
        "reconciled_planned_events":sum(
            r["take_status"]=="PAPER_0U_SOURCE_CONSISTENT_CAPTURE" and
            r["close_status"]=="PAPER_0U_SOURCE_CONSISTENT_CAPTURE"
            for r in results),
        "all_plan_rows_retained":len(results)==plan["catalog_event_denominator"],
        "status_counts":dict(sorted(status_counts.items())),
        "unassigned_original_manifests":unassigned,
        "bookmakers_independently_authenticated":False,
        "valid_actual_wager_receipts":0,
        "matched_actual_clv_bets":0,
        "official_counted":0,
        "approved_stake_u":0,
        "events":results,
    }
    payload=(json.dumps(output,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    _write_private(output_path,payload)
    return output


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args(argv)
    result=reconcile(a.plan,a.output)
    print(json.dumps({k:result[k] for k in (
        "state","source_plan_event_denominator","planned_event_denominator",
        "reconciled_planned_events","official_counted","approved_stake_u")},
        sort_keys=True))


if __name__=="__main__":
    main()
