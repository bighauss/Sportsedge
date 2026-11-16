"""G2/G3 frozen prediction audit; research only, never alters picks.

CSV columns: event_id,market,selection,model_p,market_p,outcome,
snapshot_utc,kickoff_utc,final_utc,model_sha256,source_sha256.
outcome is 1 win / 0 loss; pushes and unsettled rows excluded.
Market probability must be independently sourced/de-vigged upstream.
"""
import argparse,csv,datetime as dt,hashlib,json,math
from collections import defaultdict
FIELDS=("event_id","market","selection","model_p","market_p","outcome","snapshot_utc","kickoff_utc","final_utc","model_sha256","source_sha256")
def utc(s):
    d=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset()!=dt.timedelta(0): raise ValueError("non-UTC timestamp")
    return d
def parse(rows):
    good=[];blocked=[];seen=set()
    for i,r in enumerate(rows,2):
        try:
            if any(not r.get(k) for k in FIELDS):raise ValueError("MISSING_FIELD")
            k=(r["event_id"],r["market"],r["selection"],r["snapshot_utc"])
            if k in seen:raise ValueError("DUPLICATE")
            seen.add(k)
            for h in ("model_sha256","source_sha256"):
                s=r[h]
                if len(s)!=64 or any(c not in "0123456789abcdef" for c in s):raise ValueError("INVALID_HASH")
            if not utc(r["snapshot_utc"])<utc(r["kickoff_utc"])<utc(r["final_utc"]):raise ValueError("LOOKAHEAD")
            p=float(r["model_p"]);q=float(r["market_p"])
            if not all(math.isfinite(x) and 0<x<1 for x in (p,q)):raise ValueError("INVALID_PROBABILITY")
            if r["outcome"] not in ("0","1"):raise ValueError("UNSETTLED_OR_PUSH")
            good.append((r["market"],p,q,int(r["outcome"])))
        except (ValueError,TypeError,KeyError) as e:blocked.append({"row":i,"reason":str(e)})
    return good,blocked
def bucket(x):
    a=abs(x)
    return "0-5pp" if a<.05 else "5-10pp" if a<.10 else "10-20pp" if a<.20 else "20pp+"
def stats(rows):
    n=len(rows)
    if not n:return {"n":0,"brier":None,"market_brier":None,"log_loss":None,"market_log_loss":None,"bias":None,"observed":None,"predicted":None}
    return {"n":n,"brier":round(sum((p-y)**2 for _,p,q,y in rows)/n,6),
        "market_brier":round(sum((q-y)**2 for _,p,q,y in rows)/n,6),
        "log_loss":round(-sum(y*math.log(p)+(1-y)*math.log1p(-p) for _,p,q,y in rows)/n,6),
        "market_log_loss":round(-sum(y*math.log(q)+(1-y)*math.log1p(-q) for _,p,q,y in rows)/n,6),
        "bias":round(sum(p-y for _,p,q,y in rows)/n,6),
        "observed":round(sum(y for _,p,q,y in rows)/n,6),
        "predicted":round(sum(p for _,p,q,y in rows)/n,6)}
def audit(rows):
    valid,blocked=parse(rows);groups=defaultdict(list);cal=defaultdict(list)
    for row in valid:
        m,p,q,y=row
        groups[(m,bucket(p-q),"model_above" if p>q else "model_below_or_equal")].append(row)
        cal[(m,min(9,int(p*10)))].append(row)
    return {"status":"RESEARCH_ONLY_NOT_VALIDATED_EV","accepted":len(valid),"blocked":blocked,
        "overall":stats(valid),
        "disagreement":[{"market":m,"bucket":b,"direction":d,**stats(v)} for (m,b,d),v in sorted(groups.items())],
        "calibration":[{"market":m,"decile":d,**stats(v)} for (m,d),v in sorted(cal.items())],
        "caution":"Unsettled/push rows excluded; no confidence interval, CLV, profitability or independence certification."}
def main():
    p=argparse.ArgumentParser();p.add_argument("csv");p.add_argument("--output");a=p.parse_args()
    with open(a.csv,newline="") as f: result=audit(csv.DictReader(f))
    s=json.dumps(result,indent=2,sort_keys=True)
    if a.output:
        with open(a.output,"w") as f:f.write(s+"\n")
    else:print(s)
if __name__=="__main__":main()
