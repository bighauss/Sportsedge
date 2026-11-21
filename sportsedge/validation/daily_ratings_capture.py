"""Daily point-in-time ratings capture (Torvik CBB, CFBD SP+). PAPER / 0u.

Saves the exact response bytes of each source with a UTC observation time and
SHA256, into a private owner-only directory. Never retries, never fabricates a
missing source, never prints a key. One CFBD call per run (free tier: 1,000 a
month). Non-200 or empty bodies are recorded as BLOCKED, not as data.
"""
from __future__ import annotations

import argparse, csv, hashlib, io, json, math, os, sys, urllib.error, urllib.request
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


MAX_BYTES = 4_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward CFBD Authorization to a redirected host or path."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url, key, timeout=30):
    headers = {"User-Agent": UA, "Accept": "application/json,text/csv"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as r:
            if r.status != 200 or r.geturl() != url:
                return (r.status, b"")
            data = r.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                return (413, b"")
            return (r.status, data)
    except urllib.error.HTTPError as e:
        # Never log HTTPError's URL, which could embed credentials.
        return (e.code, b"")
    except (urllib.error.URLError, TimeoutError, OSError):
        return (None, b"")


def _numeric(value, low=-100.0, high=200.0):
    if type(value) is bool:
        return False
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(n) and low <= n <= high


def _normalized(name):
    return "".join(c for c in name.strip().lower() if c.isalnum())


def check_body(expect, body):
    """Exact-byte source gets CAPTURED only with structurally usable ratings.

    This is schema validation, NOT validation that the ratings were available
    historically, nor that the provider response was authenticated upstream.
    """
    if not body:
        return "EMPTY_BODY"
    if len(body) > MAX_BYTES:
        return "BODY_TOO_LARGE"
    if body[:300].lstrip().lower().startswith((b"<html", b"<!doctype")):
        return "HTML_NOT_RATINGS"
    if expect == "csv":
        try:
            reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
            raw_header = next(reader, [])
            header = [_normalized(x) for x in raw_header]
            if not header or not all(header) or len(header) != len(set(header)):
                return "CSV_HEADER_INVALID"
            def index(aliases):
                hits = [i for i, name in enumerate(header) if name in aliases]
                return hits[0] if len(hits) == 1 else None
            col = {
                "team": index(("team", "teamname")),
                "off": index(("adjoe", "adjo", "adjoffense", "adjustedoffense")),
                "def": index(("adjde", "adjd", "adjdefense", "adjusteddefense")),
                "tempo": index(("adjt", "adjtempo", "adjustedtempo"))
            }
            if any(x is None for x in col.values()):
                return "CSV_REQUIRED_RATINGS_MISSING"
            names = set()
            for record in reader:
                if len(record) != len(header) or not any(x.strip() for x in record):
                    return "CSV_ROW_SHAPE_INVALID"
                team = record[col["team"]].strip()
                if not team or team in names:
                    return "CSV_TEAM_DUPLICATE_OR_MISSING"
                names.add(team)
                if not (_numeric(record[col["off"]], 65, 160) and
                        _numeric(record[col["def"]], 65, 160) and
                        _numeric(record[col["tempo"]], 45, 90)):
                    return "CSV_RATINGS_INVALID"
            return None if 350 <= len(names) <= 420 else "CSV_D1_CENSUS_INCOMPLETE"
        except (UnicodeError, csv.Error):
            return "CSV_DECODE_INVALID"
    if expect != "json":
        return "SOURCE_KIND_UNKNOWN"
    try:
        records = json.loads(body)
    except (ValueError, UnicodeError):
        return "INVALID_JSON"
    if not isinstance(records, list) or len(records) != 138:
        return "CFBD_FBS_CENSUS_INCOMPLETE"
    teams = set()
    for row in records:
        if not isinstance(row, dict):
            return "CFBD_RATING_SCHEMA_INVALID"
        team = row.get("team")
        if not isinstance(team, str) or not team.strip() or team in teams:
            return "CFBD_TEAM_DUPLICATE_OR_MISSING"
        teams.add(team)
        for k in ("offense", "defense", "specialTeams"):
            value = row.get(k)
            if not isinstance(value, dict) or not _numeric(value.get("rating"), -100, 100):
                return "CFBD_RATING_SCHEMA_INVALID"
        if not _numeric(row.get("rating"), -100, 100):
            return "CFBD_RATING_SCHEMA_INVALID"
    return None

def capture(root: Path, srcs, fetch=_fetch, now=None):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_mode & 0o077:
        raise ValueError("ARCHIVE_MUST_BE_OWNER_ONLY")
    receipts = []
    for s in srcs:
        key = os.environ.get(s["key_env"]) if s["key_env"] else None
        if s["key_env"] and not key:
            observed = (now or datetime.now(timezone.utc)).isoformat()
            receipts.append({"source": s["name"], "state": "BLOCKED_KEY_ABSENT", "observed_utc": observed})
            continue
        status, body = fetch(s["url"], key)
        observed = (now or datetime.now(timezone.utc)).isoformat()
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
