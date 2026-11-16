"""Restricted, create-only DataGolf capture pair. Does not authenticate vendor."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
ENDPOINTS = frozenset({
    "players", "schedule", "field", "rankings", "skill", "decompositions",
    "pregame", "live_stats", "live_predictions", "outrights", "matchups",
    "historical_event_list", "historical_rounds", "pregame_archive",
})
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def private_directory(root):
    lexical = Path(os.path.abspath(os.path.expanduser(str(root))))
    resolved = lexical.resolve()
    for candidate in (lexical, resolved):
        if candidate == REPO_ROOT or REPO_ROOT in candidate.parents:
            raise ValueError("PRIVATE_PGA_CAPTURE_OUTSIDE_PUBLIC_REPO_REQUIRED")
    if lexical.is_symlink():
        raise ValueError("SYMLINK_ROOT_NOT_ALLOWED")
    resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not resolved.is_dir() or resolved.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_DIRECTORY_PERMISSIONS_TOO_BROAD")
    return resolved


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_CAPTURE_TIME")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("INVALID_CAPTURE_TIME") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("INVALID_CAPTURE_TIME")
    return parsed


def save_capture(receipt, root):
    """Write a raw-response+manifest pair; never overwrite or publish one alone.

    The transport and provider clocks are NOT independently authenticated.
    A caller-provided SHA only verifies byte consistency after local capture.
    """
    if not isinstance(receipt, dict):
        raise ValueError("INVALID_RECEIPT")
    raw = receipt.get("raw_bytes")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 10_000_000:
        raise ValueError("RAW_BYTES_REQUIRED")
    digest = hashlib.sha256(raw).hexdigest()
    if not isinstance(receipt.get("source_sha256"), str) or not DIGEST.fullmatch(receipt["source_sha256"]) or digest != receipt["source_sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    ts = receipt.get("captured_utc")
    _timestamp(ts)
    endpoint = receipt.get("endpoint")
    if endpoint not in ENDPOINTS:
        raise ValueError("INVALID_ENDPOINT")
    root = private_directory(root)
    name = ts.replace(":", "").replace("-", "") + "_" + endpoint + "_" + digest[:16]
    metadata = {"endpoint": endpoint, "captured_utc": ts,
                "source_sha256": digest, "status": "RAW_PROVIDER_CAPTURE_UNVERIFIED",
                "raw_filename": name + ".json"}
    raw_path = root / (name + ".json")
    meta_path = root / (name + ".receipt.json")
    payloads = ((raw_path, raw), (meta_path, json.dumps(metadata, sort_keys=True).encode("utf-8")))
    present = [path.exists() or path.is_symlink() for path, _ in payloads]
    if any(present):
        if not all(present):
            raise ValueError("PARTIAL_CAPTURE_PAIR_REFUSED")
        for path, content in payloads:
            if path.is_symlink() or path.read_bytes() != content:
                raise ValueError("CAPTURE_COLLISION")
        return {"raw_path": str(raw_path), "receipt_path": str(meta_path),
                "source_sha256": digest, "status": "CAPTURE_STORED_UNVERIFIED"}

    temp_files = []
    created = []
    try:
        for path, content in payloads:
            fd, tmp = tempfile.mkstemp(prefix=".capture-", dir=root)
            temp_files.append(tmp)
            with os.fdopen(fd, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        # Exclusive hard links cannot replace an existing destination like
        # os.replace. On conflict, preserve all prior evidence.
        for (path, _), tmp in zip(payloads, temp_files):
            os.link(tmp, path)
            created.append(path)
        dirfd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    finally:
        for tmp in temp_files:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return {"raw_path": str(raw_path), "receipt_path": str(meta_path),
            "source_sha256": digest, "status": "CAPTURE_STORED_UNVERIFIED"}
