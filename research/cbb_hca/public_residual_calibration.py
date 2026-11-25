"""Fixed-season calibration of #521 reconstructed scores, not live prices.
Fit 2019–2022, evaluate 2023–2025. No fake publication clocks or odds.
"""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean
import unittest
from .cbb_distribution_audit import fit_residual_distribution, predict_residual_distribution, reliability, probabilities
from .distribution_driver import smooth, calibration
from .evidence_io import atomic_publish

TRAIN=(2019,2020,2021,2022)
TEST=(2023,2024,2025)
FAMILIES=("normal","student_t","empirical")
BASE="additive_product"

def rows_from_report(report):
    if report.get("schema")!="CBB_PUBLIC_FACTORIAL_RETRO_V1" or report.get("approved_stake_u")!=0:
        raise ValueError("EXPECTED_RECONSTRUCTED_FACTORIAL_REPORT")
    if set(report["seasons"])!={str(s) for s in TRAIN+TEST}:
        raise ValueError("EXPECTED_SEVEN_SEASONS")
    rows=[];seen=set()
    for season in TRAIN+TEST:
        section=report["seasons"][str(season)]
        n=0
        for r in section["rows"]:
            gid=r["event_id"]
            if type(gid) is not str or not gid or gid in seen:
                raise ValueError("DUPLICATE_OR_INVALID_EVENT")
            seen.add(gid)
            d=date.fromisoformat(r["day"])
            if d.year not in (season-1,season):
                raise ValueError("SEASON_DATE_MISMATCH")
            if not r["forecasts"]:continue
            p=r["forecasts"][BASE]
            h,a=r["home_points"],r["away_points"]
            if any(type(v) is not int or v<0 for v in (h,a)) or h==a:
                raise ValueError("INVALID_FINAL")
            if any(type(p[k]) not in (int,float) or not math.isfinite(p[k]) for k in ("margin","total","home_points","away_points")):
                raise ValueError("INVALID_FORECAST")
            if not math.isclose(p["margin"],p["home_points"]-p["away_points"],abs_tol=1e-8) or not math.isclose(p["total"],p["home_points"]+p["away_points"],abs_tol=1e-8):
                raise ValueError("INCOHERENT_FORECAST")
            rows.append(dict(event_id=gid,season=season,day=d.isoformat(),neutral=r["neutral"],
                         projected_margin=p["margin"],projected_total=p["total"],actual_margin=h-a,actual_total=h+a))
            n+=1
        if n!=section["summary"]["forecast_n"]:
            raise ValueError("FORECAST_CENSUS_MISMATCH")
    return rows

def experiment(rows):
    train=[r for r in rows if r["season"] in TRAIN];test=[r for r in rows if r["season"] in TEST]
    if not train or not test or max(r["day"] for r in train)>=min(r["day"] for r in test):
        raise ValueError("CHRONOLOGICAL_SPLIT_REQUIRED")
    # Zero shift is the primary family comparison; common fitted residual mean
    # is an explicitly separate sensitivity analysis. No choice from holdout.
    all_results={}
    for shift in (False,True):
        fits={k:fit_residual_distribution([r["actual_"+k]-r["projected_"+k] for r in train],use_mean_location=shift)
              for k in ("margin","total")}
        out=[]
        for r in test:
            # Half-integer total threshold derived only from the frozen mean.
            # It is a diagnostic threshold, NOT a historical sportsbook quote.
            line=math.floor(r["projected_total"])+.5
            raw={"home_win":predict_residual_distribution(fits["margin"],r["projected_margin"]),
                 "over_model_half_line":predict_residual_distribution(fits["total"],r["projected_total"]-line)}
            out.append(dict(r,total_diagnostic_line=line,
                         outcomes={"home_win":int(r["actual_margin"]>0),"over_model_half_line":int(r["actual_total"]>line)},
                         probabilities={market:{f:smooth(v[f],v["training_n"]) for f in FAMILIES} for market,v in raw.items()}))
        metrics={};paired={}
        for market in ("home_win","over_model_half_line"):
            ys=[r["outcomes"][market] for r in out]
            metrics[market]={}
            for f in FAMILIES:
                ps=[r["probabilities"][market][f] for r in out]
                metrics[market][f]=dict(n=len(ps),brier=mean((p-y)**2 for p,y in zip(ps,ys)),
                   log_loss=mean(-(y*math.log(p)+(1-y)*math.log1p(-p)) for p,y in zip(ps,ys)),
                   calibration=calibration(ps,ys),reliability=reliability(ps,ys))
            for f in FAMILIES[1:]:
                blocks=defaultdict(list)
                for r,y in zip(out,ys):
                    week=date.fromisoformat(r["day"]).isocalendar()[:2]
                    pp=r["probabilities"][market]
                    blocks[week].append((pp[f]-y)**2-(pp["normal"]-y)**2)
                b=[(sum(v),len(v)) for v in blocks.values()];rng=random.Random(57);sim=[]
                for _ in range(1000):
                    sample=rng.choices(b,k=len(b));sim.append(sum(s for s,n in sample)/sum(n for s,n in sample))
                sim.sort()
                paired[market+"_"+f]=dict(delta_brier=sum(s for s,n in b)/sum(n for s,n in b),
                    week_blocks=len(b),descriptive_ci95=[sim[24],sim[974]])
        all_results["prior_mean_shift" if shift else "zero_shift"]=dict(
             fits={k:{a:b for a,b in v.items() if a!="deviations"} for k,v in fits.items()},
             metrics=metrics,paired_challenger_minus_normal_brier=paired,rows=out)
    return dict(train_n=len(train),heldout_n=len(test),results=all_results)

