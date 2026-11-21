#!/usr/bin/env python3
"""ESPN free college injury/QB evidence intake. READ ONLY; research/PAPER 0u.

Collect raw public ESPN JSON, retain byte hashes and capture times, join athlete
IDs to event-team rosters, and output REVIEW QUEUES. NEVER emit a file named
'injuries.csv', never assert healthy from an empty injury feed, never infer a
starting QB from roster/depth-chart membership, never change model parameters.

Docs: docs/research/ESPN_COLLEGE_AVAILABILITY_INTAKE.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://site.api.espn.com/apis/site/v2/sports/"
LEAGUES = {"CFB": "football/college-football", "CBB": "basketball/mens-college-basketball"}
CANDIDATE_FIELDS = ["sport", "event_id", "team", "espn_team_id", "athlete_id",
                    "player", "position", "status", "injury_date", "source_url",
                    "source_sha256", "reason_codes", "model_role", "impact",
                    "approved_for_model"]
QB_FIELDS = ["event_id", "team", "espn_team_id", "athlete_id", "player",
             "depthchart_source_sha256", "starter_confirmed", "reason_codes"]
SLATE_FIELDS = ("sport", "event_id", "kickoff_utc", "home", "away",
                "home_espn_id", "away_espn_id")
KNOWN = {"out", "doubtful", "questionable", "probable", "day-to-day",
         "day to day", "inactive", "injured reserve", "suspended"}
MAX_BYTES = 4_000_000


class Refused(ValueError):
    pass


def timestamp(x, key):
    if not x:
        raise Refused(f"{key}:MISSING_TIMESTAMP")
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise Refused(f"{key}:INVALID_TIMESTAMP") from exc
    if d.tzinfo is None or d.utcoffset() is None:
        raise Refused(f"{key}:OFFSET_REQUIRED")
    return d.astimezone(timezone.utc)


def valid_id(v):
    return isinstance(v, str) and bool(re.fullmatch(r"[0-9]{1,12}", v))


def slate_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        r = csv.DictReader(fh)
        if not r.fieldnames or len(set(r.fieldnames)) != len(r.fieldnames) or set(SLATE_FIELDS) - set(r.fieldnames):
            raise Refused("SLATE_HEADERS_INVALID")
        rows = list(r)
    if not rows:
        raise Refused("EMPTY_SLATE")
    seen = set()
    for g in rows:
        if None in g or not all(g.get(k) for k in SLATE_FIELDS):
            raise Refused("SLATE_RAGGED_OR_BLANK")
        if g["sport"] not in LEAGUES:
            raise Refused("UNKNOWN_SPORT")
        k = (g["sport"], g["event_id"])
        if k in seen:
            raise Refused("DUPLICATE_GAME")
        seen.add(k)
        timestamp(g["kickoff_utc"], "KICKOFF")
        if not valid_id(g["home_espn_id"]) or not valid_id(g["away_espn_id"]):
            raise Refused("TEAM_ID_INVALID")
        if g["home_espn_id"] == g["away_espn_id"] or g["home"] == g["away"]:
            raise Refused("SAME_TEAM")
    return rows


def url_for(sport, kind, team_id=None):
    if sport not in LEAGUES or (team_id is not None and not valid_id(str(team_id))):
        raise Refused("URL_INPUT_INVALID")
    root = BASE + LEAGUES[sport] + "/"
    if kind == "league_injuries":
        return root + "injuries"
    if kind in ("roster", "depthcharts", "injuries") and team_id is not None:
        return root + f"teams/{team_id}/" + kind
    raise Refused("UNSUPPORTED_ENDPOINT")


def get_bytes(url, fixture=None):
    if fixture is not None:
        return Path(fixture).read_bytes()
    req = Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity",
                               "User-Agent": "SportsEdge-Research-Availability/1.0"})
    with urlopen(req, timeout=12) as resp:
        if resp.status != 200:
            raise Refused("NON_200")
        if resp.geturl().split("/")[2] != "site.api.espn.com":
            raise Refused("REDIRECT_NOT_ESPN")
        body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise Refused("BODY_TOO_LARGE")
        return body


def roster_athletes(payload):
    """Recognize published grouped roster and flat roster; reject unknown shapes."""
    if not isinstance(payload, dict) or not isinstance(payload.get("athletes"), list):
        return {}, "ROSTER_UNRECOGNIZED"
    players, names = {}, set()
    for group in payload["athletes"]:
        if not isinstance(group, dict):
            return {}, "ROSTER_UNRECOGNIZED"
        candidates = group.get("items")
        if isinstance(candidates, list):
            candidates = candidates
        elif "id" in group:
            candidates = [group]
        else:
            return {}, "ROSTER_UNRECOGNIZED"
        for athlete in candidates:
            if not isinstance(athlete, dict):
                return {}, "ROSTER_UNRECOGNIZED"
            aid, name = str(athlete.get("id") or ""), athlete.get("displayName") or athlete.get("fullName") or ""
            if not valid_id(aid) or not name or aid in players or name in names:
                return {}, "ROSTER_AMBIGUOUS"
            names.add(name)
            p = athlete.get("position") or {}
            pos = p.get("abbreviation", "") if isinstance(p, dict) else ""
            players[aid] = {"name": name, "position": pos}
    return players, "ROSTER_MATCHABLE" if players else "ROSTER_EMPTY_UNKNOWN"


def injury_records(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("injuries"), list):
        return None
    return payload["injuries"]


def extract_injury(entry, bound_team_id=None):
    if not isinstance(entry, dict):
        return None
    team = entry.get("team") or {}
    athlete = entry.get("athlete") or {}
    if not isinstance(team, dict) or not isinstance(athlete, dict):
        return None
    team_id = str(team.get("id") or bound_team_id or "")
    if bound_team_id and team.get("id") not in (None, "", bound_team_id, int(bound_team_id)):
        return None
    aid = str(athlete.get("id") or "")
    name = athlete.get("displayName") or ""
    status = str(entry.get("status") or "").strip().lower()
    return {"team_id": team_id, "athlete_id": aid, "name": name,
            "status": status, "date": entry.get("date") or ""}


def make_report(games, fetcher, at=None, fixtures=False):
    """Fetcher receives (url, key) -> bytes; fully offline tests inject fixtures."""
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise Refused("CAPTURE_CLOCK_NEEDS_OFFSET")
    at = at.astimezone(timezone.utc)
    teams, games_by_team = {}, {}
    for g in games:
        sport = g["sport"]
        for side in ("home", "away"):
            tid, team = g[side + "_espn_id"], g[side]
            key = (sport, tid)
            if key in teams and teams[key] != team:
                raise Refused("TEAM_ID_NAME_CONFLICT")
            teams[key] = team
            games_by_team.setdefault(key, []).append(g)
    source_info, sources = {}, {}
    def capture(sport, kind, tid=None):
        key = (sport, kind, str(tid or "league"))
        if key in sources:
            return sources[key]
        url = url_for(sport, kind, tid)
        rec = {"url": url, "key": ":".join(key), "captured_utc": at.isoformat(),
               "sha256": None, "state": "FETCH_ERROR"}
        try:
            raw = fetcher(url, rec["key"])
            if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
                raise Refused("EMPTY_OR_OVERSIZED_BODY")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise Refused("UNEXPECTED_JSON_SHAPE")
            rec["sha256"] = hashlib.sha256(raw).hexdigest()
            rec["state"] = "FETCHED_JSON"
            rec["bytes"] = len(raw)
            rec["raw"] = raw
            sources[key] = (data, rec)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, UnicodeError, KeyError) as exc:
            rec["reason"] = type(exc).__name__
            sources[key] = (None, rec)
        source_info[rec["key"]] = {k: v for k, v in rec.items() if k != "raw"}
        return sources[key]
    # League-wide ESPN injury feeds are frequently empty for college sports.
    for sport in sorted({g["sport"] for g in games}):
        capture(sport, "league_injuries")
    candidates, qbs, coverage = [], [], []
    for (sport, tid), team in sorted(teams.items()):
        games_team = games_by_team[(sport, tid)]
        league_data, league_rec = capture(sport, "league_injuries")
        roster_data, roster_rec = capture(sport, "roster", tid)
        roster, roster_state = roster_athletes(roster_data)
        injury_feeds = [(league_data, league_rec, None)]
        if sport == "CBB":
            injury_feeds.append((*capture(sport, "injuries", tid), tid))
        depth_rec = None
        if sport == "CFB":
            _, depth_rec = capture(sport, "depthcharts", tid)
        valid_entries, flags = [], []
        for feed, rec, bound in injury_feeds:
            raw_entries = injury_records(feed)
            if raw_entries is None:
                flags.append("INJURY_ENDPOINT_UNAVAILABLE_OR_INVALID")
                continue
            if not raw_entries:
                flags.append("INJURY_FEED_EMPTY_UNKNOWN")
            for x in raw_entries:
                e = extract_injury(x, bound_team_id=bound)
                if e and e["team_id"] == tid:
                    valid_entries.append((e, rec))
                elif e is None:
                    flags.append("INJURY_SCHEMA_OR_TEAM_CONFLICT")
        keys, by_athlete = set(), {}
        for ent, rec in valid_entries:
            athlete_id = ent["athlete_id"]
            sig = (tid, athlete_id, ent["status"], ent["date"])
            if sig in keys:
                continue
            keys.add(sig)
            by_athlete.setdefault(athlete_id, set()).add(ent["status"])
        for ent, rec in valid_entries:
            aid = ent["athlete_id"]
            if (tid, aid, ent["status"], ent["date"]) not in keys:
                continue
            # Only one record per distinct signature per team.
            keys.remove((tid, aid, ent["status"], ent["date"]))
            reasons = ["OPERATOR_VERIFICATION_REQUIRED", "ROLE_NOT_VERIFIED",
                       "NO_PROOF_OF_INJURY_REPORT_COMPLETENESS"]
            if roster_state != "ROSTER_MATCHABLE":
                reasons.append(roster_state)
            match = roster.get(aid)
            if not match or match["name"] != ent["name"]:
                reasons.append("ATHLETE_ID_OR_NAME_ROSTER_MISMATCH")
            if ent["status"] not in KNOWN:
                reasons.append("UNKNOWN_INJURY_STATUS")
            if len(by_athlete.get(aid, set())) > 1:
                reasons.append("CONFLICTING_INJURY_STATUSES")
            if not ent["date"]:
                reasons.append("INJURY_DATE_UNKNOWN")
            else:
                try:
                    if timestamp(ent["date"], "INJURY_DATE") > at:
                        reasons.append("FUTURE_INJURY_REPORT")
                except Refused:
                    reasons.append("UNVERIFIABLE_INJURY_DATE")
            if sport == "CFB" and match and match["position"] == "QB":
                reasons.append("QB_STARTER_UNCONFIRMED")
            for g in games_team:
                reasons_game = list(reasons)
                if timestamp(g["kickoff_utc"], "KICKOFF") <= at:
                    reasons_game.append("CAPTURE_NOT_PREGAME")
                candidates.append({
                    "sport": sport, "event_id": g["event_id"], "team": team,
                    "espn_team_id": tid, "athlete_id": aid, "player": ent["name"],
                    "position": match["position"] if match else "",
                    "status": ent["status"], "injury_date": ent["date"],
                    "source_url": rec["url"], "source_sha256": rec["sha256"] or "",
                    "reason_codes": "|".join(sorted(set(reasons_game))),
                    "model_role": "", "impact": "", "approved_for_model": "false"})
        if sport == "CFB":
            for aid, r in roster.items():
                if r["position"] != "QB":
                    continue
                for g in games_team:
                    qbs.append({"event_id": g["event_id"], "team": team,
                        "espn_team_id": tid, "athlete_id": aid, "player": r["name"],
                        "depthchart_source_sha256": depth_rec.get("sha256") or "",
                        "starter_confirmed": "false",
                        "reason_codes": "QB_ROSTER_ONLY_NOT_STARTER|EXTERNAL_STARTER_CONFIRMATION_REQUIRED"})
        for g in games_team:
            reasons = sorted(set(flags + ([] if roster_state == "ROSTER_MATCHABLE" else [roster_state])))
            if timestamp(g["kickoff_utc"], "KICKOFF") <= at:
                reasons.append("CAPTURE_NOT_PREGAME")
            reasons.append("NO_CONFIRMED_NEGATIVE_INJURY_COVERAGE")
            if sport == "CFB":
                reasons.append("QB_STARTER_UNCONFIRMED")
            coverage.append({"sport": sport, "event_id": g["event_id"], "team": team,
                "espn_team_id": tid, "injury_entries": len(valid_entries),
                "roster_n": len(roster), "state": "REVIEW_REQUIRED",
                "reason_codes": sorted(set(reasons)),
                "official_eligibility": False, "stake_u": 0})
    return {
        "state": "PAPER_0U_SOURCE_INCOMPLETE", "captured_utc": at.isoformat(),
        "offline_fixture": fixtures, "events": len(games), "teams": len(teams),
        "coverage": coverage, "candidate_injuries": candidates,
        "qb_review": qbs, "sources": source_info, "official_wagers": 0,
        "no_auto_model_input": True
    }, sources


def write_csv(path, cols, rows):
    with path.open("x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def persist(report, sources, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "capture_manifest.json").open("x", encoding="utf-8") as f:
        json.dump({k: v for k, v in report.items() if k not in
                   ("candidate_injuries", "qb_review", "coverage")}, f, indent=2, sort_keys=True)
    with (output / "coverage.json").open("x", encoding="utf-8") as f:
        json.dump(report["coverage"], f, indent=2, sort_keys=True)
    write_csv(output / "injury_candidates_FOR_REVIEW.csv", CANDIDATE_FIELDS, report["candidate_injuries"])
    write_csv(output / "qb_roster_NOT_STARTERS.csv", QB_FIELDS, report["qb_review"])
    raw_dir = output / "raw_espn"
    raw_dir.mkdir()
    for key, (_, rec) in sources.items():
        if "raw" in rec:
            safe = "__".join(key) + ".json"
            (raw_dir / safe).write_bytes(rec["raw"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slate", required=True,
                   help="CSV: sport,event_id,kickoff_utc,home,away,home_espn_id,away_espn_id")
    p.add_argument("--out-dir", required=True, help="New directory; never overwrites")
    p.add_argument("--fixtures", help="Offline snapshot folder, no HTTP; not authenticated as live")
    a = p.parse_args()
    games = slate_rows(a.slate)
    if a.fixtures:
        root = Path(a.fixtures)
        def fetch(_url, key):
            return (root / (key.replace(":", "__") + ".json")).read_bytes()
    else:
        def fetch(url, _key):
            return get_bytes(url)
    report, sources = make_report(games, fetch, fixtures=bool(a.fixtures))
    persist(report, sources, a.out_dir)
    print(f"RESEARCH/PAPER 0u: {len(games)} games, {len(report['coverage'])} team-games, "
          f"{len(report['candidate_injuries'])} unapproved injury leads, "
          f"{len(report['qb_review'])} unconfirmed QB roster entries.")


if __name__ == "__main__":
    main()
