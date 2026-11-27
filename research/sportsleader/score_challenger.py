"""Prior-season score regression; retrospective research only."""
import argparse
import json
from collections import defaultdict
import numpy as np
import pyarrow.parquet as pq

def evaluate(paths, ridge=20.):
    seasons=defaultdict(list)
    seen=set()
    for path in paths:
        for r in pq.read_table(path).to_pylist():
            if r["completed"] is not True or type(r["neutral_site"]) is not bool:
                continue
            h,a=r["home_team_id"],r["away_team_id"]
            y,z=r["home_score"],r["away_score"]
            if any(type(v) is not int or v<0 for v in (y,z)):
                continue
            if h is None or a is None or h==a or r["game_id"] is None or r["game_id"] in seen:
                raise ValueError("invalid game identity")
            seen.add(r["game_id"])
            seasons[r["season"]].append((h,a,not r["neutral_site"],y,z))
    results=[]
    for season in sorted(seasons):
        train=[r for s in seasons if s<season for r in seasons[s]]
        if not train:
            continue
        teams={t:i for i,t in enumerate(sorted({t for h,a,v,y,z in train for t in (h,a)}))}
        n=len(teams)
        g=np.eye(2*n+2)*ridge
        g[-2,-2]=g[-1,-1]=0
        b=np.zeros(2*n+2)
        for h,a,v,y,z in train:
            for t,o,home,score in ((h,a,v,y),(a,h,False,z)):
                ix=[teams[t],n+teams[o],2*n,2*n+1]
                x=np.array([1.,1.,1.,float(home)])
                g[np.ix_(ix,ix)]+=np.outer(x,x)
                b[ix]+=x*score
        beta=np.linalg.solve(g,b)
        def pred(t,o,home):
            return max(0.,float(beta[-2]+beta[-1]*home+
                (beta[teams[t]] if t in teams else 0)+
                (beta[n+teams[o]] if o in teams else 0)))
        errors=[]
        for h,a,v,y,z in seasons[season]:
            p,q=pred(h,a,v),pred(a,h,False)
            errors.append([y-p,z-q,(y-z)-(p-q),(y+z)-(p+q)])
        e=np.asarray(errors)
        results.append(dict(season=season,n=len(e),train_n=len(train),
            venue=float(beta[-1]),mae=np.abs(e).mean(axis=0).tolist(),
            bias=e.mean(axis=0).tolist(),rmse=np.sqrt((e**2).mean(axis=0)).tolist()))
    return dict(results=results,metric_order=["home","away","margin","total"],
        release_state="PAPER_0U_NON_COUNTED",limitations=["fixed ridge","membership unverified","retrospective"])
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("assets",nargs="+")
    print(json.dumps(evaluate(p.parse_args().assets),sort_keys=True))
