"""G2/G3 frozen prediction audit; research only, never alters picks.

CSV columns: event_id,market,selection,model_p,market_p,outcome,
snapshot_utc,kickoff_utc,final_utc,model_sha256,source_sha256,odds.
outcome is 1 win / 0 loss; pushes and unsettled rows excluded.
Market probability must be independently sourced/de-vigged upstream.
"""
import argparse,csv,datetime as dt,json,math
from collections import Counter, defaultdict
FIELDS=("event_id","market","selection","model_p","market_p","outcome","snapshot_utc","kickoff_utc","final_utc","model_sha256","source_sha256","odds")
def utc(s):
    d=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset()!=dt.timedelta(0): raise ValueError("non-UTC timestamp")
    return d
def parse(rows):
    rows=list(rows)
    # Never select the first among conflicting frozen records. All duplicate
    # copies are held until source reconciliation, independent of file order.
    counts=Counter((r.get('event_id'),r.get('market'),r.get('selection'),
                    r.get('snapshot_utc')) for r in rows)
    good=[];blocked=[]
    for i,r in enumerate(rows,2):
        try:
            if any(not r.get(k) for k in FIELDS):raise ValueError("MISSING_FIELD")
            k=(r["event_id"],r["market"],r["selection"],r["snapshot_utc"])
            if counts[k]>1:raise ValueError("DUPLICATE")
            for h in ("model_sha256","source_sha256"):
                s=r[h]
                if len(s)!=64 or any(c not in "0123456789abcdef" for c in s):raise ValueError("INVALID_HASH")
            if not utc(r["snapshot_utc"])<utc(r["kickoff_utc"])<utc(r["final_utc"]):raise ValueError("LOOKAHEAD")
            p=float(r["model_p"]);q=float(r["market_p"])
            if not all(math.isfinite(x) and 0<x<1 for x in (p,q)):raise ValueError("INVALID_PROBABILITY")
            if r["outcome"] not in ("0","1"):raise ValueError("UNSETTLED_OR_PUSH")
            odds=int(r["odds"]); profit=(odds/100 if odds>=100 else 100/abs(odds)) if abs(odds)>=100 else None
            if profit is None or odds==0:raise ValueError("INVALID_ODDS")
            good.append((r["market"],p,q,int(r["outcome"]),profit))
        except (ValueError,TypeError,KeyError) as e:blocked.append({"row":i,"reason":str(e)})
    return good,blocked
def bucket(x):
    a=round(abs(x),4)
    return "0-5pp" if a<.05 else "5-10pp" if a<.10 else "10-20pp" if a<.20 else "20pp+"
def stats(rows):
    n=len(rows)
    if not n:return {"n":0,"roi":None,"observed_wilson_95":None,"insufficient_n30":True,"brier":None,"market_brier":None,"log_loss":None,"market_log_loss":None,"bias":None,"observed":None,"predicted":None}
    wins=sum(y for _,_,_,y,_ in rows)
    z=1.95996398454; ph=wins/n; den=1+z*z/n
    mid=(ph+z*z/(2*n))/den; rad=z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))/den
    return {"n":n,"insufficient_n30":n<30,"observed_wilson_95":[round(max(0,mid-rad),6),round(min(1,mid+rad),6)],"roi":round(sum(profit if y else -1 for _,_,_,y,profit in rows)/n,6),"brier":round(sum((p-y)**2 for _,p,q,y,_ in rows)/n,6),
        "market_brier":round(sum((q-y)**2 for _,p,q,y,_ in rows)/n,6),
        "log_loss":round(-sum(y*math.log(p)+(1-y)*math.log1p(-p) for _,p,q,y,_ in rows)/n,6),
        "market_log_loss":round(-sum(y*math.log(q)+(1-y)*math.log1p(-q) for _,p,q,y,_ in rows)/n,6),
        "bias":round(sum(p-y for _,p,q,y,_ in rows)/n,6),
        "observed":round(sum(y for _,p,q,y,_ in rows)/n,6),
        "predicted":round(sum(p for _,p,q,y,_ in rows)/n,6)}
def audit(rows):
    valid,blocked=parse(rows);groups=defaultdict(list);cal=defaultdict(list)
    for row in valid:
        m,p,q,y,_=row
        groups[(m,bucket(p-q),"model_above" if p>q else "model_below_or_equal")].append(row)
        cal[(m,min(9,int(p*10)))].append(row)
    return {"status":"RESEARCH_ONLY_NOT_VALIDATED_EV","accepted":len(valid),"blocked":blocked,
        "overall":stats(valid),
        "disagreement":[{"market":m,"bucket":b,"direction":d,**stats(v)} for (m,b,d),v in sorted(groups.items())],
        "calibration":[{"market":m,"decile":d,**stats(v)} for (m,d),v in sorted(cal.items())],
        "caution":"ROI is hypothetical flat 1u at original odds, not verified execution. Missing pushes excluded; no CLV or upstream price authenticity certification."}
def main():
    p=argparse.ArgumentParser();p.add_argument("csv");p.add_argument("--output");a=p.parse_args()
    with open(a.csv,newline="") as f: result=audit(csv.DictReader(f))
    s=json.dumps(result,indent=2,sort_keys=True)
    if a.output:
        with open(a.output,"w") as f:f.write(s+"\n")
    else:print(s)
if __name__=="__main__":main()
