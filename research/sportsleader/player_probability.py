"""Appearance-conditional probability research; no sportsbook input."""
from collections import defaultdict
from datetime import date
import math
def evaluate(predictions,min_history=100):
    days=defaultdict(list)
    for r in predictions:
        days[date.fromisoformat(r["date"])].append(r)
    history=defaultdict(list)
    scores=defaultdict(lambda:[0,0.,0.])
    for day in sorted(days):
        for r in days[day]:
            s=r["stat"]
            p,a=r["prediction"],r["actual"]
            if not all(math.isfinite(x) for x in (p,a)):
                raise ValueError("nonfinite")
            h=history[s]
            if len(h)>=min_history:
                line=math.floor(p)+0.5
                wins=sum(p+e>line for e in h)
                prob=(wins+1)/(len(h)+2)
                y=int(a>line)
                z=scores[s]
                z[0]+=1
                z[1]+=(prob-y)**2
                z[2]-=math.log(prob if y else 1-prob)
        for r in days[day]:
            history[r["stat"]].append(r["actual"]-r["prediction"])
    return {s:dict(n=n,brier=b/n,logloss=l/n) for s,(n,b,l) in scores.items() if n}
