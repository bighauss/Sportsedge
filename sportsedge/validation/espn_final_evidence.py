#!/usr/bin/env python3
"""ESPN final/result intake for SportsEdge research, OFFLINE by default.

Captures original ESPN Site v2 summary bytes (or imports an already saved
original) and stages exact final-period scores and strictly parsed stat
candidates. Never changes odds, CLV, the paper ledger or frozen v5. No model
promotion. Missing/ambiguous boxscores remain MISSING, never zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from sportsedge.validation.paper_ledger import strict_json, time_utc, Blocked, REPO_ROOT

BASE = "https://site.api.espn.com/apis/site/v2/sports/"
LEAGUES = {
    "NFL": "football/nfl",
    "CFB": "football/college-football",
    "CBB": "basketball/mens-college-basketball",
    "NBA": "basketball/nba",
    "MLB": "baseball/mlb",
}
MAX_RAW = 5_000_000
ID_RE = re.compile(r"^[0-9]{1,12}$")
SCORE_RE = re.compile(r"^(?:0|[1-9][0-9]{0,2})$")
INT_RE = re.compile(r"^(?:0|[1-9][0-9]{0,3})$")
PAIR_RE = re.compile(r"^(0|[1-9][0-9]{0,2})[/-](0|[1-9][0-9]{0,2})$")

FOOTBALL_MAP = {
    "passing": {"YDS": "PASS_YDS", "TD": "PASS_TDS", "INT": "INTERCEPTIONS"},
    "rushing": {"YDS": "RUSH_YDS", "ATT": "RUSH_ATT", "TD": "RUSH_TDS"},
    "receiving": {"YDS": "REC_YDS", "REC": "RECEPTIONS", "TD": "REC_TDS",
                  "TGT": "TARGETS", "TGTS": "TARGETS"}
}
BASKET_MAP = {"PTS": "POINTS", "REB": "REBOUNDS", "AST": "ASSISTS",
              "STL": "STEALS", "BLK": "BLOCKS", "TO": "TURNOVERS"}


class Reject(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _utc(v, label):
    try:
        value = time_utc(v)
    except Blocked as exc:
        raise Reject(label + "_INVALID") from exc
    return value


def _id(v, label):
    if not isinstance(v, str) or not ID_RE.fullmatch(v):
        raise Reject(label + "_NOT_EXACT_ESPN_ID")
    return v


def _score(v, label):
    if isinstance(v, bool):
        raise Reject(label + "_INVALID")
    if isinstance(v, int) and 0 <= v <= 999:
        return v
    if isinstance(v, str) and SCORE_RE.fullmatch(v):
        return int(v)
    raise Reject(label + "_INVALID")


def _statnum(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int) and 0 <= v <= 9999:
        return v
    if isinstance(v, str) and INT_RE.fullmatch(v):
        return int(v)
    return None


def _final_periods(sport, home, away):
    hs, aw = home.get("linescores"), away.get("linescores")
    if not isinstance(hs, list) or not isinstance(aw, list) or len(hs) != len(aw):
        raise Reject("PERIOD_LINESCORES_MISSING_OR_MISMATCH")
    minlen = 9 if sport == "MLB" else (2 if sport == "CBB" else 4)
    if not minlen <= len(hs) <= 24:
        raise Reject("PERIOD_COUNT_INCOMPLETE_OR_IMPLAUSIBLE")
    def parse(side):
        values = []
        for idx, raw in enumerate(side["linescores"], 1):
            if not isinstance(raw, dict) or "value" not in raw:
                raise Reject("PERIOD_SCORE_MISSING")
            value = raw["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise Reject("PERIOD_SCORE_INVALID")
            if int(value) != value or value < 0 or value > 999:
                raise Reject("PERIOD_SCORE_INVALID")
            if "period" in raw and raw["period"] != idx:
                raise Reject("PERIOD_ORDER_MISMATCH")
            values.append(int(value))
        return values
    scores_h = parse(home)
    scores_a = parse(away)
    if sum(scores_h) != _score(home.get("score"), "HOME_FINAL_SCORE"):
        raise Reject("HOME_PERIOD_SUM_NOT_FINAL")
    if sum(scores_a) != _score(away.get("score"), "AWAY_FINAL_SCORE"):
        raise Reject("AWAY_PERIOD_SUM_NOT_FINAL")
    if sport == "MLB":
        # Rain-shortened games need specialized posted-rule handling; don't
        # quietly synthesize non-played innings.
        out = {f"I{i}": [scores_h[i-1], scores_a[i-1]] for i in range(1,10)}
        if len(hs)>9:
            out["EXTRA"] = [sum(scores_h[9:]), sum(scores_a[9:])]
    elif sport == "CBB":
        out = {f"H{i}": [scores_h[i-1], scores_a[i-1]] for i in (1,2)}
        if len(hs)>2:
            out["OT"] = [sum(scores_h[2:]),sum(scores_a[2:])]
    else:
        out = {f"Q{i}": [scores_h[i-1], scores_a[i-1]] for i in range(1,5)}
        if len(hs)>4:
            out["OT"] = [sum(scores_h[4:]),sum(scores_a[4:])]
    return out


def _players(sport, data, team_ids):
    """Partial verified-positive stats; no missing-player zero claims."""
    box = data.get("boxscore")
    if not isinstance(box, dict) or not isinstance(box.get("players"), list):
        return {}, [], ["PLAYER_BOX_SCORE_MISSING"]
    if sport == "MLB":
        return {}, [], ["MLB_PLAYER_SCHEMA_NOT_ADMITTED"]
    result, ids = {}, set()
    warnings = set()
    athlete_teams, invalid_athletes, invalid_stat_keys = {}, set(), set()
    for group in box["players"]:
        if not isinstance(group, dict) or not isinstance(group.get("team"), dict):
            warnings.add("PLAYER_TEAM_MAPPING_MISSING")
            continue
        tid = str(group["team"].get("id",""))
        if tid not in team_ids:
            warnings.add("PLAYER_TEAM_NOT_IN_EVENT")
            continue
        cats = group.get("statistics")
        if not isinstance(cats, list):
            warnings.add("PLAYER_CATEGORIES_MISSING")
            continue
        for cat in cats:
            if not isinstance(cat, dict) or not isinstance(cat.get("labels"), list) or not isinstance(cat.get("athletes"), list):
                warnings.add("PLAYER_CATEGORY_SCHEMA_INVALID")
                continue
            groupname = str(cat.get("name","")).lower()
            allowed = FOOTBALL_MAP.get(groupname, {}) if sport in ("NFL","CFB") else BASKET_MAP
            if not allowed:
                continue
            labels = [str(x).upper() for x in cat["labels"]]
            if len(labels) != len(set(labels)):
                warnings.add("DUPLICATE_PLAYER_STAT_LABELS")
                continue
            for entry in cat["athletes"]:
                if not isinstance(entry, dict) or not isinstance(entry.get("athlete"), dict):
                    warnings.add("PLAYER_ID_MISSING")
                    continue
                pid = str(entry["athlete"].get("id",""))
                if not ID_RE.fullmatch(pid):
                    warnings.add("PLAYER_ID_INVALID")
                    continue
                vals = entry.get("stats")
                if not isinstance(vals, list) or len(vals) != len(labels):
                    warnings.add("PLAYER_STAT_WIDTH_INVALID")
                    continue
                if pid in athlete_teams and athlete_teams[pid] != tid:
                    invalid_athletes.add(pid)
                    warnings.add("PLAYER_ID_BELONGS_TO_MULTIPLE_TEAMS")
                    continue
                athlete_teams[pid] = tid
                ids.add(pid)
                rec = result.setdefault(pid, {})
                for name, raw in zip(labels, vals):
                    target = allowed.get(name)
                    number = _statnum(raw)
                    if sport in ("NFL", "CFB") and groupname == "passing" and name in ("C/ATT", "C-ATT"):
                        mm = PAIR_RE.fullmatch(str(raw))
                        if mm and int(mm[1]) <= int(mm[2]):
                            for statname, number2 in (("COMPLETIONS",int(mm[1])),("PASS_ATT",int(mm[2]))):
                                if (pid,statname) in invalid_stat_keys:
                                    continue
                                if statname in rec and rec[statname] != number2:
                                    warnings.add("CONFLICTING_PLAYER_STAT_VALUES")
                                    invalid_stat_keys.add((pid,statname))
                                    rec.pop(statname, None)
                                else:
                                    rec[statname] = number2
                        else:
                            warnings.add("UNPARSEABLE_PASS_COMPLETIONS")
                    elif sport in ("CBB","NBA") and name in ("3PT", "3PM-A"):
                        mm = PAIR_RE.fullmatch(str(raw))
                        if mm and int(mm[1]) <= int(mm[2]):
                            number = int(mm[1])
                            target = "3PM"
                        else:
                            warnings.add("UNPARSEABLE_3PT_RATIO")
                    if target:
                        if number is None:
                            warnings.add("MISSING_OR_AMBIGUOUS_STAT:" + target)
                            continue
                        if (pid,target) in invalid_stat_keys:
                            continue
                        if target in rec and rec[target] != number:
                            warnings.add("CONFLICTING_PLAYER_STAT_VALUES")
                            invalid_stat_keys.add((pid,target))
                            rec.pop(target,None)
                        else:
                            rec[target] = number
    return ({k:v for k,v in result.items() if v and k not in invalid_athletes},
            sorted(ids - invalid_athletes), sorted(warnings))


def inspect(raw, *, event_id, sport, home_espn_id, away_espn_id,
            captured_utc, kickoff_utc):
    """Produces canonical *candidate*, not authenticated official settlement."""
    if sport not in LEAGUES:
        raise Reject("UNSUPPORTED_SPORT")
    for name,value in (("EVENT",event_id),("HOME",home_espn_id),("AWAY",away_espn_id)):
        _id(value,name)
    if home_espn_id == away_espn_id:
        raise Reject("SAME_HOME_AND_AWAY_ID")
    clock = _utc(captured_utc, "CAPTURE")
    kickoff = _utc(kickoff_utc, "KICKOFF")
    if clock <= kickoff:
        raise Reject("CAPTURE_NOT_POSTGAME")
    if not isinstance(raw, bytes) or not raw or len(raw)>MAX_RAW:
        raise Reject("RAW_BYTES_EMPTY_OR_TOO_LARGE")
    try:
        doc = strict_json(raw)
    except Blocked as exc:
        raise Reject("INVALID_OR_DUPLICATE_SOURCE_JSON") from exc
    if not isinstance(doc, dict):
        raise Reject("UNEXPECTED_ESPN_SUMMARY")
    header = doc.get("header")
    if not isinstance(header, dict):
        raise Reject("ESPN_HEADER_MISSING")
    comps = header.get("competitions")
    if not isinstance(comps, list) or len(comps)!=1 or not isinstance(comps[0], dict):
        raise Reject("SINGLE_COMPETITION_REQUIRED")
    comp = comps[0]
    if str(header.get("id") or comp.get("id") or "") != event_id:
        raise Reject("ESPN_EVENT_ID_MISMATCH")
    status = comp.get("status") or header.get("status")
    stype = status.get("type") if isinstance(status, dict) else None
    if not isinstance(stype, dict) or stype.get("completed") is not True or stype.get("name") not in ("STATUS_FINAL",):
        raise Reject("FINAL_STATUS_NOT_CONFIRMED")
    if isinstance(comp.get("date"), str) and comp["date"]:
        source_date = _utc(comp["date"], "ESPN_KICKOFF")
        if source_date != kickoff:
            raise Reject("KICKOFF_IDENTITY_MISMATCH")
    parts = comp.get("competitors")
    if not isinstance(parts, list) or len(parts)!=2:
        raise Reject("TWO_COMPETITORS_REQUIRED")
    byside = {}
    for part in parts:
        if not isinstance(part, dict) or part.get("homeAway") not in ("home","away"):
            raise Reject("INVALID_HOME_AWAY")
        side = part["homeAway"]
        if side in byside:
            raise Reject("DUPLICATE_HOME_AWAY")
        team = part.get("team")
        if not isinstance(team, dict) or not ID_RE.fullmatch(str(team.get("id",""))):
            raise Reject("ESPN_TEAM_ID_MISSING")
        byside[side] = part
    if set(byside)!= {"home","away"}:
        raise Reject("TWO_SIDES_REQUIRED")
    if (str(byside["home"]["team"]["id"])!=home_espn_id or
            str(byside["away"]["team"]["id"])!=away_espn_id):
        raise Reject("TEAM_ID_OR_SIDE_MISMATCH")
    periods = _final_periods(sport, byside["home"], byside["away"])
    player_stats, roster, warnings = _players(sport, doc, {home_espn_id, away_espn_id})
    result = {
        "event_id": event_id, "sport": sport, "final_status": "FINAL",
        "home_id": home_espn_id, "away_id": away_espn_id,
        "periods": periods, "roster_ids": roster, "player_stats": player_stats,
        "player_period_stats": {}, "events": [], "events_complete": False,
        "final_available_utc": clock.isoformat(),
    }
    return {"status":"STAGED_REVIEW_ONLY","official_counted":0,"approved_stake_u":0,
            "provider_publication_authenticated":False,
            "source_full_roster_confirmed":False,
            "source_original_sha256":hashlib.sha256(raw).hexdigest(),
            "local_observation_utc":clock.isoformat(),
            "kickoff_utc":kickoff.isoformat(),
            "player_stat_warnings":warnings,
            "game_and_team_ids_verified_against_operator_crosswalk":False,
            "price_evidence_status":"NOT_CHECKED", "candidate": result}


def _fetch(sport,event_id):
    if sport not in LEAGUES:
        raise Reject("UNSUPPORTED_SPORT")
    _id(event_id,"EVENT")
    url = BASE+LEAGUES[sport]+"/summary?"+urlencode({"event":event_id})
    req = Request(url,headers={"Accept":"application/json","Accept-Encoding":"identity",
                               "User-Agent":"SportsEdge-Paper-Results/1.0"})
    try:
        with build_opener(NoRedirect()).open(req,timeout=15) as response:
            if response.status != 200 or response.geturl()!=url:
                raise Reject("ESPN_REDIRECT_OR_HTTP_INVALID")
            raw = response.read(MAX_RAW+1)
    except HTTPError as exc:
        raise Reject("ESPN_HTTP_"+str(exc.code)) from None
    except (OSError,URLError,TimeoutError):
        raise Reject("ESPN_FETCH_UNAVAILABLE") from None
    return raw,url


def save(raw, report, out, *, source_url, import_kind):
    if (not isinstance(raw, bytes) or not isinstance(report, dict)
            or hashlib.sha256(raw).hexdigest() != report.get("source_original_sha256")
            or not isinstance(report.get("candidate"), dict)):
        raise Reject("SOURCE_RECEIPT_RAW_BYTES_MISMATCH")
    out=Path(os.path.abspath(os.fspath(out)))
    resolved = out.resolve()
    if (out == REPO_ROOT or REPO_ROOT in out.parents
            or resolved == REPO_ROOT or REPO_ROOT in resolved.parents
            or any(part.is_symlink() for part in (out, *out.parents))):
        raise Reject("PUBLIC_OR_SYMLINKED_OUTPUT_PATH")
    if (not out.parent.is_dir()
            or stat.S_IMODE(out.parent.stat().st_mode) & 0o077):
        raise Reject("OUTPUT_PARENT_NOT_OWNER_PRIVATE")
    out.mkdir(mode=0o700,parents=False,exist_ok=False)
    if stat.S_IMODE(out.stat().st_mode) & 0o077:
        raise Reject("OUTPUT_DIRECTORY_NOT_PRIVATE")
    def write(name,data):
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
        fd=os.open(out/name,flags,0o600)
        with os.fdopen(fd,"wb") as f:
            f.write(data)
    write("original_espn_summary.json",raw)
    canonical=report["candidate"]
    write("canonical_final_FOR_REVIEW.json",json.dumps(canonical,sort_keys=True,indent=2).encode()+b"\n")
    receipt={**{k:v for k,v in report.items() if k != "candidate"},"source_url":source_url,"acquisition":"LIVE_HTTP" if import_kind=="live" else "LOCAL_SAVED_BYTES_NOT_PIT_ATTESTED",
             "raw_bytes":len(raw),"status":"RESEARCH_ONLY_NOT_LEDGER_ADMITTED"}
    write("result_evidence_receipt.json",json.dumps(receipt,sort_keys=True,indent=2).encode()+b"\n")
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ("sport","event-id","home-espn-id","away-espn-id","kickoff-utc","out-dir"):
        parser.add_argument("--"+arg,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--raw-file",type=Path,help="Existing original ESPN JSON; capture time is NOW")
    group.add_argument("--execute",action="store_true",help="One live ESPN summary GET (no API key)")
    a=parser.parse_args()
    try:
        if a.raw_file:
            if a.raw_file.is_symlink() or not a.raw_file.is_file():
                raise Reject("LOCAL_ORIGINAL_FILE_INVALID")
            raw=a.raw_file.read_bytes(); url="LOCAL_ESPN_JSON_NOT_UPSTREAM_AUTHENTICATED"
            mode="import"
        else:
            raw,url=_fetch(a.sport,a.event_id);mode="live"
        # The acquisition time is stamped *after* the response bytes were read.
        observed=datetime.now(timezone.utc).isoformat()
        result=inspect(raw,event_id=a.event_id,sport=a.sport,
                       home_espn_id=a.home_espn_id,away_espn_id=a.away_espn_id,
                       captured_utc=observed,kickoff_utc=a.kickoff_utc)
        save(raw,result,a.out_dir,source_url=url,import_kind=mode)
        print("RESEARCH_RESULT_STAGED",a.sport,a.event_id,
              "player_stat_warnings",len(result["player_stat_warnings"]),"official=0u")
        return 0
    except (Reject, OSError, ValueError) as exc:
        print("BLOCKED_RESULT_INTAKE:"+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
