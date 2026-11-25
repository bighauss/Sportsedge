"""Date-lagged historical matchup benchmark; never a live forecast bundle.

Public reconstructed boxes have no original observed-final timestamps. Use only
games at least two calendar days earlier, evaluate on appearance-conditional
common rows, and compare fixed matchup heuristic to matched-window ablations.
"""
import argparse, csv, json, math, hashlib
from collections import defaultdict, Counter, deque
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

STATS = ("POINTS", "REBOUNDS", "ASSISTS", "THREES")
COMBOS = {"PRA": (0,1,2), "PR": (0,1), "PA": (0,2), "RA": (1,2)}
FAMILIES = {**{k:(i,) for i,k in enumerate(STATS)}, **COMBOS}
DIAGNOSTIC_LINES = {"POINTS":9.5,"REBOUNDS":4.5,"ASSISTS":2.5,"THREES":1.5,
                    "PRA":14.5,"PR":12.5,"PA":11.5,"RA":5.5}


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
    blocks = defaultdict(lambda:[0,0.,0.])
    windows = Counter()
    residuals = defaultdict(lambda:deque(maxlen=60))
    pending = deque()
    prob_metrics = defaultdict(lambda:[0,0.,0.,0.,0.])
    paired_games, paired = set(), 0
    cursor = 0
    for day,gid,h,a,poss,players,totals in eligible:
        while pending and pending[0][0] <= day-timedelta(days=2):
            _, key, err = pending.popleft()
            residuals[key].append(err)
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
            plain = [mean(x["stats"][s] for x,_ in past) for s in STATS]
            pace_only = [v*adj for v in plain]
            defense_only = [v*factors[i] for i,v in enumerate(plain)]
            match = [v*adj*factors[i] for i,v in enumerate(plain)]
            for candidate in (pace_only, defense_only, match):
                candidate[3] = min(candidate[3],candidate[0]/3)
            windows[len(past)] += 1
            actual = [r["stats"][s] for s in STATS]
            paired+=1;paired_games.add(gid)
            # Fixed illustrative half-lines; compare on common conditional rows.
            key = (t,pid)
            prior_errs = residuals[key]
            if len(prior_errs) >= 20:
                samples = []
                for err in prior_errs:
                    draw = [max(0,round(v+e)) for v,e in zip(match,err)]
                    draw[3] = min(draw[3],draw[0]//3)
                    samples.append(draw)
                for fam,ix in FAMILIES.items():
                    line = DIAGNOSTIC_LINES[fam]
                    y = int(sum(actual[i] for i in ix)>line)
                    baseline_wins = sum(sum(x["stats"][STATS[i]] for i in ix)>line for x,_ in past)
                    candidate_wins = sum(sum(draw[i] for i in ix)>line for draw in samples)
                    for name,wins,n in (("empirical_recent",baseline_wins,len(past)),
                                        ("matchup_residual",candidate_wins,len(samples))):
                        p = (wins+0.5)/(n+1)
                        v = prob_metrics[(fam,name)]
                        v[0]+=1;v[1]+=(p-y)**2;v[2]+=-(y*math.log(p)+(1-y)*math.log1p(-p))
                        v[3]+=p;v[4]+=y
            pending.append((day,key,tuple(a-m for a,m in zip(actual,match))))
            for fam,ix in FAMILIES.items():
                baseline_error = sum(plain[i]-actual[i] for i in ix)
                week = day.isocalendar()[:2]
                for name,pred in (("last5",native),("last8",roll),("plain10",plain),
                                  ("pace_only10",pace_only),("defense_only10",defense_only),
                                  ("matchup10",match)):
                    e = sum(pred[i]-actual[i] for i in ix)
                    v = errors[(fam,name)]
                    v[0]+=1;v[1]+=abs(e);v[2]+=e*e;v[3]+=e
                    b = blocks[(fam,name,week)]
                    b[0]+=1;b[1]+=abs(e)-abs(baseline_error);b[2]+=e*e-baseline_error*baseline_error
    metrics={}
    for (fam,name),(n,ae,se,bias) in errors.items():
        metrics.setdefault(fam,{})[name]={"n":n,"mae":ae/n,"rmse":math.sqrt(se/n),"bias":bias/n}
    paired_deltas = {}
    for fam, variants in metrics.items():
        paired_deltas[fam] = {}
        for name in variants:
            data = [v for (f,m,w),v in sorted(blocks.items()) if f==fam and m==name]
            n = sum(v[0] for v in data)
            paired_deltas[fam][name] = {"delta_mae_vs_plain10":sum(v[1] for v in data)/n,
                                        "delta_mse_vs_plain10":sum(v[2] for v in data)/n,
                                        "week_blocks":len(data),
                                        "weeks_better_mae":sum(v[1]<0 for v in data)}
    probability = {}
    for (fam,name),(n,bs,ll,p,y) in prob_metrics.items():
        probability.setdefault(fam,{"diagnostic_line":DIAGNOSTIC_LINES[fam]})[name] = {
            "n":n,"brier":bs/n,"log_loss":ll/n,"mean_probability":p/n,"observed_rate":y/n}
    return {"eligible_games":len(eligible),"paired_games":len(paired_games),"paired_appearances":paired,
            "window_counts":dict(windows),"rejections":dict(rejects),"metrics":metrics,
            "paired_ablation_deltas":paired_deltas,"probability_diagnostics":probability}


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
        "Common rows require eight appearances; plain10, pace-only, defense-only and combined use the identical up-to-ten window.",
        "Reused 2023–2025 seasons are development evidence, not untouched holdout; week counts are descriptive, not significance tests.",
        "Probability diagnostics require twenty prior matchup residuals for the same player/team, capped at sixty; two-day lag, fixed illustrative half-lines, no actual odds.",
        "No confirmed availability, odds, ROI or promotion.",
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
