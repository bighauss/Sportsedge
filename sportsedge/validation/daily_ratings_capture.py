"""Daily point-in-time ratings capture (Torvik CBB, CFBD SP+). PAPER / 0u.

Saves the exact response bytes of each source with a UTC observation time and
SHA256, into a private owner-only directory. Never retries, never fabricates a
missing source, never prints a key. One CFBD call per run (free tier: 1,000 a
month). Non-200 or empty bodies are recorded as BLOCKED, not as data.
"""
from __future__ import annotations

import argparse, hashlib, json, os, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "SportsEdge-research/1.0 (+https://github.com/bighauss/Sportsedge)"


def sources(season_cbb: int, season_cfb: int):
    return [
        {"name": "torvik_team_results", "url": f"https://barttorvik.com/{season_cbb}_team_results.csv",
         "key_env": None, "expect": "csv"},
        {"name": "cfbd_ratings_sp", "url": f"https://api.collegefootballdata.com/ratings/sp?year={season_cfb}",
         "key_env": "CFBD_API_KEY", "expect": "json"},
    ]


def _fetch(url, key, timeout=30):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, b""


def check_body(expect, body):
    if not body:
        return "EMPTY_BODY"
    if expect == "csv":
        head = body[:200].lower()
        if b"<html" in head or b"<!doctype" in head:
            return "HTML_NOT_CSV"
        if body.count(b"\n") < 300:
            return "TOO_FEW_ROWS"
        return None
    try:
        doc = json.loads(body)
    except ValueError:
        return "INVALID_JSON"
    if not isinstance(doc, list) or len(doc) < 100:
        return "TOO_FEW_TEAMS"
    return None


def capture(root: Path, srcs, fetch=_fetch, now=None):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_mode & 0o077:
        raise ValueError("ARCHIVE_MUST_BE_OWNER_ONLY")
    receipts = []
    for s in srcs:
        key = os.environ.get(s["key_env"]) if s["key_env"] else None
        observed = (now or datetime.now(timezone.utc)).isoformat()
        if s["key_env"] and not key:
            receipts.append({"source": s["name"], "state": "BLOCKED_KEY_ABSENT", "observed_utc": observed})
            continue
        status, body = fetch(s["url"], key)
        problem = "HTTP_" + str(status) if status != 200 else check_body(s["expect"], body)
        rec = {"source": s["name"], "url": s["url"], "http_status": status, "observed_utc": observed,
               "bytes": len(body)}
        if problem:
            rec["state"] = "BLOCKED_" + problem
        else:
            name = f"{s['name']}.{s['expect']}"
            fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(body)
            rec.update(state="CAPTURED", file=name,
                       sha256="sha256:" + hashlib.sha256(body).hexdigest())
        receipts.append(rec)
    out = {"schema": "sportsedge-daily-ratings-capture-v1", "official_counted": 0,
           "approved_stake_u": 0, "receipts": receipts}
    fd = os.open(root / "receipt.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("private_dir", type=Path)
    p.add_argument("--cbb-season", type=int, default=2027)
    p.add_argument("--cfb-season", type=int, default=2026)
    a = p.parse_args(argv)
    out = capture(a.private_dir, sources(a.cbb_season, a.cfb_season))
    # Public log: states and sizes only, never bodies or keys.
    for r in out["receipts"]:
        print(r["source"], r["state"], r.get("bytes", 0))
    return 0 if all(r["state"] == "CAPTURED" for r in out["receipts"]) else 2


if __name__ == "__main__":
    sys.exit(main())
