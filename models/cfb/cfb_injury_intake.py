#!/usr/bin/env python3
"""CFB RUN IT injury intake: manual phone-editable JSON file -> runner injury list.

Source research (2026-11-21): no free programmatic college-football injury source is usable.
  * ESPN core API  .../leagues/college-football/teams/<id>/injuries returns
    {"count":0,"items":[]} for FBS teams (checked Michigan 130, Alabama 333) while the same
    endpoint for an NFL team returns 64 records. The site API .../college-football/teams/<id>/injuries
    returns {}. Empty is NOT "no injuries", so ESPN cannot be used as coverage.
  * CollegeFootballData has no injury endpoint. Other NCAAF injury APIs found are paid.
So coverage comes only from the manual file. A team is "covered" only when the owner lists it
in teams_reviewed; every other team on the card is reported as injury coverage missing.

Manual file (models/cfb/injuries/<YYYY-MM-DD>.json), see models/cfb/injuries/README.md:
  {"schema": "sportsedge-cfb-injuries-v1",
   "reviewed_utc": "2026-11-21T15:00:00Z",
   "teams_reviewed": ["Michigan", "Ohio State"],      # reviewed teams, even with zero injuries
   "injuries": [{"team": "Michigan", "player": "A Player", "position": "QB",
                 "status": "OUT", "starter": true, "source": "team release"}]}

Rules: only status OUT is applied. Questionable/doubtful/probable are listed, never applied.
Role comes only from the position field: QB -> QB; WR/RB/TE -> STAR_SKILL only if starter is
true; OL positions -> OL; DB positions -> DB; anything else is listed but not applied. Never guessed.
The manual file overrides any inline intake entry for the same team+player.
"""
from __future__ import annotations
import datetime as dt, hashlib, json

SCHEMA = "sportsedge-cfb-injuries-v1"
STATUSES = {"OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE"}
OL = {"OL", "OT", "OG", "C", "T", "G", "LT", "RT", "LG", "RG"}
DB = {"DB", "CB", "S", "FS", "SS", "NB"}
SKILL = {"WR", "RB", "TE"}


class InjuryFileError(ValueError):
    pass


def role_for(position, starter):
    p = str(position or "").strip().upper()
    if p == "QB": return "QB"
    if p in SKILL: return "STAR_SKILL" if starter is True else None
    if p in OL: return "OL"
    if p in DB: return "DB"
    return None


def load_manual(path):
    """Returns (doc, receipt). Raises InjuryFileError on any schema problem (fail closed)."""
    b = open(path, "rb").read()
    try:
        d = json.loads(b)
    except ValueError as e:
        raise InjuryFileError(f"INJURY_FILE_NOT_JSON: {e}")
    if d.get("schema") != SCHEMA: raise InjuryFileError(f"INJURY_FILE_SCHEMA: expected {SCHEMA}")
    rv = d.get("reviewed_utc")
    try:
        dt.datetime.fromisoformat(str(rv).replace("Z", "+00:00"))
    except ValueError:
        raise InjuryFileError("INJURY_FILE_REVIEWED_UTC_INVALID")
    if not isinstance(d.get("teams_reviewed"), list) or not isinstance(d.get("injuries"), list):
        raise InjuryFileError("INJURY_FILE_NEEDS_teams_reviewed_AND_injuries_LISTS")
    for i, r in enumerate(d["injuries"]):
        for k in ("team", "player", "status"):
            if not str(r.get(k) or "").strip(): raise InjuryFileError(f"INJURY_FILE_ROW_{i}_MISSING_{k}")
        if str(r["status"]).upper() not in STATUSES:
            raise InjuryFileError(f"INJURY_FILE_ROW_{i}_STATUS_{r['status']}")
        if r["team"] not in d["teams_reviewed"]:
            raise InjuryFileError(f"INJURY_FILE_ROW_{i}_TEAM_NOT_IN_teams_reviewed")
    receipt = {"source": "manual_injuries", "path": path, "bytes": len(b),
               "sha256": hashlib.sha256(b).hexdigest(), "observed_utc": rv}
    return d, receipt


def merge(intake, manual, path, resolve=lambda t: t):
    """New intake dict with injuries (applied OUT rows), injuries_listed (all rows, with source),
    injuries_reviewed_utc and injury_teams_reviewed. resolve() maps names to exact CFBD teams;
    an unresolved team is listed as unmatched and never applied."""
    out = dict(intake)
    listed = {}
    for r in intake.get("injuries", []):
        listed[(r.get("team"), r.get("player"))] = dict(r, source=r.get("source", "lines_intake"),
                                                        applied=str(r.get("status", "OUT")).upper() == "OUT")
    reviewed = set()
    for t in manual["teams_reviewed"]:
        rt = resolve(t)
        if rt: reviewed.add(rt)
    for r in manual["injuries"]:
        team = resolve(r["team"])
        st = str(r["status"]).upper()
        role = role_for(r.get("position"), r.get("starter"))     # never from a free-typed role
        row = {"team": team or r["team"], "player": r["player"], "position": r.get("position"),
               "role": role, "status": st, "source": f"manual:{path}" + (f" ({r['source']})" if r.get("source") else ""),
               "applied": bool(team and st == "OUT" and role)}
        if not team: row["unmatched_team"] = True
        if r.get("impact") is not None and row["applied"]: row["impact"] = r["impact"]
        listed[(row["team"], row["player"])] = row          # manual overrides inline
    out["injuries_listed"] = list(listed.values())
    out["injuries"] = [{k: v for k, v in r.items() if k in ("team", "player", "role", "status", "impact", "source")}
                       for r in out["injuries_listed"] if r["applied"]]
    out["injuries_reviewed_utc"] = manual["reviewed_utc"]
    out["injury_teams_reviewed"] = sorted(reviewed)
    return out


def missing_coverage(intake, teams):
    """Teams on the card with no injury review. Only tracked when a coverage list exists."""
    if "injury_teams_reviewed" not in intake: return []
    have = set(intake["injury_teams_reviewed"])
    return sorted({t for t in teams if t not in have})
