"""NBA market-anchor walk-forward research evaluator; no trained model changed.

Each input row must be an already-frozen pre-tipoff probability and an
independent multi-book fair-price baseline. Candidate blend weights are chosen
only from outcomes settled BEFORE each subsequent prediction snapshot.
"""
import csv,datetime as dt,json,math,re,argparse
from collections import defaultdict
HEX=re.compile(r"^[a-f0-9]{64}$")
GRID=(0.,.25,.5,.75,1.)
def utc(s):
    x=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if x.utcoffset()!=dt.timedelta(0):raise ValueError("NON_UTC")
    return x
def nll(p,y):return -math.log(p if y else 1-p)
def run(rows,min_prior=30):
    if type(min_prior)!=int or min_prior<1:raise ValueError("bad min_prior")
    good=[];blocked=[];seen=set()
    fields=("event_id","market","selection","snapshot_utc","baseline_utc",
            "tipoff_utc","final_utc","model_p","market_p","result",
            "model_sha256","baseline_sha256","baseline_books")
    for i,r in enumerate(rows,2):
        try:
            if any(not r.get(k) for k in fields):raise ValueError("MISSING_FIELD")
            key=(r["event_id"],r["market"],r["selection"])
            if key in seen:raise ValueError("DUPLICATE_EVENT_SELECTION")
            seen.add(key)
            if not r["market"].startswith("NBA:"):raise ValueError("WRONG_SPORT")
            if not HEX.fullmatch(r["model_sha256"]) or not HEX.fullmatch(r["baseline_sha256"]):
                raise ValueError("BAD_HASH")
            books=[x.strip().upper() for x in r["baseline_books"].split(";") if x.strip()]
            if len(set(books))<2 or len(books)!=len(set(books)):raise ValueError("NOT_INDEPENDENT_BOOKS")
            snap,base,tip,final=map(utc,[r[k] for k in ("snapshot_utc","baseline_utc","tipoff_utc","final_utc")])
            if not base<=snap<tip<final:raise ValueError("LOOKAHEAD")
            if r["result"] not in ("0","1"):raise ValueError("PUSH_OR_UNSETTLED")
            p,q=float(r["model_p"]),float(r["market_p"])
            if not all(math.isfinite(z) and 0<z<1 for z in (p,q)):raise ValueError("BAD_PROBABILITY")
            good.append(dict(key=key,market=r["market"],snap=snap,final=final,p=p,q=q,y=int(r["result"])))
        except (ValueError,TypeError,KeyError,OverflowError) as e:blocked.append({"row":i,"reason":str(e)})
    seen_history=defaultdict(list);out=defaultdict(list)
    for r in sorted(good,key=lambda z:(z["snap"],z["key"])):
        prior=[p for p in seen_history[r["market"]] if p["final"]<r["snap"]]
        if len(prior)<min_prior:w=0.
        else:
            w=min(GRID,key=lambda candidate:(sum(nll(z["q"]+candidate*(z["p"]-z["q"]),z["y"]) for z in prior),candidate))
        anchored=r["q"]+w*(r["p"]-r["q"])
        out[r["market"]].append({"event_id":r["key"][0],"chosen_weight":w,"prior_settled":len(prior),
            "model_nll":nll(r["p"],r["y"]),"market_nll":nll(r["q"],r["y"]),
            "anchored_nll":nll(anchored,r["y"]),"market_brier":(r["q"]-r["y"])**2,
            "anchored_brier":(anchored-r["y"])**2})
        seen_history[r["market"]].append(r)
    markets=[]
    for market,v in sorted(out.items()):
        means={k:round(sum(x[k] for x in v)/len(v),6) for k in
               ("model_nll","market_nll","anchored_nll","market_brier","anchored_brier")}
        markets.append(dict(market=market,n=len(v),insufficient_n30=len(v)<30,
                            independently_validated=False,**means))
    return dict(status="PAPER_0U_NO_PRODUCTION_PROMOTION",accepted=len(good),blocked=blocked,
                markets=markets,walkforward={m:v for m,v in sorted(out.items())},
                caution="No fair-price authentication, real sample or independent prospective proof is provided by this code.")
def main():
    p=argparse.ArgumentParser();p.add_argument("csv");p.add_argument("--output");p.add_argument("--min-prior",type=int,default=30)
    a=p.parse_args()
    with open(a.csv,newline="",encoding="utf-8") as f:r=run(csv.DictReader(f),a.min_prior)
    s=json.dumps(r,indent=2,sort_keys=True)
    if a.output:
        with open(a.output,"x",encoding="utf-8") as f:f.write(s+"\n")
    else:print(s)
if __name__=="__main__":main()
