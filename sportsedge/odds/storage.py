"""Local tamper-EVIDENT research decision log, not immutable or externally signed.

A checksum chain detects edits when anchored by a separately retained trusted
head digest. It cannot prove source authenticity, past existence, or WORM storage.
Raw provider payloads, credentials, player PII and tokens must not be written here.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path

ALLOWED = frozenset({
    "decision_id", "asof_utc", "primary_receipt_id", "secondary_receipt_id",
    "source_payload_hashes", "market_key", "state", "reason_codes",
    "pit_status", "v21_status", "approved_stake_u", "official_counted",
})
ZERO = "0" * 64
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def private_log_directory(value):
    """Refuse checkout-relative and symlinked checkout paths before mkdir."""
    lexical = Path(os.path.abspath(value))
    resolved = lexical.resolve()
    if (lexical == REPOSITORY_ROOT or REPOSITORY_ROOT in lexical.parents
            or resolved == REPOSITORY_ROOT or REPOSITORY_ROOT in resolved.parents):
        raise ValueError("RESEARCH_LOG_MUST_BE_PRIVATE_OUTSIDE_PUBLIC_REPO")
    return resolved


def _unique_json_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("BROKEN_CHAIN_DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _reject_nonfinite(token):
    raise ValueError("BROKEN_CHAIN_NONFINITE_NUMBER")


def canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def record_hash(body: dict) -> str:
    return hashlib.sha256(canonical(body)).hexdigest()


class EvidenceChain:
    def __init__(self, directory: str | Path):
        root = private_log_directory(directory)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "research_decisions.jsonl"
        if self.path.is_symlink():
            raise ValueError("REFUSE_SYMLINK_EVIDENCE_LOG")

    @staticmethod
    def _verify(raw: bytes) -> tuple[int, str, list[dict]]:
        prev = ZERO
        rows: list[dict] = []
        if not raw:
            return 0, prev, rows
        for idx, line in enumerate(raw.splitlines(), 1):
            try:
                row = json.loads(line.decode("utf-8"),
                                 object_pairs_hook=_unique_json_pairs,
                                 parse_constant=_reject_nonfinite)
            except ValueError as exc:
                if str(exc) in ("BROKEN_CHAIN_DUPLICATE_JSON_KEY",
                                "BROKEN_CHAIN_NONFINITE_NUMBER"):
                    raise
                raise ValueError("BROKEN_CHAIN_JSON") from exc
            except UnicodeError as exc:
                raise ValueError("BROKEN_CHAIN_JSON") from exc
            if (not isinstance(row, dict)
                or set(row) != {"seq", "previous_sha256", "payload", "record_sha256"}):
                raise ValueError("BROKEN_CHAIN_SHAPE")
            if row["seq"] != idx or row["previous_sha256"] != prev:
                raise ValueError("BROKEN_CHAIN_ORDER")
            if not isinstance(row["payload"], dict) or not set(row["payload"]).issubset(ALLOWED):
                raise ValueError("BROKEN_CHAIN_PAYLOAD")
            if any(name not in row["payload"] for name in
                   ("decision_id", "asof_utc", "approved_stake_u", "official_counted")):
                raise ValueError("BROKEN_CHAIN_REQUIRED_AUDIT_FIELDS")
            if row["payload"].get("approved_stake_u") != 0 or row["payload"].get("official_counted") != 0:
                raise ValueError("BET_PROMOTION_NOT_ALLOWED_IN_RESEARCH_LOG")
            head = record_hash({k: row[k] for k in ("seq", "previous_sha256", "payload")})
            if head != row["record_sha256"]:
                raise ValueError("BROKEN_CHAIN_DIGEST")
            prev = head
            rows.append(row)
        if not raw.endswith(b"\n"):
            raise ValueError("BROKEN_CHAIN_PARTIAL_WRITE")
        return len(rows), prev, rows

    def verify(self) -> tuple[int, str]:
        if self.path.is_symlink():
            raise ValueError("REFUSE_SYMLINK_EVIDENCE_LOG")
        if not self.path.exists():
            return 0, ZERO
        if stat.S_IMODE(self.path.stat().st_mode) & 0o077:
            raise ValueError("RESEARCH_LOG_FILE_PERMISSIONS_TOO_OPEN")
        n, head, _ = self._verify(self.path.read_bytes())
        return n, head

    def append(self, payload: dict) -> str:
        if not isinstance(payload, dict) or not set(payload).issubset(ALLOWED):
            raise ValueError("RESEARCH_EVIDENCE_FIELDS_NOT_ALLOWED")
        if payload.get("approved_stake_u") != 0 or payload.get("official_counted") != 0:
            raise ValueError("BET_PROMOTION_FORBIDDEN")
        if not payload.get("decision_id") or not payload.get("asof_utc"):
            raise ValueError("RESEARCH_AUDIT_ID_OR_TIME_MISSING")
        if self.path.is_symlink():
            raise ValueError("REFUSE_SYMLINK_EVIDENCE_LOG")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            if stat.S_IMODE(os.fstat(fd).st_mode) & 0o077:
                raise ValueError("RESEARCH_LOG_FILE_PERMISSIONS_TOO_OPEN")
            fcntl.flock(fd, fcntl.LOCK_EX)
            with os.fdopen(fd, "r+b", closefd=False) as f:
                raw = f.read()
                count, prev, rows = self._verify(raw)
                if any(row["payload"]["decision_id"] == payload["decision_id"] for row in rows):
                    raise ValueError("DECISION_ID_REUSED")
                body = {"seq": count + 1, "previous_sha256": prev, "payload": payload}
                head = record_hash(body)
                f.seek(0, os.SEEK_END)
                f.write(canonical({**body, "record_sha256": head}) + b"\n")
                f.flush()
                os.fsync(f.fileno())
            return head
        finally:
            os.close(fd)
