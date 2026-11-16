"""Chronological NFL market-by-market log-loss/Brier vs independent baseline.

Read-only research. Frozen probability rows must predate kickoff; external fair
baseline must identify two different books. Claimed hashes/clocks are not
cryptographic proof of quote authenticity. Never promotes an official bet.
"""
from __future__ import annotations
import argparse,csv,datetime as dt,json,math,re
from collections import defaultdict

REQUIRED=("event_id","market","selection","snapshot_utc","baseline_utc",
          "kickoff_utc","settled_utc","model_p","baseline_p","outcome",
          "model_sha256","baseline_sha256","baseline_books")
GRID=(0.,.25,.5,.75,1.)
HEX=re.compile(r"^[0-9a-f]{64}$")

def utc(s):
    d=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if d.utcoffset()!=dt.timedelta(0): raise ValueError("NON_UTC")
    return d

def nll(p,y): return -math.log(p if y else 1-p)
def brier(p,y): return (p-y)**2

def parse(rows):
    good=[];blocked=[];seen=set()
    for i,r in enumerate(rows,2):
        try:
            if any(not r.get(k) for k in REQUIRED): raise ValueError("MISSING_FIELD")
            key=(r["event_id"],r["market"],r["selection"])
            if key in seen: raise ValueError("DUPLICATE_SELECTION")
            seen.add(key)
            if not r["market"].startswith("NFL:"): raise ValueError("NOT_NFL_MARKET")
            if not HEX.fullmatch(r["model_sha256"]) or not HEX.fullmatch(r["baseline_sha256"]):
                raise ValueError("INVALID_SOURCE_HASH")
            books=[s.strip().upper() for s in r["baseline_books"].split(";") if s.strip()]
            if len(set(books))<2 or len(set(books))!=len(books): raise ValueError("BASELINE_REQUIRES_TWO_DISTINCT_BOOKS")
            snap,base,kick,settle=map(utc,[r["snapshot_utc"],r["baseline_utc"],r["kickoff_utc"],r["settled_utc"]])
            if not base<=snap<kick<settle: raise ValueError("LOOKAHEAD")
            if r["outcome"] not in ("0","1"): raise ValueError("UNSETTLED_OR_PUSH")
            p=float(r["model_p"]);q=float(r["baseline_p"])
            if not all(math.isfinite(v) and 0<v<1 for v in (p,q)): raise ValueError("INVALID_PROBABILITY")
            good.append(dict(key=key,market=r["market"],snapshot=snap,settled=settle,
                             model_p=p,baseline_p=q,y=int(r["outcome"])))
        except (ValueError,TypeError,KeyError,OverflowError) as e:
            blocked.append({"row":i,"reason":str(e)})
    return sorted(good,key=lambda r:(r["snapshot"],r["key"])),blocked

def report(rows, min_prior=30):
    if not isinstance(min_prior,int) or min_prior<1: raise ValueError("bad min_prior")
    valid,blocked=parse(rows)
    history=defaultdict(list)
    predictions=defaultdict(list)
    for r in valid:
        # Even if an older prediction was made earlier, do NOT use its outcome
        # until settlement was known before this new prediction snapshot.
        previous=[x for x in history[r["market"]] if x["settled"]<r["snapshot"]]
        if len(previous)<min_prior:
            w=0.
            trained=False
        else:
            losses=[]
            for candidate in GRID:
                loss=sum(nll(x["baseline_p"]+candidate*(x["model_p"]-x["baseline_p"]),x["y"])
                         for x in previous)
                losses.append((loss,candidate))
            w=min(losses,key=lambda z:(round(z[0],12),z[1]))[1]
            trained=True
        pp=r["baseline_p"]+w*(r["model_p"]-r["baseline_p"])
        predictions[r["market"]].append({
            "snapshot_utc":r["snapshot"].isoformat(),"event_id":r["key"][0],
            "selection":r["key"][2],"prior_settled":len(previous),
            "learned_before_snapshot":trained,"anchor_weight":w,
            "model_nll":nll(r["model_p"],r["y"]),
            "baseline_nll":nll(r["baseline_p"],r["y"]),
            "anchored_nll":nll(pp,r["y"]),
            "model_brier":brier(r["model_p"],r["y"]),
            "baseline_brier":brier(r["baseline_p"],r["y"]),
            "anchored_brier":brier(pp,r["y"]),
        })
        history[r["market"]].append(r)
    summary=[]
    for market,preds in sorted(predictions.items()):
        n=len(preds)
        means={k:round(sum(r[k] for r in preds)/n,6) for k in
               ("model_nll","baseline_nll","anchored_nll","model_brier","baseline_brier","anchored_brier")}
        eligible=sum(r["learned_before_snapshot"] for r in preds)
        summary.append({
            "market":market,"n":n,"eligible_walkforward_n":eligible,
            "insufficient_n30":n<30,"unvalidated_no_promote":True,
            **means,
            "anchored_delta_nll_vs_baseline":round(means["anchored_nll"]-means["baseline_nll"],6),
            "model_delta_nll_vs_baseline":round(means["model_nll"]-means["baseline_nll"],6),
        })
    return {"status":"RESEARCH_ONLY_PAPER_0U_NO_PROMOTION",
            "accepted":len(valid),"blocked":blocked,"markets":summary,
            "predictions":{market:preds for market,preds in sorted(predictions.items())},
            "caution":"Synthesized fixture passes do not validate feed, sharpness, closing price or forward edge."}

def main():
    a=argparse.ArgumentParser()
    a.add_argument("csv");a.add_argument("--output");a.add_argument("--min-prior",type=int,default=30)
    args=a.parse_args()
    with open(args.csv,newline="",encoding="utf-8") as f:r=report(csv.DictReader(f),args.min_prior)
    payload=json.dumps(r,indent=2,sort_keys=True)
    if args.output:
        with open(args.output,"x",encoding="utf-8") as f:f.write(payload+"\n")
    else:print(payload)
if __name__=="__main__":main()
