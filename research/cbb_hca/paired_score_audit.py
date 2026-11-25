"""Paired event scoring audit. Caller authenticates source receipts; PAPER / 0u."""
import math
import random
from statistics import mean
from .cbb_score_factorial import VARIANTS


def bootstrap(deltas, *, draws=2000, seed=7):
    if not isinstance(deltas,dict) or type(draws) is not int or draws<100:
        raise ValueError("UNIQUE_EVENT_MAPPING_AND_DRAWS_REQUIRED")
    values=list(deltas.values())
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
        raise ValueError("FINITE_DELTA_REQUIRED")
    if len(values)<2:
        return dict(n=len(values),mean=mean(values) if values else None,ci95=None,seed=seed,draws=draws)
    rng=random.Random(seed)
    samples=sorted(mean(rng.choices(values,k=len(values))) for _ in range(draws))
    def q(p):
        x=(draws-1)*p;i=int(x);j=min(i+1,draws-1)
        return samples[i]+(samples[j]-samples[i])*(x-i)
    return dict(n=len(values),mean=mean(values),ci95=[q(.025),q(.975)],seed=seed,draws=draws,
                limitation="event percentile bootstrap; no temporal or multiplicity correction")


def score_pairs(records):
    rows=list(records);ids=[r["event_id"] for r in rows]
    if any(not isinstance(e,str) or not e for e in ids) or len(set(ids))!=len(ids):
        raise ValueError("UNIQUE_EVENTS_REQUIRED")
    errors={v:{} for v in VARIANTS}
    for r in rows:
        if set(r["forecasts"])!=set(VARIANTS):raise ValueError("FOUR_IDENTICAL_VARIANTS_REQUIRED")
        a=r["actual"]
        for v in VARIANTS:
            p=r["forecasts"][v]
            values=[x[k] for x in (a,p) for k in ("home_points","away_points","possessions")]
            if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in values) or a["possessions"]<=0:
                raise ValueError("INVALID_SCORE_OR_ACTUAL_POSSESSIONS")
            h=p["home_points"]-a["home_points"];away=p["away_points"]-a["away_points"]
            errors[v][r["event_id"]]=dict(home=h,away=away,margin=h-away,total=h+away,
                                         possessions=p["possessions"]-a["possessions"])
    metrics={v:{} for v in VARIANTS};paired={};interactions={}
    for field in ("home","away","scoring","margin","total","possessions"):
        losses={}
        for v in VARIANTS:
            es=([x for e in errors[v].values() for x in (e["home"],e["away"])] if field=="scoring"
                else [e[field] for e in errors[v].values()])
            metrics[v][field]=dict(n_events=len(rows),mae=mean(abs(x) for x in es) if es else None,
                                  rmse=math.sqrt(mean(x*x for x in es)) if es else None,bias=mean(es) if es else None)
            losses[v]={e:(abs(x["home"])+abs(x["away"]))/2 if field=="scoring" else abs(x[field])
                       for e,x in errors[v].items()}
        paired[field]={v:bootstrap({e:losses[VARIANTS[0]][e]-losses[v][e] for e in ids}) for v in VARIANTS[1:]}
        interactions[field]=bootstrap({e:losses[VARIANTS[3]][e]-losses[VARIANTS[2]][e]-losses[VARIANTS[1]][e]+losses[VARIANTS[0]][e] for e in ids})
    return dict(status="PAPER_0U_PREJOINED_SOURCE_AUTHENTICITY_UNVERIFIED",n_events=len(rows),metrics=metrics,
                baseline_minus_challenger_mae=paired,loss_interaction=interactions,approved_stake_u=0)
