"""Seven-sport, single-event point-in-time research freeze recorder.

Never derives odds, projections or EV; never signs or authenticates sources.
A successful local archive is PAPER/0u and cannot certify provider publication.
Real pregame feature snapshots are required, not created by this module.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[2]
SPORTS = frozenset({"NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"})
FAMILIES = frozenset({"ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP",
                      "PERIOD", "SPECIAL", "ALTERNATE", "SGP", "OUTRIGHT",
                      "MATCHUP", "DFS", "OTHER"})
PERIODS = frozenset({"FG", "1H", "2H", "1Q", "2Q", "3Q", "4Q",
                     "F5", "1IN", "ROUND", "TOURNAMENT", "OTHER"})
POLICY = "SPORTSEDGE_STRICT_V21_V22_20261115_R1"
SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUEST_KEYS = frozenset({
    "schema", "sport", "event_id", "market_family", "period",
    "model_version", "training_cutoff_utc", "registered_utc",
    "freeze_utc", "event_start_utc", "evaluation_end_utc",
    "model_code", "model_config", "feature_sources",
})
FEATURE_KEYS = frozenset({
    "source_id", "file", "published_utc", "observed_utc",
    "captured_utc", "data_through_utc",
})
FILE_KEYS = frozenset({"path", "sha256"})
MAX_BYTES = 30_000_000


def _utc(v, field):
    if not isinstance(v, str):
        raise ValueError("UTC_STRING_REQUIRED:" + field)
    try:
        x = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("BAD_TIMESTAMP:" + field) from exc
    if x.tzinfo is None or x.utcoffset() != timedelta(0):
        raise ValueError("UTC_REQUIRED:" + field)
    return x.astimezone(timezone.utc)


def _unique_json(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError("DUPLICATE_JSON_KEY:" + k)
        obj[k] = v
    return obj


def _parse(raw):
    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json,
                     parse_constant=lambda x: (_ for _ in ()).throw(
                         ValueError("NONFINITE_JSON:" + x)))
    if not isinstance(obj, dict) or set(obj) != REQUEST_KEYS:
        raise ValueError("INVALID_FREEZE_REQUEST_FIELDS")
    return obj


def _contained(path, root):
    return path == root or root in path.parents


def _private_path(path, label, *, output=False):
    p = Path(path)
    absolute = Path(os.path.abspath(p))
    resolved = absolute.resolve()
    if _contained(absolute, ROOT) or _contained(resolved, ROOT):
        raise ValueError("PUBLIC_REPOSITORY_PATH:" + label)
    if p.is_symlink():
        raise ValueError("SYMLINK_FORBIDDEN:" + label)
    if not resolved.parent.is_dir() or (resolved.parent.stat().st_mode & 0o077):
        raise ValueError("PRIVATE_PARENT_PERMISSIONS_REQUIRED:" + label)
    if output:
        if absolute.exists() or absolute.is_symlink():
            raise ValueError("OUTPUT_MUST_BE_NEW:" + label)
    else:
        if not resolved.is_file() or not stat.S_ISREG(resolved.stat().st_mode):
            raise ValueError("MISSING_REGULAR_SOURCE:" + label)
        if resolved.stat().st_mode & 0o077:
            raise ValueError("PRIVATE_FILE_PERMISSIONS_REQUIRED:" + label)
        if not 0 < resolved.stat().st_size <= MAX_BYTES:
            raise ValueError("SOURCE_SIZE_INVALID:" + label)
    return resolved


def _raw_file(path, label):
    resolved = _private_path(path, label)
    raw = resolved.read_bytes()
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("SOURCE_SIZE_INVALID:" + label)
    return raw


def _artifact(item, label, *, public_code=False):
    if not isinstance(item, dict) or set(item) != FILE_KEYS:
        raise ValueError("INVALID_FILE_DESCRIPTOR:" + label)
    given = item["sha256"]
    if not isinstance(given, str) or not SHA.fullmatch(given):
        raise ValueError("INVALID_SHA256:" + label)
    if public_code:
        rawpath = item["path"]
        if not isinstance(rawpath, str) or rawpath.startswith("/") or "\\" in rawpath:
            raise ValueError("REPO_RELATIVE_CODE_PATH_REQUIRED")
        filepath = (ROOT / rawpath).resolve()
        if not _contained(filepath, ROOT) or filepath.is_symlink() or (
                not filepath.is_file() or filepath.suffix != ".py"):
            raise ValueError("INVALID_MODEL_CODE_PATH")
        raw = filepath.read_bytes()
        if not 0 < len(raw) <= MAX_BYTES:
            raise ValueError("MODEL_CODE_SIZE_INVALID")
    else:
        raw = _raw_file(item["path"], label)
    digest = "sha256:" + sha256(raw).hexdigest()
    if digest != given:
        raise ValueError("ARTIFACT_HASH_MISMATCH:" + label)
    # Do not publish private file paths.
    return {"sha256": digest, "size_bytes": len(raw)}


def analyze(request, *, actual_now=None):
    if not isinstance(request, dict) or set(request) != REQUEST_KEYS:
        raise ValueError("INVALID_FREEZE_REQUEST_FIELDS")
    if request["schema"] != "sportsedge-seven-sport-pit-freeze-request-v1":
        raise ValueError("UNKNOWN_FREEZE_SCHEMA")
    if request["sport"] not in SPORTS:
        raise ValueError("UNKNOWN_SPORT")
    if request["market_family"] not in FAMILIES or request["period"] not in PERIODS:
        raise ValueError("UNKNOWN_MARKET_FAMILY_OR_PERIOD")
    for f in ("event_id", "model_version"):
        v = request[f]
        if not isinstance(v, str) or not v.strip() or len(v) > 160:
            raise ValueError("INVALID_ID:" + f)
    registered = _utc(request["registered_utc"], "registered")
    training = _utc(request["training_cutoff_utc"], "training")
    freeze = _utc(request["freeze_utc"], "freeze")
    tip = _utc(request["event_start_utc"], "event_start")
    evaluation_end = _utc(request["evaluation_end_utc"], "evaluation_end")
    now = datetime.now(timezone.utc) if actual_now is None else actual_now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("ACTUAL_NOW_MUST_BE_UTC")
    if not training <= registered <= freeze < tip <= evaluation_end:
        raise ValueError("TRAIN_FREEZE_EVENT_EVALUATION_CHRONOLOGY")
    # Local archive must be genuinely prospective. No arbitrary historical
    # timestamp relabeling or snapshots created after kickoff.
    if not freeze <= now <= freeze + timedelta(minutes=5) or not now < tip:
        raise ValueError("FREEZE_NOT_PROSPECTIVE_WITH_CURRENT_CLOCK")
    code = _artifact(request["model_code"], "model_code", public_code=True)
    config = _artifact(request["model_config"], "model_config")
    features = request["feature_sources"]
    if not isinstance(features, list) or not (1 <= len(features) <= 1000):
        raise ValueError("NONEMPTY_BOUNDED_FEATURE_SOURCES_REQUIRED")
    seen = set()
    verified = []
    for index, row in enumerate(features):
        if not isinstance(row, dict) or set(row) != FEATURE_KEYS:
            raise ValueError("INVALID_FEATURE_FIELDS")
        name = row["source_id"]
        if not isinstance(name, str) or not name.strip() or len(name) > 160 or name in seen:
            raise ValueError("DUPLICATE_OR_INVALID_FEATURE_SOURCE_ID")
        seen.add(name)
        through = _utc(row["data_through_utc"], "data_through")
        published = _utc(row["published_utc"], "published")
        observed = _utc(row["observed_utc"], "observed")
        captured = _utc(row["captured_utc"], "captured")
        if not through <= published <= observed <= captured <= freeze:
            raise ValueError("FEATURE_PUBLICATION_OR_CAPTURE_AFTER_FREEZE")
        verified.append({
            "source_id": name,
            "raw_file": _artifact(row["file"], "feature_" + str(index)),
            "data_through_utc": through.isoformat(),
            "published_utc_claimed": published.isoformat(),
            "observed_utc_claimed": observed.isoformat(),
            "captured_utc_claimed": captured.isoformat(),
        })
    return {
        "schema": "sportsedge-seven-sport-pit-freeze-record-v1",
        "state": "PAPER_0U_LOCAL_CHRONOLOGY_ONLY",
        "sport": request["sport"], "event_id": request["event_id"],
        "market_family": request["market_family"], "period": request["period"],
        "model_version": request["model_version"],
        "policy_version": POLICY,
        "registered_utc_claimed": registered.isoformat(),
        "training_cutoff_utc_claimed": training.isoformat(),
        "freeze_utc_claimed": freeze.isoformat(),
        "event_start_utc_claimed": tip.isoformat(),
        "evaluation_end_utc_claimed": evaluation_end.isoformat(),
        "local_archive_created_utc": now.isoformat(),
        "model_code": code,
        "model_config": config,
        "feature_sources": verified,
        "feature_count": len(verified),
        "source_externally_authenticated": False,
        "coverage_is_verified": False,
        "calibration_verified": False,
        "has_authentic_book_quotes": False,
        "clv_verified": False,
        "release_certified": False,
        "official_counted": 0,
        "approved_stake_u": 0,
    }


def freeze_file(request_path, destination, *, actual_now=None):
    src = _private_path(request_path, "request")
    dst = _private_path(destination, "output", output=True)
    if src == dst:
        raise ValueError("SOURCE_EQUALS_OUTPUT")
    raw = _raw_file(src, "request")
    request = _parse(raw)
    result = analyze(request, actual_now=actual_now)
    result["original_request_sha256"] = "sha256:" + sha256(raw).hexdigest()
    payload = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(dst, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        try:
            dst.unlink()
        except OSError:
            pass
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description="Record actual prospective seven-sport PIT research freeze; 0u always")
    parser.add_argument("request")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = freeze_file(args.request, args.out)
    print(json.dumps({
        "status": result["state"], "sport": result["sport"],
        "feature_count": result["feature_count"],
        "official_counted": 0, "approved_stake_u": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
