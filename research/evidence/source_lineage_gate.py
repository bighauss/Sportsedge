"""Research-only claimed source independence check; not provider authentication."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
class Refused(ValueError): pass
REQUIRED={"source_id","upstream_operator_id","aggregator_id","book_id","event_id","market_id","selection_id","opposite_selection_id","line","price","opposite_price","observed_utc","captured_utc","decision_utc","kickoff_utc","raw_sha256","receipt_id","status"}
def utc(s):
    try: t=datetime.fromisoformat(s.replace("Z","+00:00"))
    except (ValueError,AttributeError) as e: raise Refused("INVALID_UTC") from e
    if t.tzinfo is None or t.utcoffset().total_seconds()!=0: raise Refused("UTC_REQUIRED")
    return t.astimezone(timezone.utc)
def number(s,price=False):
    try: n=Decimal(str(s))
    except InvalidOperation as e: raise Refused("INVALID_NUMBER") from e
    if not n.is_finite() or (price and (n!=n.to_integral_value() or not 100<=abs(n)<=100000)): raise Refused("INVALID_NUMBER")
    return str(n.normalize())
def inspect_pair(rows,max_age_seconds=300):
    if type(max_age_seconds)!=int or not 0<max_age_seconds<=300: raise Refused("INVALID_AGE_POLICY")
    if not isinstance(rows,list) or len(rows)!=2: raise Refused("TWO_RECEIPTS_REQUIRED")
    ids=[]
    for q in rows:
        if not isinstance(q,dict) or set(q)!=REQUIRED or any(not isinstance(v,str) or not v.strip() for v in q.values()): raise Refused("RECEIPT_SCHEMA_INVALID")
        if q["status"]!="OPEN": raise Refused("MARKET_NOT_OPEN")
        if len(q["raw_sha256"])!=64 or any(c not in "0123456789abcdef" for c in q["raw_sha256"]): raise Refused("INVALID_SHA256")
        number(q["price"],True);number(q["opposite_price"],True)
        observed,captured,decision,kickoff=[utc(q[k]) for k in ("observed_utc","captured_utc","decision_utc","kickoff_utc")]
        if not observed<=captured<=decision<kickoff: raise Refused("LOOKAHEAD_OR_LIVE")
        if (decision-observed).total_seconds()>max_age_seconds: raise Refused("STALE_QUOTE")
        if q["selection_id"]==q["opposite_selection_id"]: raise Refused("INVALID_OPPOSITE")
        ids.append((q["event_id"],q["market_id"],q["selection_id"],q["opposite_selection_id"],number(q["line"]),kickoff))
    if ids[0]!=ids[1]: raise Refused("MARKET_IDENTITY_MISMATCH")
    for k in ("source_id","upstream_operator_id","aggregator_id","book_id","receipt_id"):
        if rows[0][k].strip().casefold()==rows[1][k].strip().casefold(): raise Refused("NOT_INDEPENDENT_"+k.upper())
    return {"status":"PAPER_SOURCE_CLAIMS_ONLY","authenticated":False,"approved_stake_u":0,"warning":"Declared operator and aggregator IDs require independent attestation"}
