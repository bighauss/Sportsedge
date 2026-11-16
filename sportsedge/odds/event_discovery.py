"""Private, authorized, no-odds-quota event ID discovery for The Odds API v4.

Only GET /sports/{sport}/events. Archives original bytes/hash + private CSV catalog.
No odds/book authenticity, bet selection, automatic scheduling or paid data.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from sportsedge.odds.free_odds_aggregator_intake import (
    BASE, EVENT_RE, KEY_RE, SPORTS, _secure_open, private_archive_root,
    strict_json, utc,
)
from sportsedge.odds.the_odds_api_clv_export import _remove_owned, _write_private

MAX_BYTES = 4_000_000
MAX_EVENTS = 5000
COLS = ("sport","source_event_id","home_team","away_team","kickoff_utc",
        "captured_at_utc","capture_state","suggested_close_capture_utc")


def clock(value):
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("DISCOVERY_CLOCK_MUST_BE_UTC")
    return value.astimezone(timezone.utc)


def discover_events(sport, private_dir, *, key=None, opener=None, now=None):
    if sport not in SPORTS:
        raise ValueError("SPORT_NOT_ALLOWED")
    root = private_archive_root(private_dir)  # Before any HTTP or quota use.
    api_key = key if key is not None else os.environ.get("SPORTSEDGE_ODDS_API_KEY")
    if not isinstance(api_key, str) or not KEY_RE.fullmatch(api_key):
        raise ValueError("USER_API_KEY_MISSING_OR_UNSAFE")
    clock(now)
    safe_url = BASE + SPORTS[sport] + "/events"
    request = Request(safe_url + "?" + urlencode({"apiKey": api_key,"dateFormat":"iso"}),
                      headers={"Accept":"application/json",
                               "User-Agent":"SportsEdge-UserAuthorized-Research/1.0"})
    try:
        with (opener or _secure_open)(request,timeout=25) as response:
            if hasattr(response,"geturl") and response.geturl() != request.full_url:
                raise ValueError("DISCOVERY_REDIRECT_REFUSED")
            if hasattr(response,"status") and response.status != 200:
                raise ValueError("DISCOVERY_UNEXPECTED_HTTP_STATUS")
            raw=response.read(MAX_BYTES+1)
            headers=response.headers
    except HTTPError as exc:
        raise ValueError("DISCOVERY_HTTP_ERROR_CODE:"+str(exc.code)) from None
    except (URLError,OSError):
        raise ValueError("DISCOVERY_TRANSPORT_FAILED") from None
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError("DISCOVERY_RESPONSE_EMPTY_OR_OVERSIZE")
    if api_key.encode("utf-8") in raw:
        raise ValueError("DISCOVERY_RESPONSE_ECHOED_API_KEY")
    try:
        data=strict_json(raw)
    except (UnicodeError,json.JSONDecodeError):
        raise ValueError("DISCOVERY_INVALID_JSON") from None
    if not isinstance(data,list) or len(data)>MAX_EVENTS:
        raise ValueError("DISCOVERY_EXPECTED_BOUNDED_EVENT_LIST")
    captured=clock(now)
    records=[]
    seen=set()
    for ev in data:
        if not isinstance(ev,dict) or ev.get("sport_key") != SPORTS[sport]:
            raise ValueError("DISCOVERY_EVENT_SPORT_MISMATCH")
        ident=ev.get("id")
        if not isinstance(ident,str) or not EVENT_RE.fullmatch(ident):
            raise ValueError("DISCOVERY_PROVIDER_EVENT_ID_INVALID")
        if ident in seen:
            raise ValueError("DISCOVERY_DUPLICATE_PROVIDER_EVENT_ID")
        seen.add(ident)
        home,away=ev.get("home_team"),ev.get("away_team")
        if (not isinstance(home,str) or not home.strip() or
            not isinstance(away,str) or not away.strip() or home.strip()==away.strip()):
            raise ValueError("DISCOVERY_EVENT_TEAMS_INVALID")
        try:
            kickoff=utc(ev.get("commence_time"))
        except ValueError:
            raise ValueError("DISCOVERY_EVENT_START_TIMESTAMP_INVALID") from None
        pregame=kickoff>captured
        records.append({
            "sport":sport,"source_event_id":ident,
            "home_team":home.strip(),"away_team":away.strip(),
            "kickoff_utc":kickoff.isoformat(),"captured_at_utc":captured.isoformat(),
            "capture_state":"UPCOMING_PREGAME" if pregame else "ALREADY_STARTED_NO_PREGAME",
            "suggested_close_capture_utc":(kickoff-timedelta(minutes=5)).isoformat() if pregame else "",
        })
    records.sort(key=lambda r:(r["kickoff_utc"],r["source_event_id"]))
    buf=StringIO()
    writer=csv.DictWriter(buf,fieldnames=COLS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    catalog=buf.getvalue().encode("utf-8")
    digest=sha256(raw).hexdigest()
    stem="events_"+sport+"_"+captured.strftime("%Y%m%dT%H%M%S%fZ")+"_"+digest[:16]
    original_name=stem+".json"
    catalog_name=stem+".catalog.csv"
    manifest_name=stem+".manifest.json"
    server_date=None
    value=headers.get("Date") if headers is not None else None
    if value:
        try:
            server_date=parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError):
            server_date=None
    def quota_header(name):
        value=headers.get(name) if headers is not None else None
        return value if isinstance(value,str) and value.isdecimal() and len(value)<=12 else None
    manifest={
        "schema":"sportsedge-oddsapi-provider-event-catalog-v1",
        "state":"PAPER_0U_EVENT_DISCOVERY_NOT_ORIGINAL_BOOK_EVIDENCE",
        "sport":sport,"provider":"the-odds-api.com",
        "read_only_endpoint":safe_url,
        "original_raw_filename":original_name,
        "original_raw_sha256":"sha256:"+digest,
        "catalog_filename":catalog_name,
        "catalog_sha256":"sha256:"+sha256(catalog).hexdigest(),
        "captured_at_utc":captured.isoformat(),
        "server_date_claim":server_date,
        "provider_credits_last_claim":quota_header("x-requests-last"),
        "provider_credits_remaining_claim":quota_header("x-requests-remaining"),
        "events_returned":len(records),
        "upcoming_pregame_events":sum(r["capture_state"]=="UPCOMING_PREGAME" for r in records),
        "live_or_started_events":sum(r["capture_state"]!="UPCOMING_PREGAME" for r in records),
        "source_event_ids_provider_claim_only":True,
        "provider_says_events_endpoint_uses_no_odds_credits":True,
        "has_bookmaker_prices":False,
        "bookmakers_independently_authenticated":False,
        "official_counted":0,"approved_stake_u":0,
    }
    created=[]
    try:
        for filename,payload in (
            (original_name,raw),
            (catalog_name,catalog),
            (manifest_name,(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode("utf-8")),
        ):
            created.append(_write_private(root/filename,payload))
    except BaseException:
        for path,identity in reversed(created):
            _remove_owned(path,identity)
        raise
    return {**manifest,"manifest_filename":manifest_name,"events":records}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sport",choices=sorted(SPORTS))
    parser.add_argument("private_dir",type=Path)
    parser.add_argument("--limit",type=int,default=25)
    args=parser.parse_args(argv)
    if not 0<=args.limit<=500:
        parser.error("--limit must be from 0 through 500")
    result=discover_events(args.sport,args.private_dir)
    info={k:result[k] for k in (
        "state","sport","manifest_filename","catalog_filename",
        "original_raw_sha256","events_returned","upcoming_pregame_events",
        "live_or_started_events","provider_credits_last_claim","official_counted","approved_stake_u")}
    info["events"]=result["events"][:args.limit]
    print(json.dumps(info,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
