#!/usr/bin/env python3
"""Capture public ESPN evidence for the AdjustedFit public-replay bridge (PAPER / 0u, NON_COUNTED).

Writes, to --out:
  d1_evidence.json       Division I team ids from the ESPN groups=50 team list (hash of the real bytes)
  venue_evidence.json    event ids whose venue equals the home team's venue and neutralSite is false
  capture_manifest.json  url -> sha256/bytes of every response used
  raw/<sha256>.bin       the original response bytes behind each manifest hash
  schema_probe.json      every JSON path containing a 'venue' key in sample responses
  status.json            always written, including on failure

Limits, stated plainly: ESPN's team list is a public mirror, not an NCAA registry; team venues come
from documented fields only (site team doc, then the core team resource venue $ref) and are never
guessed; captured_utc is the capture start, so the evidence can only be used for freezes after it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball"
HEADERS = {"User-Agent": "sportsedge-research/1.0"}
D1_COUNT_RANGE = (340, 380)
MIN_TEAMS_WITH_VENUE = 300
_VENUE_REF = re.compile(r"/venues/(\d+)")


def parse_team_ids(raw):
    doc = json.loads(raw)
    teams = doc["sports"][0]["leagues"][0]["teams"]
    return sorted({str(t["team"]["id"]) for t in teams})


def _venue_id(node):
    if not isinstance(node, dict):
        return None
    value = str(node.get("id") or "").strip()
    if value:
        return value
    match = _VENUE_REF.search(str(node.get("$ref") or ""))
    return match.group(1) if match else None


def parse_team_venue(raw):
    """Venue id of one team from documented fields only; None when absent. Never guesses."""
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        return None
    team = doc.get("team") if isinstance(doc.get("team"), dict) else {}
    franchise = team.get("franchise") if isinstance(team.get("franchise"), dict) else {}
    for node in (franchise.get("venue"), team.get("venue"), doc.get("venue")):
        found = _venue_id(node)
        if found:
            return found
    return None


def venue_key_paths(node, prefix="", out=None, limit=60):
    """JSON paths whose key mentions 'venue' (schema inspection only)."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(node, dict):
        for key, value in node.items():
            path = prefix + "/" + str(key)
            if "venue" in str(key).lower():
                out.append(path)
            venue_key_paths(value, path, out, limit)
    elif isinstance(node, list):
        for value in node[:3]:
            venue_key_paths(value, prefix + "[]", out, limit)
    return out


def d1_count_ok(count):
    return D1_COUNT_RANGE[0] <= count <= D1_COUNT_RANGE[1]


def classify_events(doc, team_venue):
    """Return (verified_home_event_ids, census). neutralSite must be exactly false."""
    census = {"events": 0, "verified_home": 0, "no_competition": 0, "no_home_competitor": 0,
              "neutral_or_unknown": 0, "venue_missing": 0, "venue_mismatch": 0}
    verified = []
    for ev in doc.get("events") or []:
        census["events"] += 1
        comps = ev.get("competitions") or []
        if not comps:
            census["no_competition"] += 1
            continue
        comp = comps[0]
        gid = str(ev.get("id") or "").strip()
        home = next((c for c in comp.get("competitors") or [] if c.get("homeAway") == "home"), None)
        if not gid or home is None:
            census["no_home_competitor"] += 1
            continue
        if comp.get("neutralSite") is not False:
            census["neutral_or_unknown"] += 1
            continue
        venue = str((comp.get("venue") or {}).get("id") or "").strip()
        home_venue = team_venue.get(str((home.get("team") or {}).get("id") or ""))
        if not venue or not home_venue:
            census["venue_missing"] += 1
            continue
        if venue != home_venue:
            census["venue_mismatch"] += 1
            continue
        verified.append(gid)
        census["verified_home"] += 1
    return verified, census


