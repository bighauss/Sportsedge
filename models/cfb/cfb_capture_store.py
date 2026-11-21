"""Private, append-only CFB pregame capture directory. Research only, PAPER / 0u.

Layout of one capture directory (owner-only, outside the public checkout)::

    capture.json                                  season / week / capture mode
    <source>__<YYYYmmddTHHMMSSffffffZ>.bin        original bytes, never rewritten
    <source>__<YYYYmmddTHHMMSSffffffZ>.receipt.json

Each receipt carries provider, sha256, byte count and ``published_utc`` (or
null when the provider gives no publication clock), ``observed_utc`` and
``captured_utc``. Several captures of a source may coexist; the assembler
selects the latest one captured at or before the freeze, never a later one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re

CAPTURE_SCHEMA = "sportsedge-cfb-pregame-capture-v1"
RECEIPT_SCHEMA = "sportsedge-cfb-source-receipt-v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
CFBD_SOURCES = ("cfbd_games", "cfbd_advanced", "cfbd_talent", "cfbd_returning")
OPERATOR_SOURCES = ("operator_qb", "operator_injuries")
SOURCES = CFBD_SOURCES + OPERATOR_SOURCES
MODES = ("PROSPECTIVE_PREGAME",)
STEM = re.compile(r"^(?P<src>[a-z_]+)__(?P<stamp>\d{8}T\d{12}Z)$")
MAX_BYTES = 8_000_000


class CaptureRefused(ValueError):
    pass


def utc(value, label="TIME"):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CaptureRefused("UTC_Z_REQUIRED:" + label)
    try:
        t = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise CaptureRefused("BAD_UTC:" + label) from None
    return t.astimezone(timezone.utc)


def stamp(t: datetime) -> str:
    if t.tzinfo is None or t.utcoffset().total_seconds() != 0:
        raise CaptureRefused("CLOCK_MUST_BE_UTC")
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if t.microsecond else "%Y-%m-%dT%H:%M:%SZ"
    return t.astimezone(timezone.utc).strftime(fmt)


def now_utc():
    return datetime.now(timezone.utc)


def strict_json(raw: bytes):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise CaptureRefused("DUPLICATE_JSON_KEY")
            out[k] = v
        return out

    def bad(_):
        raise CaptureRefused("NONFINITE_JSON_NUMBER")

    def flt(text):
        v = float(text)
        if v != v or v in (float("inf"), float("-inf")):
            raise CaptureRefused("NONFINITE_JSON_NUMBER")
        return v
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad, parse_float=flt)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise CaptureRefused("INVALID_JSON") from None


def private_dir(path, *, create=False) -> Path:
    p = Path(os.path.abspath(os.fspath(path)))
    for cand in (p, p.resolve()):
        if cand == REPO_ROOT or REPO_ROOT in cand.parents:
            raise CaptureRefused("PRIVATE_DATA_MUST_BE_OUTSIDE_PUBLIC_REPO")
    if create:
        p.mkdir(mode=0o700, parents=True, exist_ok=True)
    if p.is_symlink() or not p.is_dir():
        raise CaptureRefused("PRIVATE_DIR_MISSING_OR_SYMLINK")
    if p.stat().st_mode & 0o077:
        raise CaptureRefused("PRIVATE_DIR_MUST_BE_0700")
    return p


def write_exclusive(path: Path, data: bytes):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def read_private(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise CaptureRefused("SOURCE_TOO_LARGE")
    return data


def init_capture(directory, *, season: int, week: int, season_type="regular",
                 mode="PROSPECTIVE_PREGAME") -> dict:
    d = private_dir(directory, create=True)
    if mode not in MODES:
        # Season-wide files downloaded after games are not pregame evidence.
        raise CaptureRefused("HISTORICAL_OR_UNKNOWN_CAPTURE_MODE_NOT_PREGAME_EVIDENCE")
    if type(season) is not int or not 2000 <= season <= 2100 or type(week) is not int or not 0 <= week <= 20:
        raise CaptureRefused("SEASON_OR_WEEK_INVALID")
    if season_type not in ("regular", "postseason"):
        raise CaptureRefused("SEASON_TYPE_INVALID")
    doc = {"schema": CAPTURE_SCHEMA, "season": season, "week": week,
           "season_type": season_type, "capture_mode": mode}
    path = d / "capture.json"
    if path.exists():
        if strict_json(read_private(path)) != doc:
            raise CaptureRefused("CAPTURE_DIR_SCOPE_CONFLICT")
        return doc
    write_exclusive(path, (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode())
    return doc


def load_capture(directory) -> dict:
    d = private_dir(directory)
    doc = strict_json(read_private(d / "capture.json"))
    if not isinstance(doc, dict) or doc.get("schema") != CAPTURE_SCHEMA:
        raise CaptureRefused("CAPTURE_SCHEMA_INVALID")
    if doc.get("capture_mode") not in MODES:
        raise CaptureRefused("HISTORICAL_OR_UNKNOWN_CAPTURE_MODE_NOT_PREGAME_EVIDENCE")
    return doc


def store_source(directory, source: str, body: bytes, *, provider: str, observed_utc: datetime,
                 captured_utc: datetime | None = None, published_utc: datetime | None = None,
                 url: str | None = None, http_status: int | None = None) -> dict:
    if source not in SOURCES:
        raise CaptureRefused("UNKNOWN_SOURCE")
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_BYTES:
        raise CaptureRefused("SOURCE_BYTES_INVALID")
    if not isinstance(provider, str) or not provider.strip():
        raise CaptureRefused("PROVIDER_REQUIRED")
    d = private_dir(directory)
    load_capture(d)
    captured = captured_utc or now_utc()
    if published_utc is not None and published_utc > observed_utc:
        raise CaptureRefused("PUBLISHED_AFTER_OBSERVED")
    if observed_utc > captured:
        raise CaptureRefused("OBSERVED_AFTER_CAPTURED")
    strict_json(body)  # all sources are JSON; refuse malformed bytes up front
    key = captured.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"{source}__{key}"
    receipt = {"schema": RECEIPT_SCHEMA, "source": source, "provider": provider, "url": url,
               "http_status": http_status, "file": stem + ".bin", "bytes": len(body),
               "sha256": "sha256:" + sha256(body).hexdigest(),
               "published_utc": stamp(published_utc) if published_utc else None,
               "published_utc_basis": "PROVIDER_CLAIM" if published_utc else "UNKNOWN_UPPER_BOUND_IS_OBSERVED",
               "observed_utc": stamp(observed_utc), "captured_utc": stamp(captured),
               "official_counted": 0, "approved_stake_u": 0}
    write_exclusive(d / (stem + ".bin"), body)
    write_exclusive(d / (stem + ".receipt.json"),
                    (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
    return receipt


def select_source(directory, source: str, frozen: datetime):
    """Latest verified capture with captured_utc <= frozen; later captures are ignored."""
    d = private_dir(directory)
    best = None
    for rp in sorted(d.glob(source + "__*.receipt.json")):
        m = STEM.fullmatch(rp.name[: -len(".receipt.json")])
        if not m or m.group("src") != source:
            continue
        rec = strict_json(read_private(rp))
        if not isinstance(rec, dict) or rec.get("schema") != RECEIPT_SCHEMA or rec.get("source") != source:
            raise CaptureRefused("RECEIPT_INVALID:" + source)
        captured = utc(rec.get("captured_utc"), "captured")
        observed = utc(rec.get("observed_utc"), "observed")
        published = utc(rec["published_utc"], "published") if rec.get("published_utc") else observed
        if not published <= observed <= captured:
            raise CaptureRefused("SOURCE_CLOCK_ORDER:" + source)
        if captured > frozen:
            continue
        if best is None or captured > best[0]:
            best = (captured, rec)
    if best is None:
        return None, None
    rec = best[1]
    body = read_private(d / rec["file"])
    if len(body) != rec.get("bytes") or "sha256:" + sha256(body).hexdigest() != rec.get("sha256"):
        raise CaptureRefused("SOURCE_SHA_MISMATCH:" + source)
    return rec, body


def main(argv=None):
    import argparse
    import sys
    p = argparse.ArgumentParser(description="Initialise a CFB capture dir or register an operator file.")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("capture_dir")
    i.add_argument("--season", type=int, required=True)
    i.add_argument("--week", type=int, required=True)
    i.add_argument("--season-type", default="regular")
    r = sub.add_parser("register", help="archive an operator QB / injury JSON file with its clocks")
    r.add_argument("capture_dir")
    r.add_argument("--source", choices=OPERATOR_SOURCES, required=True)
    r.add_argument("--file", required=True)
    r.add_argument("--provider", required=True, help="e.g. operator:official-availability-report")
    r.add_argument("--observed-utc", required=True, help="when the operator observed the information (Z)")
    a = p.parse_args(argv)
    try:
        if a.cmd == "init":
            init_capture(a.capture_dir, season=a.season, week=a.week, season_type=a.season_type)
            print("CAPTURE_DIR_READY")
        else:
            body = read_private(Path(a.file))
            rec = store_source(a.capture_dir, a.source, body, provider=a.provider,
                               observed_utc=utc(a.observed_utc, "observed_utc"))
            print(a.source, "REGISTERED", rec["sha256"])
    except (CaptureRefused, OSError) as exc:
        print("BLOCKED " + (str(exc) if isinstance(exc, CaptureRefused) else "OS_ERROR"), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
