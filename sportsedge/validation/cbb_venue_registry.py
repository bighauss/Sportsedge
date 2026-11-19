"""CBB research projection venue gate: fail closed before any home-court adjustment.

CSV source metadata is declared, not independently authenticated provider proof.
Historical cards and frozen v5 are never modified here.
"""
from __future__ import annotations
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_COLUMNS = ("game_id", "neutral", "source", "source_sha256",
                     "published_utc", "captured_utc", "tipoff_utc")
_SOURCES = frozenset(("ESPN", "CFBD"))


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError("CBB_VENUE_UTC_Z_TIME_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("CBB_VENUE_UTC_INVALID") from exc


def _rows(source: str, *, kind: str) -> list[dict]:
    path = Path(source)
    if not path.is_file():
        raise ValueError("CBB_VENUE_FILE_MISSING:" + kind)
    if path.stat().st_size > 5_000_000:
        raise ValueError("CBB_VENUE_FILE_OVERSIZE:" + kind)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, strict=True)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or any(
                not isinstance(v,str) or not v or v != v.strip() for v in fields):
            raise ValueError("CBB_VENUE_HEADER_INVALID:" + kind)
        if kind == "registry" and tuple(fields) != _REGISTRY_COLUMNS:
            raise ValueError("CBB_VENUE_REGISTRY_SCHEMA_INVALID")
        if kind == "games" and not {"game_id", "neutral"}.issubset(fields):
            raise ValueError("CBB_VENUE_GAMES_SCHEMA_INVALID")
        result = []
        try:
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("CBB_VENUE_CSV_ROW_INVALID:" + kind)
                result.append(row)
        except csv.Error as exc:
            raise ValueError("CBB_VENUE_CSV_INVALID:" + kind) from exc
    return result


def verify_cbb_venue(games_path: str, registry_path: str, game_id: str,
                     asof_utc: datetime) -> bool:
    """Verify exact game/registry identity and pregame source clocks; return neutral."""
    if not isinstance(game_id, str) or not game_id.strip():
        raise ValueError("CBB_VENUE_EVENT_ID_REQUIRED")
    if not isinstance(asof_utc, datetime) or asof_utc.tzinfo is None or (
            asof_utc.utcoffset() != timedelta(0)):
        raise ValueError("CBB_VENUE_ASOF_MUST_BE_UTC")
    games = [g for g in _rows(games_path, kind="games") if g["game_id"] == game_id]
    registry = [r for r in _rows(registry_path, kind="registry")
                if r["game_id"] == game_id]
    if len(games) != 1:
        raise ValueError("CBB_VENUE_GAME_MISSING_OR_DUPLICATE")
    if len(registry) != 1:
        raise ValueError("CBB_VENUE_REGISTRY_MISSING_OR_DUPLICATE")
    g, r = games[0], registry[0]
    if g["neutral"] not in ("0", "1") or r["neutral"] not in ("0", "1"):
        raise ValueError("CBB_VENUE_NEUTRAL_FLAG_MUST_BE_EXPLICIT")
    if g["neutral"] != r["neutral"]:
        raise ValueError("CBB_VENUE_NEUTRAL_FLAG_SOURCE_MISMATCH")
    if r["source"] not in _SOURCES:
        raise ValueError("CBB_VENUE_SOURCE_UNSUPPORTED")
    if not _SHA256.fullmatch(r["source_sha256"]):
        raise ValueError("CBB_VENUE_DECLARED_SOURCE_SHA_INVALID")
    pub = _utc(r["published_utc"])
    cap = _utc(r["captured_utc"])
    tip = _utc(r["tipoff_utc"])
    if not (pub <= cap <= asof_utc < tip):
        raise ValueError("CBB_VENUE_NOT_FROZEN_BEFORE_TIP")
    return r["neutral"] == "1"
