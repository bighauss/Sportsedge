"""One-shot Firecrawl Alexandria NFL/ESPN pregame source capture (research only).

Runs only when explicitly invoked with a separate, operator-issued Firecrawl API
key and an independent archive-encryption key. The ChatGPT plugin OAuth session
is NOT a GitHub Actions secret and is never silently reused.

No model admission, sportsbook claims, or automatic wagers. Original HTTP
response bytes live only in mode-0600 runner scratch, then in an authenticated
encrypted, persistent artifact. Never upload plaintext from the public repo.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from sportsedge.validation.firecrawl_espn_injury_intake import (
    MAX_BYTES, TEAM, EVENT, InjuryEvidenceError, archive, _utc,
)
from sportsedge.validation.seven_sport_pit_freeze import _private_path

URL = "https://api.firecrawl.dev/v2/scrape"
BUNDLE_SCHEMA = "sportsedge-firecrawl-espn-private-source-bundle-v1"
SUMMARY_SCHEMA = "sportsedge-firecrawl-espn-public-status-v1"
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
UTC = timezone.utc


def _hash(raw):
    return "sha256:" + sha256(raw).hexdigest()


def _write_private(path, raw):
    target = _private_path(path, "private_output", output=True)
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)
    return target


def _private_dir(directory):
    # Require an existing owner-private directory outside the repository.
    path = Path(os.path.abspath(directory))
    _private_path(path / "__nonexistent_output__", "private_directory",
                  output=True)
    if path.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_DIRECTORY_PERMISSIONS_REQUIRED")
    return path


def _cipher(archive_key):
    if not isinstance(archive_key, str) or not archive_key:
        raise ValueError("ARCHIVE_ENCRYPTION_KEY_MISSING")
    try:
        from cryptography.fernet import Fernet
        return Fernet(archive_key.encode("ascii"))
    except (ImportError, ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("INVALID_FERNET_ARCHIVE_ENCRYPTION_KEY") from exc


def _request(team, request_id, key):
    if not isinstance(key, str) or len(key) < 15 or len(key) > 1024:
        raise ValueError("FIRECRAWL_API_KEY_MISSING_OR_INVALID")
    payload = json.dumps({
        "alexandria": {
            "provider": "espn-com",
            "capability": "sports-data/injuries",
            "options": {"sport": "football", "league": "nfl", "team": team},
        }
    }, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return Request(
        URL, data=payload, method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-request-id": request_id,
            "User-Agent": "SportsEdge-Private-Prospective-Research/1.0",
        },
    )


def fetch_original(*, team, key, request_id, opener=urlopen):
    """One potentially billed HTTPS request, no automatic retry on uncertainty."""
    req = _request(team, request_id, key)
    try:
        with opener(req, timeout=30) as response:
            status = response.status
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        # Provider error body and Authorization header must never enter CI logs.
        raise InjuryEvidenceError("FIRECRAWL_HTTP_RESPONSE_BLOCKED_" +
                                  str(exc.code)) from None
    except (URLError, TimeoutError, OSError) as exc:
        # A request may have been billed; don't auto-retry a new charge.
        raise InjuryEvidenceError("FIRECRAWL_TRANSPORT_UNCERTAIN_NO_AUTORETRY") from None
    if status != 200:
        raise InjuryEvidenceError("FIRECRAWL_HTTP_RESPONSE_NOT_200")
    if not 0 < len(raw) <= MAX_BYTES:
        raise InjuryEvidenceError("FIRECRAWL_HTTP_ORIGINAL_SIZE_INVALID")
    return raw


def _bundle(raw, receipt, *, fernet):
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "original_http_response_b64": base64.b64encode(raw).decode("ascii"),
        "original_http_response_sha256": _hash(raw),
        "sanitized_intake_receipt": receipt,
    }
    payload = json.dumps(bundle, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    encrypted = fernet.encrypt(gzip.compress(payload, compresslevel=6))
    # Verify source byte preservation and AES+HMAC authenticated ciphertext
    # via Fernet decrypt before the encrypted archive can be published.
    check = json.loads(gzip.decompress(fernet.decrypt(encrypted)))
    if (base64.b64decode(check["original_http_response_b64"], validate=True)
            != raw or check["sanitized_intake_receipt"] != receipt):
        raise InjuryEvidenceError("ENCRYPTED_ARCHIVE_ROUNDTRIP_FAILED")
    return encrypted


def capture(*, private_dir, artifact_dir, team, event_id, event_start_utc,
            api_key, archive_key, run_id, now=None, opener=urlopen):
    """One-shot archive. All credentials/capture destinations checked BEFORE billing.

    The caller supplies event identity but that does not independently verify
    an event schedule or current NFL roster. All gate statuses stay false.
    """
    if type(team) is not str or not TEAM.fullmatch(team):
        raise InjuryEvidenceError("EXPLICIT_NFL_TEAM_ABBREVIATION_REQUIRED")
    if type(event_id) is not str or not EVENT.fullmatch(event_id):
        raise InjuryEvidenceError("EXPLICIT_EVENT_ID_REQUIRED")
    if type(run_id) is not str or not RUN_ID.fullmatch(run_id):
        raise InjuryEvidenceError("INVALID_UNIQUE_RUN_ID")
    now = datetime.now(UTC) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset().total_seconds() != 0:
        raise InjuryEvidenceError("ACTUAL_CLOCK_MUST_BE_UTC")
    event_start = _utc(event_start_utc, "event_start")
    if now >= event_start:
        raise InjuryEvidenceError("EVENT_ALREADY_STARTED_OR_FINISHED")
    if not isinstance(api_key, str) or len(api_key) < 15:
        raise InjuryEvidenceError("FIRECRAWL_API_KEY_NOT_CONFIGURED")
    fernet = _cipher(archive_key)
    scratch = _private_dir(private_dir)
    artifact = _private_dir(artifact_dir)
    if scratch == artifact or scratch in artifact.parents or artifact in scratch.parents:
        raise InjuryEvidenceError("SCRATCH_AND_EXPORT_MUST_BE_DISJOINT")
    paths = [
        scratch / ("firecrawl-original-" + run_id + ".json"),
        scratch / ("firecrawl-receipt-" + run_id + ".json"),
        artifact / ("firecrawl-archive-" + run_id + ".fernet"),
        artifact / ("firecrawl-status-" + run_id + ".json"),
    ]
    for path in paths:
        _private_path(path, "expected_new_output", output=True)
    request_id = run_id + "-" + uuid4().hex
    raw = fetch_original(team=team, key=api_key, request_id=request_id,
                         opener=opener)
    original = _write_private(paths[0], raw)
    try:
        # UTC now checked AFTER retrieval; a replayed source timestamp must
        # never be substituted for the actual local observation clock.
        observed_now = datetime.now(UTC) if opener is urlopen else now
        receipt = archive(original, paths[1], team=team, event_id=event_id,
                          event_start_utc=event_start_utc, now_utc=observed_now)
        cipher = _bundle(raw, receipt, fernet=fernet)
        encrypted = _write_private(paths[2], cipher)
    finally:
        # Only encrypted raw evidence may persist, even on failure. Full
        # GitHub Actions runner scratch is also removed in its cleanup step.
        original.unlink(missing_ok=True)
        paths[1].unlink(missing_ok=True)
    status = {
        "schema": SUMMARY_SCHEMA,
        "state": receipt["state"],
        "run_id": run_id,
        "original_private_capture_encrypted": True,
        "encrypted_bytes_sha256": _hash(cipher),
        "research_only": True,
        "live_publisher_publication_verified": False,
        "official_nfl_game_designation_verified": False,
        "gate_a_closed": False, "gate_b_closed": False,
        "gate_c_closed": False, "gate_d_closed": False, "gate_e_closed": False,
        "official_counted": 0, "approved_stake_u": 0,
    }
    _write_private(paths[3], (json.dumps(status, indent=2, sort_keys=True,
                                        allow_nan=False) + "\n").encode())
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--team", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--event-start-utc", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = capture(
            private_dir=args.private_dir, artifact_dir=args.artifact_dir,
            team=args.team, event_id=args.event_id,
            event_start_utc=args.event_start_utc, run_id=args.run_id,
            api_key=os.environ.get("FIRECRAWL_API_KEY", ""),
            archive_key=os.environ.get("SPORTSEDGE_ARCHIVE_FERNET_KEY", ""),
        )
    except Exception as exc:
        # Do not print user-supplied paths, exception repr of network headers,
        # provider response bodies, player IDs, or secret material.
        code = (str(exc) if isinstance(exc, (InjuryEvidenceError, ValueError))
                else "SOURCE_ARCHIVE_INTERNAL_ERROR")
        print("BLOCK_PROSPECTIVE_FIRECRAWL_CAPTURE:" + code, file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
