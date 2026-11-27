"""Fixed synthetic thresholds; not historical sportsbook lines."""
import argparse,json,math
from research.sportsleader.chronological_residuals import select

def evaluate(rows):
    out=[]
    for season in sorted({r["season"] for r in rows})[1:]:
        pairs=select(rows,season)
        prior=[r for r in rows if r["season"]<season]
        target=[r for r in rows if r["season"]==season]
        for market,fn in (("spread",lambda h,a:h-a),("total",lambda h,a:h+a),
                          ("home_total",lambda h,a:h),("away_total",lambda h,a:a)):
            values=sorted(fn(r["home_actual"],r["away_actual"]) for r in prior)
            center=values[len(values)//2]
            for offset in (-5,0,5):
                line=center+offset+.5
                base=(1+sum(v>line for v in values))/(2+len(values))
                brier=loss=bb=bl=0.
                for r in target:
                    h,a=r["home_prediction"],r["away_prediction"]
                    p=(1+sum(fn(max(0,round(h+dh)),max(0,round(a+da)))>line for dh,da in pairs))/(2+len(pairs))
                    y=fn(r["home_actual"],r["away_actual"])>line
                    brier+=(p-y)**2
                    loss-=math.log(p if y else 1-p)
                    bb+=(base-y)**2
                    bl-=math.log(base if y else 1-base)
                n=len(target)
                out.append(dict(season=season,market=market,line=line,n=n,brier=brier/n,logloss=loss/n,baseline_brier=bb/n,baseline_logloss=bl/n))
    return dict(results=out,release_state="PAPER_0U_NON_COUNTED",line_source="SYNTHETIC_PRIOR_MEDIAN")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("path")
    with open(p.parse_args().path) as f:
        print(json.dumps(evaluate(json.load(f)),sort_keys=True))
