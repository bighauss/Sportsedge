"""Permissioned The Odds API v4 intake, research-only and fail-closed.

The $0 API key must be obtained by the USER. An authenticated aggregator
response does not independently authenticate original sportsbook offers.
Never emits picks, fair odds, CLV, validation certificates or wagers.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import json
import math
import os
import ssl
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener

# Exact provider-advertised v4 sport keys. PGA Majors outrights use a different
# multiway settlement contract and are not normalized by this game-lines intake.
SPORTS = {
    "NFL": "americanfootball_nfl",
    "CFB": "americanfootball_ncaaf",
    "CBB": "basketball_ncaab",
    "NBA": "basketball_nba",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
}
BOOKS = {"draftkings", "fanduel", "betmgm", "betrivers", "pinnacle", "caesars"}
KEY_RE = re.compile(r"[A-Za-z0-9_.:-]{8,256}\Z")
MARKET_RE = re.compile(r"[a-z][a-z0-9_]{1,55}\Z")
EVENT_RE = re.compile(r"[a-zA-Z0-9_-]{8,100}\Z")
BASE = "https://api.the-odds-api.com/v4/sports/"
MAX_BYTES=20_000_000
REPOSITORY_ROOT=Path(__file__).resolve().parents[2]


def private_archive_root(destination):
    """Reject both syntactic and symlink-resolved public checkout paths.

    Validate BEFORE a credit-consuming provider request, independent of CWD.
    """
    lexical=Path(os.path.abspath(destination))
    resolved=lexical.resolve()
    if (lexical==REPOSITORY_ROOT or REPOSITORY_ROOT in lexical.parents
            or resolved==REPOSITORY_ROOT or REPOSITORY_ROOT in resolved.parents):
        raise ValueError("RAW_ODDS_ARCHIVE_MUST_BE_OUTSIDE_PUBLIC_REPO")
    return resolved


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The Odds API uses ?apiKey=...; never follow a redirect to a
        # different host which could receive this credential.
        raise ValueError("AGGREGATOR_REDIRECT_REFUSED")


def _secure_open(request, timeout):
    opener=build_opener(_RejectRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    return opener.open(request, timeout=timeout)



def utc(s):
    if not isinstance(s,str):raise ValueError("INVALID_PROVIDER_TIME")
    try:d=datetime.fromisoformat(s.replace("Z","+00:00"))
    except ValueError as exc:raise ValueError("INVALID_PROVIDER_TIME") from exc
    if d.tzinfo is None or d.utcoffset().total_seconds()!=0:
        raise ValueError("NON_UTC_PROVIDER_TIME")
    return d.astimezone(timezone.utc)


def strict_json(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError("DUPLICATE_PROVIDER_JSON_KEY")
            out[k]=v
        return out
    def nonfinite(text):
        raise ValueError("NONFINITE_PROVIDER_JSON_NUMBER")
    def finite_float(text):
        value=float(text)
        if not math.isfinite(value):
            raise ValueError("NONFINITE_PROVIDER_JSON_NUMBER")
        return value
    return json.loads(raw.decode("utf-8"),object_pairs_hook=pairs,
                      parse_constant=nonfinite,parse_float=finite_float)


def capture(sport, destination, *, key=None, event_id=None, markets=("h2h","spreads","totals"),
            bookmakers=("draftkings","fanduel"), opener=None, audit_only=False):
    if sport not in SPORTS:raise ValueError("SPORT_NOT_ALLOWED")
    # The GitHub Actions authorized read-only provider workflow already
    # supplies ODDS_API_KEY. Accept that as a documented, lower-priority
    # alias for private capture, but NEVER fall back when an operator
    # explicitly supplied a key (even an invalid/empty one).
    api_key = (key if key is not None else
               (os.environ.get("SPORTSEDGE_ODDS_API_KEY") or
                os.environ.get("ODDS_API_KEY")))
    if not api_key or not KEY_RE.fullmatch(api_key):
        raise ValueError("USER_API_KEY_MISSING_OR_UNSAFE")
    if event_id is not None and not EVENT_RE.fullmatch(event_id):
        raise ValueError("EVENT_ID_INVALID")
    if not markets or len(set(markets))!=len(markets) or any(not MARKET_RE.fullmatch(x) for x in markets):
        raise ValueError("MARKETS_INVALID_OR_DUPLICATED")
    if not bookmakers or len(set(bookmakers))!=len(bookmakers) or any(x not in BOOKS for x in bookmakers):
        raise ValueError("BOOKS_INVALID_OR_DUPLICATED")
    # Reject public checkout output BEFORE any outbound API request or quota use.
    root=private_archive_root(destination)
    # Only documented read-only v4 endpoints. No guessed or restricted DK URL.
    path = SPORTS[sport]+("/events/"+quote(event_id,safe="")+"/odds" if event_id else "/odds")
    safe_url=BASE+path
    params={"apiKey":api_key,"regions":"us","markets":",".join(markets),
            "bookmakers":",".join(bookmakers),"oddsFormat":"american","dateFormat":"iso"}
    req=Request(safe_url+"?"+urlencode(params),headers={"Accept":"application/json",
                "User-Agent":"SportsEdge-UserAuthorized-Research/1.0"})
    try:
        with (opener or _secure_open)(req,timeout=25) as response:
            # Also reject a redirected final URL from custom, authorized transports.
            if hasattr(response,"geturl") and response.geturl()!=req.full_url:
                raise ValueError("AGGREGATOR_REDIRECT_REFUSED")
            if hasattr(response,"status") and response.status != 200:
                raise ValueError("AGGREGATOR_UNEXPECTED_HTTP_STATUS")
            raw=response.read(MAX_BYTES+1)
            headers=response.headers
    except HTTPError as err:
        # Never propagate an HTTPError string: it may contain apiKey=SECRET.
        raise ValueError("AGGREGATOR_HTTP_ERROR_CODE:"+str(err.code)) from None
    except (URLError,OSError):
        raise ValueError("AGGREGATOR_TRANSPORT_FAILED") from None
    if not raw or len(raw)>MAX_BYTES:raise ValueError("AGGREGATOR_RESPONSE_EMPTY_OR_OVERSIZE")
    if api_key.encode("utf-8") in raw:raise ValueError("AGGREGATOR_ECHOED_SECRET_IN_RESPONSE")
    try:payload=strict_json(raw)
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError("AGGREGATOR_JSON_INVALID") from None
    events=[payload] if isinstance(payload,dict) and event_id else payload
    if not isinstance(events,list) or any(not isinstance(x,dict) for x in events):
        raise ValueError("AGGREGATOR_EXPECTED_EVENTS_LIST")
    now=datetime.now(timezone.utc)
    if event_id is not None and (len(events)!=1 or events[0].get("id")!=event_id):
        raise ValueError("EVENT_ID_RESPONSE_MISMATCH")
    event_count=0;quoted=0;book_count=0;blocked=0;stale_or_missing=0;families=set();seen=set()
    for ev in events:
        if not isinstance(ev.get("id"),str) or not ev.get("home_team") or not ev.get("away_team"):
            raise ValueError("EVENT_ID_OR_TEAMS_MISSING")
        start=utc(ev.get("commence_time"))
        is_live=start<=now
        if ev.get("sport_key")!=SPORTS[sport]:raise ValueError("SPORT_KEY_MISMATCH")
        if not isinstance(ev.get("bookmakers"),list):raise ValueError("MARKET_LIST_MISSING")
        event_count+=1
        for book in ev["bookmakers"]:
            if not isinstance(book,dict) or book.get("key") not in bookmakers:
                raise ValueError("UNEXPECTED_BOOKMAKER")
            if not isinstance(book.get("markets"),list):raise ValueError("INVALID_BOOK_MARKETS")
            book_count+=1
            for m in book["markets"]:
                if not isinstance(m,dict) or m.get("key") not in markets or not isinstance(m.get("outcomes"),list):
                    raise ValueError("UNEXPECTED_MARKET_OR_OUTCOME_SCHEMA")
                update=m.get("last_update") or book.get("last_update")
                last_update=utc(update) if update is not None else None
                if last_update is not None and last_update>now:
                    raise ValueError("FUTURE_AGGREGATOR_MARKET_TIMESTAMP")
                families.add(m['key'])
                for o in m['outcomes']:
                    if not isinstance(o,dict) or not isinstance(o.get("name"),str):
                        raise ValueError("INVALID_AGGREGATOR_OUTCOME")
                    odds=o.get('price')
                    if isinstance(odds,bool) or not isinstance(odds,int) or abs(odds)<100 or abs(odds)>1000000:
                        raise ValueError("INVALID_AGGREGATOR_AMERICAN_ODDS")
                    point=o.get('point')
                    if point is not None and (
                        isinstance(point,bool) or not isinstance(point,(int,float))
                        or not math.isfinite(point)
                    ):
                        raise ValueError("INVALID_AGGREGATOR_POINT")
                    identity=(ev['id'],book['key'],m['key'],o['name'],o.get('description'),point)
                    if identity in seen:raise ValueError("DUPLICATE_AGGREGATOR_OUTCOME")
                    seen.add(identity)
                    quoted+=1
                    if is_live:blocked+=1
                    if last_update is None or (now-last_update).total_seconds()>300:
                        stale_or_missing+=1
    digest="sha256:"+sha256(raw).hexdigest()
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    base="aggregator_"+sport+"_"+now.strftime("%Y%m%dT%H%M%S%fZ")+"_"+digest[7:23]
    archive=root/(base+".json")
    flags=os.O_EXCL|os.O_CREAT|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(archive,flags,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    # No key, no secret URL, no inferred upstream bookmaker authenticity.
    response_date=headers.get('Date') if headers is not None else None
    if response_date:
        try: response_date=parsedate_to_datetime(response_date).astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError):response_date=None
    summary={"schema":"sportsedge-oddsapi-aggregator-raw-v1",
       "state":("PAPER_0U_AGGREGATOR_NOT_UPSTREAM_BOOK_AUTHENTICATED"
                if quoted else "BLOCK_EMPTY_AGGREGATOR_RESPONSE"),
       "sport":sport,"provider":"the-odds-api.com","read_only_endpoint":safe_url,
       "source_transport_api_credential_used":True,
       "source_upstream_book_authenticated":False,
       "bookmakers_are_independently_authenticated":False,
       "quote_time_is_aggregator_claim_only":True,
       "captured_utc":now.isoformat(),"http_server_date_claim":response_date,
       "provider_request_credits_last":headers.get('x-requests-last') if headers else None,
       "provider_remaining_credits":headers.get('x-requests-remaining') if headers else None,
       "original_raw_sha256":digest,"original_bytes":len(raw),
       "raw_filename":archive.name,"events_returned":event_count,
       "book_entries":book_count,"outcomes_returned":quoted,
       "live_poststart_outcomes_blocked":blocked,
       "stale_or_missing_aggregator_market_timestamp_outcomes":stale_or_missing,
       "requested_markets":list(markets),"returned_market_keys":sorted(families),
       "missing_requested_market_keys_unverified":sorted(set(markets)-families),
       "requested_books":list(bookmakers),"requested_event_id":event_id,
       "original_source_chain_certified":False,
       "matched_clv_triplets":0,"official_counted":0,"approved_stake_u":0}
    if audit_only:
        # NCAA billing has not been adjudicated. Neither card loader accepts
        # an audit manifest as a sport-scoped input.
        summary["schema"] = "sportsedge-ncaa-odds-audit-v1"
        summary["observed_sport"] = summary.pop("sport")
    manifest=root/(base+".manifest.json")
    manifest_fd=os.open(manifest,flags,0o600)
    with os.fdopen(manifest_fd,'w',encoding='utf-8') as f:
        json.dump(summary,f,indent=2,sort_keys=True,allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sport',choices=sorted(SPORTS))
    p.add_argument('private_dir')
    p.add_argument('--event-id')
    p.add_argument('--markets',nargs='+',default=['h2h','spreads','totals'])
    p.add_argument('--bookmakers',nargs='+',default=['draftkings','fanduel'])
    a=p.parse_args(argv)
    info=capture(a.sport,a.private_dir,event_id=a.event_id,
                 markets=tuple(a.markets),bookmakers=tuple(a.bookmakers))
    print(json.dumps({k:info[k] for k in ('state','sport','events_returned',
        'outcomes_returned','original_raw_sha256','official_counted','approved_stake_u')},sort_keys=True))

if __name__=='__main__': main()