def fetch(url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("FETCH_FAILED:" + url + ":" + type(last).__name__)


def _days(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--season", type=int, default=2027)
    ap.add_argument("--start", default="2026-11-01")
    ap.add_argument("--end", default=None, help="default: today + 3 days (UTC)")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    out = Path(a.out)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    captured = _stamp(now)
    start = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end) if a.end else now.date() + timedelta(days=3)
    status = {"label": "PAPER_0U_NON_COUNTED", "status": "FAILED", "captured_utc": captured,
              "window": [start.isoformat(), end.isoformat()], "errors": []}
    manifest, probe = {}, {}

    def record(url, raw):
        digest = hashlib.sha256(raw).hexdigest()
        manifest[url] = {"sha256": digest, "bytes": len(raw)}
        (out / "raw" / (digest + ".bin")).write_bytes(raw)
        return raw

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "models" / "cbb"))
        import public_replay_adapted as A
        teams_url = BASE + "/teams?groups=50&limit=500"
        teams_raw = record(teams_url, fetch(teams_url))
        ids = parse_team_ids(teams_raw)
        status["d1_team_count"] = len(ids)
        if not d1_count_ok(len(ids)):
            raise RuntimeError("D1_COUNT_OUT_OF_RANGE:" + str(len(ids)))
        d1_doc = A.build_evidence_doc(kind=A.KIND_D1, ids=ids, season=a.season,
                                      source_label="ESPN_TEAMS_GROUPS_50", source_bytes=teams_raw,
                                      captured_utc=captured)
        (out / "d1_evidence.json").write_text(json.dumps(d1_doc, indent=1, sort_keys=True))

        def team_job(tid):
            pairs, venue, source, err = [], None, None, None
            site_url = BASE + "/teams/" + tid
            try:
                raw = fetch(site_url)
                pairs.append((site_url, raw))
                venue = parse_team_venue(raw)
                source = "SITE_TEAM_DOC" if venue else None
                if venue is None:
                    core_url = CORE + "/seasons/" + str(a.season) + "/teams/" + tid
                    raw2 = fetch(core_url)
                    pairs.append((core_url, raw2))
                    venue = parse_team_venue(raw2)
                    source = "CORE_TEAM_RESOURCE" if venue else None
            except (RuntimeError, ValueError) as exc:
                err = str(exc)
            return tid, pairs, venue, source, err

        team_venue, errors, sources = {}, [], {}
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            for tid, pairs, venue, source, err in pool.map(team_job, ids):
                for url, raw in pairs:
                    record(url, raw)
                    kind = "site_team" if url.startswith(BASE) else "core_team"
                    if len(probe.setdefault(kind + "_venue_paths", {})) < 3:
                        try:
                            probe[kind + "_venue_paths"][url] = venue_key_paths(json.loads(raw))
                        except ValueError:
                            probe[kind + "_venue_paths"][url] = ["NOT_JSON"]
                if err:
                    errors.append(err)
                if venue:
                    team_venue[tid] = venue
                    sources[source] = sources.get(source, 0) + 1
        status["teams_with_venue"] = len(team_venue)
        status["team_fetch_errors"] = len(errors)
        status["venue_source_counts"] = sources

        verified, census = [], {}
        for day in _days(start, end):
            url = BASE + "/scoreboard?dates=" + day.strftime("%Y%m%d") + "&groups=50&limit=400"
            raw = record(url, fetch(url))
            doc = json.loads(raw)
            if len(probe.setdefault("scoreboard_venue_paths", {})) < 2 and doc.get("events"):
                probe["scoreboard_venue_paths"][url] = venue_key_paths(doc["events"][0])
            ids_day, day_census = classify_events(doc, team_venue)
            verified.extend(ids_day)
            for key, value in day_census.items():
                census[key] = census.get(key, 0) + value
        status["scoreboard_census"] = census
        if len(team_venue) < MIN_TEAMS_WITH_VENUE:
            raise RuntimeError("TEAM_VENUE_COVERAGE_TOO_LOW:" + str(len(team_venue)))
        if not verified:
            raise RuntimeError("NO_VERIFIED_HOME_EVENTS")
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        venue_doc = A.build_evidence_doc(kind=A.KIND_VENUE, ids=verified, season=a.season,
                                         source_label="ESPN_SCOREBOARD_PLUS_TEAM_VENUE",
                                         source_bytes=manifest_bytes, captured_utc=captured)
        (out / "venue_evidence.json").write_text(json.dumps(venue_doc, indent=1, sort_keys=True))
        status["status"] = "OK"
        status["usable_for"] = "freezes strictly after captured_utc only"
    except Exception as exc:  # status.json must always be written
        status["errors"].append(type(exc).__name__ + ":" + str(exc))
    finally:
        status["capture_completed_utc"] = _stamp(datetime.now(timezone.utc))
        (out / "schema_probe.json").write_text(json.dumps(probe, indent=1, sort_keys=True))
        (out / "capture_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
        (out / "status.json").write_text(json.dumps(status, indent=1, sort_keys=True))
    print(json.dumps(status, sort_keys=True))
    return 0 if status["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
