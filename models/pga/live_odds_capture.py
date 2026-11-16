"""Opt-in live PGA major-outright capture. No requests without user-supplied key."""
import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from odds_provider_adapter import MAJORS, parse_outrights

BASE="https://api.the-odds-api.com/v4/sports"

def capture(sport_key, *, api_key=None, regions="us", opener=urlopen,
            clock=None, timeout=15):
    """Return raw provider bytes + digest and parsed rows; never log API key.

    External provider authentication and pregame availability still require audit.
    """
    if sport_key not in MAJORS:
        raise ValueError("UNSUPPORTED_GOLF_MARKET")
    key=api_key if api_key is not None else os.environ.get("THE_ODDS_API_KEY")
    if not isinstance(key,str) or not key.strip():
        raise ValueError("ODDS_API_KEY_REQUIRED")
    if regions not in ("us", "us2", "uk", "eu", "au"):
        raise ValueError("INVALID_REGION")
    if not isinstance(timeout,(int,float)) or timeout<=0 or timeout>60:
        raise ValueError("INVALID_TIMEOUT")
    params=urlencode({"apiKey":key,"regions":regions,"markets":"outrights",
                      "oddsFormat":"decimal","dateFormat":"iso"})
    url=f"{BASE}/{sport_key}/odds?{params}"
    # API key is in the request URL by provider contract: never print or persist URL.
    req=Request(url,headers={"Accept":"application/json","User-Agent":"SportsEdge-PGA/1"})
    with opener(req,timeout=timeout) as response:
        raw=response.read(8_000_001)
    if len(raw)>8_000_000:
        raise ValueError("RESPONSE_TOO_LARGE")
    payload=json.loads(raw)
    if not isinstance(payload,list):
        raise ValueError("INVALID_PROVIDER_PAYLOAD")
    now=clock() if clock else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset().total_seconds()!=0:
        raise ValueError("UTC_CLOCK_REQUIRED")
    captured=now.isoformat(timespec="seconds").replace("+00:00","Z")
    parsed=parse_outrights(payload,sport_key=sport_key,captured_utc=captured,asof_utc=captured)
    return {"source_sha256":hashlib.sha256(raw).hexdigest(),"raw_bytes":raw,
            "captured_utc":captured,"provider":"the-odds-api",
            "parsed":parsed,"status":"UNVERIFIED_PLAYER_MAPPING_PAPER_0U"}
