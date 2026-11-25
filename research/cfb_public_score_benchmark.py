"""Public FBS-only score baseline, reconstructed history, PAPER / 0u.

Schedule final scores, not last play or betting lines. Regular season only.
Strict earlier week and >=48h kickoff lag (not authenticated final availability).
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from statistics import mean
import unittest

FIELDS=("game_id","season","week","season_type","start_date","start_time_tbd",
        "completed","neutral_site","status","home_id","away_id","home_points",
        "away_points","home_division","away_division","fbs_game")
MODELS=("league_hfa","rolling_ppg_hfa","od_hfa","od_no_hfa")
URL="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_schedules/cfb_schedules_{season}.parquet"
def integer(x, minimum=0):
    if type(x) is not int or x<minimum: raise ValueError("INVALID_INTEGER")
    return x

def kickoff(x):
    if not isinstance(x,str): raise ValueError("INVALID_KICKOFF")
    d=datetime.fromisoformat(x.replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("NAIVE_KICKOFF")
    return d.astimezone(timezone.utc)

def admit(rows, season):
    groups=defaultdict(list);counts=Counter();rejects=[]
    for i,r in enumerate(rows):
        try: gid=integer(r["game_id"],1)
        except ValueError:
            counts["INVALID_EVENT_ID"]+=1;rejects.append({"source_row":i,"reason":"INVALID_EVENT_ID"});continue
        groups[gid].append(r)
    games=[]
    for gid,rr in sorted(groups.items()):
        try:
            if len(rr)!=1:raise ValueError("DUPLICATE_EVENT")
            r=rr[0]
            if r["season"]!=season:raise ValueError("SEASON_MISMATCH")
            if r["season_type"]!="regular":raise ValueError("NON_REGULAR")
            if r["completed"] is not True or r["status"]!="STATUS_FINAL":raise ValueError("NOT_EXPLICIT_FINAL")
            if r["fbs_game"] is not True or r["home_division"]!="fbs" or r["away_division"]!="fbs":raise ValueError("NOT_CONFIRMED_FBS_VS_FBS")
            if r["start_time_tbd"] is not False:raise ValueError("KICKOFF_UNCONFIRMED")
            if type(r["neutral_site"]) is not bool:raise ValueError("VENUE_UNKNOWN")
            week=integer(r["week"]);tip=kickoff(r["start_date"])
            h,a=integer(r["home_id"],1),integer(r["away_id"],1)
            hs,aws=integer(r["home_points"]),integer(r["away_points"])
            if h==a or hs==aws:raise ValueError("INVALID_FINAL")
            games.append(dict(game_id=gid,season=season,week=week,tip=tip.isoformat(),home=h,away=a,home_score=hs,away_score=aws,neutral=r["neutral_site"]))
        except (ValueError,TypeError,OverflowError) as e:
            counts[str(e)]+=1;rejects.append({"game_id":gid,"reason":str(e)})
    return games,dict(counts),rejects

def forecast(games):
    if len({g["game_id"] for g in games})!=len(games):raise ValueError("DUPLICATE_ADMITTED_GAME")
    out=[]
    for g in sorted(games,key=lambda r:(r["tip"],r["game_id"])):
        row=dict(g,forecasts={})
        if g["week"]<5:
            row["hold"]="WARMUP_WEEK";out.append(row);continue
        tip=kickoff(g["tip"])
        prior=[p for p in games if p["season"]==g["season"] and p["week"]<g["week"] and kickoff(p["tip"])<=tip-timedelta(hours=48)]
        pf,pa=defaultdict(list),defaultdict(list)
        for p in prior:
            h,a=p["home"],p["away"];hs,aws=p["home_score"],p["away_score"]
            pf[h].append(hs);pa[h].append(aws);pf[a].append(aws);pa[a].append(hs)
        h,a=g["home"],g["away"]
        row.update(prior_n=len(prior),prior_team_n=[len(pf[h]),len(pf[a])])
        if min(len(pf[h]),len(pf[a]))<4:
            row["hold"]="INSUFFICIENT_FBS_HISTORY"
        else:
            lg=mean([s for p in prior for s in (p["home_score"],p["away_score"])])
            shift=0. if g["neutral"] else 1.25
            od=[(mean(pf[h])+mean(pa[a]))/2,(mean(pf[a])+mean(pa[h]))/2]
            row["forecasts"]={"league_hfa":[lg+shift,lg-shift],
               "rolling_ppg_hfa":[mean(pf[h])+shift,mean(pf[a])-shift],
               "od_hfa":[od[0]+shift,od[1]-shift],"od_no_hfa":od}
        out.append(row)
    return out

def metrics(rows):
    chosen=[r for r in rows if r["forecasts"]]
    models={}
    for m in MODELS:
        if not chosen:models[m]=None;continue
        errors=defaultdict(list)
        for r in chosen:
            h,a=r["forecasts"][m];dh=h-r["home_score"];da=a-r["away_score"]
            for k,e in (("home",dh),("away",da),("margin",dh-da),("total",dh+da)):errors[k].append(e)
        models[m]={k:{"mae":mean(abs(x) for x in v),"rmse":math.sqrt(mean(x*x for x in v)),"bias_pred_minus_actual":mean(v)} for k,v in errors.items()}
    return {"attempted":len(rows),"paired_n":len(chosen),"neutral_evaluated":sum(r["neutral"] for r in chosen),"holds":dict(Counter(r["hold"] for r in rows if "hold" in r)),"models":models}

def publish(path, report):
    path=Path(path)
    raw=(json.dumps(report,sort_keys=True,allow_nan=False)+"\n").encode()
    fd,tmp=tempfile.mkstemp(prefix=".cfb-stage-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        if Path(tmp).read_bytes()!=raw:raise OSError("STAGED_BYTES_MISMATCH")
        os.link(tmp,path)
        d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:os.unlink(tmp)

def run(args):
    import pyarrow.parquet as pq
    all_rows=[];sources=[]
    for season in args.seasons:
        path=Path(args.root)/f"cfb_schedules_{season}.parquet"
        raw=pq.read_table(path,columns=list(FIELDS)).to_pylist()
        games,census,rejects=admit(raw,season)
        rows=forecast(games);result=metrics(rows)
        if not result["paired_n"]:raise ValueError(f"no eligible forecasts {season}")
        with path.open("rb") as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
        sources.append(dict(season=season,url=URL.format(season=season),sha256=sha,input_n=len(raw),admitted_n=len(games),rejections=census,rejected_rows=rejects,metrics=result))
        all_rows.extend(rows)
        print(json.dumps({"season":season,"input_n":len(raw),"admitted_n":len(games),"rejections":census,"metrics":result},sort_keys=True))
    report=dict(schema="CFB_PUBLIC_SCORE_BENCHMARK_V1",status="RETROSPECTIVE_RECONSTRUCTED_PAPER_0U",official_counted=0,approved_stake_u=0,
       generated_utc=datetime.now(timezone.utc).isoformat(),code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       population="confirmed FBS versus FBS only, regular season, schedule STATUS_FINAL; source classification not independently authenticated",
       chronology="prior same-season weeks and >=48h kickoff lag, not archived publication clocks",
       assumptions="min 4 FBS prior games per team, week>=5, fixed 2.5 point HFA only nonneutral; no odds, no opponent adjustment",
       sources=sources,pooled=metrics(all_rows),rows=all_rows)
    publish(args.output,report)
    print(json.dumps({"pooled":report["pooled"]},sort_keys=True))

class Tests(unittest.TestCase):
    def fixture(self):
        return dict(game_id=1,season=2023,week=1,season_type="regular",start_date="2023-09-02T12:00:00Z",start_time_tbd=False,
                    completed=True,neutral_site=False,status="STATUS_FINAL",home_id=1,away_id=2,home_points=35,away_points=14,
                    home_division="fbs",away_division="fbs",fbs_game=True)
    def test_strict_admission(self):
        s=self.fixture()
        self.assertEqual(len(admit([s],2023)[0]),1)
        for patch in ({"neutral_site":None},{"completed":1},{"status":"STATUS_SCHEDULED"},{"away_division":"fcs"},{"season_type":"postseason"},{"home_points":True},{"start_time_tbd":True},{"start_date":"2023-09-02"}):
            self.assertEqual(admit([dict(s,**patch)],2023)[0],[])
        self.assertEqual(admit([s,s],2023)[1],{"DUPLICATE_EVENT":1})
    def games(self):
        s=self.fixture()
        return admit([dict(s,game_id=i,week=i,start_date=f"2023-09-{i*5:02d}T12:00:00Z") for i in range(1,6)],2023)[0]
    def test_neutral_and_fixed_hfa(self):
        g=self.games();r=forecast(g)[-1]
        self.assertEqual(r["forecasts"]["od_hfa"],[36.25,12.75])
        g[-1]["neutral"]=True
        self.assertEqual(forecast(g)[-1]["forecasts"]["od_hfa"],[35.,14.])
    def test_target_score_and_order(self):
        g=self.games();p=forecast(g)[-1]["forecasts"];g[-1]["home_score"]=99
        self.assertEqual(forecast(list(reversed(g)))[-1]["forecasts"],p)
    def test_same_week_and_late_prior_hold(self):
        g=self.games();g[0]["week"]=5
        self.assertEqual(forecast(g)[-1]["hold"],"INSUFFICIENT_FBS_HISTORY")
        g=self.games();g[0]["tip"]="2023-09-24T12:00:00+00:00"
        self.assertEqual(forecast(g)[-1]["hold"],"INSUFFICIENT_FBS_HISTORY")
    def test_metrics_common_sample(self):
        m=metrics(forecast(self.games()));self.assertEqual(m["paired_n"],1)
        self.assertEqual(m["models"]["od_hfa"]["margin"]["mae"],2.5)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true");p.add_argument("--root");p.add_argument("--output")
    p.add_argument("--seasons",nargs="+",type=int,default=list(range(2015,2026)))
    args=p.parse_args()
    if args.self_test:unittest.main(argv=[__file__],verbosity=2)
    else:
        if not args.root or not args.output:p.error("root and output required")
        run(args)
