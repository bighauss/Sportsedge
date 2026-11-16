"""Research-only preregistered binary forward holdout. No source attestation."""
import math
from datetime import datetime

class Hold(ValueError):
    pass

def utc(s):
    if not isinstance(s,str) or not s.endswith("Z"): raise Hold("UTC_REQUIRED")
    try: return datetime.fromisoformat(s[:-1]+"+00:00")
    except ValueError as e: raise Hold("UTC_INVALID") from e

def evaluate(freeze, rows):
    if not isinstance(freeze,dict) or not isinstance(rows,list) or not rows: raise Hold("INPUT_REQUIRED")
    if freeze.get("status")!="PREREGISTERED_PAPER" or freeze.get("official") is not False: raise Hold("PAPER_FREEZE_REQUIRED")
    h=freeze.get("model_sha256")
    if not isinstance(h,str) or len(h)!=64 or any(c not in "0123456789abcdef" for c in h): raise Hold("MODEL_HASH_REQUIRED")
    registered=utc(freeze.get("registered_utc"))
    seen=set(); scored=[]; missing=0
    for r in rows:
        if not isinstance(r,dict): raise Hold("ROW_INVALID")
        vals=[]
        for field in ("event_id","market_id","period","selection","line"):
            value=r.get(field)
            if (isinstance(value,bool) or not isinstance(value,(str,int,float))
                    or not str(value).strip()
                    or (isinstance(value,float) and not math.isfinite(value))):
                raise Hold("DUPLICATE_OR_MISSING_IDENTITY")
            vals.append((type(value).__name__,str(value)))
        key=tuple(vals)
        if key in seen: raise Hold("DUPLICATE_OR_MISSING_IDENTITY")
        seen.add(key)
        if utc(r.get("feature_available_utc"))>utc(r.get("freeze_utc")) or not (registered<=utc(r.get("freeze_utc"))<utc(r.get("event_start_utc"))): raise Hold("LOOKAHEAD_OR_NOT_PREREGISTERED")
        if r.get("model_sha256")!=h: raise Hold("MODEL_CHANGED")
        # Validate forecasts on EVERY preregistered row, including those
        # without a settled outcome; otherwise the unsettled denominator can
        # hide missing/NaN book/model probabilities.
        for name in ("model_p","book_p"):
            p=r.get(name)
            if type(p) not in (float,int) or not math.isfinite(p) or not 0<p<1: raise Hold("PROBABILITY_INVALID")
        if r.get("outcome") is None: missing+=1; continue
        if type(r["outcome"]) is not int or r["outcome"] not in (0,1): raise Hold("OUTCOME_INVALID")
        scored.append(r)
    def metrics(k):
        if not scored:return None
        return {"brier":sum((r[k]-r["outcome"])**2 for r in scored)/len(scored),
                "logloss":-sum(r["outcome"]*math.log(r[k])+(1-r["outcome"])*math.log1p(-r[k]) for r in scored)/len(scored)}
    return {"status":"PAPER_0U_UNATTESTED_FORWARD_RESEARCH","official":False,"stake_u":0,
            "denominator":len(rows),"scored":len(scored),"unsettled":missing,
            "model":metrics("model_p"),"book":metrics("book_p"),
            "source_authentication_verified":False,"calibration_certified":False}
