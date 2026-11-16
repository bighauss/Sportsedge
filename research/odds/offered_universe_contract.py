"""Fail-closed offered-universe research census; no source authentication or wagering."""
import hashlib
import math
from datetime import datetime

class UniverseHold(ValueError):
    pass

SPORTS = {"NFL","CFB","CBB","NBA","MLB","NHL","PGA"}
KEYS = ("sport","event_id","market","period","participant_id","side","line","settlement_rule")
ALLOWED = {"OFFERED","EXCLUDED"}

def utc(value):
    if not isinstance(value,str) or not value.endswith("Z"):
        raise UniverseHold("UTC_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1]+"+00:00")
    except ValueError as exc:
        raise UniverseHold("UTC_INVALID") from exc

def census(original_bytes, manifest, rows):
    if not isinstance(original_bytes,bytes) or not original_bytes or len(original_bytes)>50_000_000:
        raise UniverseHold("ORIGINAL_BYTES_REQUIRED")
    if not isinstance(manifest,dict) or not isinstance(rows,list):
        raise UniverseHold("MANIFEST_OR_ROWS_INVALID")
    if manifest.get("official") is not False or manifest.get("stake_u") != 0 or type(manifest.get("stake_u")) not in (int,float):
        raise UniverseHold("PAPER_ONLY")
    if hashlib.sha256(original_bytes).hexdigest()!=manifest.get("original_sha256"):
        raise UniverseHold("ORIGINAL_HASH_MISMATCH")
    n=manifest.get("original_offer_count")
    if type(n) is not int or n<1 or len(rows)!=n:
        raise UniverseHold("ORIGINAL_DENOMINATOR_MISMATCH")
    if not isinstance(manifest.get("provider"),str) or not manifest["provider"].strip():
        raise UniverseHold("PROVIDER_MISSING")
    observed=utc(manifest.get("provider_observed_utc"))
    captured=utc(manifest.get("local_captured_utc"))
    event=utc(manifest.get("event_start_utc"))
    if not observed<=captured<event:
        raise UniverseHold("SOURCE_CHRONOLOGY_INVALID")
    seen=set();counts={"OFFERED":0,"EXCLUDED":0}
    for row in rows:
        if not isinstance(row,dict):
            raise UniverseHold("ROW_INVALID")
        key=[]
        for field in KEYS:
            v=row.get(field)
            if isinstance(v,bool) or not isinstance(v,(str,int,float)) or not str(v).strip() or (isinstance(v,float) and not math.isfinite(v)):
                raise UniverseHold("IDENTITY_INVALID")
            key.append((type(v).__name__,str(v)))
        if row["sport"] not in SPORTS:
            raise UniverseHold("SPORT_UNSUPPORTED")
        key=tuple(key)
        if key in seen:
            raise UniverseHold("DUPLICATE_OFFER")
        seen.add(key)
        state=row.get("status")
        if state not in ALLOWED:
            raise UniverseHold("UNCLASSIFIED_OFFER")
        if state=="EXCLUDED" and (not isinstance(row.get("exclusion_reason"),str) or not row["exclusion_reason"].strip()):
            raise UniverseHold("EXCLUSION_REASON_REQUIRED")
        if state=="OFFERED" and row.get("exclusion_reason") not in (None,""):
            raise UniverseHold("CONTRADICTORY_OFFER")
        counts[state]+=1
    return {"status":"PAPER_0U_UNATTESTED_UNIVERSE","official":False,"stake_u":0,
            "original_denominator":n,"offered":counts["OFFERED"],"excluded":counts["EXCLUDED"],
            "source_authentication_verified":False,"original_sha256":manifest["original_sha256"]}
