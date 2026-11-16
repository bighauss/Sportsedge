"""Permissioned CBBD /games prospective evidence capture; NEVER a source of pregame ratings.

Documented endpoint: https://api.collegebasketballdata.com/games
No network without explicit CBBD_API_KEY. No URLs/headers containing credentials
are ever written. Original bytes remain in PRIVATE create-only storage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://api.collegebasketballdata.com/games"
MAX_BODY = 8 * 1024 * 1024
ZULU = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
SHA = re.compile(r"^[a-f0-9]{64}$")


class Hold(ValueError):
    pass


def utc(text, field):
    if not isinstance(text, str) or not ZULU.fullmatch(text):
        raise Hold(field + ": UTC_Z_REQUIRED")
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise Hold(field + ": INVALID_DATETIME") from exc


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def safe_path(path):
    """Reject both lexical checkout paths and symlinked checkout aliases."""
    lexical = Path(os.path.abspath(os.path.expanduser(str(path))))
    resolved = lexical.resolve()
    for p in (lexical, resolved):
        if p == ROOT or ROOT in p.parents:
            raise Hold("PUBLIC_GIT_REPOSITORY_IS_NOT_PRIVATE_STORAGE")
    return resolved


def _private_directory(path):
    directory = safe_path(path)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.stat().st_mode & 0o077:
        raise Hold("PRIVATE_DIRECTORY_PERMISSIONS_TOO_BROAD")
    return directory


def _private_create(path, raw):
    target = safe_path(path)
    created = False
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        if created:
            try:
                target.unlink()
            except OSError:
                pass
        raise


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Hold("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _bad_constant(x):
    raise Hold("NONFINITE_JSON:" + x)


def decoded(raw):
    if not isinstance(raw, bytes) or len(raw) == 0 or len(raw) > MAX_BODY:
        raise Hold("EMPTY_OR_EXCESSIVE_RESPONSE")
    try:
        rows = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs,
                          parse_constant=_bad_constant)
    except (ValueError, UnicodeError) as exc:
        raise Hold("NON_JSON_PROVIDER_BODY") from exc
    if not isinstance(rows, list):
        raise Hold("EXPECTED_GAMES_ARRAY")
    if len(rows) >= 3000:
        raise Hold("POSSIBLY_TRUNCATED_AT_PROVIDER_3000_GAME_LIMIT")
    return rows


def checked_window(season, start_utc, end_utc):
    if type(season) is not int or not 2000 <= season <= 2100:
        raise Hold("INVALID_SEASON_END_YEAR")
    start, end = utc(start_utc, "start"), utc(end_utc, "end")
    if not start < end or end-start > timedelta(hours=24):
        raise Hold("REQUEST_MUST_COVER_AT_MOST_ONE_UTC_DAY")
    # Refuse mixing seasons; 2027 refers to 2026-27 (Aug 2026-July 2027).
    for point in (start, end-timedelta(microseconds=1)):
        expected = point.year + (point.month >= 8)
        if expected != season:
            raise Hold("SEASON_END_YEAR_WINDOW_MISMATCH")
    return (start, end)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise Hold("REDIRECT_NOT_ALLOWED")


def _transport(request, max_body):
    opener = build_opener(_NoRedirect, HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise Hold("PROVIDER_NON_200")
            if response.geturl() != request.full_url:
                raise Hold("PROVIDER_URL_CHANGED")
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            raw = response.read(max_body + 1)
            return raw, content_type, response.geturl()
    except HTTPError as exc:
        raise Hold("PROVIDER_HTTP_STATUS_" + str(exc.code)) from None
    except URLError:
        raise Hold("PROVIDER_NETWORK_ERROR") from None


def capture_games(*, season, start_utc, end_utc, private_dir,
                  key=None, transport=None, clock=None):
    """Capture one authenticated API request. No user claims are silently verified."""
    start, end = checked_window(season, start_utc, end_utc)
    secret = key if key is not None else os.getenv("CBBD_API_KEY")
    if not isinstance(secret, str) or not secret.strip() or "\n" in secret or "\r" in secret:
        raise Hold("NO_AUTHORIZED_CBBD_API_KEY_NO_NETWORK")
    # Refuse an exposed destination BEFORE making an authenticated HTTP request.
    directory = _private_directory(private_dir)
    params = urlencode({"season": season, "startDateRange": iso(start),
                        "endDateRange": iso(end)})
    url = BASE + "?" + params
    request = Request(url, headers={"Authorization": "Bearer " + secret,
                                    "Accept": "application/json",
                                    "User-Agent": "SportsEdgeResearchCapture/1.0"}, method="GET")
    raw, content_type, actual = (transport or _transport)(request, MAX_BODY)
    if content_type != "application/json" or actual != url:
        raise Hold("UNEXPECTED_PROVIDER_CONTENT_TYPE_OR_URL")
    rows = decoded(raw)
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if not isinstance(now, datetime) or now.utcoffset() != timedelta(0):
        raise Hold("CAPTURE_CLOCK_NOT_UTC")
    received = iso(now)
    digest = hashlib.sha256(raw).hexdigest()
    stem = "cbbd_games_" + str(season) + "_" + now.strftime("%Y%m%dT%H%M%S%fZ")
    original = directory / (stem + ".raw.json")
    manifest_path = directory / (stem + ".manifest.json")
    if original.exists() or manifest_path.exists():
        raise FileExistsError("CAPTURE_NAME_ALREADY_EXISTS")
    manifest = {
        "format": "CBBD_GAMES_CAPTURE_V1",
        "provider": "collegebasketballdata",
        "documented_endpoint": BASE,
        "request_url_without_credentials": url,
        "season": season, "start_utc": iso(start), "end_utc": iso(end),
        "local_observed_utc": received, "source_sha256": digest,
        "source_bytes": len(raw), "returned_rows": len(rows),
        "status": "PROVIDER_TLS_RESPONSE_LOCAL_CLOCK_ONLY_NO_EXTERNAL_PUBLISH_ATTESTATION",
        "coverage_note": "EMPTY_IS_NOT_NO_GAMES; source limits/completeness not independently checked",
        "credential_persisted": False,
    }
    # If a process dies between two create-only writes an orphan is kept for
    # recovery rather than overwriting or silently deleting original bytes.
    _private_create(original, raw)
    _private_create(manifest_path, (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return {"raw_path": str(original), "manifest_path": str(manifest_path),
            "sha256": digest, "rows": len(rows), "observed_utc": received,
            "status": "LOCAL_OBSERVATION_UNVERIFIED_PRE_PUBLICATION"}


def finals_from_capture(raw_path, manifest_path, *, output_path):
    """Produce non-counted final receipts; retain all other provider rows with status.

    CBBD /games supplies no per-game first-publication UTC. Use this snapshot's
    observed timestamp for both fields (conservative upper bound), labeled
    explicitly so NO historical-before-snapshot inference is possible.
    """
    raw_path, manifest_path, output_path = (safe_path(p) for p in
                                            (raw_path, manifest_path, output_path))
    if output_path in (raw_path, manifest_path):
        raise Hold("SOURCE_OUTPUT_COLLISION")
    _private_directory(output_path.parent)
    raw = raw_path.read_bytes()
    man = json.loads(manifest_path.read_text("utf-8"),
                     object_pairs_hook=_unique_pairs, parse_constant=_bad_constant)
    if not isinstance(man, dict) or man.get("format") != "CBBD_GAMES_CAPTURE_V1":
        raise Hold("UNRECOGNIZED_OR_MISSING_MANIFEST")
    if man.get("documented_endpoint") != BASE or man.get("provider") != "collegebasketballdata":
        raise Hold("UNVERIFIED_CAPTURE_PROVIDER")
    observed = utc(man.get("local_observed_utc"), "local_observed_utc")
    digest = hashlib.sha256(raw).hexdigest()
    if man.get("source_sha256") != digest or man.get("source_bytes") != len(raw):
        raise Hold("ORIGINAL_RESPONSE_SHA_MISMATCH")
    rows = decoded(raw)
    if man.get("returned_rows") != len(rows):
        raise Hold("ORIGINAL_RESPONSE_ROW_COUNT_MISMATCH")
    results, ids = [], {}
    for index, game in enumerate(rows):
        row = {"input_index": index, "status": "BLOCKED", "official": False,
               "stake_u": 0}
        try:
            if not isinstance(game, dict):
                raise Hold("GAME_OBJECT_REQUIRED")
            ident = game.get("id")
            if type(ident) is not int or ident <= 0:
                raise Hold("CBBD_GAME_ID_REQUIRED")
            row["game_id"] = str(ident)
            # Reject ALL duplicates, even the first occurrence.
            ids.setdefault(ident, []).append(index)
            season = game.get("season")
            if type(season) is not int or season != man["season"]:
                raise Hold("SEASON_MISMATCH")
            home, away = game.get("homeTeamId"), game.get("awayTeamId")
            if any(type(x) is not int or x <= 0 for x in (home, away)) or home == away:
                raise Hold("TEAM_IDS_INVALID")
            kickoff = utc(game.get("startDate"), "startDate")
            if kickoff.year + (kickoff.month >= 8) != season:
                raise Hold("GAME_TIP_SEASON_MISMATCH")
            if game.get("startTimeTbd") is not False:
                raise Hold("UNCONFIRMED_TIPOFF_CLOCK")
            if not kickoff < observed:
                row["status"] = "NOT_FINAL_OR_FUTURE_EVENT"
            elif game.get("status") != "final":
                row["status"] = "NOT_FINAL_OR_FUTURE_EVENT"
            else:
                hp, ap = game.get("homePoints"), game.get("awayPoints")
                if any(type(x) is not int or x < 0 or x > 250 for x in (hp, ap)) or hp == ap:
                    raise Hold("INVALID_FINAL_SCORE")
                row.update({
                    "status": "FINAL_RECEIPT_LOCAL_CAPTURE_UNAUTHENTICATED",
                    "final": {
                        "game_id": str(ident), "season": season,
                        "home_team_id": str(home), "away_team_id": str(away),
                        "status": "FINAL", "period": "FG_INCL_OT",
                        "home_score": hp, "away_score": ap,
                        "sha256": digest,
                        "published_utc": iso(observed),
                        "captured_utc": iso(observed),
                        "publication_basis": "UPPER_BOUND_LOCAL_OBSERVATION_NOT_PROVIDER_PUBLICATION",
                    },
                })
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            row["reason"] = str(exc)
        results.append(row)
    for index_list in ids.values():
        if len(index_list) > 1:
            for index in index_list:
                results[index] = {"input_index": index, "game_id": results[index].get("game_id"),
                                  "status": "BLOCKED", "reason": "DUPLICATE_PROVIDER_GAME_ID",
                                  "official": False, "stake_u": 0}
    report = {
        "format": "CBBD_LOCAL_FINAL_RECEIPTS_V1",
        "status": "PAPER_0U_SOURCE_NOT_INDEPENDENTLY_ATTESTED",
        "official": False, "stake_u": 0,
        "source_sha256": digest,
        "local_observed_utc": iso(observed),
        "row_count": len(results),
        "rows": results,
        "warnings": [
            "NO_CBBD_PER_GAME_PUBLICATION_TIMESTAMP; CONSERVATIVE_LOCAL_OBSERVATION_ONLY",
            "RAW_CAPTURE_ARCHIVED_NOW_CANNOT_BACKFILL_ORIGINAL_HISTORICAL_PUBLICATION",
            "MATCH_PREDICTIONS_BY_EXACT_CBBD_IDS_ONLY_NOT_TEAM_NAMES",
            "NO_OFFICIAL_BETTING_OR_SOURCE_AUTHENTICATION_FROM_THIS_ADAPTER",
        ],
    }
    _private_create(output_path, (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))
    return {"report_path": str(output_path), "rows": len(results),
            "finals": sum(x["status"] == "FINAL_RECEIPT_LOCAL_CAPTURE_UNAUTHENTICATED" for x in results),
            "status": report["status"]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="action", required=True)
    c = commands.add_parser("capture")
    c.add_argument("--season", type=int, required=True)
    c.add_argument("--start-utc", required=True)
    c.add_argument("--end-utc", required=True)
    c.add_argument("--private-dir", required=True)
    f = commands.add_parser("finals")
    f.add_argument("--raw", required=True)
    f.add_argument("--manifest", required=True)
    f.add_argument("--output", required=True)
    args = p.parse_args(argv)
    if args.action == "capture":
        result = capture_games(season=args.season, start_utc=args.start_utc,
                               end_utc=args.end_utc, private_dir=args.private_dir)
    else:
        result = finals_from_capture(args.raw, args.manifest, output_path=args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
