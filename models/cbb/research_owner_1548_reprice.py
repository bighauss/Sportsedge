"""Reproduce afternoon owner-board diagnostic from explicitly selected inputs.

No production model or bet release. The 11:25 public reconstructed projection
table is older than the 15:48 owner odds. Training SDs are from 2019-2021 only.
"""
import argparse
import csv
import json
import math
import re
from pathlib import Path
from datetime import datetime
from halves.halves_model import project_period, shape_cdf

WEIGHTS = (1, .875, .75, .625, .5, .375, .25, .125, 0)
ALIASES = {"Alcorn":"Alcorn State","Southern University":"Southern","Albany NY":"UAlbany",
           "CSUN":"Cal State Northridge","Saint Thomas MN":"St. Thomas","USC Upstate":"South Carolina Upstate",
           "CSU Bakersfield":"Cal State Bakersfield","Mississippi Valley":"Mississippi Valley State","Hawaii":"Hawai'i"}
def key(a,h):
    return "@".join(re.sub("[^a-z]","",ALIASES.get(v,v).lower()) for v in (a,h))
def utc(s):
    d = datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None:
        raise ValueError("MISSING_TIMEZONE")
    return d
def normal(z):
    x = abs(z)/math.sqrt(2)
    t = 1/(1+.3275911*x)
    e = 1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-.284496736)*t+.254829592)*t*math.exp(-x*x)
    return (1+(-e if z<0 else e))/2
def cdf(s,z):
    if s["kind"]=="normal":
        return normal(z)
    a,b=s["z_knots"],s["p_knots"]
    if z<=a[0]:
        return b[0]*normal(z)/normal(a[0])
    if z>=a[-1]:
        return 1-(1-b[-1])*(1-normal(z))/(1-normal(a[-1]))
    return shape_cdf(s,z)
def implied(o):
    return 100/(o+100) if o>0 else -o/(-o+100)
def net(o):
    return o/100 if o>0 else 100/-o
def load(path):
    with path.open() as f:
        return list(csv.DictReader(f))
def replay(board,projection,metrics,coef_path):
    pmap={}
    for l in projection.read_text().splitlines():
        if re.match(r"^\| \d+:\d+ [AP]M CT \|",l):
            p=[x.strip() for x in l.split("|")[1:-1]]
            k=key(*p[1].split(" @ "))
            if k in pmap: raise ValueError("DUPLICATE_PROJECTION")
            pmap[k]=p
    sds={(r["model"],r["target"]):float(r["residual_sd"]) for r in load(metrics) if r["group"]=="TRAIN"}
    coef=json.loads(coef_path.read_text())
    coef["_sha256"]="explicit_coefficients"
    results,holds,seen=[],[],set()
    for q in load(board):
        rid,a,h,per,mk=(q[k] for k in ("row_key","away","home","period","market"))
        def hold(reason): holds.append([rid,a,h,per,mk,reason])
        if rid in seen: raise ValueError("DUPLICATE_SOURCE_ROW")
        seen.add(rid)
        if not utc("2026-11-25T17:25:43Z")<=utc(q["captured_utc"])<=utc("2026-11-25T21:49:24Z")<utc(q["tip_utc"]):
            hold("CLOCK_MISMATCH"); continue
        p=pmap.get(key(a,h))
        if not p: hold("NO_MATCH"); continue
        try: M,T=float(p[2]),float(p[3])
        except ValueError: hold("NO_NATIVE_PROJECTION"); continue
        if per=="1H" and mk=="ML": hold("HALF_ML_SETTLEMENT_UNVERIFIED"); continue
        target={"SPREAD":"margin","ML":"margin","TOTAL":"total","TT_HOME":"home","TT_AWAY":"away"}[mk]
        model,shape="native_frozen",{"kind":"normal"}
        if per=="1H":
            d=project_period("H1",(T+M)/2,(T-M)/2,coefficients=coef)
            model="native_half_research"
            mu,sigma=d["mean"][target],d["sd"][target]
            spec=coef["targets"]["H1_"+("TEAM" if target in ("home","away") else target.upper())]
            shape=next(v["shape"] for v in spec["variants"] if v["name"]=="base")
        else:
            try: M,T=float(p[6]),float(p[7]); model="FG1"
            except ValueError: pass
            mu={"margin":M,"total":T,"home":(T+M)/2,"away":(T-M)/2}[target]
            sigma=sds[model,target+"_points" if target in ("home","away") else target]
        if not math.isfinite(mu) or not math.isfinite(sigma) or sigma<=0:
            hold("INVALID_PROJECTION"); continue
        if mk in ("TOTAL","TT_HOME","TT_AWAY") and q["totals_order"]!="over_under":
            hold("TOTAL_ORDER_UNVERIFIED"); continue
        line=float(q["line"]) if q["line"] else None
        if mk!="ML" and (line is None or line%1!=.5):
            hold("UNSUPPORTED_LINE"); continue
        threshold=0 if mk=="ML" else -line if mk=="SPREAD" else line
        C=lambda x:cdf(shape,(x-mu)/sigma)
        pa=1-C(threshold)
        if mk=="ML": pa=(1-C(.5))/(1-(C(.5)-C(-.5)))
        odds=[int(q[k]) for k in ("price_a","price_b")]
        if min(map(abs,odds))<100: hold("INVALID_PRICE"); continue
        ip=[implied(o) for o in odds]
        for i,o in enumerate(odds):
            pin=(pa,1-pa)[i]; pm=ip[i]/sum(ip)
            ev=[(w*pin+(1-w)*pm)*(net(o)+1)-1 for w in WEIGHTS]
            side=("home","away")[i] if mk in ("SPREAD","ML") else ("over","under")[i]
            dl=-line if mk=="SPREAD" and i else line
            results.append([rid,a,h,q["tip_utc"],q["captured_utc"],per,mk,side,dl,o,model,
                            f"{mu:.5f}",f"{sigma:.5f}",f"{pin:.7f}",f"{pm:.7f}",
                            *[f"{v:.7f}" for v in ev],"PAPER_0U_NON_COUNTED"])
    return results,holds
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ("board","projection","metrics","coefficients","out"):
        p.add_argument("--"+n,type=Path,required=True)
    a=p.parse_args()
    rows,holds=replay(a.board,a.projection,a.metrics,a.coefficients)
    a.out.mkdir(parents=True,exist_ok=True)
    for name,header,body in (
        ("research_reprice.csv",["row_key","away","home","tip_utc","captured_utc","period","market","side","line","price","model","mean","sd","p_independent","p_market_novig",*["ev_w"+str(w) for w in WEIGHTS],"status"],rows),
        ("holds.csv",["row_key","away","home","period","market","reason"],holds)):
        with (a.out/name).open("w",newline="") as f:
            w=csv.writer(f,lineterminator="\n");w.writerow(header);w.writerows(body)
if __name__=="__main__":
    main()
