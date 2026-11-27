"""Evaluate appearance-conditional player forecasts, without market inputs."""
import math
from collections import defaultdict
def metrics(predictions):
    groups=defaultdict(list)
    for r in predictions:
        p,a=r["prediction"],r["actual"]
        if not all(math.isfinite(x) for x in (p,a)):
            raise ValueError("invalid prediction or actual")
        groups[r["stat"]].append(a-p)
    return {s:dict(n=len(e),mae=sum(map(abs,e))/len(e),bias=sum(e)/len(e),
        rmse=math.sqrt(sum(x*x for x in e)/len(e))) for s,e in sorted(groups.items())}
