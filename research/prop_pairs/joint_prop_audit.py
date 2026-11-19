"""Research-only player-prop pair scoring. Input must already be PIT-matched and settled."""
import math

def evaluate(rows):
    rows=list(rows)
    if not rows:
        return {"status":"NO_DATA","games":0,"observed_joint_rate":None,"independence_expected_rate":None,"independence_brier":None,"joint_model_brier":None}
    seen=set(); pair=None; jp_present=None; obs=[]; ind=[]; joint=[]
    for r in rows:
        if not isinstance(r,dict): raise ValueError("INVALID_ROW")
        for k in ("event_id","a","b","pa","pb","ya","yb"):
            if k not in r or r[k] is None: raise ValueError("MISSING_REQUIRED:"+k)
        if any(not isinstance(r[k],str) or not r[k].strip() for k in ("event_id","a","b")):
            raise ValueError("INVALID_IDENTITY")
        identity=tuple(sorted((r["a"],r["b"])))
        if identity[0]==identity[1]: raise ValueError("SAME_SELECTION")
        if pair is None: pair=identity
        if identity!=pair: raise ValueError("MIXED_PROP_PAIRS")
        if r["event_id"] in seen: raise ValueError("DUPLICATE_EVENT")
        seen.add(r["event_id"])
        for k in ("pa","pb"):
            p=r[k]
            if isinstance(p,bool) or not isinstance(p,(float,int)) or not math.isfinite(p) or not 0<=p<=1:
                raise ValueError("INVALID_PROBABILITY:"+k)
        for k in ("ya","yb"):
            if type(r[k]) is not int or r[k] not in (0,1): raise ValueError("INVALID_SETTLEMENT:"+k)
        has_joint="joint_p" in r and r["joint_p"] is not None
        if jp_present is None: jp_present=has_joint
        if has_joint!=jp_present: raise ValueError("INCOMPLETE_JOINT_FORECASTS")
        if has_joint:
            p=r["joint_p"]
            if isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
                raise ValueError("INVALID_JOINT_PROBABILITY")
            if not max(0,r["pa"]+r["pb"]-1)-1e-12<=p<=min(r["pa"],r["pb"])+1e-12:
                raise ValueError("INCOHERENT_JOINT_PROBABILITY")
            joint.append(p)
        ind.append(r["pa"]*r["pb"])
        obs.append(r["ya"]*r["yb"])
    n=len(rows)
    return {"status":"RESEARCH_ONLY","games":n,"pair":list(pair),
        "observed_joint_rate":sum(obs)/n,
        "independence_expected_rate":sum(ind)/n,
        "independence_brier":sum((p-y)**2 for p,y in zip(ind,obs))/n,
        "joint_model_brier":sum((p-y)**2 for p,y in zip(joint,obs))/n if jp_present else None,
        "sample_warning":"VERY_SMALL_SAMPLE" if n<30 else "EXPLORATORY_SAMPLE" if n<100 else None,
        "certified":False,"approved_stake_u":0}
