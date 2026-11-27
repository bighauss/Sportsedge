"""Retrospective independent margin challenger; no market inputs."""
from collections import defaultdict
from statistics import mean
import argparse
import json
import numpy as np
import pyarrow.parquet as pq

def evaluate(paths, ridge=20.0):
    if not np.isfinite(ridge) or ridge <= 0:
        raise ValueError("positive finite ridge required")
    seasons = defaultdict(list)
    seen = set()
    for path in paths:
        for r in pq.read_table(path).to_pylist():
            if r["completed"] is not True or type(r["neutral_site"]) is not bool:
                continue
            if any(type(r[k]) is not int or r[k]<0 for k in ("home_score","away_score")):
                continue
            h,a = r["home_team_id"],r["away_team_id"]
            if h is None or a is None or h == a or r["game_id"] is None or r["game_id"] in seen:
                raise ValueError("invalid game identity")
            seen.add(r["game_id"])
            seasons[r["season"]].append((h,a,not r["neutral_site"],r["home_score"]-r["away_score"]))
    out=[]
    for season in sorted(seasons):
        train=[r for s in seasons if s<season for r in seasons[s]]
        if not train:
            continue
        teams={t:i for i,t in enumerate(sorted({t for h,a,_,_ in train for t in (h,a)}))}
        n=len(teams)
        gram=np.eye(n+1)*ridge
        gram[n,n]=0
        rhs=np.zeros(n+1)
        for h,a,venue,y in train:
            ix=[teams[h],teams[a],n]
            x=np.array([1.,-1.,float(venue)])
            gram[np.ix_(ix,ix)]+=np.outer(x,x)
            rhs[ix]+=x*y
        if gram[n,n]==0:
            raise ValueError("no non-neutral training games")
        beta=np.linalg.solve(gram,rhs)
        raw=mean(y for h,a,v,y in train if v)
        for venue in (False,True):
            test=[r for r in seasons[season] if r[2]==venue]
            if not test:
                continue
            def rating(t):
                return float(beta[teams[t]]) if t in teams else 0.
            errors=[abs(y-(rating(h)-rating(a)+float(beta[n])*v)) for h,a,v,y in test]
            out.append(dict(season=season,neutral=not venue,n=len(test),train_n=len(train),
                adjusted_venue=float(beta[n]),raw_venue=raw,mae=mean(errors),
                raw_mae=mean(abs(y-raw*v) for h,a,v,y in test),
                unknown_team_games=sum(h not in teams or a not in teams for h,a,v,y in test)))
    return dict(results=out,ridge=ridge,release_state="PAPER_0U_NON_COUNTED",
                limitations=["retrospective", "membership unverified", "fixed ridge", "unknown teams zero"])

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("assets",nargs="+")
    print(json.dumps(evaluate(p.parse_args().assets),sort_keys=True))
