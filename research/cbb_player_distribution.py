"""Appearance-conditional distribution challengers for the verified #519 backtest.

Fixed diagnostic half-lines, NOT sportsbook quotes. Each probability uses only
the same admitted prior player appearances as the historical mean benchmark.
No live integration, promotion, push/void inference or DNP modeling.
"""
from collections import defaultdict
from datetime import date
import math
import random
from statistics import mean, variance
import unittest

LINES={"POINTS":9.5,"REBOUNDS":4.5,"ASSISTS":2.5,"THREES":1.5,
       "PRA":14.5,"PR":12.5,"PA":11.5,"RA":5.5,
       "STEALS":0.5,"BLOCKS":0.5,"TURNOVERS":1.5}
FAMILIES=("poisson","negative_binomial","empirical")

def _cdf(mu,k,shape=None):
    """Count CDF on integer support via log-PMF; explicit Poisson limit."""
    if mu==0:
        return 1.
    if shape is None:
        logs=[-mu+j*math.log(mu)-math.lgamma(j+1) for j in range(k+1)]
    else:
        # Stable NB log probability parameterization, mean mu and shape r.
        logp=-math.log1p(mu/shape)
        logq=math.log(mu)-math.log(shape+mu)
        logs=[shape*logp]
        for j in range(1,k+1):
            logs.append(logs[-1]+math.log(shape+j-1)-math.log(j)+logq)
    return min(1.,max(0.,math.fsum(math.exp(x) for x in logs)))

def predict(values,line):
    if len(values)<5 or len(values)>8 or any(type(v) is not int or v<0 or v>750 for v in values):
        raise ValueError("INVALID_PRIOR_COUNT_SAMPLE")
    if type(line) not in (int,float) or not math.isfinite(line) or not 0<=line<=750 or line%1!=.5:
        raise ValueError("DIAGNOSTIC_HALF_LINE_REQUIRED")
    mu=mean(values);var=variance(values);k=math.floor(line)
    shape=mu*mu/(var-mu) if mu>0 and var>mu+1e-9 else None
    # Explicit nested Poisson limit for zero/underdispersion. No exception fallback.
    pp=1-_cdf(mu,k)
    np=1-_cdf(mu,k,shape) if shape is not None else pp
    ep=sum(v>line for v in values)/len(values)
    raw=dict(zip(FAMILIES,(pp,np,ep)))
    n=len(values)
    return {"line":line,"n":n,"mean":mu,"sample_variance":var,"nb_shape":shape,
            "nb_state":"OVERDISPERSED_MOMENTS" if shape is not None else "POISSON_LIMIT",
            "raw":raw,"p_over":{f:(p*n+.5)/(n+1) for f,p in raw.items()}}

def for_history(recent):
    out={}
    for stat,line in LINES.items():
        values=[p["stats"][stat] for p in recent]
        if all(v is not None for v in values):
            out[stat]=predict(values,line)
    return out

def summary(rows,*,draws=1000,seed=57):
    result={}
    for stat,line in LINES.items():
        eligible=[r for r in rows if stat in r.get("prop_distribution",{}) and r["actual"][stat] is not None]
        metrics={};deltas={};n=len(eligible)
        if not n:
            result[stat]={"n":0,"line":line,"metrics":{}}
            continue
        ys=[int(r["actual"][stat]>line) for r in eligible]
        by_family={}
        for family in FAMILIES:
            ps=[r["prop_distribution"][stat]["p_over"][family] for r in eligible]
            losses=[(p-y)**2 for p,y in zip(ps,ys)]
            ll=[-(y*math.log(p)+(1-y)*math.log1p(-p)) for p,y in zip(ps,ys)]
            event=defaultdict(list);bins=defaultdict(list)
            for r,p,y,b,l in zip(eligible,ps,ys,losses,ll):
                event[r["game_id"]].append((b,l))
                bins[min(9,int(p*10))].append((p,y))
            metrics[family]={"brier":mean(losses),"log_loss":mean(ll),
                "event_weighted_brier":mean(mean(x[0] for x in v) for v in event.values()),
                "event_weighted_log_loss":mean(mean(x[1] for x in v) for v in event.values()),
                "reliability":[{"bin":i,"n":len(v),"mean_p":mean(x[0] for x in v),"observed_rate":mean(x[1] for x in v)} for i,v in sorted(bins.items())]}
            by_family[family]=losses
        for family in FAMILIES[1:]:
            blocks=defaultdict(list)
            for r,a,b in zip(eligible,by_family[family],by_family["poisson"]):
                week=date.fromisoformat(r["day"]).isocalendar()[:2]
                blocks[week].append(a-b)
            block=[(sum(v),len(v)) for v in blocks.values()]
            rng=random.Random(seed);ci=None
            if len(block)>=2:
                draws_out=[]
                for _ in range(draws):
                    sample=rng.choices(block,k=len(block))
                    draws_out.append(sum(x[0] for x in sample)/sum(x[1] for x in sample))
                draws_out.sort();ci=[draws_out[int(.025*draws)],draws_out[int(.975*draws)]]
            deltas[family]={"delta_brier":sum(x[0] for x in block)/n,"week_blocks":len(block),"descriptive_ci95":ci}
        result[stat]={"n":n,"line":line,"n_games":len({r["game_id"] for r in eligible}),
            "over_rate":mean(ys),"nb_poisson_limit_n":sum(r["prop_distribution"][stat]["nb_state"]=="POISSON_LIMIT" for r in eligible),
            "metrics":metrics,"paired_vs_poisson":deltas}
    return result

class Tests(unittest.TestCase):
    def test_zero_and_underdispersion(self):
        q=predict([0]*5,.5)
        self.assertEqual(q["raw"],dict.fromkeys(FAMILIES,0.))
        self.assertEqual(q["nb_state"],"POISSON_LIMIT")
        self.assertEqual(q["p_over"]["poisson"],.5/6)
        self.assertEqual(predict([2]*5,2.5)["raw"]["poisson"],predict([2]*5,2.5)["raw"]["negative_binomial"])
    def test_known_poisson(self):
        self.assertAlmostEqual(predict([1]*5,.5)["raw"]["poisson"],1-math.exp(-1))
    def test_known_nb(self):
        q=predict([0,0,0,0,10],.5)
        self.assertAlmostEqual(q["nb_shape"],4/18)
        self.assertAlmostEqual(q["raw"]["negative_binomial"],1-(q["nb_shape"]/(q["nb_shape"]+2))**q["nb_shape"])
    def test_invalid_inputs(self):
        for v in ([1]*4,[1]*4+[True],[1]*4+[float("nan")],[1]*4+[-1]):
            with self.assertRaises(ValueError):predict(v,.5)
        for line in (1,float("nan"),-1.5):
            with self.assertRaises(ValueError):predict([1]*5,line)
    def test_individual_brier_not_aggregate_error(self):
        q=predict([0,1,0,1,0],.5)
        r=[dict(game_id=str(i),day="2024-01-01",actual={"STEALS":y},prop_distribution={"STEALS":q}) for i,y in enumerate((0,1))]
        p=q["p_over"]["empirical"]
        self.assertAlmostEqual(summary(r)["STEALS"]["metrics"]["empirical"]["brier"],(p*p+(1-p)**2)/2)
    def test_monotonicity(self):
        a=predict([0,0,0,3,10],.5);b=predict([0,0,0,3,10],4.5)
        for f in FAMILIES:self.assertGreaterEqual(a["p_over"][f],b["p_over"][f])

if __name__=="__main__":unittest.main()
