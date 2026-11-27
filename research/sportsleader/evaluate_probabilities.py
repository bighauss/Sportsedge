"""Research-only three-outcome moneyline probability evaluation."""
import argparse
import json
import math
from research.sportsleader.chronological_residuals import select

def evaluate(rows):
    results=[]
    seasons=sorted({r["season"] for r in rows})
    for season in seasons[1:]:
        pairs=select(rows,season)
        prior=[r for r in rows if r["season"]<season]
        def outcome(h,a):
            return 0 if h>a else 1 if h<a else 2
        counts=[1,1,1]
        for r in prior:
            counts[outcome(r["home_actual"],r["away_actual"])]+=1
        baseline=[x/sum(counts) for x in counts]
        errors=[]
        for r in rows:
            if r["season"]!=season:
                continue
            h,a=r["home_prediction"],r["away_prediction"]
            if not all(math.isfinite(x) and x>=0 for x in (h,a)):
                raise ValueError("invalid prediction")
            c=[1,1,1]
            for dh,da in pairs:
                c[outcome(max(0,round(h+dh)),max(0,round(a+da)))]+=1
            p=[x/sum(c) for x in c]
            y=outcome(r["home_actual"],r["away_actual"])
            def brier(q):
                return sum((x-(i==y))**2 for i,x in enumerate(q))
            errors.append((brier(p),-math.log(p[y]),brier(baseline),-math.log(baseline[y])))
        results.append(dict(season=season,n=len(errors),prior_n=len(pairs),
            metrics=[sum(x[i] for x in errors)/len(errors) for i in range(4)]))
    return dict(results=results,metric_order=["brier","logloss","baseline_brier","baseline_logloss"],
                release_state="PAPER_0U_NON_COUNTED")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("path")
    with open(p.parse_args().path) as f:
        print(json.dumps(evaluate(json.load(f)),sort_keys=True))
