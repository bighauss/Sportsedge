"""Retrospective public CBB formula experiment; NOT a CBBD rating replay.

Uses the actual factorial compare() on reconstructed prior-date ORtg/DRtg,
not the external PPG-based cells. ESPN schedule + team-box identities must
agree. Source files are current retrospective releases, not archived pretip
receipts. No odds, production changes or official results.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
import random
import unittest
from .cbb_score_factorial import compare, VARIANTS
from .evidence_io import atomic_publish

SCHED = ("game_id","season","game_date","home_id","away_id","home_score",
         "away_score","neutral_site","status_type_completed","status_type_name")
BOX = ("game_id","season","game_date","team_id","opponent_team_id",
       "team_home_away","team_score","opponent_team_score","field_goals_attempted",
       "free_throws_attempted","turnovers","offensive_rebounds")
METRICS = ("home_points","away_points","margin","total","possessions")


def ident(x):
    if type(x) is not int or x <= 0:
        raise ValueError("INVALID_ID")
    return str(x)


def nonnegative(x):
    if type(x) is not int or x < 0:
        raise ValueError("INVALID_COUNT")
    return x


def day(x):
    if type(x) is not date:
        raise ValueError("INVALID_DATE")
    return x


def group(rows):
    grouped = defaultdict(list)
    invalid = 0
    for r in rows:
        try:
            grouped[ident(r.get("game_id"))].append(r)
        except ValueError:
            invalid += 1
    return grouped, invalid


def schedule_games(schedules, boxes, season):
    sg, si = group(schedules)
    bg, bi = group(boxes)
    census = Counter(schedule_rows=len(schedules), box_rows=len(boxes),
                     invalid_schedule_id_rows=si, invalid_box_id_rows=bi,
                     orphan_box_events=len(set(bg)-set(sg)))
    games, rejects = [], []
    for gid, entries in sorted(sg.items()):
        try:
            if len(entries) != 1:
                raise ValueError("DUPLICATE_SCHEDULE")
            s = entries[0]
            if s["season"] != season:
                raise ValueError("SEASON_MISMATCH")
            if s["status_type_completed"] is not True or s["status_type_name"] != "STATUS_FINAL":
                raise ValueError("NOT_VERIFIED_FINAL")
            h,a = ident(s["home_id"]),ident(s["away_id"])
            d = day(s["game_date"])
            if h == a or type(s["neutral_site"]) is not bool:
                raise ValueError("INVALID_TEAMS_OR_VENUE")
            hs,aws=nonnegative(s["home_score"]),nonnegative(s["away_score"])
            if hs == aws:
                raise ValueError("TIED_FINAL")
        except ValueError as e:
            census[str(e)] += 1
            rejects.append({"event_id":gid,"reason":str(e)})
            continue
        g=dict(event_id=gid,day=d,home=h,away=a,neutral=s["neutral_site"],
               home_points=hs,away_points=aws,margin=hs-aws,total=hs+aws,
               possessions=None,box_hold=None)
        try:
            pairs=bg.get(gid,[])
            if len(pairs)!=2:
                raise ValueError("BOX_COUNT_NOT_TWO")
            sides={r["team_home_away"]:r for r in pairs}
            if set(sides)!={"home","away"}:
                raise ValueError("BOX_SIDE_CONFLICT")
            estimates=[]
            for side,t,opp,score,other in (("home",h,a,hs,aws),("away",a,h,aws,hs)):
                r=sides[side]
                if (r["season"]!=season or day(r["game_date"])!=d or ident(r["team_id"])!=t
                    or ident(r["opponent_team_id"])!=opp or nonnegative(r["team_score"])!=score
                    or nonnegative(r["opponent_team_score"])!=other):
                    raise ValueError("BOX_SCHEDULE_CONFLICT")
                fga,fta,to,orb=[nonnegative(r[k]) for k in BOX[-4:]]
                estimates.append(fga+0.44*fta+to-orb)
            poss=mean(estimates)
            if not all(40<=p<=110 for p in estimates):
                raise ValueError("BOX_POSSESSIONS_OUT_OF_RANGE")
            g["possessions"]=poss
        except ValueError as e:
            g["box_hold"]=str(e)
            census[str(e)] += 1
        games.append(g)
    census["admitted_schedule_finals"]=len(games)
    census["complete_box_finals"]=sum(g["possessions"] is not None for g in games)
    return games,dict(census),rejects


def context(prior, shrink_games):
    """Reconstructed raw per-possession ratings, not opponent-adjusted CBBD."""
    hist=defaultdict(list)
    pace=mean(g["possessions"] for g in prior)
    league=100*sum(g["total"] for g in prior)/(2*sum(g["possessions"] for g in prior))
    for g in prior:
        p=g["possessions"]
        hist[g["home"]].append((g["home_points"],g["away_points"],p))
        hist[g["away"]].append((g["away_points"],g["home_points"],p))
    ratings={}
    for t,rows in hist.items():
        denom=sum(r[2] for r in rows)+shrink_games*pace
        ratings[t]={"off":(100*sum(r[0] for r in rows)+shrink_games*pace*league)/denom,
                    "def":(100*sum(r[1] for r in rows)+shrink_games*pace*league)/denom}
    # Same native residual definition; only prior, non-neutral finals.
    residual=[]
    for g in prior:
        if g["neutral"]:
            continue
        h,a=ratings[g["home"]],ratings[g["away"]]
        expected=(h["off"]+a["def"]-a["off"]-h["def"])*g["possessions"]/100
        residual.append(g["margin"]-expected)
    return {"ratings":ratings,"league_mean_ortg":league,"league_pace":pace,
            "team_pace":{t:(mean(r[2] for r in v),len(v)) for t,v in hist.items()},
            "settings":{"min_pace_games":4},
            "hca":{"value":mean(residual) if len(residual)>=50 else None,"n":len(residual)}}


def walk(games, shrink_games=8):
    import cbbd_native_score_model as native
    by_day=defaultdict(list)
    for g in games:
        by_day[g["day"]].append(g)
    out=[]
    # Extra day lag reduces next-day overlap; cannot authenticate actual release clocks.
    for d, targets in sorted(by_day.items()):
        prior=[g for g in games if g["day"]<=d-timedelta(days=2) and g["possessions"] is not None]
        ctx=context(prior,shrink_games) if len(prior)>=150 else None
        for g in sorted(targets,key=lambda x:x["event_id"]):
            row={**g,"day":d.isoformat(),"prior_n":len(prior),"forecasts":{}}
            if ctx is None:
                row["hold"]="WARMUP"
            else:
                try:
                    row["forecasts"]=compare(ctx,g["home"],g["away"],neutral=g["neutral"])
                except native.Pass as e:
                    row["hold"]=str(e)
            # Forecast decision does not depend on target possession availability.
            out.append(row)
    return out


def summarize(rows):
    eligible=[r for r in rows if r["forecasts"]]
    result={}
    for name in VARIANTS:
        metrics={}
        for k in METRICS:
            es=[r["forecasts"][name][k]-r[k] for r in eligible if r[k] is not None]
            metrics[k]={"n":len(es),"mae":mean(abs(e) for e in es) if es else None,
                        "rmse":math.sqrt(mean(e*e for e in es)) if es else None,
                        "bias_pred_minus_actual":mean(es) if es else None}
        result[name]=metrics
    # Descriptive week-block resampling, not independent game bootstrap.
    paired={}
    for k in ("margin","total"):
        for v in VARIANTS[1:]:
            blocks=defaultdict(list)
            for r in eligible:
                week=date.fromisoformat(r["day"]).isocalendar()[:2]
                blocks[week].append(abs(r["forecasts"][v][k]-r[k])-
                                    abs(r["forecasts"][VARIANTS[0]][k]-r[k]))
            b=[(sum(vals),len(vals)) for vals in blocks.values()]
            rng=random.Random(17)
            sims=[]
            if len(b)>=4:
                for _ in range(1000):
                    sample=rng.choices(b,k=len(b))
                    sims.append(sum(x[0] for x in sample)/sum(x[1] for x in sample))
                sims.sort()
            paired[k+"_"+v]={"n":sum(n for _,n in b),"blocks":len(b),
                             "delta_mae":sum(s for s,_ in b)/sum(n for _,n in b) if b else None,
                             "descriptive_ci95":[sims[24],sims[974]] if sims else None}
    return {"attempted":len(rows),"forecast_n":len(eligible),"holds":dict(Counter(r["hold"] for r in rows if "hold" in r)),
            "metrics":result,"paired_challenger_minus_baseline":paired}


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def run(root, output, seasons):
    import pyarrow.parquet as pq
    import cbbd_native_score_model as native
    report={"schema":"CBB_PUBLIC_FACTORIAL_RETRO_V1","status":"RECONSTRUCTED_PAPER_0U",
            "generated_utc":datetime.now(timezone.utc).isoformat(),
            "native_sha256":native.MODEL_CODE_SHA256,"code_sha256":digest(Path(__file__)),
            "rating_basis":"raw reconstructed points per 100 possessions; not CBBD opponent-adjusted ratings",
            "chronology":"strict earlier calendar dates, additional one-day embargo; not authenticated historical availability",
            "population":"ESPN schedule/box matched, no verified season-specific Division I membership filter",
            "possessions":"box estimate FG including OT, not play-by-play possessions",
            "official_counted":0,"approved_stake_u":0,"seasons":{}}
    for season in seasons:
        s=root/f"mbb_schedule_{season}.parquet";b=root/f"team_box_{season}.parquet"
        gs,census,rejects=schedule_games(pq.read_table(s,columns=list(SCHED)).to_pylist(),
                                       pq.read_table(b,columns=list(BOX)).to_pylist(),season)
        rows=walk(gs)
        summary=summarize(rows)
        if not summary["forecast_n"]:
            raise ValueError(f"no matched forecasts for {season}")
        report["seasons"][str(season)]={"source_sha256":{"schedule":digest(s),"box":digest(b)},
              "source_url":{"schedule":f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_mens_college_basketball_schedules/{s.name}",
                            "box":f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_mens_college_basketball_team_boxscores/{b.name}"},
              "census":census,"rejected_schedule_events":rejects,"summary":summary,"rows":rows}
        print(json.dumps({"season":season,"census":census,"summary":summary},allow_nan=False,sort_keys=True))
    atomic_publish(output,(json.dumps(report,allow_nan=False,sort_keys=True)+"\n").encode())


class Regression(unittest.TestCase):
    def fixture(self):
        d=date(2024,1,1)
        s=dict(game_id=1,season=2024,game_date=d,home_id=10,away_id=20,
               home_score=80,away_score=70,neutral_site=True,status_type_completed=True,status_type_name="STATUS_FINAL")
        b=dict(game_id=1,season=2024,game_date=d,team_id=10,opponent_team_id=20,
               team_home_away="home",team_score=80,opponent_team_score=70,
               field_goals_attempted=60,free_throws_attempted=20,turnovers=12,offensive_rebounds=10)
        a=dict(b,team_id=20,opponent_team_id=10,team_home_away="away",team_score=70,opponent_team_score=80)
        return s,b,a
    def test_join_and_duplicate_hold(self):
        s,b,a=self.fixture()
        gs,c,_=schedule_games([s],[b,a],2024)
        self.assertAlmostEqual(gs[0]["possessions"],70.8)
        self.assertTrue(gs[0]["neutral"])
        self.assertIsNone(schedule_games([s],[b,a,b],2024)[0][0]["possessions"])
        self.assertEqual(schedule_games([s,s],[b,a],2024)[0],[])
    def test_missing_box_retains_schedule(self):
        s,b,a=self.fixture()
        gs,_,_=schedule_games([s],[b,dict(a,turnovers=None)],2024)
        self.assertEqual(len(gs),1)
        self.assertIsNone(gs[0]["possessions"])
    def test_orientation_and_venue(self):
        s,b,a=self.fixture()
        self.assertIsNone(schedule_games([s],[dict(b,opponent_team_id=30),a],2024)[0][0]["possessions"])
        self.assertEqual(schedule_games([dict(s,neutral_site=None)],[b,a],2024)[0],[])
    def test_context_native_formula_and_neutral(self):
        s,b,a=self.fixture();g=schedule_games([s],[b,a],2024)[0][0]
        ctx=context([g]*160,8)
        p=compare(ctx,"10","20",neutral=True)
        self.assertEqual(p["additive_product"]["hca_applied"],0)
        self.assertAlmostEqual(p["additive_product"]["possessions"],70.8)
    def test_later_and_same_date_box_do_not_change_forecast(self):
        s,b,a=self.fixture();g=schedule_games([s],[b,a],2024)[0][0]
        base=[dict(g,event_id=str(i+10)) for i in range(150)]
        target=dict(g,event_id="target",day=g["day"]+timedelta(days=3))
        same=dict(target,event_id="same",home_points=200,margin=130,total=270)
        first=[r for r in walk(base+[target]) if r["event_id"]=="target"][0]
        second=[r for r in walk(base+[target,same]) if r["event_id"]=="target"][0]
        self.assertEqual(first["forecasts"],second["forecasts"])
        self.assertTrue(first["forecasts"])
        missing=[r for r in walk(base+[dict(target,possessions=None)]) if r["event_id"]=="target"][0]
        self.assertEqual(first["forecasts"],missing["forecasts"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--root",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--seasons",nargs="+",type=int,default=list(range(2019,2026)))
    a=parser.parse_args()
    if a.self_test:
        unittest.main(argv=[__file__],verbosity=2)
    else:
        if a.root is None or a.output is None: parser.error("root and output required")
        run(a.root,a.output,a.seasons)
