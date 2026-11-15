"""Point-in-time *file-level* lineage guard for source-backed model projections.

It verifies original on-disk feature bytes and chronology at the time of a
forecast. A file checksum / source self-claim is NOT an independent provider
signature or proof rows were originally published before a game. The guard is
intentionally a stricter PAPER-only prerequisite, never a promotion path.

The manifest is create-only upstream and should be externally archived with
trusted receipt information (separate from this source-code repository).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import re

from .source_ingestion import SOURCES

HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
BAD_ROLES = {"odds", "lines", "lines_extra", "props", "prop_odds",
             "bestbook", "dk", "prices", "bets"}
BAD_FILE_NAMES = {"odds.csv", "prop_odds.csv", "bets.csv", "prices.csv",
                  "odds.json", "lines.csv", "bookmaker.csv"}
SOURCE_FILE_KEYS = frozenset({
    "role", "path", "raw_sha256", "source_id", "observed_at_utc",
    "captured_at_utc", "data_through_utc",
})
MANIFEST_KEYS = frozenset({
    "version", "sport", "event_id", "forecast_asof_utc",
    "model_trained_until_utc", "files",
})
MANIFEST_VERSION = "SPORTSEDGE_PIT_FILE_MANIFEST_V1"


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, str):
        if not value or len(value) > 70:
            raise ValueError("PIT_TIMESTAMP_MISSING")
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("PIT_TIMESTAMP_INVALID") from exc
    if (not isinstance(value, datetime) or value.tzinfo is None or
            value.utcoffset() is None or value.utcoffset().total_seconds() != 0):
        raise ValueError("PIT_TIMESTAMP_NOT_UTC")
    return value.astimezone(timezone.utc)


def _hash(value: Any) -> str:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("PIT_ORIGINAL_HASH_INVALID")
    return value


def _no_secret_fields(data: Any, allowed: frozenset[str], label: str) -> dict:
    if not isinstance(data, dict) or set(data) != set(allowed):
        raise ValueError("PIT_SCHEMA_EXTRA_OR_MISSING_FIELDS:" + label)
    return data


def _inputs_to_check(feature_paths: dict[str,str]) -> dict[str, Path]:
    if not isinstance(feature_paths, dict) or not feature_paths:
        raise ValueError("MODEL_SOURCE_FEATURES_REQUIRED")
    result: dict[str, Path] = {}
    for role, value in feature_paths.items():
        if not isinstance(role, str) or not NAME.fullmatch(role):
            raise ValueError("INVALID_MODEL_FEATURE_ROLE")
        if role.casefold() in BAD_ROLES:
            # Old card/odds inputs are not allowed in model provenance.
            # They can be supplied separately to old card runners, but NOT
            # to this source-backed projection-only CLI pathway.
            raise ValueError("BOOKMAKER_FIELD_IN_MODEL_FEATURE_PATHS:" + role)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("MODEL_FEATURE_PATH_MISSING:" + role)
        path = Path(value)
        if path.is_symlink():
            raise ValueError("PIT_SYMLINK_FEATURE_REFUSED")
        if path.is_dir():
            if role not in ("folder", "data_dir"):
                raise ValueError("PIT_DIRECTORY_ROLE_NOT_SUPPORTED:" + role)
            children = sorted(path.glob("*.csv"))
            # The recovered MLB model directory also contains odds files.
            # They are never treated as independent feature dependencies.
            for file in children:
                if file.name.casefold() in BAD_FILE_NAMES:
                    continue
                if file.is_symlink():
                    raise ValueError("PIT_SYMLINK_FEATURE_REFUSED")
                result[role + "/" + file.name] = file.resolve()
        else:
            if path.name.casefold() in BAD_FILE_NAMES:
                raise ValueError("BOOKMAKER_FILE_USED_AS_MODEL_FEATURE:" + role)
            result[role] = path.resolve()
    if not result or not all(p.is_file() for p in result.values()):
        raise ValueError("PIT_FEATURE_FILE_NOT_FOUND")
    return result


@dataclass(frozen=True)
class PITFileAudit:
    status: str
    verified_roles: tuple[str,...]
    source_ids: tuple[str,...]
    file_count: int
    data_sha256: str
    latest_captured_at_utc: str
    forecast_asof_utc: str
    model_trained_until_utc: str
    independently_authenticated: bool = False
    official_counted: int = 0
    approved_stake_u: int = 0


def verify_model_feature_manifest(
    manifest: dict,
    feature_paths: dict[str,str],
    *,
    sport: str,
    event_id: str,
    forecast_asof_utc: datetime,
    independent_source_verified: bool = False,
) -> PITFileAudit:
    """Check exact role/path/hash/time matching; never infer authenticated input."""
    if independent_source_verified:
        raise ValueError("CALLER_CANNOT_ATTEST_INDEPENDENT_PIT_SOURCE")
    m = _no_secret_fields(manifest, MANIFEST_KEYS, "manifest")
    if m["version"] != MANIFEST_VERSION:
        raise ValueError("PIT_UNKNOWN_MANIFEST_VERSION")
    if m["sport"] != sport or m["event_id"] != event_id:
        raise ValueError("PIT_EVENT_OR_SPORT_MISMATCH")
    asof = _utc(m["forecast_asof_utc"])
    if asof != _utc(forecast_asof_utc):
        raise ValueError("PIT_FORECAST_FREEZE_MISMATCH")
    train_end = _utc(m["model_trained_until_utc"])
    if train_end >= asof:
        raise ValueError("PIT_MODEL_TRAINED_ON_EVALUATION")
    paths = _inputs_to_check(feature_paths)
    rows = m["files"]
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise ValueError("PIT_SOURCE_FILE_ROWS_REQUIRED")
    by_role = {}
    for item in rows:
        row = _no_secret_fields(item, SOURCE_FILE_KEYS, "file")
        role = row["role"]
        if not isinstance(role, str) or role in by_role:
            raise ValueError("PIT_FEATURE_ROLE_REUSED")
        by_role[role] = row
    if set(by_role) != set(paths):
        raise ValueError("PIT_FEATURE_ROLE_COVERAGE_MISMATCH")
    latest = None
    ids = set()
    unique_paths = set()
    h = sha256()
    for role, path in sorted(paths.items()):
        row = by_role[role]
        if path != Path(row["path"]).resolve() or path in unique_paths:
            raise ValueError("PIT_FEATURE_PATH_MISMATCH_OR_DUPLICATE")
        unique_paths.add(path)
        sid = row["source_id"]
        if not isinstance(sid, str) or not NAME.fullmatch(sid):
            raise ValueError("PIT_SOURCE_ID_REQUIRED")
        if sid not in SOURCES:
            raise ValueError("PIT_SOURCE_NOT_REGISTERED")
        if SOURCES[sid].sport != sport:
            raise ValueError("PIT_SOURCE_DIFFERENT_SPORT")
        ids.add(sid)
        observed = _utc(row["observed_at_utc"])
        captured = _utc(row["captured_at_utc"])
        through = _utc(row["data_through_utc"])
        if not (through <= observed <= captured <= asof):
            raise ValueError("PIT_FEATURE_LOOKAHEAD_OR_BAD_CAPTURE_ORDER:" + role)
        raw = path.read_bytes()
        if not raw:
            raise ValueError("PIT_EMPTY_FEATURE_BYTES:" + role)
        checksum = "sha256:" + sha256(raw).hexdigest()
        if checksum != _hash(row["raw_sha256"]):
            raise ValueError("PIT_FEATURE_RAW_HASH_MISMATCH:" + role)
        h.update(role.encode() + b"\x00" + bytes.fromhex(checksum[7:]))
        latest = max(latest, captured) if latest else captured
    return PITFileAudit(
        status="PIT_FILE_BYTES_AND_CLAIMED_TIMES_CHECKED_RESEARCH_ONLY",
        verified_roles=tuple(sorted(paths)), source_ids=tuple(sorted(ids)),
        file_count=len(paths), data_sha256="sha256:" + h.hexdigest(),
        latest_captured_at_utc=latest.isoformat(),
        forecast_asof_utc=asof.isoformat(),
        model_trained_until_utc=train_end.isoformat(),
    )
