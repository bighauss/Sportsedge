"""Append-only, hash-chained CFB PAPER ledger (JSON lines). Never rewrites a line.

Every entry records ``seq``, ``prev_entry_sha256``, ``appended_utc`` and its
own ``entry_sha256`` over the canonical entry. ``verify`` refuses any edited,
reordered, truncated-in-the-middle or re-hashed history. The ledger proves only
local ordering and integrity, not an external clock. PAPER / 0u.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

from models.cfb import cfb_capture_store as store

SCHEMA = "sportsedge-cfb-paper-ledger-v1"
GENESIS = "0" * 64
TYPES = ("CARD_FROZEN", "GAME_GRADED")


class LedgerRefused(ValueError):
    pass


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def verify(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    store.private_dir(p.parent)
    raw = store.read_private(p)
    if raw and not raw.endswith(b"\n"):
        raise LedgerRefused("LEDGER_PARTIAL_LAST_LINE")
    entries, prev = [], GENESIS
    for i, line in enumerate(raw.splitlines(), 1):
        try:
            e = store.strict_json(line)
        except store.CaptureRefused:
            raise LedgerRefused("LEDGER_LINE_INVALID_JSON") from None
        if not isinstance(e, dict) or e.get("schema") != SCHEMA or e.get("seq") != i:
            raise LedgerRefused("LEDGER_SEQUENCE_BROKEN")
        if e.get("prev_entry_sha256") != prev:
            raise LedgerRefused("LEDGER_CHAIN_BROKEN")
        body = {k: v for k, v in e.items() if k != "entry_sha256"}
        if sha256(_canon(body)).hexdigest() != e.get("entry_sha256"):
            raise LedgerRefused("LEDGER_ENTRY_REWRITTEN")
        if e.get("official_counted") != 0 or e.get("approved_stake_u") != 0:
            raise LedgerRefused("LEDGER_NON_PAPER_ENTRY")
        prev = e["entry_sha256"]
        entries.append(e)
    return entries


def append(path, payload: dict, *, now=None) -> dict:
    if payload.get("type") not in TYPES:
        raise LedgerRefused("LEDGER_ENTRY_TYPE_UNKNOWN")
    p = Path(path)
    store.private_dir(p.parent, create=True)
    entries = verify(p)
    prev = entries[-1]["entry_sha256"] if entries else GENESIS
    now = now or store.now_utc()
    if entries and store.utc(entries[-1]["appended_utc"]) > now:
        raise LedgerRefused("LEDGER_CLOCK_MOVED_BACKWARD")
    entry = {**payload, "schema": SCHEMA, "seq": len(entries) + 1, "prev_entry_sha256": prev,
             "appended_utc": store.stamp(now), "official_counted": 0, "approved_stake_u": 0}
    entry["entry_sha256"] = sha256(_canon(entry)).hexdigest()
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(p, flags, 0o600)
    with os.fdopen(fd, "ab") as f:
        f.write(_canon(entry) + b"\n")
        f.flush()
        os.fsync(f.fileno())
    return entry
