"""Daily point-in-time ratings capture (CBBD adjusted CBB, CFBD SP+; Torvik by manual import). PAPER / 0u.

Saves the exact response bytes of each source with a UTC observation time and
SHA256, into a new private owner-only directory. Never retries, follows
redirects, fabricates a missing source, or prints a key.
"""
from __future__ import annotations

import argparse, csv, hashlib, io, json, os, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import stat
from zoneinfo import ZoneInfo

UA = "SportsEdge-research/1.0 (+https://github.com/bighauss/Sportsedge)"
MAX_BYTES = 2_000_000
CT = ZoneInfo("America/Chicago")


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("RATINGS_CLOCK_MUST_HAVE_OFFSET")
    return value.astimezone(timezone.utc)


def _stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def sources(season_cbb: int, season_cfb: int):
    if any(type(s) is not int or not 2000 <= s <= 2100 for s in (season_cbb, season_cfb)):
        raise ValueError("INVALID_SEASON")
    return [
        {"name": "torvik_team_results", "url": f"https://barttorvik.com/{season_cbb}_team_results.csv",
         "key_env": None, "expect": "csv", "season": season_cbb},
        {"name": "cfbd_ratings_sp", "url": f"https://api.collegefootballdata.com/ratings/sp?year={season_cfb}",
         "key_env": "CFBD_API_KEY", "expect": "json", "season": season_cfb},
    ]


def cbbd_source(season_cbb: int):
    if type(season_cbb) is not int or not 2000 <= season_cbb <= 2100:
        raise ValueError("INVALID_SEASON")
    return {"name": "cbbd_ratings_adjusted",
            "url": f"https://api.collegebasketballdata.com/ratings/adjusted?season={season_cbb}",
            "key_env": "CBBD_API_KEY", "expect": "cbbd_json", "season": season_cbb}


def known_sources(season: int):
    return sources(season, season) + [cbbd_source(season)]


def automated_sources(season_cbb: int, season_cfb: int):
    """Runner path. Torvik returns HTTP 403 to data-center IPs, so it is manual-import only."""
    return [cbbd_source(season_cbb), sources(season_cbb, season_cfb)[1]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _fetch(url, key, timeout=30):
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=timeout) as r:
            if r.geturl() != url or r.status != 200:
                return r.status, b""
            return r.status, r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, b""


def _finite(value, lo, hi):
    return not isinstance(value, bool) and lo <= float(value) <= hi


