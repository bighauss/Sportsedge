"""Read-only provider payload parser. Network retrieval and credentials are separate.

The Odds API golf coverage: Majors outright only; never infer DK availability.
"""
import math
from datetime import datetime

MAJORS = {"golf_masters_tournament_winner",
          "golf_pga_championship_winner", "golf_us_open_winner",
          "golf_the_open_championship_winner"}

def _dt(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED")
    return datetime.fromisoformat(s[:-1] + "+00:00")

def parse_outrights(payload, *, sport_key, captured_utc, asof_utc):
    """Parse actual odds JSON; retain blocked quotes; never fabricate an offer."""
    if sport_key not in MAJORS:
        raise ValueError("UNSUPPORTED_GOLF_MARKET")
    captured = _dt(captured_utc)
    asof = _dt(asof_utc)
    if captured > asof:
        raise ValueError("CAPTURE_AFTER_ASOF")
    if not isinstance(payload, list):
        raise ValueError("INVALID_PAYLOAD")
    rows, blocked = [], []
    for event in payload:
        if not isinstance(event, dict):
            blocked.append({"reason": "INVALID_EVENT"});continue
        try:
            start = _dt(event["commence_time"])
            if captured >= start:
                blocked.append({"event":event.get("id"),"reason":"POST_START"});continue
            for book in event.get("bookmakers",[]):
                for market in book.get("markets",[]):
                    if market.get("key") != "outrights":
                        continue
                    updated = _dt(market["last_update"])
                    if updated > captured:
                        blocked.append({"event":event.get("id"),"reason":"QUOTE_AFTER_CAPTURE"});continue
                    for outcome in market.get("outcomes",[]):
                        price=outcome.get("price")
                        if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<=1:
                            blocked.append({"event":event.get("id"),"reason":"INVALID_DECIMAL_ODDS"});continue
                        if not isinstance(outcome.get("name"),str) or not outcome["name"].strip():
                            blocked.append({"event":event.get("id"),"reason":"MISSING_GOLFER"});continue
                        rows.append({"event_id":event["id"],"sport_key":sport_key,
                                     "golfer_name_unmapped":outcome["name"],
                                     "bookmaker":book["key"],"market":"outright",
                                     "decimal_odds":price,"implied_probability":1/price,
                                     "captured_utc":captured_utc,"quote_updated_utc":market["last_update"],
                                     "status":"UNVERIFIED_ID_AND_PROVIDER"})
        except (KeyError,TypeError,ValueError,OverflowError):
            blocked.append({"event":event.get("id"),"reason":"INVALID_PROVIDER_STRUCTURE"})
    return {"rows":rows,"blocked":blocked,"status":"PAPER_0U_NO_MODEL_EDGE"}
