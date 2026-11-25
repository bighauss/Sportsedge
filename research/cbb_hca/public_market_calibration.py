"""Chronological, research-only full-game probability diagnostics.
Fixed native forecast thresholds; not sportsbook offers or star ratings.
"""
import argparse
import json
import math
from pathlib import Path
from statistics import mean, stdev
import unittest
from .public_pace_efficiency_challenger import extract, fit, predict, TRAIN, TEST

def markets(total, margin):
    return {"ml":margin,"spread":margin,"total":total,
            "home_tt":(total+margin)/2,"away_tt":(total-margin)/2}

def probability(center, line, location, sd):
    if not all(type(x) in (int,float) and math.isfinite(x) for x in (center,line,location,sd)) or sd<=0:
        raise ValueError("INVALID_NORMAL_INPUT")
    return min(1-1e-6,max(1e-6,0.5*math.erfc(-(center+location-line)/(sd*math.sqrt(2)))))

def diagnostic(report):
    rows,missing=extract(report)
    train=[r for r in rows if r["season"] in TRAIN]
    test=[r for r in rows if r["season"] in TEST]
    if not train or not test or max(r["day"] for r in train)>=min(r["day"] for r in test):
        raise ValueError("CHRONOLOGICAL_SPLIT_REQUIRED")
    f=fit(train)
    def prepare(r):
        preds=predict(r,f)
        return markets(r["at"],r["am"]),{k:markets(v[0],v[1]) for k,v in preds.items() if k in ("native","joint")}
    tr=[prepare(r) for r in train]
    te=[prepare(r) for r in test]
    result={}
    for k in ("ml","spread","total","home_tt","away_tt"):
        result[k]={}
        for name in ("native","joint"):
            residual=[a[k]-p[name][k] for a,p in tr]
            loc,sd=mean(residual),stdev(residual)
            pairs=[]
            for a,p in te:
                line=0 if k=="ml" else math.floor(p["native"][k])+.5
                pairs.append((probability(p[name][k],line,loc,sd),int(a[k]>line)))
            bins=[]
            if k=="ml":
                for lo,hi in zip((.5,.6,.7,.8,.9),(.6,.7,.8,.9,1.000001)):
                    vals=[(max(p,1-p),int((p>=.5)==bool(y))) for p,y in pairs if lo<=max(p,1-p)<hi]
                    bins.append(dict(lo=lo,hi=min(hi,1),n=len(vals),confidence=mean(v[0] for v in vals) if vals else None,accuracy=mean(v[1] for v in vals) if vals else None))
            result[k][name]=dict(n=len(pairs),location=loc,sd=sd,
                brier=mean((p-y)**2 for p,y in pairs),
                log_loss=mean(-math.log(p if y else 1-p) for p,y in pairs),confidence_bins=bins)
    return dict(status="RECONSTRUCTED_RESEARCH_ONLY",approved_stake_u=0,official_counted=0,
        train_n=len(train),evaluation_n=len(test),missing_actual_possessions=missing,results=result,
        limitations=["Model-derived half-lines, not book offers.","Already examined evaluation years.","No push, availability, period, star-rating, or wagering claims."])

class Regression(unittest.TestCase):
    def test_normal_symmetry(self):
        self.assertEqual(probability(10,10,0,2),.5)
        self.assertAlmostEqual(probability(11,10,0,2)+probability(9,10,0,2),1)
    def test_invalid(self):
        for x in (0,-1,float("nan"),float("inf"),True):
            with self.assertRaises(ValueError): probability(0,0,0,x)
    def test_team_total_identity(self):
        a=markets(150,10)
        self.assertEqual(a["home_tt"],80)
        self.assertEqual(a["away_tt"],70)
    def test_neutral(self):
        r=dict(pp=70,pe=2,pm=6,hca=0,pt=140)
        f=dict(pace=(0,1),eff=(0,1),hca_scale=.4)
        self.assertEqual(predict(r,f)["joint"],(140,6,70))
    def test_train_only(self):
        from datetime import date
        rows=[dict(season=2022,day=date(2022,1,1),neutral=False,pp=60+i%20,ap=61+i%20,pe=1.5+i%11/10,ae=1.6+i%11/10,hca=5,am=3,pm=6) for i in range(120)]
        a=fit(rows)
        self.assertEqual(a,fit(rows+[dict(rows[0],season=2025,ap=999,am=100)]))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true"); p.add_argument("--input",type=Path)
    a=p.parse_args()
    if a.self_test: unittest.main(argv=[__file__],verbosity=2)
    elif a.input: print(json.dumps(diagnostic(json.loads(a.input.read_bytes())),sort_keys=True,allow_nan=False))
    else: p.error("input required")