def _fields(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("DUPLICATE_JSON_KEY")
    return result


def _bad_json_constant(_):
    raise ValueError("NONFINITE_JSON_NUMBER")


def _inspect(expect, body, season):
    if not body:
        return "EMPTY_BODY", 0
    if len(body) > MAX_BYTES:
        return "BODY_TOO_LARGE", 0
    if expect == "csv":
        if body[:200].lstrip().startswith(b"<"):
            return "HTML_NOT_CSV", 0
        needed = {"team", "adjoe", "adjde", "adjt"}
        try:
            rows = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
            header = next(rows)
            if not needed.issubset(header) or any(header.count(k) != 1 for k in needed):
                return "CSV_SCHEMA", 0
            team, off, defense, tempo = (header.index(k) for k in ("team", "adjoe", "adjde", "adjt"))
            names = set()
            for row in rows:
                if len(row) != len(header):
                    return "CSV_ROW_WIDTH", 0
                key = row[team].strip().casefold()
                if (not key or key in names or not _finite(row[off], 20, 250)
                        or not _finite(row[defense], 20, 250) or not _finite(row[tempo], 20, 120)):
                    return "CSV_TEAM_OR_RATING_INVALID", 0
                names.add(key)
        except (UnicodeError, csv.Error, StopIteration, ValueError, OverflowError):
            return "INVALID_CSV", 0
        return (None, len(names)) if 350 <= len(names) <= 420 else ("CSV_CENSUS_OUT_OF_RANGE", len(names))
    if expect not in ("json", "cbbd_json"):
        return "SOURCE_KIND_UNKNOWN", 0
    try:
        doc = json.loads(body, object_pairs_hook=_fields, parse_constant=_bad_json_constant)
    except (ValueError, RecursionError):
        return "INVALID_JSON", 0
    if not isinstance(doc, list):
        return "JSON_SCHEMA", 0
    names = set()
    if expect == "cbbd_json":
        ids = set()
        for row in doc:
            if not isinstance(row, dict) or type(row.get("season")) is not int or row.get("season") != season:
                return "CBBD_WRONG_SEASON_OR_SCHEMA", 0
            team = row.get("team")
            tid = row.get("teamId")
            if not isinstance(team, str) or not team.strip() or type(tid) is not int or tid <= 0 or tid in ids:
                return "CBBD_TEAM_INVALID", 0
            key = team.strip().casefold()
            o, dfn, net = (row.get(k) for k in ("offensiveRating", "defensiveRating", "netRating"))
            if (key in names or any(type(n) not in (float, int) for n in (o, dfn, net))
                    or not 60 <= o <= 160 or not 60 <= dfn <= 160 or not -80 <= net <= 80):
                return "CBBD_TEAM_OR_RATING_INVALID", 0
            names.add(key)
            ids.add(tid)
        return (None, len(names)) if 350 <= len(names) <= 420 else ("CBBD_CENSUS_OUT_OF_RANGE", len(names))
    for row in doc:
        if not isinstance(row, dict) or row.get("year") != season or type(row.get("year")) is not int:
            return "SP_WRONG_SEASON_OR_SCHEMA", 0
        team = row.get("team")
        if not isinstance(team, str) or not team.strip():
            return "SP_TEAM_INVALID", 0
        key = team.strip().casefold()
        nums = [row.get("rating")] + [
            row[k].get("rating") if isinstance(row.get(k), dict) else None
            for k in ("offense", "defense", "specialTeams")
        ]
        if key in names or any(type(n) not in (float, int) or not -250 <= n <= 250 for n in nums):
            return "SP_TEAM_OR_RATING_INVALID", 0
        names.add(key)
    return (None, len(names)) if 125 <= len(names) <= 175 else ("SP_CENSUS_OUT_OF_RANGE", len(names))


def capture(root: Path, srcs, fetch=_fetch, clock=None, claim_date=None, *, local_torvik=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    srcs = tuple(srcs)
    sources_expected = {s["url"]: s for src in srcs for s in known_sources(src["season"])}
    if not srcs or any(sources_expected.get(s.get("url")) != s for s in srcs):
        raise ValueError("UNRECOGNIZED_RATINGS_SOURCE")
    if len({s["name"] for s in srcs}) != len(srcs):
        raise ValueError("DUPLICATE_RATINGS_SOURCE")
    if local_torvik is not None and (len(srcs) != 1 or srcs[0]["name"] != "torvik_team_results"):
        raise ValueError("LOCAL_IMPORT_ALLOWS_TORVIK_ONLY")
    if local_torvik is None and any(s["name"] == "torvik_team_results" for s in srcs):
        raise ValueError("TORVIK_LOCAL_IMPORT_ONLY")
    root.mkdir(mode=0o700, exist_ok=False)
    receipts = []
    for s in srcs:
        key = os.environ.get(s["key_env"]) if s["key_env"] else None
        started = _utc(clock())
        rec = {"source": s["name"], "url": s["url"], "season": s["season"],
               "request_started_utc": _stamp(started), "provider_published_utc": None,
               "observation_basis": "LOCAL_FILE_NOT_PROVIDER_ATTESTED" if local_torvik is not None
               else "HTTPS_RETRIEVAL"}
        if claim_date is not None and started.astimezone(CT).date().isoformat() != claim_date:
            receipts.append({**rec, "state": "BLOCKED_CLAIM_DATE_CHANGED"})
            continue
        if s["key_env"] and not key:
            receipts.append({**rec, "state": "BLOCKED_KEY_ABSENT"})
            continue
        if local_torvik is not None:
            fd = os.open(local_torvik, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise ValueError("LOCAL_INPUT_MUST_BE_REGULAR_FILE")
                body = source.read(MAX_BYTES + 1)
            status = None
        else:
            status, body = fetch(s["url"], key)
        observed = _utc(clock())
        problem, count = (_inspect(s["expect"], body, s["season"]) if status == 200 or local_torvik is not None
                          else ("HTTP_" + str(status), 0))
        if started > observed:
            problem = "CLOCK_MOVED_BACKWARD"
        rec.update(http_status=status, observed_utc=_stamp(observed), bytes=len(body))
        if problem:
            rec["state"] = "BLOCKED_" + problem
        else:
            ext = "csv" if s["expect"] == "csv" else "json"
            name = f"{s['name']}.{ext}"
            fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(body)
            rec.update(state="CAPTURED", file=name, row_count=count,
                       sha256="sha256:" + hashlib.sha256(body).hexdigest())
        receipts.append(rec)
    out = {"schema": "sportsedge-daily-ratings-capture-v1", "official_counted": 0,
           "approved_stake_u": 0, "receipts": receipts}
    fd = os.open(root / "receipt.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return out


def eligible_bytes(body, receipt, *, source, season, decision, kickoff, max_age_seconds):
    """Gate decrypted bytes at the forecast cutoff; makes no publisher-time claim."""
    decision, kickoff = _utc(decision), _utc(kickoff)
    expected = next((s for s in known_sources(season) if s["name"] == source), None)
    if (not isinstance(receipt, dict) or expected is None or receipt.get("source") != source or receipt.get("season") != season
            or receipt.get("url") != expected["url"] or receipt.get("state") != "CAPTURED"):
        raise ValueError("RATINGS_RECEIPT_SCOPE_MISMATCH")
    try:
        def _parse(s):
            s = str(s).strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        observed, started = (_utc(_parse(receipt[k])) for k in
                             ("observed_utc", "request_started_utc"))
    except (KeyError, ValueError, TypeError):
        raise ValueError("RATINGS_RECEIPT_CLOCK_INVALID") from None
    if (type(max_age_seconds) not in (float, int) or not 0 < max_age_seconds <= 366 * 86400
            or not started <= observed <= decision < kickoff
            or (decision - observed).total_seconds() > max_age_seconds):
        raise ValueError("RATINGS_NOT_ELIGIBLE_AT_DECISION")
    if (receipt.get("bytes") != len(body)
            or receipt.get("sha256") != "sha256:" + hashlib.sha256(body).hexdigest()):
        raise ValueError("RATINGS_BYTES_MISMATCH")
    problem, count = _inspect(expected["expect"], body, season)
    if problem or count != receipt.get("row_count"):
        raise ValueError("RATINGS_PAYLOAD_INVALID")
    return body


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("private_dir", type=Path)
    p.add_argument("--cbb-season", type=int)
    p.add_argument("--cfb-season", type=int)
    p.add_argument("--claim-date")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true", help="permit requests to CBBD and CFBD (Torvik blocks runners)")
    modes.add_argument("--import-torvik", type=Path, help="archive an original Torvik CSV locally without fetching")
    a = p.parse_args(argv)
    if not a.execute and a.import_torvik is None:
        print("DRY_RUN: no requests or writes")
        return 0
    today = datetime.now(CT).date()
    cbb = a.cbb_season if a.cbb_season is not None else today.year + (today.month >= 9)
    cfb = a.cfb_season if a.cfb_season is not None else today.year - (today.month <= 1)
    if os.getenv("GITHUB_ACTIONS") == "true" and (not a.claim_date or a.import_torvik is not None):
        return 2
    try:
        srcs = sources(cbb, cfb)[:1] if a.import_torvik is not None else automated_sources(cbb, cfb)
        out = capture(a.private_dir, srcs,
                      claim_date=a.claim_date, local_torvik=a.import_torvik)
    except (ValueError, OSError):
        print("BLOCKED_RATINGS_CAPTURE", file=sys.stderr)
        return 2
    # Public log: states and sizes only, never bodies or keys.
    for r in out["receipts"]:
        print(r["source"], r["state"], r.get("bytes", 0))
    return 0 if all(r["state"] == "CAPTURED" for r in out["receipts"]) else 2


if __name__ == "__main__":
    sys.exit(main())
