"""Research nflverse weekly opportunity shares; no bets/model modification."""
from __future__ import annotations
import argparse,csv,gzip,hashlib,io,json,math
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path

class Blocked(ValueError): pass

def utc(s):
    try: d=datetime.fromisoformat(s.replace("Z","+00:00"))
    except (ValueError,AttributeError) as ex: raise Blocked("invalid UTC timestamp") from ex
    if d.utcoffset()!=timedelta(0): raise Blocked("non-UTC timestamp")
    return d

def integer(v,name,hi):
    try: x=int(v)
    except (TypeError,ValueError) as ex: raise Blocked("invalid "+name) from ex
    if isinstance(v,bool) or str(x)!=str(v).strip() or not 0<x<=hi: raise Blocked("invalid "+name)
    return x

def opportunities(v,name):
    try: x=float(v)
    except (ValueError,TypeError) as ex: raise Blocked("missing "+name) from ex
    if not math.isfinite(x) or x!=int(x) or x<0 or x>200: raise Blocked("bad "+name)
    return int(x)

def derive(source_bytes, meta):
    if hashlib.sha256(source_bytes).hexdigest()!=meta.get("source_sha256"): raise Blocked("source SHA256 mismatch")
    if len(source_bytes)>30_000_000: raise Blocked("oversized source")
    if not utc(meta["captured_at_utc"])<utc(meta["kickoff_utc"]): raise Blocked("not captured before kickoff")
    season=integer(meta["season"],"season",2100)
    target=integer(meta["target_week"],"target_week",22)
    if season<2000: raise Blocked("bad season")
    roster=meta.get("roster")
    if not isinstance(roster,list) or not 2<=len(roster)<=200: raise Blocked("explicit GSIS roster required")
    bound={}
    for p in roster:
        if not isinstance(p,dict): raise Blocked("invalid roster record")
        pid,team=p.get("player_id"),p.get("team")
        if not isinstance(pid,str) or not pid.strip() or not isinstance(team,str) or not team.strip() or pid in bound:
            raise Blocked("blank/duplicate GSIS roster ID")
        bound[pid]=team.strip().upper()
    teams=set(bound.values())
    if len(teams)!=2: raise Blocked("exactly two teams required")
    data=source_bytes
    if meta.get("compressed",False):
        try: data=gzip.decompress(source_bytes)
        except (OSError,EOFError) as ex: raise Blocked("corrupt gzip") from ex
    if len(data)>80_000_000: raise Blocked("decompressed source too large")
    try: reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    except UnicodeDecodeError as ex: raise Blocked("not UTF8") from ex
    cols=set(reader.fieldnames or [])
    if not {"season","week","season_type","player_id","targets","carries"}.issubset(cols) or not ({"recent_team","team"} & cols):
        raise Blocked("missing nflverse weekly columns")
    week_rows=defaultdict(dict)
    for r in reader:
        yr=integer(r.get("season"),"row season",2100); w=integer(r.get("week"),"row week",22)
        if yr!=season or r.get("season_type") not in ("REG","REGULAR"): continue
        a=(r.get("team") or "").strip().upper(); b=(r.get("recent_team") or "").strip().upper()
        if a and b and a!=b: raise Blocked("conflicting team values")
        tm=a or b
        if tm not in teams: continue
        if w>=target: raise Blocked("target/future-week data in as-of source")
        pid=(r.get("player_id") or "").strip()
        tar=opportunities(r.get("targets"),"targets"); car=opportunities(r.get("carries"),"carries")
        if (tar or car) and not pid: raise Blocked("unattributed offense")
        if not pid: continue
        if pid in week_rows[(tm,w)]: raise Blocked("duplicate player-week")
        if pid in bound and bound[pid]!=tm: raise Blocked("GSIS team mismatch")
        week_rows[(tm,w)][pid]=(tar,car)
    half=float(meta.get("half_life_days",180)); pseudo=float(meta.get("shrink_pseudo_team_opportunities",20))
    if not math.isfinite(half) or not 7<=half<=730 or not math.isfinite(pseudo) or not 0<=pseudo<=1000:
        raise Blocked("invalid priors")
    minweeks=integer(meta.get("min_prior_weeks",3),"min_prior_weeks",21)
    players=[];coverage={}
    for team in sorted(teams):
        weeks=sorted(w for tm,w in week_rows if tm==team)
        if len(weeks)<minweeks: raise Blocked(team+": insufficient prior weeks")
        total=[0.,0.]; unknown=[0.,0.]; counts=defaultdict(lambda:[0.,0.,0])
        for w in weeks:
            weight=0.5**(((target-w)*7)/half) # weekly spacing is approximate
            for pid,vals in week_rows[(team,w)].items():
                for j in (0,1):
                    total[j]+=vals[j]*weight
                    if pid not in bound: unknown[j]+=vals[j]*weight
                    else: counts[pid][j]+=vals[j]*weight
                if pid in bound: counts[pid][2]+=1
        if total[0]<20 or total[1]<20: raise Blocked(team+": insufficient team opportunities")
        if unknown[0]/total[0]>.15 or unknown[1]/total[1]>.20: raise Blocked(team+": roster coverage insufficient")
        for pid,tm in sorted(bound.items()):
            if tm!=team: continue
            t,c,n=counts[pid]
            if n<2: raise Blocked(pid+": insufficient prior player weeks")
            players.append(dict(player_id=pid,team=team,prior_weeks=n,
                                target_share_raw=round(t/total[0],6),
                                carry_share_raw=round(c/total[1],6),
                                target_share_shrunk=round(t/(total[0]+pseudo),6),
                                carry_share_shrunk=round(c/(total[1]+pseudo),6),
                                snap_share=None,route_share=None))
        coverage[team]=dict(weeks=weeks,unmapped_target_share=round(unknown[0]/total[0],6),
                            unmapped_carry_share=round(unknown[1]/total[1],6))
    return dict(status="PAPER_0U_UNVERIFIED_CAPTURE",source_sha256=meta["source_sha256"],
                captured_at_utc=meta["captured_at_utc"],kickoff_utc=meta["kickoff_utc"],
                season=season,target_week=target,half_life_days=half,
                shrink_pseudo_team_opportunities=pseudo,coverage=coverage,players=players,
                note="No snaps, routes, injuries, market calibration, or proven source authenticity")

def run_manifest(path):
    path=Path(path).resolve()
    m=json.loads(path.read_text(encoding="utf-8"))
    rel=Path(m["source_path"]); full=(path.parent/rel).resolve()
    if rel.is_absolute() or not full.is_relative_to(path.parent) or not full.is_file():
        raise Blocked("source escapes manifest directory")
    return derive(full.read_bytes(),m)

def main():
    p=argparse.ArgumentParser();p.add_argument("manifest",type=Path);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();r=run_manifest(a.manifest)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("x",encoding="utf-8") as f: json.dump(r,f,indent=2,sort_keys=True);f.write("\n")
    print("PAPER / 0u usage features only; no official model changed")
if __name__=="__main__": main()
