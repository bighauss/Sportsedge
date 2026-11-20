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
import argparse
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
from .bestbook_slate_overlay import apply_bestbook_public_reference
from .weather_slate_overlay import attach_weather_references, load_triplets
from .projection_slate_audit import attach_independent_projection_audit

# These sports are schedule/inventory ONLY. The five-sport pricing kernel does
# not price NHL/PGA markets and must never be invoked for them.
SCHEDULE_ONLY_SPORTS = frozenset({"NHL", "PGA"})
SCHEDULE_SPORTS = SPORTS | SCHEDULE_ONLY_SPORTS

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
    # Inventory labels are NOT supported/wagerable pricing market types.
    "NHL": ("ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PERIOD_MARKET",
            "PLAYER_PROP", "GOALIE_SAVES", "FIRST_GOAL", "SGP", "DFS"),
    "PGA": ("OUTRIGHT", "TOP5", "TOP10", "TOP20", "MAKE_CUT",
            "MISS_CUT", "MATCHUP", "THREE_BALL", "ROUND_LEADER",
            "FIRST_ROUND_LEADER", "ROUND_SCORE", "TOURNAMENT_SCORE",
            "BIRDIES", "BOGEYS", "EAGLES", "HOLE_IN_ONE", "DFS"),
}
ALLOWED_ROOT = frozenset({
    "schema", "slate_id", "slate_date_ct", "sports",
    "expected_events", "event_inputs", "projection_evidence",
})
EXPECTED_KEYS = frozenset({"sport", "event_id", "start_utc"})
INPUT_KEYS = frozenset({"sport", "event_id", "manifest"})


def _exact(obj, keys, label):
    if not isinstance(obj, dict) or set(obj) != keys:
        raise ValueError("INVALID_SLATE_FIELDS:" + label)
    return obj


def _identity(sport, event_id):
    if sport not in SCHEDULE_SPORTS or not isinstance(event_id, str) or not ID.fullmatch(event_id):
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
        if kind=="SGP":
            # This CLI does not have a verified posted DraftKings *parlay*
            # price, correlation model or sportsbook SGP settlement rules.
            # Permit only an explicit inventory placeholder, not a synthetic
            # fake price masquerading as a single-leg PriceReceipt.
            if (period!="FG" or set(m)!={"sport","event_id","kind","period"}
                    or set(item)-{"market","dk_quote","dk_opposite_quote","v21_inputs"}
                    or item.get("dk_quote") is not None
                    or item.get("dk_opposite_quote") is not None
                    or item.get("v21_inputs") not in (None,{})):
                raise ValueError("SGP_INVENTORY_ONLY_NO_SINGLE_LEG_QUOTE")
            if families["SGP"] >= 1:
                # No posted parlay ID or distinct legs exist in an inventory
                # placeholder. Repeating it cannot represent a second offer.
                raise ValueError("DUPLICATE_UNPRICED_SGP_INVENTORY")
            families["SGP"]+=1
            continue
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


def _sgp_unpriced_row(event_key):
    # Not a wager candidate and NOT a v2.1-priced parlay. Preserve visible
    # row count without substituting independent straight-leg EVs for joint.
    return {
        "market": [event_key[0],event_key[1],"SGP","FG"],
        "research_state":"BLOCK",
        "research_reasons":["SGP_REQUIRES_POSTED_JOINT_QUOTE_AND_CALIBRATED_EVENTS"],
        "guard_state":"BLOCK",
        "guard_reasons":["SGP_NOT_ADMITTED_TO_SINGLE_LEG_V21_GATE"],
        "v21_status":"NOT_RUN_NO_PROVABLE_SGP_OFFER",
        "raw_ev_unverified":None,
        "blended_ev_unverified":None,
        "official_counted":0,"approved_stake_u":0,"card":None,
    }


def _simple_reason(exc):
    # Never expose private filenames, original provider URLs, raw player
    # records, credentials, model fields or source payloads in public logs.
    msg = str(exc).split(":",1)[0].strip()
    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}",msg):
        return msg
    return "EVENT_INPUT_CONTRACT_INVALID"


