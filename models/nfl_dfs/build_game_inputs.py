"""Build RESEARCH-ONLY Showdown inputs from frozen nflverse PBP snapshots.

The manifest identifies the frozen PBP CSV, roster ID map, template game JSON,
kickoff time, source SHA256 hashes and capture timestamps. Only plays from
games strictly before the target date are used. This is NOT a live projection
update and never uses DK AvgPointsPerGame, FanDuel points, or ownership.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path

PBP_COLUMNS = ("game_id","game_date","posteam","season_type",
    "pass_attempt","rush_attempt","complete_pass","pass_touchdown",
    "rush_touchdown","interception","fumble_lost","passing_yards",
    "receiving_yards","rushing_yards","passer_player_id","receiver_player_id",
    "rusher_player_id","yardline_100")
ROSTER_COLUMNS = ("player_name","team","gsis_id","position")


class Blocked(ValueError):
    pass


def utc(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z","+00:00"))
        if dt.tzinfo is None: raise ValueError("timezone missing")
        return dt.astimezone(timezone.utc)
    except (ValueError, AttributeError) as ex:
        raise Blocked(f"Invalid UTC timestamp {iso!r}") from ex


def verified(root, manifest, key, kickoff):
    spec = manifest.get(key)
    if not isinstance(spec, dict) or not all(x in spec for x in ("path","sha256","captured_at_utc")):
        raise Blocked(f"{key}: path/hash/capture timestamp required")
    path = (root / spec["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise Blocked("Disallowed path traversal")
    if utc(spec["captured_at_utc"]) >= kickoff:
        raise Blocked(f"{key}: not captured pre-kickoff")
    if hashlib.sha256(path.read_bytes()).hexdigest() != spec["sha256"]:
        raise Blocked(f"{key}: SHA256 mismatch")
    return path


def records(path, required):
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        if not set(required).issubset(reader.fieldnames or ()):
            raise Blocked(f"{path.name}: missing {set(required)-set(reader.fieldnames or ())}")
        return list(reader)


def val(row, name):
    raw=row.get(name,"")
    if raw=="" or raw is None: return 0.0   # null means N/A on different play types
    try: v=float(raw)
    except (TypeError,ValueError) as ex: raise Blocked(f"Bad {name}: {raw!r}") from ex
    if not math.isfinite(v) or abs(v)>100000: raise Blocked(f"Invalid {name} value")
    return v


def build(manifest_path, lookback=5, min_games=3):
    if not (1<=min_games<=lookback): raise Blocked("Invalid lookback")
    manifest_path=Path(manifest_path).resolve()
    root=manifest_path.parent
    m=json.loads(manifest_path.read_text(encoding="utf-8"))
    kickoff=utc(m["kickoff_utc"])
    paths={key:verified(root,m,key,kickoff) for key in ("pbp","roster","template")}
    cfg=json.loads(paths["template"].read_text(encoding="utf-8"))
    teams=list(cfg["teams"])
    if len(teams)!=2 or len(set(teams))!=2: raise Blocked("Exactly two teams required")
    roster=records(paths["roster"],ROSTER_COLUMNS)
    identities={}
    for r in roster:
        if r["team"] not in teams: continue
        pid=r["gsis_id"]
        if not pid or (pid in identities and identities[pid]!=(r["player_name"],r["team"])):
            raise Blocked("Ambiguous GSIS player ID")
        identities[pid]=(r["player_name"],r["team"])
    for name,p in cfg["players"].items():
        if p["pos"] not in ("K","DST") and (name,p["team"]) not in identities.values():
            raise Blocked(f"Player not bound to GSIS: {name}")
    all_plays=records(paths["pbp"],PBP_COLUMNS)
    tracked={}
    for tm in teams:
        games={}
        for r in all_plays:
            if r["posteam"]!=tm or r["season_type"]!="REG": continue
            try: day=datetime.strptime(r["game_date"],"%Y-%m-%d").date()
            except ValueError as ex: raise Blocked("Invalid game date") from ex
            if day >= kickoff.date():
                raise Blocked(f"Current/future game present: {r['game_id']}")
            gid=r["game_id"]
            if not gid: raise Blocked("Missing game ID")
            games.setdefault(gid,(day,[]))[1].append(r)
        most_recent=sorted(games.values(),key=lambda x:x[0],reverse=True)[:lookback]
        if len(most_recent)<min_games: raise Blocked(f"{tm}: insufficient prior games")
        tracked[tm]=(len(most_recent),[r for _,game in most_recent for r in game])

    diagnostics={}
    for tm,(n_games,plays) in tracked.items():
        passes=[r for r in plays if val(r,"pass_attempt")==1]
        rushes=[r for r in plays if val(r,"rush_attempt")==1]
        if len(passes)<n_games*12 or len(rushes)<n_games*8:
            raise Blocked(f"{tm}: PBP volume incomplete")
        qb=cfg["teams"][tm]["qb"]
        qids={pid for pid,name_team in identities.items() if name_team==(qb,tm)}
        if len(qids)!=1 or sum(r["passer_player_id"] in qids for r in passes)/len(passes)<.75:
            raise Blocked(f"{tm}: QB identity/usage incompatible with template")
        target,catch,rec_y,rec_td,rz=Counter(),Counter(),Counter(),Counter(),Counter()
        carry,rush_y,rush_td,gl=Counter(),Counter(),Counter(),Counter()
        for r in passes:
            name,actual_team=identities.get(r["receiver_player_id"],("_other",tm))
            if actual_team!=tm: raise Blocked("Receiver identity belongs to wrong team")
            target[name]+=1
            if val(r,"complete_pass")==1:
                catch[name]+=1
                rec_y[name]+=val(r,"receiving_yards")
            rec_td[name]+=val(r,"pass_touchdown")
            if 0<val(r,"yardline_100")<=20: rz[name]+=1
        for r in rushes:
            name,actual_team=identities.get(r["rusher_player_id"],("_other",tm))
            if actual_team!=tm: raise Blocked("Rusher identity belongs to wrong team")
            carry[name]+=1
            rush_y[name]+=val(r,"rushing_yards")
            rush_td[name]+=val(r,"rush_touchdown")
            if 0<val(r,"yardline_100")<=5: gl[name]+=1
        team_catch=sum(catch.values())/len(passes)
        avg_rec=sum(rec_y.values())/max(1,sum(catch.values()))
        avg_rush=sum(rush_y.values())/len(rushes)
        if not (.2<=team_catch<=.95 and avg_rec>0 and avg_rush>0):
            raise Blocked(f"{tm}: implausible team efficiencies")
        new={
            "pass_att":round(len(passes)/n_games,4),
            "rush_att":round(len(rushes)/n_games,4),
            "pass_td":round(sum(val(r,"pass_touchdown") for r in passes)/n_games,4),
            "rush_td":round(sum(val(r,"rush_touchdown") for r in rushes)/n_games,4),
            "int_rate":round(sum(val(r,"interception") for r in passes)/len(passes),6),
            "fum_lost":round(sum(val(r,"fumble_lost") for r in plays)/n_games,4),
            "targets":dict(target),
            "rush":dict(carry),
            "recv":{"_default":[round(team_catch,5),round(avg_rec,5)]},
            "ypc":{},
            "pass_td_w":{},
            "rush_td_w":{}
        }
        for name,n in target.items():
            new["recv"][name]=[
                round((catch[name]+3*team_catch)/(n+3),5),
                round((rec_y[name]+3*avg_rec)/(catch[name]+3),5)]
            new["pass_td_w"][name]=round(3*rec_td[name]+.15*rz[name]+.02*n,5)
        for name,n in carry.items():
            new["ypc"][name]=round((rush_y[name]+4*avg_rush)/(n+4),5)
            new["rush_td_w"][name]=round(3*rush_td[name]+.15*gl[name]+.02*n,5)
        if not new["pass_td_w"] or not new["rush_td_w"]:
            raise Blocked(f"{tm}: empty TD redistribution pools")
        cfg["teams"][tm].update(new)
        diagnostics[tm]={"prior_games":n_games,"plays":len(plays),
                         "unbound_targets":target["_other"],"unbound_carries":carry["_other"]}

    ngs=None
    if "ngs_receiving" in m:
        path=verified(root,m,"ngs_receiving",kickoff)
        rows=records(path,("season","week","player_gsis_id","team_abbr",
                            "targets","receptions"))
        ngs={"rows":len(rows),
             "matched_player_ids":len({r["player_gsis_id"] for r in rows
                if r["player_gsis_id"] in identities and r["team_abbr"] in teams
                and r["week"]!="0"}),
             "use":"diagnostic only; no uncalibrated NGS multiplier"}
    cfg["_auto_build"]={
        "status":"PAPER_RESEARCH_ONLY", "kickoff_utc":m["kickoff_utc"],
        "pre_game_only":True,"team_coverage":diagnostics,
        "sources":{k:{"sha256":m[k]["sha256"],"captured_at_utc":m[k]["captured_at_utc"]}
            for k in ("pbp","roster","template","ngs_receiving") if k in m},
        "ngs":ngs,
        "assumptions":"5-game mean and explicit catch/rush shrinkage (pseudo samples 3/4); UNCALIBRATED",
        "preserved_manual":["market","weather","players.p_active",
                            "fg accuracy","DST turnover/TD parameters"],
        "provider_fantasy_points_used":False}
    return cfg


def main():
    p=argparse.ArgumentParser()
    p.add_argument("manifest",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--lookback",type=int,default=5)
    p.add_argument("--min-games",type=int,default=3)
    a=p.parse_args()
    cfg=build(a.manifest,a.lookback,a.min_games)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    if a.out.resolve()==(a.manifest.parent / cfg["salary_file"]).resolve():
        raise Blocked("Cannot overwrite owner DK salaries")
    a.out.write_text(json.dumps(cfg,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PAPER","output":str(a.out),"audit":cfg["_auto_build"]},indent=2))


if __name__=="__main__":
    main()