class Tests(unittest.TestCase):
    def test_prefit_parity(self):
        r=[-4,-1,0,1,7]
        for shift in (True,False):
            fit=fit_residual_distribution(r,use_mean_location=shift)
            for x in (-100,-1,0,1,100):
                self.assertEqual(probabilities(r,x,use_mean_location=shift),predict_residual_distribution(fit,x))
    def test_empirical_equality(self):
        f=fit_residual_distribution([-2,-1,0,1,2])
        self.assertEqual(predict_residual_distribution(f,0)["empirical"],.5)
    def test_bad_training_and_nonfinite(self):
        with self.assertRaises(ValueError):fit_residual_distribution([1,2])
        with self.assertRaises(ValueError):fit_residual_distribution([1,2,3,4,float("nan")])
        with self.assertRaises(ValueError):predict_residual_distribution(fit_residual_distribution([-2,-1,0,1,2]),float("inf"))
    def test_fixed_fit_ignores_holdout(self):
        def r(i,yr):
            return dict(event_id=str(i)+str(yr),season=yr,day=f"{yr}-01-{i+1:02d}",neutral=False,
                        projected_margin=2.,actual_margin=i-3,projected_total=150.,actual_total=145+i)
        tr=[r(i,2022) for i in range(10)];te=[r(i,2023) for i in range(10)]
        a=experiment(tr+te);te[-1]["actual_margin"]=100
        b=experiment(tr+te)
        self.assertEqual(a["results"]["zero_shift"]["fits"],b["results"]["zero_shift"]["fits"])
        self.assertEqual(a["results"]["zero_shift"]["rows"][-1]["probabilities"],b["results"]["zero_shift"]["rows"][-1]["probabilities"])

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--self-test",action="store_true")
    p.add_argument("--input",type=Path);p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:unittest.main(argv=[__file__],verbosity=2)
    else:
        if a.input is None or a.output is None:p.error("input and output required")
        raw=a.input.read_bytes();report=experiment(rows_from_report(json.loads(raw)))
        report.update(status="RECONSTRUCTED_FIXED_SEASON_CALIBRATION_PAPER_0U",
            input_sha256=hashlib.sha256(raw).hexdigest(),code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            train_seasons=TRAIN,heldout_seasons=TEST,approved_stake_u=0,official_counted=0,
            limitations=["Historical reconstruction, not authenticated pretip CBBD forecasts.","Total thresholds derived from projected means, not actual betting lines.","Mid-distribution equality is not push settlement; no ROI or EV.","Week-block intervals descriptive; cross-week team dependence remains.","Fixed mean shift sensitivity not selected from holdout."])
        atomic_publish(a.output,(json.dumps(report,sort_keys=True,allow_nan=False)+"\n").encode())
        print(json.dumps({**report,"results":{k:{a:b for a,b in v.items() if a!="rows"} for k,v in report["results"].items()}},sort_keys=True,allow_nan=False))