def run_slate(manifest, *, now=None, bestbook_report=None, bestbook_event_map=None, weather_triplets=None):
    if not isinstance(manifest, dict):
        raise ValueError("INVALID_SLATE_FIELDS:root")
    _exact({k:v for k,v in manifest.items() if k!="projection_evidence"},
           ALLOWED_ROOT-{"projection_evidence"}, "root")
    if manifest["schema"] != SCHEMA:
        raise ValueError("UNSUPPORTED_SLATE_SCHEMA")
    slate_id=manifest["slate_id"]
    if not isinstance(slate_id,str) or not ID.fullmatch(slate_id):
        raise ValueError("INVALID_SLATE_ID")
    day=_date(manifest["slate_date_ct"])
    sports=manifest["sports"]
    if (not isinstance(sports,list) or not sports
            or any(s not in SCHEDULE_SPORTS for s in sports)
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
        if key[0] in SCHEDULE_ONLY_SPORTS:
            raise ValueError("SCHEDULE_ONLY_SPORT_HAS_NO_VALIDATED_PRICER")
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
            "no_capture":0,"no_market_rows":0,"sgp_only_games":0,
            "sgp_inventory_rows":0,"after_start":0,"priced_research":0,
            "blocked_research":0,"model_input_failures":0,
            "schedule_only_unpriced_events":0}
    for key,start in sorted(registry.items(),key=lambda x:(x[1],x[0])):
        sport,event_id=key
        present=parsed.get(key,Counter())
        family_matrix={}
        for family in FAMILIES[sport]:
            count=present.get(family,0)
            family_matrix[family]={
                "submitted_research_candidates":count,
                "status":("NO_SUPPORTED_PRICING_ADAPTER" if sport in SCHEDULE_ONLY_SPORTS
                          else "RESEARCH_INPUT_RECEIVED_NOT_AUTHENTICATED" if count
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
        if sport in SCHEDULE_ONLY_SPORTS:
            event_out.update(status="BLOCK",
                             reasons=["NO_SUPPORTED_NHL_OR_PGA_PRICING_KERNEL",
                                      "SCHEDULE_AND_MARKET_OFFERING_NOT_AUTHENTICATED"])
            totals["schedule_only_unpriced_events"]+=1
        elif key not in inputs:
            event_out.update(status="BLOCK", reasons=["SCHEDULE_EVENT_CAPTURE_MISSING"])
            totals["no_capture"]+=1
        elif when >= start:
            event_out.update(status="BLOCK", reasons=["SCHEDULE_EVENT_STARTED"])
            totals["after_start"]+=1
        elif not inputs[key]["markets"]:
            event_out.update(
                status="BLOCK",
                reasons=["NO_MARKETS_SUBMITTED_OR_OFFERED_UNVERIFIED"],
                research_rows=[],
            )
            totals["no_market_rows"]+=1
        else:
            try:
                submitted=inputs[key]["markets"]
                single_leg=[x for x in submitted
                            if x["market"]["kind"]!="SGP"]
                sgp_count=len(submitted)-len(single_leg)
                totals["sgp_inventory_rows"]+=sgp_count
                if not single_leg:
                    rows=[_sgp_unpriced_row(key) for x in submitted]
                    event_out.update(
                        status="BLOCK",
                        reasons=["ONLY_UNPRICED_SGP_INVENTORY_SUBMITTED"],
                        research_rows=rows,
                        research_candidates=len(rows),
                        research_priced=0,
                        research_blocked=len(rows),
                    )
                    totals["sgp_only_games"]+=1
                    totals["blocked_research"]+=len(rows)
                    events.append(event_out)
                    continue
                priced_manifest={**inputs[key],"markets":single_leg}
                result=run_from_manifest(priced_manifest)
                if result.get("sport")!=sport or result.get("event_id")!=event_id:
                    raise ValueError("RESEARCH_OUTPUT_EVENT_NOT_REGISTERED")
                if result.get("approved_stake_u")!=0 or result.get("official_counted")!=0 or result.get("card") is not None:
                    raise ValueError("RESEARCH_ENGINE_TRIED_TO_PROMOTE_CARD")
                priced_rows=result.get("rows",[])
                if len(priced_rows)!=len(single_leg):
                    raise ValueError("SILENTLY_DROPPED_RESEARCH_MARKET")
                priced_iter=iter(priced_rows)
                rows=[_sgp_unpriced_row(key)
                      if item["market"]["kind"]=="SGP" else next(priced_iter)
                      for item in submitted]
                if len(rows)!=len(submitted):
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
                    research_model_sha256=result.get("model_sha256"),
                    research_feature_sha256=result.get("feature_sha256"),
                    model_method=result.get("model_projection_method"),
                    pit_status=result.get("pit_file_manifest_status"),
                    player_projection_producer=result.get("player_projection_producer"),
                    player_projection_builder_census=result.get("player_projection_builder_census"),
                    research_rows=rows,
                    sgp_joint_pricing_certified=False,
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
                else "SCHEDULE_ONLY_NO_PRICING_KERNEL" if sport in SCHEDULE_ONLY_SPORTS
                else "RESEARCH_ONLY_NOT_RELEASE_CLEARED",
        }
    result={
        "schema":SCHEMA,
        "slate_id":slate_id,"slate_date_ct":day.isoformat(),
        "state":"BLOCK_OFFICIAL_RELEASE_RESEARCH_ONLY",
        "generated_at_utc":when.isoformat(),
        "source_authentication_verified":False,
        "schedule_independently_authenticated":False,
        "full_market_inventory_independently_authenticated":False,
        "prospective_probability_calibration_verified":False,
        "verified_bookmaker_clv":False,
        "five_sports":sport_summary,  # legacy compatibility key
        "sport_coverage":sport_summary,
        "research_pricing_sports":sorted(SPORTS),
        "schedule_only_sports":sorted(SCHEDULE_ONLY_SPORTS),
        "counts":totals,
        "events":events,
        "approved_stake_u":0, "official_counted":0, "card":None,
        "issue10_release_certified":False,
    }
    # Keep the public-price comparison OUT of all model/quote/risk input paths.
    # An explicitly bound homepage reference is for display and missing-data
    # audit only. Its best-book labels cannot become original DK receipts.
    if bestbook_report is not None:
        if bestbook_event_map is None:
            raise ValueError("BESTBOOK_EVENT_IDENTITY_MAPPING_REQUIRED")
        result=apply_bestbook_public_reference(
            result,bestbook_report,bestbook_event_map,now_utc=when)
    elif bestbook_event_map is not None:
        raise ValueError("BESTBOOK_PUBLIC_PAGE_REPORT_REQUIRED")
    # The same no-promotion boundary applies to weather. It is attached
    # only after every existing price/model/risk decision has finished.
    if weather_triplets is not None:
        result=attach_weather_references(result,weather_triplets,now_utc=when)
    # Pure post-pricing annotation: original research signals remain PAPER/0u.
    # Absent independent receipts are BLOCKED individually; never infer our
    # probabilities from the DK price or a third-party forecast.
    return attach_independent_projection_audit(
        result, manifest.get("projection_evidence", []))


def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slate_input",help="private original RUN IT slate JSON")
    parser.add_argument("slate_output",help="private create-only RUN IT result JSON")
    parser.add_argument("--bestbook-page",help="private owner-permitted original public BestBook HTML/text")
    parser.add_argument("--bestbook-event-map",help="private exact page-label to existing event ID map JSON")
    parser.add_argument("--weather-triplet",nargs=3,action="append",
                        metavar=("ORIGINAL_REQUEST","RAW_RESPONSE","ORIGINAL_RECEIPT"),
                        help="private original Open-Meteo request, raw response and receipt; repeat per event")
    opts=parser.parse_args(argv)
    source,dest=Path(opts.slate_input),Path(opts.slate_output)
    if bool(opts.bestbook_page)!=bool(opts.bestbook_event_map):
        raise ValueError("BESTBOOK_SOURCE_AND_EXPLICIT_EVENT_MAP_REQUIRED_TOGETHER")
    # The input may contain private quote IDs and source metadata. Do not
    # read a manifest or emit an output inside the public checkout, regardless
    # of the process working directory or symlinked path spelling.
    repo_root=Path(__file__).resolve().parents[2]
    source_resolved, dest_resolved=source.resolve(),dest.resolve()
    if source_resolved==repo_root or repo_root in source_resolved.parents:
        raise ValueError("RESEARCH_SLATE_INPUT_MUST_BE_PRIVATE")
    if dest_resolved==repo_root or repo_root in dest_resolved.parents:
        raise ValueError("RESEARCH_SLATE_OUTPUT_MUST_BE_PRIVATE")
    if source.resolve()==dest.resolve():
        raise ValueError("REFUSE_SLATE_INPUT_OVERWRITE")
    original=source.read_bytes()
    if not original or len(original)>MAX_MANIFEST_BYTES:
        raise ValueError("INVALID_SLATE_INPUT_SIZE")
    request=json.loads(original.decode("utf-8"),
                       object_pairs_hook=_unique_json_keys,
                       parse_constant=_deny_nonfinite_json)
    bestbook_report=None
    bestbook_map=None
    if opts.bestbook_page:
        # Only read owner-private original source bytes, never a scraped login.
        # Neither the public quote nor its best-book label is authenticated.
        from sportsedge.odds.bestbook_public_reference import (
            _read_source as read_private_public_page,
            analyze as analyze_bestbook_homepage,
        )
        original_bestbook=read_private_public_page(opts.bestbook_page)
        bestbook_report=analyze_bestbook_homepage(original_bestbook)
        raw_map=read_private_public_page(opts.bestbook_event_map)
        bestbook_map=json.loads(raw_map.decode("utf-8"),
                                object_pairs_hook=_unique_json_keys,
                                parse_constant=_deny_nonfinite_json)
    weather_triplets=load_triplets(opts.weather_triplet) if opts.weather_triplet else None
    result=run_slate(request,bestbook_report=bestbook_report,
                     bestbook_event_map=bestbook_map,
                     weather_triplets=weather_triplets)
    result["input_sha256"]="sha256:"+sha256(original).hexdigest()
    # Source/output privacy already checked against the resolved repository root.
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
