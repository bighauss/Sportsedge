"""Opt-in DataGolf v1/v2 evidence capture; no credentials or network at import."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE="https://feeds.datagolf.com"
V1={"player_list":"/get-player-list",
    "field_updates":"/field-updates",
    "schedule":"/get-schedule",
    "raw_event_list":"/historical-raw-data/event-list",
    "rounds":"/historical-raw-data/rounds",
    "odds_event_list":"/historical-odds/event-list",
    "historical_outrights":"/historical-odds/outrights"}
V2={"tournaments":"/v2/tournaments",
    "rankings":"/v2/current-rankings"}
SAFE_PARAMS={"tour","season","upcoming_only","event_id","year","market",
             "book","odds_format","file_format"}
ALLOWED_MARKETS={"win","top_5","top_10","top_20","make_cut","mc"}
ALLOWED_BOOKS={"draftkings","pinnacle","fanduel","betmgm","caesars",
               "bet365","circa","betonline","bovada"}

def capture(endpoint, *, params=None, api_key=None, opener=urlopen,
            clock=None, timeout=15):
    """Return raw byte receipt, not verified point-in-time historic forecasts.

    Query-string key is required by DataGolf. Never log the request URL.
    """
    paths={**V1,**V2}
    if endpoint not in paths:
        raise ValueError("UNKNOWN_DATAGOLF_ENDPOINT")
    key=api_key if api_key is not None else os.environ.get("DATAGOLF_API_KEY")
    if not isinstance(key,str) or not key.strip():
        raise ValueError("DATAGOLF_API_KEY_REQUIRED")
    params={} if params is None else dict(params)
    if any(k not in SAFE_PARAMS for k in params):
        raise ValueError("UNSUPPORTED_PARAMETER")
    if endpoint=="historical_outrights":
        if params.get("market") not in ALLOWED_MARKETS or params.get("book") not in ALLOWED_BOOKS:
            raise ValueError("MARKET_AND_BOOK_REQUIRED")
    if endpoint=="rounds" and not all(k in params for k in ("tour","event_id","year")):
        raise ValueError("ROUND_EVENT_YEAR_REQUIRED")
    if any(not isinstance(v,(str,int)) or isinstance(v,bool) or
           not re.fullmatch(r"[A-Za-z0-9_-]{1,50}",str(v)) for v in params.values()):
        raise ValueError("INVALID_PARAMETER_VALUE")
    if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not 0<timeout<=60:
        raise ValueError("INVALID_TIMEOUT")
    query=urlencode({**params,"file_format":"json","key":key})
    req=Request(BASE+paths[endpoint]+"?"+query,
                headers={"Accept":"application/json","User-Agent":"SportsEdge-PGA/1"})
    with opener(req,timeout=timeout) as response:
        raw=response.read(8_000_001)
    if len(raw)>8_000_000:
        raise ValueError("RESPONSE_TOO_LARGE")
    parsed=json.loads(raw)
    if not isinstance(parsed,(dict,list)):
        raise ValueError("INVALID_PROVIDER_PAYLOAD")
    if isinstance(parsed,dict) and any(k in parsed for k in ("error","errors")):
        raise ValueError("PROVIDER_ERROR")
    now=clock() if clock else datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset().total_seconds()!=0:
        raise ValueError("UTC_CLOCK_REQUIRED")
    return {"endpoint":endpoint,"params":params,
            "captured_utc":now.isoformat(timespec="seconds").replace("+00:00","Z"),
            "source_sha256":hashlib.sha256(raw).hexdigest(),
            "raw_bytes":raw,"payload":parsed,
            "status":"PROVIDER_RESPONSE_UNVERIFIED_PAPER_0U"}
