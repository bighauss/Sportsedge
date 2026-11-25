"""Research-only paired fixed-origin comparison; no runner/ledger/odds changes.

Input CSV: one completed game per row with game_id, home_id, away_id,
tip_utc, observed_final_utc, home_points, away_points, home_possessions,
away_possessions, neutral (0/1). IDs must be stable, timestamps offset-aware.
observed_final_utc is an actual evidence-availability clock, NEVER a fabricated
historical timestamp. A retrospective archive with no such clock cannot
qualify for this strict replay. Input normalization is a separate lane.

Usage: python paired_holdout_audit.py games.csv --cutoff ISO --asof ISO
       --output-dir new_directory [--prior-games 3 --ridge 10]
Prior strength and ridge penalty must be fixed without consulting holdout.
This fixed-origin research comparison does not establish betting profitability.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

MODELS = ("raw", "both_sides", "shrinkage", "schedule_ridge")

def stamp(s):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.utcoffset() is None:
        raise ValueError("timestamp requires offset")
    return d.astimezone(timezone.utc)

def number(s, positive=False):
    v = float(s)
    if not math.isfinite(v) or v < 0 or (positive and v <= 0):
        raise ValueError("invalid numeric input")
    return v

def load_games(raw):
    rows = []
    seen = set()
    for index, r in enumerate(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))), 2):
        try:
            gid, h, a = (r[k].strip() for k in ("game_id", "home_id", "away_id"))
            if not gid or not h or not a or h == a or gid in seen:
                raise ValueError("duplicate game or invalid identity")
            tip, observed = stamp(r["tip_utc"]), stamp(r["observed_final_utc"])
            if observed <= tip:
                raise ValueError("final observed before game")
            hp, ap = (number(r[k]) for k in ("home_points", "away_points"))
            if hp == ap or hp != int(hp) or ap != int(ap):
                raise ValueError("invalid completed basketball score")
            poss = (number(r["home_possessions"], True) + number(r["away_possessions"], True)) / 2
            if r["neutral"] not in ("0", "1"):
                raise ValueError("unknown venue")
            rows.append(dict(gid=gid,h=h,a=a,tip=tip,observed=observed,hp=hp,ap=ap,
                             poss=poss,neutral=r["neutral"]=="1"))
            seen.add(gid)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"input row {index}: {exc}") from exc
    if not rows:
        raise ValueError("no games")
    return rows

def fit(games, prior, penalty):
    if not games or not math.isfinite(prior) or not math.isfinite(penalty) or min(prior,penalty)<=0:
        raise ValueError("training or hyperparameter invalid")
    accum = defaultdict(lambda: np.zeros(4))
    for g in games:
        for team, points, against in ((g["h"],g["hp"],g["ap"]),(g["a"],g["ap"],g["hp"])):
            accum[team] += [1,g["poss"],points,against]
    mu = 100*sum(v[2] for v in accum.values())/sum(v[1] for v in accum.values())
    if mu <= 0:
        raise ValueError("invalid league scoring rate")
    ratings = {}
    for t,(n,p,off,deff) in accum.items():
        pace = p/n
        o,d = 100*off/p,100*deff/p
        ratings[t] = (n,pace,o,d,(n*o+prior*mu)/(n+prior),(n*d+prior*mu)/(n+prior))
    # Joint offense and opponent-defense effects; ridge shrinks both to zero.
    teams = sorted(accum)
    idx = {t:i for i,t in enumerate(teams)}
    k = len(teams)
    x = np.zeros((2*len(games),2*k+1))
    y = np.zeros(len(x))
    for i,g in enumerate(games):
        for j,(t,o,pts,sign) in enumerate(((g["h"],g["a"],g["hp"],1),(g["a"],g["h"],g["ap"],-1))):
            row = 2*i+j
            x[row,idx[t]]=1
            x[row,k+idx[o]]=1
            x[row,-1]=0 if g["neutral"] else sign
            y[row]=100*pts/g["poss"]-mu
    beta = np.linalg.solve(x.T@x+penalty*np.eye(x.shape[1]),x.T@y)
    return ratings,mu,idx,beta

def predict(fitted,g):
    ratings,mu,idx,beta=fitted
    h,a=g["h"],g["a"]
    if h not in ratings or a not in ratings:
        return None,"MISSING_TRAINING_TEAM"
    hn,hp,ho,hd,hso,hsd=ratings[h]
    an,ap,ao,ad,aso,asd=ratings[a]
    if min(hn,an)<3:
        return None,"INSUFFICIENT_TRAINING_GAMES"
    pace=(hp+ap)/2
    k=len(idx)
    venue=0 if g["neutral"] else beta[-1]
    rates={
        "raw":(ho,ao),
        "both_sides":(ho*ad/mu,ao*hd/mu),
        "shrinkage":(hso*asd/mu,aso*hsd/mu),
        "schedule_ridge":(mu+beta[idx[h]]+beta[k+idx[a]]+venue,
                          mu+beta[idx[a]]+beta[k+idx[h]]-venue)
    }
    if any(not math.isfinite(v) or v<=0 for pair in rates.values() for v in pair):
        return None,"INVALID_RATE"
    return {m:(p*pace/100,q*pace/100) for m,(p,q) in rates.items()},"SCORED"

def replay(games,cutoff,asof,prior,penalty):
    if asof<=cutoff:
        raise ValueError("asof must be after cutoff")
    training=[g for g in games if g["tip"]<cutoff and g["observed"]<cutoff]
    fitted=fit(training,prior,penalty)
    rows=[]
    errors=defaultdict(list)
    for g in sorted(games,key=lambda g:(g["tip"],g["gid"])):
        if not cutoff<=g["tip"]<asof:
            continue
        row=dict(game_id=g["gid"],tip=g["tip"].isoformat(),home_id=g["h"],away_id=g["a"])
        if g["observed"]>asof:
            row["status"]="FINAL_NOT_AVAILABLE"
        else:
            preds,status=predict(fitted,g)
            row["status"]=status
            row.update(actual_home=g["hp"],actual_away=g["ap"])
            if preds:
                for m,(h,a) in preds.items():
                    row.update({m+"_home":h,m+"_away":a})
                    for target,err in (("margin",(h-a)-(g["hp"]-g["ap"])),
                                       ("total",h+a-g["hp"]-g["ap"]),
                                       ("home",h-g["hp"]),("away",a-g["ap"])):
                        row[m+"_"+target+"_error"]=err
                        errors[m,target].append(err)
        rows.append(row)
    metrics={}
    for (m,target),e in errors.items():
        v=np.asarray(e)
        metrics.setdefault(m,{})[target]=dict(n=len(v),mae=float(np.abs(v).mean()),
            rmse=float(np.sqrt(np.square(v).mean())),bias=float(v.mean()))
    return rows,dict(training_games=len(training),holdout_games=len(rows),
        dispositions=dict(Counter(r["status"] for r in rows)),metrics=metrics)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("games",type=Path)
    p.add_argument("--cutoff",required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--output-dir",required=True,type=Path)
    p.add_argument("--prior-games",default=3,type=float)
    p.add_argument("--ridge",default=10,type=float)
    a=p.parse_args()
    raw=a.games.read_bytes()
    cutoff,asof=stamp(a.cutoff),stamp(a.asof)
    rows,report=replay(load_games(raw),cutoff,asof,a.prior_games,a.ridge)
    report.update(label="PAPER_0U_RESEARCH_FIXED_ORIGIN",input_sha256=hashlib.sha256(raw).hexdigest(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        cutoff=cutoff.isoformat(),asof=asof.isoformat(),prior_games=a.prior_games,ridge=a.ridge,
        generated_utc=datetime.now(timezone.utc).isoformat(),numpy_version=np.__version__,
        limitations="Normalized input clock and identity provenance require independent audit; no odds or probability calibration.")
    a.output_dir.mkdir(parents=True,exist_ok=False)
    fields=list(dict.fromkeys(k for r in rows for k in r)) or ["game_id","status"]
    with (a.output_dir/"paired_rows.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    (a.output_dir/"metrics.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=="__main__":
    main()
