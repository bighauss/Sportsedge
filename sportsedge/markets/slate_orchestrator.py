"""Five-sport, full-slate, missing-market-aware SportsEdge research runner.

Every expected scheduled event is accounted for. Missing captures or entire
sports are VISIBLE BLOCKs, never silently treated as "no +EV opportunities".
Only actual submitted model/market rows enter the existing one-event research
pricer and v2.1 gate. This module cannot establish sportsbook availability,
independent source authenticity, real profit, or issue official picks.

Usage: python -m sportsedge.markets.slate_orchestrator PRIVATE_SLATE.json
       PRIVATE_CREATE_ONLY_OUTPUT.json

Required source manifests and quote receipts follow sportsedge.markets.cli.
Private outputs must be kept outside the public GitHub source checkout.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import re
import sys

from .cli import (
    run_from_manifest, _iso, _unique_json_keys,
    _deny_nonfinite_json, MAX_MANIFEST_BYTES
)
from .allmarkets_research import SPORTS, PERIODS

SCHEMA = "sportsedge-five-sport-slate-research-v1"
CENTRAL = ZoneInfo("America/Chicago")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
BASE_FAMILIES = ("ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP")
FOOTBALL_EXTRA = ("ATTD", "FIRST_TD", "TD_2PLUS", "SGP")
BASKETBALL_EXTRA = ("FIRST_BASKET", "SGP")
BASEBALL_EXTRA = ("NRFI", "YRFI", "SGP")
FAMILIES = {
    "NFL": BASE_FAMILIES + FOOTBALL_EXTRA,
    "CFB": BASE_FAMILIES + FOOTBALL_EXTRA,
    "CBB": BASE_FAMILIES + BASKETBALL_EXTRA,
    "NBA": BASE_FAMILIES + BASKETBALL_EXTRA,
    "MLB": BASE_FAMILIES + BASEBALL_EXTRA,
}
ALLOWED_ROOT = frozenset({
    "schema", "slate_id", "slate_date_ct", "sports",
    "expected_events", "event_inputs",
})
EXPECTED_KEYS = frozenset({"sport", "event_id", "start_utc"})
INPUT_KEYS = frozenset({"sport", "event_id", "manifest"})


def _exact(obj, keys, label):
    if not isinstance(obj, dict) or set(obj) != keys:
        raise ValueError("INVALID_SLATE_FIELDS:" + label)
    return obj


def _identity(sport, event_id):
    if sport not in SPORTS or not isinstance(event_id, str) or not ID.fullmatch(event_id):
        raise ValueError("INVALID_SPORT_OR_EVENT_ID")
    return (sport, event_id)


def _date(s):
    from datetime import date
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError("INVALID_SLATE_DATE")
    try:
        d = date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError("INVALID_SLATE_DATE") from exc
    if d.isoformat() != s:
        raise ValueError("INVALID_SLATE_DATE")
    return d


def _manifest_identity(data):
    if not isinstance(data, dict):
        raise ValueError("NON_OBJECT_EVENT_MANIFEST")
    if ("projection" in data) == ("projection_ref" in data):
        raise ValueError("EXACTLY_ONE_EVENT_MODEL_PROJECTION_REQUIRED")
    p = data.get("projection", data.get("projection_ref"))
    if not isinstance(p, dict) or "sport" not in p or "event_id" not in p:
        raise ValueError("EVENT_PROJECTION_IDENTITY_MISSING")
    return _identity(p["sport"], p["event_id"]), _iso(p["asof_utc"])


def _quote_integrity(data, expected_key, expected_start, used_quotes):
    if not isinstance(data.get("markets"), list):
        raise ValueError("MARKETS_MISSING_OR_NOT_ARRAY")
    if len(data["markets"]) > 5000:
        raise ValueError("TOO_MANY_MARKETS_PER_GAME")
    # Count supported research *families*, not presumed markets available
    # at DraftKings. The latter require authentic provider market inventories.
    families=Counter()
    for item in data["markets"]:
        if not isinstance(item, dict) or not isinstance(item.get("market"), dict):
            raise ValueError("MALFORMED_MARKET_CANDIDATE")
        m=item["market"]
        if _identity(m.get("sport"),m.get("event_id")) != expected_key:
            raise ValueError("MARKET_REGISTERED_EVENT_MISMATCH")
        kind=m.get("kind")
        period=m.get("period")
        if kind not in FAMILIES[expected_key[0]] and kind != "SGP":
            raise ValueError("MARKET_FAMILY_OUTSIDE_SPORT")
        if period not in PERIODS:
            raise ValueError("MARKET_PERIOD_UNKNOWN")
        families[kind]+=1
        for side in ("dk_quote","dk_opposite_quote"):
            q=item.get(side)
            if q is None:
                continue
            if not isinstance(q, dict) or not isinstance(q.get("market"), dict):
                raise ValueError("MALFORMED_QUOTE")
            qm=q["market"]
            if _identity(qm.get("sport"), qm.get("event_id")) != expected_key:
                raise ValueError("QUOTE_EVENT_MISMATCH")
            if _iso(q["event_start_utc"]) != expected_start:
                raise ValueError("QUOTE_START_DIFFERS_FROM_SCHEDULE")
            for field in ("book","provider_id","quote_id"):
                if not isinstance(q.get(field), str) or not q[field].strip():
                    raise ValueError("QUOTE_ORIGINAL_SOURCE_ID_MISSING")
            quote_key=(q["book"].casefold(),q["provider_id"].casefold(),
                       q["quote_id"].casefold())
            if quote_key in used_quotes:
                if used_quotes[quote_key] != expected_key:
                    raise ValueError("PROVIDER_QUOTE_ID_REUSED_ACROSS_GAMES")
                raise ValueError("PROVIDER_QUOTE_ID_REUSED_WITHIN_SLATE")
            used_quotes[quote_key]=expected_key
    return families


def _simple_reason(exc):
    # Never expose private filenames, original provider URLs, raw player
    # records, credentials, model fields or source payloads in public logs.
    msg = str(exc).split(":",1)[0].strip()
    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}",msg):
        return msg
    return "EVENT_INPUT_CONTRACT_INVALID"


def run_slate(manifest, *, now=None):
    _exact(manifest, ALLOWED_ROOT, "root")
    if manifest["schema"] != SCHEMA:
        raise ValueError("UNSUPPORTED_SLATE_SCHEMA")
    slate_id=manifest["slate_id"]
    if not isinstance(slate_id,str) or not ID.fullmatch(slate_id):
        raise ValueError("INVALID_SLATE_ID")
    day=_date(manifest["slate_date_ct"])
    sports=manifest["sports"]
    if (not isinstance(sports,list) or not sports
            or any(s not in SPORTS for s in sports)
            or len(set(sports))!=len(sports)):
        raise ValueError("INVALID_REQUESTED_SPORTS")
    expected=manifest["expected_events"]
    supplied=manifest["event_inputs"]
    if (not isinstance(expected,list) or not isinstance(supplied,list)
            or len(expected)>500 or len(supplied)>500):
        raise ValueError("INVALID_OR_OVERSIZED_SLATE")
    clock=(datetime.now(timezone.utc) if now is None else now)
    if clock.tzinfo is None or clock.utcoffset().total_seconds()!=0:
        raise ValueError("SLATE_CLOCK_MUST_BE_UTC")
    when=clock.astimezone(timezone.utc)
    registry={}
    for row in expected:
        _exact(row, EXPECTED_KEYS, "expected_event")
        key=_identity(row["sport"],row["event_id"])
        if row["sport"] not in sports:
            raise ValueError("EVENT_SPORT_NOT_REQUESTED")
        if key in registry:
            raise ValueError("DUPLICATED_SCHEDULE_EVENT")
        start=_iso(row["start_utc"])
        if start.astimezone(CENTRAL).date()!=day:
            raise ValueError("EVENT_START_NOT_ON_CENTRAL_SLATE_DATE")
        registry[key]=start
    inputs={}
    for row in supplied:
        _exact(row, INPUT_KEYS, "event_input")
        key=_identity(row["sport"],row["event_id"])
        if key not in registry:
            raise ValueError("UNSCHEDULED_EVENT_INPUT")
        if key in inputs:
            raise ValueError("DUPLICATED_EVENT_INPUT")
        inputs[key]=row["manifest"]
    # Validate all source IDs before entering any market pricer. A reused
    # provider quote across two events blocks the entire research import.
    used_quotes={}
    parsed={}
    for key,data in inputs.items():
        projection_key,asof=_manifest_identity(data)
        if projection_key!=key:
            raise ValueError("MODEL_EVENT_MISMATCH_WITH_SCHEDULE")
        if asof >= registry[key]:
            raise ValueError("MODEL_FEATURE_ASOF_AFTER_EVENT_START")
        parsed[key]=_quote_integrity(data,key,registry[key],used_quotes)
    events=[]
    totals={"expected":len(registry),"inputs":len(inputs),
            "no_capture":0,"after_start":0,"priced_research":0,
            "blocked_research":0,"model_input_failures":0}
    for key,start in sorted(registry.items(),key=lambda x:(x[1],x[0])):
        sport,event_id=key
        present=parsed.get(key,Counter())
        family_matrix={}
        for family in FAMILIES[sport]:
            count=present.get(family,0)
            family_matrix[family]={
                "submitted_research_candidates":count,
                "status":("RESEARCH_INPUT_RECEIVED_NOT_AUTHENTICATED" if count
                          else "NOT_SUBMITTED_OR_NOT_OFFERED_UNVERIFIED"),
                "official_counted":0,
            }
        event_out={
            "sport":sport, "event_id":event_id,
            "start_utc":start.isoformat(), "families":family_matrix,
            "research_candidates":0,"research_priced":0,
            "research_blocked":0,"official_counted":0,
            "approved_stake_u":0,"card":None,
        }
        if key not in inputs:
            event_out.update(status="BLOCK", reasons=["SCHEDULE_EVENT_CAPTURE_MISSING"])
            totals["no_capture"]+=1
        elif when >= start:
            event_out.update(status="BLOCK", reasons=["SCHEDULE_EVENT_STARTED"])
            totals["after_start"]+=1
        else:
            try:
                result=run_from_manifest(inputs[key])
                if result.get("sport")!=sport or result.get("event_id")!=event_id:
                    raise ValueError("RESEARCH_OUTPUT_EVENT_NOT_REGISTERED")
                if result.get("approved_stake_u")!=0 or result.get("official_counted")!=0 or result.get("card") is not None:
                    raise ValueError("RESEARCH_ENGINE_TRIED_TO_PROMOTE_CARD")
                rows=result.get("rows",[])
                if len(rows)!=len(inputs[key]["markets"]):
                    raise ValueError("SILENTLY_DROPPED_RESEARCH_MARKET")
                event_out["research_candidates"]=len(rows)
                event_out["research_priced"]=sum(r["research_state"]=="PAPER_0U" for r in rows)
                event_out["research_blocked"]=len(rows)-event_out["research_priced"]
                totals["priced_research"]+=event_out["research_priced"]
                totals["blocked_research"]+=event_out["research_blocked"]
                event_out.update(
                    status="PAPER_0U_RESEARCH_ONLY",
                    reasons=["QUOTES_AND_MODEL_NOT_INDEPENDENTLY_AUTHENTICATED",
                             "V21_AND_ISSUE10_RELEASE_GATES_STILL_OPEN"],
                    model_method=result.get("model_projection_method"),
                    pit_status=result.get("pit_file_manifest_status"),
                    research_rows=rows,
                )
            except (ValueError, KeyError, TypeError, OSError) as exc:
                totals["model_input_failures"]+=1
                event_out.update(status="BLOCK",
                                 reasons=[_simple_reason(exc)])
        events.append(event_out)
    sport_summary={}
    for sport in sports:
        entries=[e for e in events if e["sport"]==sport]
        sport_summary[sport]={
            "expected_games":len(entries),
            "submitted_games":sum(e["event_id"] in {
                k[1] for k in inputs if k[0]==sport} for e in entries),
            "research_processed_games":sum(e["status"]=="PAPER_0U_RESEARCH_ONLY" for e in entries),
            "status":"NO_AUTHENTICATED_SCHEDULE_EVIDENCE" if not entries
                else "RESEARCH_ONLY_NOT_RELEASE_CLEARED",
        }
    return {
        "schema":SCHEMA,
        "slate_id":slate_id,"slate_date_ct":day.isoformat(),
        "state":"BLOCK_OFFICIAL_RELEASE_RESEARCH_ONLY",
        "generated_at_utc":when.isoformat(),
        "source_authentication_verified":False,
        "schedule_independently_authenticated":False,
        "full_market_inventory_independently_authenticated":False,
        "prospective_probability_calibration_verified":False,
        "verified_bookmaker_clv":False,
        "five_sports":sport_summary,
        "counts":totals,
        "events":events,
        "approved_stake_u":0, "official_counted":0, "card":None,
        "issue10_release_certified":False,
    }


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=2:
        raise SystemExit("Usage: python -m sportsedge.markets.slate_orchestrator PRIVATE_INPUT.json PRIVATE_OUTPUT.json")
    source,dest=map(Path,args)
    if source.resolve()==dest.resolve():
        raise ValueError("REFUSE_SLATE_INPUT_OVERWRITE")
    original=source.read_bytes()
    if not original or len(original)>MAX_MANIFEST_BYTES:
        raise ValueError("INVALID_SLATE_INPUT_SIZE")
    request=json.loads(original.decode("utf-8"),
                       object_pairs_hook=_unique_json_keys,
                       parse_constant=_deny_nonfinite_json)
    result=run_slate(request)
    result["input_sha256"]="sha256:"+sha256(original).hexdigest()
    # Source/model/price references are private. Do not write into public repo.
    root=Path.cwd().resolve()
    if root==dest.resolve() or root in dest.resolve().parents:
        raise ValueError("RESEARCH_SLATE_OUTPUT_MUST_BE_PRIVATE")
    payload=(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n").encode("utf-8")
    fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(payload);f.flush();os.fsync(f.fileno())
    except Exception:
        dest.unlink(missing_ok=True);raise
    print(json.dumps({
        "status":result["state"],"expected":result["counts"]["expected"],
        "no_capture":result["counts"]["no_capture"],
        "blocked_research":result["counts"]["blocked_research"],
        "official_counted":0,"approved_stake_u":0
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
