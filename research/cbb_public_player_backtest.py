"""Public historical conditional player evaluation of native last-4/5 means.

Reconstructed schedule + player boxes, not pretip roster or original CBBD data.
Do not import into live pricing. Compare on common appearance-conditional rows.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import mean
import tempfile
import unittest
from cbbd_player_history import historical_baselines
from research import cbb_player_distribution as distribution

SCHED=("game_id","season","game_date","home_id","away_id","home_score","away_score","status_type_completed","status_type_name")
CORE={"POINTS":"points","REBOUNDS":"rebounds","ASSISTS":"assists","THREES":"three_point_field_goals_made"}
EXTRA={"STEALS":"steals","BLOCKS":"blocks","TURNOVERS":"turnovers"}
STATS=("MINUTES",*CORE,"PRA","PR","PA","RA",*EXTRA)
PLAYER_FIELDS=("game_id","season","game_date","athlete_id","team_id","minutes",*CORE.values(),*EXTRA.values())

def ident(x):
    if type(x) is int and x>0:return str(x)
    if type(x) is str and x.isascii() and x.isdigit() and x==str(int(x)) and int(x)>0:return x
    raise ValueError("INVALID_ID")

def number(x, *, count=False):
    if isinstance(x,bool):raise ValueError("INVALID_STAT")
    try:v=float(x)
    except (TypeError,ValueError):raise ValueError("INVALID_STAT")
    if not math.isfinite(v) or not 0<=v<=250 or (count and not v.is_integer()):raise ValueError("INVALID_STAT")
    return int(v) if count else v

def field_number(r, col, label, *, count=False):
    """Keep absent source values separate from malformed observed values."""
    raw=r.get(col)
    if raw is None or (isinstance(raw,str) and not raw.strip()):
        raise ValueError("MISSING_"+label)
    try:
        return number(raw,count=count)
    except ValueError:
        raise ValueError("INVALID_"+label) from None

def schedule(rows,season):
    groups=defaultdict(list);counts=Counter()
    for r in rows:
        try:groups[ident(r["game_id"])].append(r)
        except ValueError:counts["INVALID_SCHEDULE_ID"]+=1
    out={}
    for gid,rr in groups.items():
        try:
            if len(rr)!=1:raise ValueError("DUPLICATE_SCHEDULE")
            r=rr[0]
            if r["season"]!=season or r["status_type_completed"] is not True or r["status_type_name"]!="STATUS_FINAL":raise ValueError("NOT_MATCHED_FINAL")
            d=r["game_date"]
            if type(d) is not date:raise ValueError("INVALID_DATE")
            h,a=ident(r["home_id"]),ident(r["away_id"])
            hs,aws=number(r["home_score"],count=True),number(r["away_score"],count=True)
            if h==a or hs==aws:raise ValueError("INVALID_FINAL")
            out[gid]=(d,{h,a})
        except ValueError as e:counts[str(e)]+=1
    return out,dict(counts)

def admit(rows,games,season):
    groups=defaultdict(list);counts=Counter()
    for r in rows:
        counts["input_rows"]+=1
        try:groups[(ident(r["athlete_id"]),ident(r["game_id"]))].append(r)
        except ValueError:counts["INVALID_PLAYER_OR_GAME_ID"]+=1
    clean=[];rejects=[]
    for (pid,gid),rr in groups.items():
        try:
            if len(rr)!=1:raise ValueError("DUPLICATE_PLAYER_GAME_ALL_COPIES")
            r=rr[0];tid=ident(r["team_id"])
            try:d=date.fromisoformat(r["game_date"])
            except (ValueError,TypeError):raise ValueError("INVALID_PLAYER_DATE") from None
            if r["season"]!=str(season) or gid not in games or d!=games[gid][0] or tid not in games[gid][1]:raise ValueError("SCHEDULE_PLAYER_IDENTITY_MISMATCH")
            m=field_number(r,"minutes","MINUTES")
            if m==0:raise ValueError("ZERO_RECORDED_MINUTES_UNKNOWN_PARTICIPATION")
            if m>100:raise ValueError("INVALID_MINUTES_RANGE")
            v={k:field_number(r,col,"CORE_"+k,count=True) for k,col in CORE.items()}
            v["PRA"]=v["POINTS"]+v["REBOUNDS"]+v["ASSISTS"]
            for k,col in EXTRA.items():
                try:v[k]=field_number(r,col,"OPTIONAL_"+k,count=True)
                except ValueError as e:
                    v[k]=None
                    counts[str(e)]+=1
            v.update(PR=v["POINTS"]+v["REBOUNDS"],PA=v["POINTS"]+v["ASSISTS"],RA=v["REBOUNDS"]+v["ASSISTS"])
            clean.append(dict(player_id=pid,game_id=gid,team_id=tid,day=d,minutes=m,stats=v))
        except ValueError as e:
            counts[str(e)]+=len(rr);rejects.append(dict(player_id=pid,game_id=gid,copies=len(rr),reason=str(e)))
    counts["admitted_appearances"]=len(clean)
    return clean,dict(counts),rejects

def walk(records, *, include_distribution=False):
    by_player=defaultdict(list)
    for r in records:by_player[r["player_id"]].append(r)
    out=[]
    for pid,appearances in by_player.items():
        appearances.sort(key=lambda r:(r["day"],r["game_id"]))
        for r in appearances:
            d=r["day"]
            # At least two calendar days; do not infer actual release times.
            prior=[p for p in appearances if p["day"]<=d-timedelta(days=2)]
            row=dict(player_id=pid,game_id=r["game_id"],team_id=r["team_id"],day=d.isoformat(),
                     actual={"MINUTES":r["minutes"],**r["stats"]},forecasts={})
            recent=prior[-8:]
            if len(recent)<5:
                row["hold"]="INSUFFICIENT_PRIOR_APPEARANCES"
            elif len({p["team_id"] for p in recent}|{r["team_id"]})!=1:
                row["hold"]="TEAM_TRANSFER_OR_MIXED_HISTORY"
            elif len({p["day"] for p in recent})!=len(recent):
                row["hold"]="AMBIGUOUS_MULTIPLE_APPEARANCES_SAME_DATE"
            else:
                # Native baseline's ordering uses verified dates, synthetic midnight
                # labels only inside retrospective comparison, not pretip receipts.
                native=[dict(p,game_start_utc=p["day"].isoformat()+"T00:00:00Z",
                             stats={k:p["stats"][k] for k in (*CORE,"PRA")}) for p in recent]
                b=historical_baselines(native)
                if len(b)!=1:raise ValueError("NATIVE_BASELINE_PARITY_FAILED")
                base={"MINUTES":b[0]["mean_minutes"],**{k:v["mean"] for k,v in b[0]["stats"].items()}}
                for k in ("PR","PA","RA",*EXTRA):
                    vals=[p["stats"][k] for p in recent[-5:]]
                    base[k]=mean(vals) if all(v is not None for v in vals) else None
                alt={"MINUTES":mean(p["minutes"] for p in recent)}
                for k in STATS[1:]:
                    vals=[p["stats"][k] for p in recent]
                    alt[k]=mean(vals) if all(v is not None for v in vals) else None
                row["forecasts"]={"native_5":base,"rolling_8":alt}
                row["history_game_ids"]=[p["game_id"] for p in recent]
                if include_distribution:
                    row["prop_distribution"]=distribution.for_history(recent)
            out.append(row)
    return out

def summarize(rows):
    metrics={}
    for k in STATS:
        pairs=[r for r in rows if r["forecasts"] and r["actual"][k] is not None and all(v[k] is not None for v in r["forecasts"].values())]
        metrics[k]={"n":len(pairs)}
        for m in ("native_5","rolling_8"):
            es=[r["forecasts"][m][k]-r["actual"][k] for r in pairs]
            metrics[k][m]={"mae":mean(abs(e) for e in es) if es else None,
                "rmse":math.sqrt(mean(e*e for e in es)) if es else None,
                "bias_pred_minus_actual":mean(es) if es else None}
    return {"attempted":len(rows),"paired_appearances":sum(bool(r["forecasts"]) for r in rows),
            "holds":dict(Counter(r["hold"] for r in rows if "hold" in r)),"metrics":metrics}

def digest(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def publish(path,obj):
    raw=(json.dumps(obj,sort_keys=True,allow_nan=False)+"\n").encode()
    fd,tmp=tempfile.mkstemp(prefix=".player-stage-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
        if Path(tmp).read_bytes()!=raw:raise OSError("STAGED_BYTES_MISMATCH")
        os.link(tmp,path)
        d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:os.unlink(tmp)

def run(args):
    import pyarrow.parquet as pq
    report={"status":"RECONSTRUCTED_CONDITIONAL_PLAYER_RESEARCH_PAPER_0U","approved_stake_u":0,"official_counted":0,
            "code_sha256":digest(Path(__file__)),"limitations":["Observed appearances only; no pregame roster, participation or odds.","Native_5 reuses actual historical_baselines for core six stats; extra combos and steals/blocks/turnovers are research extensions only.","Common sample requires five prior games for both, 8-game window limited to same team; no season-specific Division I filter.","Two-day lag is a retrospective chronology proxy, not authenticated availability."],"seasons":{}}
    for season in args.seasons:
        s=args.root/f"mbb_schedule_{season}.parquet";b=args.root/f"player_box_{season}.csv"
        games,sc=schedule(pq.read_table(s,columns=list(SCHED)).to_pylist(),season)
        with b.open(newline="",encoding="utf-8-sig") as f:
            reader=csv.DictReader(f)
            if not set(PLAYER_FIELDS)<=set(reader.fieldnames or ()):raise ValueError("PLAYER_CSV_SCHEMA_MISMATCH:"+str(reader.fieldnames))
            clean,census,rejects=admit(reader,games,season)
        rows=walk(clean,include_distribution=args.prop_distributions);summary=summarize(rows)
        if args.prop_distributions:
            summary['prop_distributions']=distribution.summary(rows)
            report['distribution_code_sha256']=digest(Path(distribution.__file__))
            report['limitations'].append('Fixed illustrative half-lines, all families use identical (n*p+0.5)/(n+1) smoothing; NB uses explicit Poisson limit for non-overdispersion. Week-block CIs descriptive; no real price or push settlement.')
        if not summary["paired_appearances"]:raise ValueError("NO_PAIRED_APPEARANCES")
        report["seasons"][str(season)]={"schedule_sha256":digest(s),"player_csv_sha256":digest(b),
            "schedule_census":sc,"player_census":census,"rejected_rows":rejects,"summary":summary,"rows":rows}
        print(json.dumps({"season":season,"schedule_census":sc,"player_census":census,"summary":summary},sort_keys=True))
    publish(args.output,report)

class Tests(unittest.TestCase):
    def raw(self,i,day="2024-01-01"):
        return dict(game_id=str(i),season="2024",game_date=day,athlete_id="1",team_id="2",minutes="20",
                    points="10",rebounds="5",assists="3",three_point_field_goals_made="1",steals="1",blocks="0",turnovers="2")
    def test_duplicate_and_identity(self):
        r=self.raw(1);g={"1":(date(2024,1,1),{"2","3"})}
        self.assertEqual(admit([r,dict(r,points="99")],g,2024)[0],[])
        self.assertEqual(admit([dict(r,team_id="4")],g,2024)[0],[])
        self.assertEqual(admit([dict(r,athlete_id="")],g,2024)[0],[])
    def test_nonfinite_no_zero(self):
        r=self.raw(1);g={"1":(date(2024,1,1),{"2","3"})}
        self.assertEqual(admit([dict(r,points="NaN")],g,2024)[0],[])
        self.assertIsNone(admit([dict(r,steals="")],g,2024)[0][0]["stats"]["STEALS"])
    def test_reason_census_distinguishes_missing_invalid_and_zero(self):
        r=self.raw(1);g={"1":(date(2024,1,1),{"2","3"})}
        for changes,reason in (
            ({"minutes":""},"MISSING_MINUTES"),
            ({"minutes":"NaN"},"INVALID_MINUTES"),
            ({"minutes":"0"},"ZERO_RECORDED_MINUTES_UNKNOWN_PARTICIPATION"),
            ({"minutes":"101"},"INVALID_MINUTES_RANGE"),
            ({"points":""},"MISSING_CORE_POINTS"),
            ({"points":"-1"},"INVALID_CORE_POINTS"),
            ({"game_date":None},"INVALID_PLAYER_DATE")):
            clean,census,rejects=admit([dict(r,**changes)],g,2024)
            self.assertEqual(clean,[])
            self.assertEqual(census[reason],1)
            self.assertEqual(rejects[0]["reason"],reason)
        clean,census,_=admit([dict(r,steals="",blocks="NaN")],g,2024)
        self.assertEqual(len(clean),1)
        self.assertEqual(census["MISSING_OPTIONAL_STEALS"],1)
        self.assertEqual(census["INVALID_OPTIONAL_BLOCKS"],1)
        self.assertIsNone(clean[0]["stats"]["STEALS"])
        self.assertIsNone(clean[0]["stats"]["BLOCKS"])
    def test_chronology_and_native(self):
        rs=[self.raw(i,f"2024-01-{i*3:02d}") for i in range(1,7)]
        g={r["game_id"]:(date.fromisoformat(r["game_date"]),{"2","3"}) for r in rs}
        c,_,_=admit(rs,g,2024)
        self.assertEqual(walk(c)[-1]["forecasts"]["native_5"]["POINTS"],10)
        self.assertEqual(walk(c)[-1]["forecasts"]["rolling_8"]["PRA"],18)
        c[-1]["stats"]["POINTS"]=99
        self.assertEqual(walk(c)[-1]["forecasts"]["native_5"]["POINTS"],10)
        c[-1]["day"]=c[-2]["day"]
        self.assertFalse(walk(c)[-1]["forecasts"])
    def test_distribution_uses_prior_only(self):
        rs=[self.raw(i,f"2024-01-{i*3:02d}") for i in range(1,7)]
        g={r["game_id"]:(date.fromisoformat(r["game_date"]),{"2","3"}) for r in rs}
        c,_,_=admit(rs,g,2024)
        a=walk(c,include_distribution=True)[-1]["prop_distribution"]
        c[-1]["stats"]["POINTS"]=99
        b=walk(c,include_distribution=True)[-1]["prop_distribution"]
        self.assertEqual(a,b)
        self.assertEqual(len(a),11)
    def test_transfer_hold(self):
        rs=[self.raw(i,f"2024-01-{i*3:02d}") for i in range(1,7)]
        g={r["game_id"]:(date.fromisoformat(r["game_date"]),{"2","3"}) for r in rs}
        c,_,_=admit(rs,g,2024);c[-1]["team_id"]="3"
        self.assertEqual(walk(c)[-1]["hold"],"TEAM_TRANSFER_OR_MIXED_HISTORY")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--self-test",action="store_true")
    p.add_argument("--prop-distributions",action="store_true")
    p.add_argument("--root",type=Path);p.add_argument("--output",type=Path);p.add_argument("--seasons",nargs="+",type=int,default=[2023,2024,2025]);a=p.parse_args()
    if a.self_test:unittest.main(argv=[__file__],verbosity=2)
    else:
        if a.root is None or a.output is None:p.error("root and output required")
        run(a)
