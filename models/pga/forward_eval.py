"""PGA immutable pre-event probability ledger evaluator; no fitting or invented inputs."""
import math
from collections import defaultdict
from datetime import datetime

def _utc(s):
    if not isinstance(s,str) or not s.endswith("Z"):
        raise ValueError("UTC_Z_REQUIRED")
    return datetime.fromisoformat(s[:-1]+"+00:00")

def evaluate(rows):
    """All event/market/player rows; block all collisions, never first-copy wins."""
    keys=defaultdict(list)
    for i,r in enumerate(rows):
        if isinstance(r,dict):
            keys[(r.get("event_id"),r.get("market"),r.get("player_id"),r.get("asof_utc"))].append(i)
    collisions={i for ids in keys.values() if len(ids)>1 for i in ids}
    good=[];blocked=[]
    for i,r in enumerate(rows):
        reasons=[]
        if not isinstance(r,dict):
            blocked.append({"index":i,"reasons":["INVALID_ROW"]});continue
        if i in collisions:reasons.append("DUPLICATE_EVENT_SNAPSHOT")
        for k in ("event_id","market","player_id","asof_utc","event_start_utc","probability","outcome","source_sha256","model_sha256"):
            if k not in r or r[k] is None:reasons.append("MISSING_"+k.upper())
        for k in ("source_sha256","model_sha256"):
            v=r.get(k)
            if not isinstance(v,str) or len(v)!=64 or any(ch not in "0123456789abcdef" for ch in v):
                reasons.append("INVALID_"+k.upper())
        try:
            if _utc(r["asof_utc"]) >= _utc(r["event_start_utc"]):reasons.append("NOT_PREGAME")
        except (ValueError,TypeError,KeyError,OverflowError):
            reasons.append("INVALID_CLOCK")
        p=r.get("probability")
        if isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
            reasons.append("INVALID_PROBABILITY")
        if type(r.get("outcome")) is not int or r["outcome"] not in (0,1):
            reasons.append("INVALID_OUTCOME")
        if not isinstance(r.get("event_id"),str) or not r.get("event_id","").strip():
            reasons.append("INVALID_EVENT")
        if reasons:blocked.append({"index":i,"reasons":sorted(set(reasons))})
        else:good.append(r)
    metrics={}
    groups=defaultdict(list)
    for r in good:groups[r["market"]].append(r)
    for market,records in groups.items():
        brier=sum((r["probability"]-r["outcome"])**2 for r in records)/len(records)
        logloss=-sum(r["outcome"]*math.log(max(1e-12,r["probability"]))+
                     (1-r["outcome"])*math.log(max(1e-12,1-r["probability"])) for r in records)/len(records)
        metrics[market]={"n":len(records),"events":len({r["event_id"] for r in records}),
                         "brier":brier,"log_loss":logloss,
                         "mean_predicted":sum(r["probability"] for r in records)/len(records),
                         "observed":sum(r["outcome"] for r in records)/len(records),
                         "small_sample":len({r["event_id"] for r in records})<30}
    return {"status":"RESEARCH_ONLY_NO_PROMOTION","accepted":len(good),
            "blocked":blocked,"metrics":metrics,"unit_status":"PAPER_0U"}
