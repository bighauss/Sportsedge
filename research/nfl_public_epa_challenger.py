"""Corrected public EPA/success score challengers, PAPER/0u.

Compare to the exact #522 score benchmark rows. Reconstructed sources, not
authenticated historical release snapshots. Train 2015–19; test 2020–24.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean
import unittest
from nfl_public_score_benchmark import read_schedule, publish, integer

TRAIN=set(range(2015,2020))
TEST=set(range(2020,2025))
BASE="offense_defense_fixed_hfa"
FIELDS={"game_id","season","season_type","week","game_date","home_team","away_team",
        "play_id","play_type","posteam","defteam","epa","success"}
MIN_PLAYS=20
MIN_HISTORY=4


def digest(p):
    with open(p,"rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def read_rates(path, schedule, season):
    """Pass/rush only; joint finite EPA and binary success; no missing-to-zero."""
    seen=set(); bad=set(); acc=defaultdict(lambda:[0,0,0.,0.]); census=Counter()
    with gzip.open(path,"rt",encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not FIELDS<=set(reader.fieldnames or ()):
            raise ValueError("PBP EPA schema mismatch")
        for r in reader:
            if r["season_type"]!="REG" or r["play_type"] not in ("pass","run"):
                continue
            gid=r["game_id"]; g=schedule.get(gid)
            if g is None:
                census["unmatched_play"]+=1
                continue
            t,o=r["posteam"],r["defteam"]
            try:
                if (integer(r["season"])!=season or g["season"]!=season or
                    integer(r["week"])!=g["week"] or r["game_date"]!=g["day"] or
                    (r["home_team"],r["away_team"])!=(g["home"],g["away"]) or
                    {t,o}!={g["home"],g["away"]} or t==o):
                    raise ValueError("identity")
                key=(gid,integer(r["play_id"]))
                if key in seen:
                    raise ValueError("duplicate play")
                seen.add(key)
            except (ValueError,TypeError,OverflowError):
                bad.add(gid); census["invalid_identity_or_duplicate"]+=1
                continue
            a=acc[gid,t];a[0]+=1
            try:
                e,s=float(r["epa"]),float(r["success"])
                if not math.isfinite(e) or s not in (0.,1.):
                    raise ValueError("invalid stat")
            except (ValueError,TypeError,OverflowError):
                census["missing_or_invalid_stat"]+=1
                continue
            a[1]+=1;a[2]+=e;a[3]+=s
    rates={}
    for gid,g in schedule.items():
        if g["season"]!=season:
            continue
        if gid in bad:
            census["quarantined_event"]+=1;continue
        sides=[acc.get((gid,t)) for t in (g["home"],g["away"])]
        if any(a is None or a[1]<MIN_PLAYS or a[1]/a[0]<.9 for a in sides):
            census["insufficient_complete_plays"]+=1;continue
        rates[gid]={t:{"n":a[1],"epa":a[2]/a[1],"success":a[3]/a[1]}
                    for t,a in zip((g["home"],g["away"]),sides)}
    census["usable_events"]=len(rates)
    return rates,dict(census)


def matchup(offense, allowed):
    # Both rates are measured from the offense's perspective: higher allowed
    # means a weaker defense. The sum, not the difference, is monotone.
    return .5*(offense+allowed)


def feature_rows(games, rates, benchmark):
    out=[]
    for b in benchmark:
        row={"game_id":b["game_id"],"season":b["season"],"week":b["week"],
             "day":b["day"],"home_score":b["home_score"],"away_score":b["away_score"],
             "baseline":b["forecasts"].get(BASE),"features":{}}
        g=games[b["game_id"]]
        if any(b[k]!=g[k] for k in ("season","week","day","home","away","home_score","away_score")):
            raise ValueError("benchmark identity mismatch")
        d=date.fromisoformat(g["day"])
        prior=[p for p in games.values() if p["season"]==g["season"]
               and p["week"]<g["week"] and (d-date.fromisoformat(p["day"])).days>=2
               and p["game_id"] in rates]
        h,a=g["home"],g["away"]
        hist=defaultdict(list)
        for p in prior:
            h0,a0=p["home"],p["away"]
            q=rates[p["game_id"]]
            hist[h0].append((q[h0],q[a0]));hist[a0].append((q[a0],q[h0]))
        row["history_n"]=[len(hist[h]),len(hist[a])]
        if not row["baseline"]:
            row["hold"]="BASELINE_HOLD"
        elif min(row["history_n"])<MIN_HISTORY:
            row["hold"]="INSUFFICIENT_PAIRED_RATE_HISTORY"
        else:
            for key in ("epa","success"):
                def rate(t,i):
                    return mean(x[i][key] for x in hist[t])
                row["features"][key]=[matchup(rate(h,0),rate(a,1)),matchup(rate(a,0),rate(h,1))]
        out.append(row)
    return out


def fit(rows,key):
    train=[r for r in rows if r["season"] in TRAIN and r["features"]]
    xs=[];ys=[]
    for r in train:
        xs.extend(r["features"][key])
        ys.extend([r["home_score"]-1.5,r["away_score"]+1.5])
    if len(xs)<100:
        raise ValueError("insufficient training; no fallback coefficients")
    mx,my=mean(xs),mean(ys)
    den=sum((x-mx)**2 for x in xs)
    if den<=1e-12:
        raise ValueError("degenerate training")
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den
    return {"intercept":my-slope*mx,"slope":slope,"n_team_rows":len(xs),"n_games":len(train)}


def evaluate(rows):
    coefs={k:fit(rows,k) for k in ("epa","success")}
    test=[r for r in rows if r["season"] in TEST]
    eligible=[]
    for r in test:
        if not r["features"]:continue
        p={"baseline":r["baseline"]}
        for k,c in coefs.items():
            x,y=r["features"][k]
            h=c["intercept"]+c["slope"]*x+1.5
            a=c["intercept"]+c["slope"]*y-1.5
            if not all(math.isfinite(v) and v>=0 for v in (h,a)):
                r["hold"]="INVALID_SCORE_PREDICTION";break
            p[k]=[h,a]
        else:
            r["predictions"]=p;eligible.append(r)
    if not eligible:raise ValueError("no held-out matched rows")
    metrics={}
    for model in ("baseline","epa","success"):
        metrics[model]={}
        for k in ("margin","total"):
            sign=-1 if k=="margin" else 1
            errors=[r["predictions"][model][0]+sign*r["predictions"][model][1]-
                    r["home_score"]-sign*r["away_score"] for r in eligible]
            metrics[model][k]={"mae":mean(abs(e) for e in errors),
                "rmse":math.sqrt(mean(e*e for e in errors)),"bias_pred_minus_actual":mean(errors)}
    paired={}
    for m in ("epa","success"):
        for k in ("margin","total"):
            sign=-1 if k=="margin" else 1
            blocks=defaultdict(list)
            for r in eligible:
                y=r["home_score"]+sign*r["away_score"]
                def loss(model):
                    h,a=r["predictions"][model];return abs(h+sign*a-y)
                blocks[r["season"],r["week"]].append(loss(m)-loss("baseline"))
            b=[(sum(v),len(v)) for v in blocks.values()]
            rng=random.Random(57)
            sims=[]
            for _ in range(2000):
                sample=rng.choices(b,k=len(b));sims.append(sum(s for s,n in sample)/sum(n for s,n in sample))
            sims.sort()
            paired[m+"_"+k]={"delta_mae":sum(s for s,n in b)/sum(n for s,n in b),
               "week_blocks":len(b),"descriptive_ci95":[sims[49],sims[1949]],
               "limitation":"week block; residual cross-week team dependence remains"}
    return {"fit":coefs,"train_seasons":sorted(TRAIN),"heldout_seasons":sorted(TEST),
            "heldout_attempted":len(test),"heldout_paired_n":len(eligible),
            "holds":dict(Counter(r["hold"] for r in test if "hold" in r)),
            "metrics":metrics,"paired_challenger_minus_baseline":paired,"rows":test}


def run(args):
    report=json.loads(Path(args.benchmark).read_bytes())
    if report["final_source"]!="schedule":
        raise ValueError("schedule-based benchmark required")
    rc=report["source_reconciliation"]
    if digest(args.schedule)!=rc["schedule_sha256"]:
        raise ValueError("schedule digest mismatch")
    games,_=read_schedule(args.schedule,TRAIN|TEST)
    games={g["game_id"]:g for g in games if g["game_id"] not in rc["conflicts"]}
    sources={x["season"]:x for x in report["sources"]}
    if set(sources)!=TRAIN|TEST:raise ValueError("ten season benchmark required")
    rates={};census={}
    for season in sorted(sources):
        path=Path(args.root)/f"play_by_play_{season}.csv.gz"
        if digest(path)!=sources[season]["sha256"]:
            raise ValueError("PBP digest mismatch")
        r,c=read_rates(path,games,season);rates.update(r);census[season]=c
    rows=feature_rows(games,rates,report["forecasts"])
    result=evaluate(rows)
    result.update(status="RETROSPECTIVE_RECONSTRUCTED_PAPER_0U",official_counted=0,
         approved_stake_u=0,benchmark_sha256=digest(args.benchmark),source_census=census,
         code_sha256=digest(__file__),source_sha256={s:v["sha256"] for s,v in sources.items()},
         feature_definition="mean of prior per-game pass/run EPA or success offense and opponent allowed, with fixed HFA",
         chronology="prior week and >=2 days; release timing not authenticated")
    publish(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k!="rows"},sort_keys=True))


class Regression(unittest.TestCase):
    def test_weaker_defense_increases_feature(self):
        self.assertGreater(matchup(.1,.3),matchup(.1,-.3))
    def test_no_fallback(self):
        with self.assertRaises(ValueError):fit([],"epa")
    def test_heldout_never_fits(self):
        rows=[{"season":2019,"features":{"epa":[float(i),float(i+1)]},
               "home_score":2*i+1.5,"away_score":2*(i+1)-1.5} for i in range(60)]
        before=fit(rows,"epa")
        self.assertEqual(before,fit(rows+[dict(rows[0],season=2020,home_score=9999)],"epa"))
        self.assertAlmostEqual(before["slope"],2.)
    def test_target_and_same_week_excluded(self):
        games={str(i):dict(game_id=str(i),season=2020,week=i,day=f"2020-09-{i*3:02d}",
              home="A",away="B",home_score=20,away_score=10) for i in range(1,10)}
        rates={i:{"A":{"epa":.1,"success":.5},"B":{"epa":.2,"success":.4}} for i in games}
        b=dict(games["9"],forecasts={BASE:[20,10]})
        before=feature_rows(games,rates,[b])[0]
        rates["9"]["A"]["epa"]=999
        self.assertEqual(before,feature_rows(games,rates,[b])[0])
        games["8"]["week"]=9
        self.assertEqual(feature_rows(games,rates,[b])[0]["history_n"],[7,7])
    def test_missing_history_held(self):
        g=dict(game_id="x",season=2020,week=9,day="2020-11-01",home="A",away="B",
               home_score=20,away_score=10)
        self.assertEqual(feature_rows({"x":g},{},[dict(g,forecasts={BASE:[20,10]})])[0]["hold"],
                         "INSUFFICIENT_PAIRED_RATE_HISTORY")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--root");parser.add_argument("--schedule")
    parser.add_argument("--benchmark");parser.add_argument("--output")
    args=parser.parse_args()
    if args.self_test:unittest.main(argv=[__file__],verbosity=2)
    else:
        if not all((args.root,args.schedule,args.benchmark,args.output)):
            parser.error("all inputs required")
        run(args)
