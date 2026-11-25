"""Date-lagged historical matchup benchmark; never a live forecast bundle.

Public reconstructed boxes have no original observed-final timestamps. Use only
games at least two calendar days earlier, evaluate on appearance-conditional
common rows, and compare fixed matchup heuristic to last-five and last-eight.
"""
import argparse, csv, json, math, hashlib
from collections import defaultdict, Counter, deque
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

STATS = ("POINTS", "REBOUNDS", "ASSISTS", "THREES")
COMBOS = {"PRA": (0,1,2), "PR": (0,1), "PA": (0,2), "RA": (1,2)}
FAMILIES = {**{k:(i,) for i,k in enumerate(STATS)}, **COMBOS}


def evaluate(records, pace_rows):
    games, rejects = defaultdict(list), Counter()
    for r in records:
        games[r["game_id"]].append(r)
    pace = {}
    for r in pace_rows:
        gid = r["event_id"]
        if gid in pace:
            raise ValueError("DUPLICATE_PACE_GAME")
        pace[gid] = r
    eligible = []
    for gid, players in games.items():
        try:
            p = pace[gid]
            d = date.fromisoformat(p["day"])
            h,a = p["home"],p["away"]
            poss = float(p["possessions"])
            if not 30 <= poss <= 150 or h == a or any(r["day"] != d or r["team_id"] not in (h,a) for r in players):
                raise ValueError("IDENTITY_OR_PACE")
            totals = {t:tuple(sum(r["stats"][s] for r in players if r["team_id"] == t) for s in STATS) for t in (h,a)}
            if totals[h][0] != int(p["home_points"]) or totals[a][0] != int(p["away_points"]):
                raise ValueError("PLAYER_POINTS_NOT_RECONCILED")
            if not all(any(r["team_id"] == t for r in players) for t in (h,a)):
                raise ValueError("MISSING_TEAM")
            eligible.append((d,gid,h,a,poss,players,totals))
        except (ValueError,TypeError,KeyError) as exc:
            rejects[str(exc) if not isinstance(exc,KeyError) else "PACE_GAME_MISSING"] += 1
    eligible.sort(key=lambda g:(g[0],g[1]))
    recent, team_pace = defaultdict(lambda:deque(maxlen=10)), defaultdict(lambda:deque(maxlen=10))
    defense, league = defaultdict(lambda:[0,[0.]*4]), [0,[0.]*4]
    errors = defaultdict(lambda:[0,0.,0.,0.])
    paired_games, paired = set(), 0
    cursor = 0
    for day,gid,h,a,poss,players,totals in eligible:
        while cursor < len(eligible) and eligible[cursor][0] <= day-timedelta(days=2):
            _,_,ph,pa,pp,ps,ts = eligible[cursor]
            for t,o in ((ph,pa),(pa,ph)):
                team_pace[t].append(pp)
                defense[t][0]+=1; league[0]+=1
                for i,v in enumerate(ts[o]):
                    defense[t][1][i]+=v/pp; league[1][i]+=v/pp
            for r in ps:
                recent[(r["team_id"],r["player_id"])].append((r,pp))
            cursor+=1
        for r in players:
            t,pid = r["team_id"],r["player_id"]
            o = a if t == h else h
            past = list(recent[(t,pid)])
            if len(past)<8 or min(len(team_pace[t]),len(team_pace[o]))<5:
                rejects["INSUFFICIENT_PRIOR_PLAYER_OR_TEAM"]+=1
                continue
            if len({x[0]["day"] for x in past})!=len(past):
                rejects["AMBIGUOUS_PRIOR_SAME_DAY"]+=1
                continue
            n, allowed = defense[o]
            lgn, lgs = league
            factors = [((allowed[i]+10*lgs[i]/lgn)/(n+10))/(lgs[i]/lgn) if lgs[i]>0 else 1. for i in range(4)]
            adj = (mean(team_pace[t])+mean(team_pace[o]))/2/mean(p for _,p in past)
            native = [mean(x["stats"][s] for x,_ in past[-5:]) for s in STATS]
            roll = [mean(x["stats"][s] for x,_ in past[-8:]) for s in STATS]
            match = [mean(x["stats"][s] for x,_ in past)*adj*factors[i] for i,s in enumerate(STATS)]
            match[3] = min(match[3],match[0]/3)
            actual = [r["stats"][s] for s in STATS]
            paired+=1;paired_games.add(gid)
            for fam,ix in FAMILIES.items():
                for name,pred in (("last5",native),("last8",roll),("matchup10",match)):
                    e = sum(pred[i]-actual[i] for i in ix)
                    v = errors[(fam,name)]
                    v[0]+=1;v[1]+=abs(e);v[2]+=e*e;v[3]+=e
    metrics={}
    for (fam,name),(n,ae,se,bias) in errors.items():
        metrics.setdefault(fam,{})[name]={"n":n,"mae":ae/n,"rmse":math.sqrt(se/n),"bias":bias/n}
    return {"eligible_games":len(eligible),"paired_games":len(paired_games),"paired_appearances":paired,
            "rejections":dict(rejects),"metrics":metrics}


def main():
    import pyarrow.parquet as pq
    # Existing independently reviewed #519 source admission functions.
    from research.cbb_public_player_backtest import schedule, admit, SCHED
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--pace-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--seasons",nargs="+",type=int,default=[2023,2024,2025])
    args=p.parse_args()
    result={"label":"PAPER_0U_NON_COUNTED_DATE_LAG_REPLAY","limitations":[
        "Two-calendar-day lag proxy, not original observation times; appearance-conditional only.",
        "Team opponent rates sum admitted player stats; points must reconcile, rebounds exclude team-only rebounds.",
        "Common rows require eight appearances; no confirmed availability, odds, ROI or promotion.",
        "Public-date benchmark of the heuristic, not exact prospective player bundle."],"seasons":{}}
    for season in args.seasons:
        sched=args.root/f"mbb_schedule_{season}.parquet"
        box=args.root/f"player_box_{season}.csv"
        pace=args.pace_root/f"games_{season}.csv"
        games,sc=schedule(pq.read_table(sched,columns=list(SCHED)).to_pylist(),season)
        with box.open(newline="",encoding="utf-8-sig") as f:
            records, census,_=admit(csv.DictReader(f),games,season)
        with pace.open(newline="") as f:
            report=evaluate(records,csv.DictReader(f))
        if not report["paired_appearances"]:
            raise ValueError("NO_PAIRED_MATCHUP_ROWS")
        report.update(schedule_census=sc,player_census=census,
                      input_sha256={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (sched,box,pace)})
        result["seasons"][str(season)]=report
        print(json.dumps({"season":season,**report},sort_keys=True),flush=True)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=1,allow_nan=False))


if __name__=="__main__":
    main()
