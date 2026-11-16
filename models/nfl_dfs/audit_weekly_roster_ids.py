"""Audit exact DK roster vs frozen nflverse weekly player identities.

Never fuzzy-match player names, infer active status, or use DraftKings average
fantasy points. A past player-week team is NOT an authoritative current roster
receipt. Exact historical identities can be exported as RESEARCH candidates,
but the game-input builder still requires independent roster/lineup evidence.

Input is a registered archive manifest: kickoff_utc, weekly {path, sha256,
captured_at_utc}, salaries {path, sha256, captured_at_utc}. Captures must be
strictly pre-kickoff and path/hash verified. No external network.
"""
import argparse
import csv
import json
from pathlib import Path

from build_game_inputs import Blocked, utc, verified, records
from build_weekly_game_inputs import load_snapshot_csv


def audit(manifest_path):
    mpath=Path(manifest_path).resolve()
    root=mpath.parent
    man=json.loads(mpath.read_text(encoding="utf-8"))
    kickoff=utc(man["kickoff_utc"])
    source=verified(root,man,"weekly",kickoff)
    salaries=verified(root,man,"salaries",kickoff)
    rows=load_snapshot_csv(source,("player_id","player_display_name","position",
                                  "season","season_type","week","team"))
    dk=records(salaries,("Name","TeamAbbrev","Position","Roster Position","Salary",
                         "ID","Status"))
    matches={}
    for r in rows:
        if r["season_type"]!="REG" or not r["player_id"]:
            continue
        key=(r["player_display_name"],r["team"],r["position"])
        matches.setdefault(key,set()).add(r["player_id"])
    cohort={}
    for row in dk:
        slot=row["Roster Position"]
        if slot!="FLEX":
            continue
        key=(row["Name"],row["TeamAbbrev"],row["Position"])
        if key in cohort:
            raise Blocked("Duplicate FLEX name/team/position")
        cohort[key]=row
    if not cohort:
        raise Blocked("No FLEX rows for this showdown")
    exact=[]
    unmatched=[]
    for (name,team,pos),r in sorted(cohort.items()):
        if pos in ("K","DST"):
            continue
        ids=matches.get((name,team,pos),set())
        if len(ids)==1:
            exact.append({"player_name":name,"team":team,"position":pos,
                          "gsis_id":next(iter(ids)),
                          "binding":"EXACT_PRIOR_WEEK_NAME_TEAM_POSITION_ONLY"})
        else:
            unmatched.append({"player_name":name,"team":team,"position":pos,
                              "reason":"HISTORICAL_PLAYER_ID_AMBIGUOUS" if len(ids)>1
                                       else "NO_EXACT_PRIOR_WEEK_IDENTITY"})
    if not exact:
        raise Blocked("No exact historical GSIS mapping")
    return {
        "status":"RESEARCH_ONLY_DO_NOT_TREAT_AS_ACTIVE_ROSTER",
        "kickoff_utc":man["kickoff_utc"],
        "source_sha256":man["weekly"]["sha256"],
        "owner_salary_sha256":man["salaries"]["sha256"],
        "exact_count":len(exact),"unmatched_count":len(unmatched),
        "exact":exact,"unmatched":unmatched,
        "blocked_for_full_auto_build":bool(unmatched),
        "warning":"Historical team/name match is not confirmation of current injury, depth chart, roster or starter"
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest",type=Path)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    report=audit(a.manifest)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("exact","unmatched")},indent=2))


if __name__=="__main__":
    main()
