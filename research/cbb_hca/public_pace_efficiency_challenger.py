"""PAPER/0u: fixed-season pace/efficiency/HCA challenger on reconstructed reports.
No odds, production changes, or authenticated historical publication clocks.
"""
import argparse
import hashlib
import json
import math
from datetime import date
from statistics import mean

TRAIN = {2019, 2020, 2021, 2022}
TEST = {2023, 2024, 2025}

def affine(xs, ys):
    mx, my = mean(xs), mean(ys)
    den = sum((x-mx)**2 for x in xs)
    if den <= 0:
        raise ValueError("UNIDENTIFIED_SLOPE")
    b = sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den
    return my-b*mx,b

def finite(x):
    if type(x) not in (int,float) or not math.isfinite(x):
        raise ValueError("NONFINITE_OR_INVALID_NUMBER")
    return x

def extract(report):
    if report["schema"] != "CBB_PUBLIC_FACTORIAL_RETRO_V1" or report["approved_stake_u"] != 0 or set(report["seasons"]) != {str(s) for s in TRAIN|TEST}:
        raise ValueError("INVALID_RECONSTRUCTED_REPORT")
    rows=[]; seen=set(); missing=0
    for s in sorted(TRAIN|TEST):
        for r in report["seasons"][str(s)]["rows"]:
            eid=r["event_id"]
            if not isinstance(eid,str) or not eid or eid in seen:
                raise ValueError("INVALID_OR_DUPLICATE_EVENT")
            seen.add(eid)
            if not r["forecasts"]:
                continue
            if r["possessions"] is None:
                missing+=1; continue
            d=date.fromisoformat(r["day"])
            if d.year not in (s-1,s) or type(r["neutral"]) is not bool:
                raise ValueError("INVALID_VENUE_OR_DATE")
            p=r["forecasts"]["additive_product"]
            pp,ap=finite(p["possessions"]),finite(r["possessions"])
            pt,at=finite(p["total"]),finite(r["total"])
            pm,am=finite(p["margin"]),finite(r["margin"])
            hca=finite(p["hca_applied"])
            if min(pp,ap,pt,at)<=0 or abs(pm)>pt or abs(am)>at or (r["neutral"] and hca!=0):
                raise ValueError("INCOHERENT_PROJECTION")
            if not math.isclose(at,r["home_points"]+r["away_points"]) or not math.isclose(am,r["home_points"]-r["away_points"]):
                raise ValueError("INCOHERENT_FINAL")
            rows.append(dict(id=eid,season=s,day=d,neutral=r["neutral"],pp=pp,ap=ap,pt=pt,at=at,pm=pm,am=am,hca=hca,pe=pt/pp,ae=at/ap))
    return rows,missing

def fit(rows):
    tr=[r for r in rows if r["season"] in TRAIN]
    if len(tr)<100:
        raise ValueError("INSUFFICIENT_TRAINING")
    pace=affine([r["pp"] for r in tr],[r["ap"] for r in tr])
    eff=affine([r["pe"] for r in tr],[r["ae"] for r in tr])
    h=[r for r in tr if not r["neutral"]]
    den=sum(r["hca"]**2 for r in h)
    if den<=0:
        raise ValueError("UNIDENTIFIED_HCA")
    scale=sum(r["hca"]*(r["am"]-r["pm"]+r["hca"]) for r in h)/den
    return dict(pace=pace,eff=eff,hca_scale=scale)

def predict(r,f):
    pp=f["pace"][0]+f["pace"][1]*r["pp"]
    pe=f["eff"][0]+f["eff"][1]*r["pe"]
    m=r["pm"]-r["hca"]+f["hca_scale"]*r["hca"]
    if min(pp,pe)<=0 or abs(m)>pp*pe:
        raise ValueError("INCOHERENT_CHALLENGER")
    return {"native":(r["pt"],r["pm"],r["pp"]),
        "pace_only":(pp*r["pe"],r["pm"],pp),
        "eff_only":(r["pp"]*pe,r["pm"],r["pp"]),
        "pace_eff":(pp*pe,r["pm"],pp),
        "hca_only":(r["pt"],m,r["pp"]),
        "joint":(pp*pe,m,pp)}

def metrics(rows,f):
    out={}
    for r in rows:
        for name,(t,m,p) in predict(r,f).items():
            dt,dm=t-r["at"],m-r["am"]
            out.setdefault(name,[]).append((abs(dt),dt,abs(dm),(abs(dt+dm)+abs(dt-dm))/4,abs(p-r["ap"])))
    keys=("total_mae","total_bias","margin_mae","team_score_mae","pace_mae")
    return {n:dict(zip(keys,map(mean,zip(*v)))) for n,v in out.items()}

def audit(report):
    rows,missing=extract(report)
    tr=[r for r in rows if r["season"] in TRAIN]
    te=[r for r in rows if r["season"] in TEST]
    if not tr or not te or max(r["day"] for r in tr)>=min(r["day"] for r in te):
        raise ValueError("CHRONOLOGICAL_SPLIT_REQUIRED")
    f=fit(tr)
    pace=[(r["pp"]-r["ap"])*(r["pe"]+r["ae"])/2 for r in te]
    eff=[(r["pe"]-r["ae"])*(r["pp"]+r["ap"])/2 for r in te]
    return dict(status="RECONSTRUCTED_RESEARCH_ONLY",approved_stake_u=0,official_counted=0,
        train_n=len(tr),evaluation_n=len(te),missing_actual_possessions=missing,
        fit=f,metrics=metrics(te,f),season_metrics={str(s):metrics([r for r in te if r["season"]==s],f) for s in sorted(TEST)},
        total_bias_decomposition=dict(pace=mean(pace),efficiency=mean(eff)),
        limitations=["Already examined evaluation seasons; no untouched holdout.",
          "Complete-box paired sample; retrospective raw ratings, not live CBBD or pretip archives.",
          "Box possession estimate includes overtime. Separate pace/efficiency regressions are not a possession simulation.",
          "No odds, EV, ROI, calibrated probabilities or production promotion."])

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("input"); a=p.parse_args()
    with open(a.input,"rb") as f: raw=f.read()
    result=audit(json.loads(raw))
    result["input_sha256"]=hashlib.sha256(raw).hexdigest()
    print(json.dumps(result,sort_keys=True,allow_nan=False,indent=2))
