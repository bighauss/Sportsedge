#!/usr/bin/env python3
"""Cross-run GitHub Artifact claim for the optional NFL odds pilot.

Runs only inside an explicitly dispatched GitHub Action after secrets and
encryption checks, BEFORE any billable Odds API request. A public metadata
artifact reserves a Central calendar day across action reruns. Cannot provide
an absolute quota guarantee if a privileged user deletes the artifact or the
provider bills more than the expected quote; always fail closed when unable
to inspect durable artifact state.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
CLAIM_FILENAME = "nfl-daily-claim.json"
HOLD_ARTIFACT_NAME = "nfl-daily-odds-quota-hold"
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
NAME_RE = re.compile(r"nfl-daily-odds-attempt-\d{4}-\d{2}-\d{2}")


class Blocked(ValueError):
    pass


def _utc(now):
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None or now.utcoffset() is None:
        raise Blocked("PILOT_CLOCK_NEEDS_OFFSET")
    return now.astimezone(timezone.utc)


def _repo_and_run(repository, run_id, token):
    if not isinstance(repository, str) or not REPO_RE.fullmatch(repository):
        raise Blocked("REPO_UNVERIFIED")
    owner, name = repository.split("/")
    if owner in (".", "..") or name in (".", ".."):
        raise Blocked("REPO_UNVERIFIED")
    if not str(run_id).isascii() or not str(run_id).isdecimal() or int(run_id) < 1:
        raise Blocked("RUN_ID_UNVERIFIED")
    if not isinstance(token, str) or not token.strip():
        raise Blocked("ACTIONS_READ_TOKEN_MISSING")


def api_artifacts(repository, token, name):
    """Read repository Actions artifact metadata without exposing the token."""
    query = urlencode({"name": name, "per_page": 100})
    url = "https://api.github.com/repos/" + repository + "/actions/artifacts?" + query
    req = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SportsEdge-Quota-Claim/1.0",
    })
    try:
        with urlopen(req, timeout=10) as response:
            if response.status != 200:
                raise Blocked("ACTIONS_ARTIFACT_API_NOT_200")
            raw = response.read(500_001)
            if len(raw) > 500_000:
                raise Blocked("ACTIONS_ARTIFACT_API_OVERSIZED")
        out = json.loads(raw)
    except (OSError, ValueError, TypeError) as exc:
        raise Blocked("ACTIONS_ARTIFACT_LOOKUP_FAILED") from None
    return validate_artifacts(out, name)


def validate_artifacts(response, name):
    if not isinstance(response, dict) or type(response.get("total_count")) is not int:
        raise Blocked("ARTIFACT_RESPONSE_UNRELIABLE")
    count = response["total_count"]
    rows = response.get("artifacts")
    if count < 0 or not isinstance(rows, list):
        raise Blocked("ARTIFACT_RESPONSE_UNRELIABLE")
    if count == 0 and rows:
        raise Blocked("ARTIFACT_RESPONSE_INCONSISTENT")
    if count and not rows:
        raise Blocked("ARTIFACT_RESPONSE_INCONSISTENT")
    if any(not isinstance(r, dict) or r.get("name") != name for r in rows):
        raise Blocked("ARTIFACT_NAME_MISMATCH")
    return response


def reserve(root, *, repository, run_id, token, now=None, lookup=api_artifacts):
    _repo_and_run(repository, run_id, token)
    now = _utc(now)
    day = now.astimezone(CT).date().isoformat()
    claim = "nfl-daily-odds-attempt-" + day
    # Permission/metadata failures stop before we create an attempt or call a
    # paid source. Quota holds from prior attempts survive separate runners.
    holds = lookup(repository, token, HOLD_ARTIFACT_NAME)
    previous = lookup(repository, token, claim)
    validate_artifacts(holds, HOLD_ARTIFACT_NAME)
    validate_artifacts(previous, claim)
    if holds["total_count"]:
        raise Blocked("PILOT_QUOTA_HOLD_REVIEW_REQUIRED")
    if previous["total_count"]:
        raise Blocked("PILOT_ALREADY_ATTEMPTED_CENTRAL_DATE")
    if root is None:
        raise Blocked("RUNNER_TEMP_MISSING")
    root = Path(root)
    if not root.is_dir():
        raise Blocked("RUNNER_TEMP_MISSING")
    payload = {"schema": "nfl-daily-odds-attempt-v1", "name": claim,
               "date_ct": day, "created_utc": now.isoformat(),
               "repository": repository, "run_id": str(run_id),
               "message": "Claimed BEFORE optional billable request; deleting this record voids one-day guard"}
    path = root / CLAIM_FILENAME
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True)
            f.write("\n")
    except OSError as exc:
        raise Blocked("ATTEMPT_CLAIM_CREATE_FAILED") from None
    return payload


def verify(root, *, repository, run_id, token, now=None, lookup=api_artifacts):
    _repo_and_run(repository, run_id, token)
    now = _utc(now)
    path = Path(root) / CLAIM_FILENAME
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise Blocked("ATTEMPT_CLAIM_FILE_UNAVAILABLE") from None
    if not isinstance(record, dict):
        raise Blocked("ATTEMPT_CLAIM_INVALID")
    claim = record.get("name")
    if (not isinstance(claim, str) or not NAME_RE.fullmatch(claim)
            or record.get("repository") != repository
            or record.get("run_id") != str(run_id)
            or record.get("date_ct") != now.astimezone(CT).date().isoformat()
            or claim != "nfl-daily-odds-attempt-" + record.get("date_ct", "")):
        raise Blocked("ATTEMPT_CLAIM_IDENTITY_OR_DAY_CHANGED")
    response = lookup(repository, token, claim)
    validate_artifacts(response, claim)
    if response["total_count"] != 1:
        raise Blocked("ATTEMPT_CLAIM_NOT_UNIQUE_OR_NOT_VISIBLE")
    item = response["artifacts"][0]
    wf = item.get("workflow_run")
    if (item.get("expired") is not False
            or not isinstance(wf, dict)
            or str(wf.get("id")) != str(run_id)):
        raise Blocked("ATTEMPT_CLAIM_WRONG_RUN_OR_EXPIRED")
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("reserve", "verify"))
    a = p.parse_args(argv)
    env = os.environ
    opts = dict(repository=env.get("GITHUB_REPOSITORY"),
                run_id=env.get("GITHUB_RUN_ID"),
                token=env.get("GH_ACTIONS_READ_TOKEN"))
    try:
        if a.action == "reserve":
            r = reserve(env.get("RUNNER_TEMP"), **opts)
            out = env.get("GITHUB_OUTPUT")
            if not out:
                raise Blocked("GITHUB_OUTPUT_MISSING")
            with open(out, "a", encoding="utf-8") as f:
                f.write("artifact_name=" + r["name"] + "\n")
                f.write("date_ct=" + r["date_ct"] + "\n")
        else:
            verify(env.get("RUNNER_TEMP"), **opts)
    except (Blocked, OSError) as exc:
        print("::error::" + (str(exc) if isinstance(exc, Blocked) else "PILOT_CLAIM_IO_FAILED"),
              file=sys.stderr)
        return 2
    print("PILOT_DAILY_ARTIFACT_" + ("RESERVED" if a.action == "reserve" else "VERIFIED"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
