"""Research-only identity audit: owner DK -> official game roster -> nflverse GSIS.

Three independent checks: DK draftable identity, published team roster bucket,
and raw nflverse same-team prior player IDs. No fuzzy matching, provider FP
or fantasy-point averaging. Never treats roster listing as final active status.

Manifest JSON: kickoff_utc, season, week, official_roster_source_url, and
weekly/owner_dk/official_roster each with path, sha256, captured_at_utc.
Run: python reconcile_official_roster.py private/manifest.json --out private/report.json
Keep OWNER salary, original raw source, full sensitive reports in PRIVATE storage.
"""
from __future__ import annotations
import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path


class Blocked(ValueError):
    pass


def timestamp(x):
    try:
        v=datetime.fromisoformat(x.replace("Z","+00:00"))
        if v.tzinfo is None: raise ValueError("missing timezone")
        return v.astimezone(timezone.utc)
    except (ValueError,AttributeError) as e:
        raise Blocked("timezone-aware ISO timestamp required") from e


def frozen(root, item, kickoff):
    if not isinstance(item,dict) or not all(k in item for k in ("path","sha256","captured_at_utc")):
        raise Blocked("source path/hash/capture time required")
    p=(root/item["path"]).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise Blocked("invalid source file path")
    if timestamp(item["captured_at_utc"])>=kickoff:
        raise Blocked("source not captured before kickoff")
    if hashlib.sha256(p.read_bytes()).hexdigest()!=item["sha256"]:
        raise Blocked("source digest mismatch")
    return p


def load(path, fields):
    raw=path.read_bytes()
    if len(raw)>14_000_000: raise Blocked("source larger than limit")
    if path.name.endswith(".gz"):
        try: raw=gzip.decompress(raw)
        except (OSError,EOFError) as e: raise Blocked("bad gzip") from e
    if len(raw)>80_000_000: raise Blocked("large uncompressed file")
    try:
        r=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if not set(fields).issubset(r.fieldnames or []):
            raise Blocked("missing columns: "+str(sorted(set(fields)-set(r.fieldnames or []))))
        return list(r)
    except UnicodeError as e:
        raise Blocked("bad CSV encoding") from e


def reconcile(manifest_path):
    path=Path(manifest_path).resolve()
    m=json.loads(path.read_text(encoding="utf-8"))
    root=path.parent
    kickoff=timestamp(m["kickoff_utc"])
    year,week=int(m["season"]),int(m["week"])
    if not 2000<=year<=2100 or not 2<=week<=22:
        raise Blocked("invalid week/season")
    files={k:frozen(root,m[k],kickoff) for k in ("weekly","owner_dk","official_roster")}
    weekly=load(files["weekly"],("player_id","player_display_name","position","team",
                                  "season","week","season_type"))
    dk=load(files["owner_dk"],("Name","TeamAbbrev","Position","ID","Roster Position",
                              "Salary","Game Info","Status"))
    roster=load(files["official_roster"],("dk_name","team","official_name","official_role",
                                         "program_group","nflverse_name"))
    if len({(x["dk_name"],x["team"]) for x in roster})!=len(roster):
        raise Blocked("duplicate official roster mapping")
    official={(x["dk_name"],x["team"]):x for x in roster}
    ids=defaultdict(set)
    for x in weekly:
        try: y,w=int(x["season"]),int(x["week"])
        except ValueError as e: raise Blocked("bad historical week") from e
        if y!=year or w>=week or x["season_type"]!="REG" or not x["player_id"]:continue
        ids[(x["player_display_name"],x["team"])].add((x["player_id"],x["position"]))
    dkflex={}; slots=defaultdict(set); games=set()
    for x in dk:
        role=x["Roster Position"]
        if role not in ("CPT","FLEX"): raise Blocked("non-Showdown DK salary")
        key=(x["Name"],x["TeamAbbrev"])
        slots[key].add(role);games.add(x["Game Info"])
        if role=="FLEX":
            if key in dkflex:raise Blocked("duplicate FLEX identity")
            dkflex[key]=x
    if len(games)!=1 or len(dkflex)<6 or any(v!={"CPT","FLEX"} for v in slots.values()):
        raise Blocked("mixed contest or unpaired DK slots")
    report=[]
    for (name,team),dkrow in sorted(dkflex.items(),key=lambda kv: (kv[0][1],kv[0][0])):
        if dkrow["Position"] in ("DST","K"):continue
        rec=official.get((name,team))
        if rec is None:raise Blocked("unreviewed owner DK player: "+name)
        group=rec["program_group"]
        if group not in ("ACTIVE_ROSTER","PRACTICE_SQUAD","NOT_LISTED"):
            raise Blocked("unknown official roster group")
        if group!="NOT_LISTED" and rec["official_name"]!=name:
            raise Blocked("official roster identity mismatch")
        provider_name=rec["nflverse_name"] or name
        candidates=ids.get((provider_name,team),set())
        gsis={x[0] for x in candidates}
        positions={x[1] for x in candidates}
        gsis_id=next(iter(gsis)) if len(gsis)==1 else None
        source_pos=next(iter(positions)) if len(positions)==1 else None
        role_mismatch=bool(source_pos and dkrow["Position"]!=source_pos)
        unavailable=group!="ACTIVE_ROSTER" or dkrow["Status"].upper() in ("IR","OUT")
        if unavailable:why="NOT_ACTIVE_ROSTER_OR_DK_OUT"
        elif gsis_id is None:why="NO_PRIOR_SAME_TEAM_GSIS_ID"
        elif role_mismatch:why="STATS_POSITION_DIFFERS_FROM_DK_ROLE"
        else:why="HISTORICAL_ID_ONLY_PENDING_FINAL_INACTIVES"
        report.append({
            "dk_name":name,"team":team,"dk_position":dkrow["Position"],
            "official_program_group":group,"official_role":rec["official_role"],
            "gsis_id":gsis_id,"source_position":source_pos,
            "nflverse_name":provider_name if gsis_id else None,
            "explicit_alias": bool(rec["nflverse_name"] and rec["nflverse_name"]!=name),
            "can_research_prior_role_features":why=="HISTORICAL_ID_ONLY_PENDING_FINAL_INACTIVES",
            "can_enter_contest":False,
            "block_reason":why})
    counts=defaultdict(int)
    for r in report:counts[r["block_reason"]]+=1
    return {"status":"RESEARCH_ONLY_WAITING_FINAL_INACTIVES",
            "historical_gsis_found":sum(bool(x["gsis_id"]) for x in report),
            "conditional_research_players":sum(x["can_research_prior_role_features"] for x in report),
            "contest_ready":0,"offense_rows":len(report),
            "reason_counts":dict(counts),
            "official_roster_source_url":m["official_roster_source_url"],
            "provenance":{"weekly_sha256":m["weekly"]["sha256"],
                          "owner_dk_sha256":m["owner_dk"]["sha256"],
                          "roster_transcription_sha256":m["official_roster"]["sha256"]},
            "caveat":"Game-program roster is not a final active/inactive feed; URL+SHA checks do not independently authenticate publication. Published provider data may be corrected later.",
            "player_audit":report}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("manifest",type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    r=reconcile(a.manifest)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in r.items() if k!="player_audit"},indent=2))


if __name__=="__main__":main()
