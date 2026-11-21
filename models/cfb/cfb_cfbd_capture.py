"""Prospective CFBD pregame capture into a private CFB capture directory. PAPER / 0u.

Dry-run by default. With ``--execute`` it makes at most four documented
read-only CFBD GETs (games for one week, season advanced stats, talent,
returning production) using ``CFBD_API_KEY`` from the environment, with no
redirects and no retries. The key is never printed or stored. Missing key =>
exit 2 before any request (fail closed). Run this BEFORE kickoff: a capture
taken after games are played is post-game data and the assembler refuses it
for those games. SP+ comes from ``sportsedge.validation.daily_ratings_capture``.
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlencode

from models.cfb import cfb_capture_store as store
from sportsedge.validation import daily_ratings_capture as ratings_capture

BASE = "https://api.collegefootballdata.com"
PROVIDER = "collegefootballdata.com"


def endpoints(season: int, week: int, season_type: str = "regular"):
    if type(season) is not int or not 2000 <= season <= 2100 or type(week) is not int or not 0 <= week <= 20:
        raise store.CaptureRefused("SEASON_OR_WEEK_INVALID")
    if season_type not in ("regular", "postseason"):
        raise store.CaptureRefused("SEASON_TYPE_INVALID")
    return {
        "cfbd_games": f"{BASE}/games?" + urlencode({"year": season, "week": week, "seasonType": season_type,
                                                    "classification": "fbs"}),
        "cfbd_advanced": f"{BASE}/stats/season/advanced?" + urlencode({"year": season, "excludeGarbageTime": "true"}),
        "cfbd_talent": f"{BASE}/talent?" + urlencode({"year": season}),
        "cfbd_returning": f"{BASE}/player/returning?" + urlencode({"year": season}),
    }


def capture(directory, *, season, week, season_type="regular", fetch=None, clock=None, key=None):
    key = key if key is not None else os.environ.get("CFBD_API_KEY")
    if not key:
        return {"state": "BLOCKED_KEY_ABSENT", "receipts": [], "official_counted": 0, "approved_stake_u": 0}
    fetch = fetch or ratings_capture._fetch
    clock = clock or store.now_utc
    store.init_capture(directory, season=season, week=week, season_type=season_type)
    states = []
    for source, url in endpoints(season, week, season_type).items():
        started = clock()
        status, body = fetch(url, key)
        observed = clock()
        if status != 200 or not body:
            states.append({"source": source, "state": f"BLOCKED_HTTP_{status}"})
            continue
        if key.encode() in body:
            states.append({"source": source, "state": "BLOCKED_SECRET_ECHO"})
            continue
        try:
            rec = store.store_source(directory, source, body, provider=PROVIDER, url=url, http_status=status,
                                     observed_utc=observed, captured_utc=clock())
        except store.CaptureRefused as exc:
            states.append({"source": source, "state": "BLOCKED_" + str(exc)})
            continue
        if started > observed:
            states.append({"source": source, "state": "BLOCKED_CLOCK_MOVED_BACKWARD"})
            continue
        states.append({"source": source, "state": "CAPTURED", "bytes": rec["bytes"]})
    ok = all(s["state"] == "CAPTURED" for s in states)
    return {"state": "CAPTURED" if ok else "PARTIAL", "receipts": states, "official_counted": 0,
            "approved_stake_u": 0}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("capture_dir")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--season-type", default="regular")
    p.add_argument("--execute", action="store_true", help="permit up to four CFBD requests")
    a = p.parse_args(argv)
    if not a.execute:
        for name in endpoints(a.season, a.week, a.season_type):
            print("DRY_RUN", name)
        return 0
    try:
        out = capture(a.capture_dir, season=a.season, week=a.week, season_type=a.season_type)
    except (store.CaptureRefused, OSError):
        print("BLOCKED_CFBD_CAPTURE", file=sys.stderr)
        return 2
    for r in out["receipts"]:  # states and sizes only, never bodies or keys
        print(r["source"], r["state"], r.get("bytes", 0))
    if out["state"] == "BLOCKED_KEY_ABSENT":
        print("BLOCKED_KEY_ABSENT", file=sys.stderr)
    return 0 if out["state"] == "CAPTURED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
