"""Build DK Showdown CPT/FLEX-ID CSV from canonical SportsEdge lineup results.

Fail closed on bad/missing final-inactives manifest, salary IDs, illegal builds,
wrong slate, or an excluded player. This checks LOCAL evidence integrity, not
that the claimed third-party inactive source is genuinely authenticated.
Always label output MANUAL_SOURCE_VERIFICATION_REQUIRED / research only.
No lineup is entered or submitted to DraftKings, and no ownership or ROI claim.

Usage:
 python models/nfl_dfs/export_verified_showdown.py \
   --lineups models/nfl_dfs/out/PIT_CIN_2026-11-15_lineups.json \
   --salaries models/nfl_dfs/data/DKSalaries_PIT_CIN_2026-11-15.csv \
   --inactive-manifest private/inactives.json \
   --kickoff-utc 2026-11-16T01:20:00Z \
   --expected-game PIT@CIN --out private/showdown_research.csv
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

class ExportBlocked(ValueError):
    pass

def utc(v):
    try:
        t=datetime.fromisoformat(v.replace("Z","+00:00"))
        if t.tzinfo is None: raise ValueError("timezone missing")
        return t.astimezone(timezone.utc)
    except (AttributeError,ValueError) as ex:
        raise ExportBlocked("Invalid timestamp") from ex

def salaries(path, game):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        rdr=csv.DictReader(f)
        fields=("Name","TeamAbbrev","Position","ID","Roster Position","Salary","Game Info","Status")
        if not set(fields).issubset(rdr.fieldnames or []):
            raise ExportBlocked("DK salary CSV missing required columns")
        rows=list(rdr)
    result={}; used=set(); games=set()
    for r in rows:
        if game not in r["Game Info"]:
            raise ExportBlocked("Another matchup in salary file")
        games.add(r["Game Info"])
        slot=r["Roster Position"]
        if slot not in ("CPT","FLEX"):raise ExportBlocked("Not a DK Showdown salary export")
        name=r["Name"]; team=r["TeamAbbrev"]
        if not name or not team or not r["ID"] or r["ID"] in used:raise ExportBlocked("Duplicate or invalid DK draftable ID")
        used.add(r["ID"])
        try:
            cost=int(r["Salary"])
        except ValueError as ex:raise ExportBlocked("Invalid salary") from ex
        if cost<=0:raise ExportBlocked("Nonpositive salary")
        item=result.setdefault(name,{"team":team,"pos":r["Position"],"status":r["Status"],"slots":{}})
        if item["team"]!=team or item["pos"]!=r["Position"]:
            raise ExportBlocked("Ambiguous same-name player identity")
        if slot in item["slots"]:raise ExportBlocked("Duplicate CPT/FLEX slot")
        item["slots"][slot]={"id":r["ID"],"salary":cost}
    if len(games)!=1:raise ExportBlocked("Mixed contest slate")
    for name,item in result.items():
        if set(item["slots"])!={"CPT","FLEX"}:
            raise ExportBlocked(f"Unpaired CPT/FLEX salary: {name}")
        if item["slots"]["CPT"]["salary"]*2!=item["slots"]["FLEX"]["salary"]*3:
            raise ExportBlocked(f"Captain salary mismatch {name}")
    return result

def inactives(manifest_path,kickoff):
    path=Path(manifest_path).resolve()
    m=json.loads(path.read_text(encoding="utf-8"))
    required=("game","kickoff_utc","captured_at_utc","source_url","original_file",
              "sha256","inactive_players","teams_confirmed_complete")
    if not all(k in m for k in required):raise ExportBlocked("Missing inactive receipt required field")
    if utc(m["kickoff_utc"])!=kickoff or utc(m["captured_at_utc"])>=kickoff:
        raise ExportBlocked("Inactive receipt is not pre-kickoff, or wrong event")
    if m["teams_confirmed_complete"] is not True:
        raise ExportBlocked("Complete two-team inactive list not attested")
    if not str(m["source_url"]).startswith(("https://www.steelers.com/",
                                             "https://www.bengals.com/",
                                             "https://www.nfl.com/")):
        raise ExportBlocked("Unrecognized official source URL")
    raw=(path.parent / m["original_file"]).resolve()
    if not raw.is_relative_to(path.parent):
        raise ExportBlocked("Receipt path traversal")
    if hashlib.sha256(raw.read_bytes()).hexdigest()!=m["sha256"]:
        raise ExportBlocked("Inactive original bytes hash mismatch")
    names=m["inactive_players"]
    if not isinstance(names,list) or any(not isinstance(x,str) or not x.strip() for x in names):
        raise ExportBlocked("Invalid inactive name list")
    if len(names)!=len(set(names)):
        raise ExportBlocked("Duplicate inactive identities")
    return m,set(names)

def export(lineup_json,salary_csv,manifest,kickoff_utc,expected_game,rank_by="mean",max_lineups=20):
    if rank_by not in ("mean","opt_rate") or not 1<=max_lineups<=150:
        raise ExportBlocked("Invalid selection parameters")
    kickoff=utc(kickoff_utc)
    sal=salaries(salary_csv,expected_game)
    receipt, inactive=inactives(manifest,kickoff)
    if receipt["game"]!=expected_game:
        raise ExportBlocked("Inactives receipt event mismatch")
    out=json.loads(Path(lineup_json).read_text(encoding="utf-8"))
    key="top_by_mean" if rank_by=="mean" else "top_by_opt_rate"
    if not isinstance(out.get(key),list) or not out[key]:
        raise ExportBlocked("No canonical lineups in artifact")
    if out.get("summary",{}).get("label")!="RESEARCH / PAPER - not Model_P, unvalidated":
        raise ExportBlocked("Unrecognized canonical result state")
    export_rows=[]; details=[]; rejected=[]
    for l in out[key][:max_lineups]:
        captain=l.get("cpt"); flex=l.get("flex")
        if not captain or not isinstance(flex,list) or len(flex)!=5:
            raise ExportBlocked("Bad six-slot lineup")
        names=[captain]+flex
        if len(set(names))!=6:raise ExportBlocked("Player repeated across CPT/FLEX")
        if any(p not in sal for p in names):raise ExportBlocked("Missing player in owner DK salary file")
        ids=[sal[captain]["slots"]["CPT"]["id"]]+[sal[p]["slots"]["FLEX"]["id"] for p in flex]
        cost=sal[captain]["slots"]["CPT"]["salary"]+sum(sal[p]["slots"]["FLEX"]["salary"] for p in flex)
        if cost>50000 or len({sal[p]["team"] for p in names})!=2:
            raise ExportBlocked("Invalid lineup salary or single-team build")
        unavailable=[p for p in names if p in inactive or sal[p]["status"].upper() in ("IR","OUT")]
        if unavailable:
            rejected.append({"cpt":captain,"inactive_or_ir":unavailable})
            continue
        export_rows.append(ids)
        details.append({"captain":captain,"flex":flex,"salary":cost,"ids":ids})
    if not export_rows:
        raise ExportBlocked("All requested lineups contain unavailable players")
    audit={
        "status":"RESEARCH_EXPORT_MANUAL_SOURCE_VERIFICATION_REQUIRED",
        "game":expected_game,"kickoff_utc":kickoff_utc,"rank_by":rank_by,
        "lineups_exported":len(export_rows),"rejected_inactive":rejected,
        "receipt_sha256":receipt["sha256"],"receipt_source_url_claim":receipt["source_url"],
        "owner_salary_sha256":hashlib.sha256(Path(salary_csv).read_bytes()).hexdigest(),
        "source_authentication_independent":False,
        "ready_for_automated_entry":False,
        "notes":"Local source hashes and self-declared official URL do not prove full or authentic inactives. Human verification of official team lists and contest remains mandatory.",
        "lineups":details
    }
    return export_rows,audit

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lineups",required=True,type=Path)
    p.add_argument("--salaries",required=True,type=Path)
    p.add_argument("--inactive-manifest",required=True,type=Path)
    p.add_argument("--kickoff-utc",required=True)
    p.add_argument("--expected-game",required=True)
    p.add_argument("--rank-by",choices=("mean","opt_rate"),default="mean")
    p.add_argument("--max-lineups",type=int,default=20)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    ids,audit=export(a.lineups,a.salaries,a.inactive_manifest,a.kickoff_utc,
                     a.expected_game,a.rank_by,a.max_lineups)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["CPT"]+["FLEX"]*5);w.writerows(ids)
    a.out.with_suffix(".audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    print(json.dumps({k:v for k,v in audit.items() if k!="lineups"},indent=2))

if __name__=="__main__":main()
