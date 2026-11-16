#!/usr/bin/env python3
"""Archive typed sportsbook observations privately, NEVER authenticate them.

A typed DK/app/UI observation is a user assertion, not a provider-original
receipt. Each original CSV byte remains unmodified on disk. This parser retains
every logical input record and all rejected offers. No wager or certification.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import stat

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "sportsedge-manual-paper-capture-v1"
HEADER = (
    "sport", "event_id", "game_start_utc", "book", "source_surface",
    "market_family", "provider_market_id", "period", "selection_id", "side",
    "participant_id", "stat", "line", "price_american", "observed_at_utc",
    "offer_state", "exclusion_reason",
)
SPORTS = frozenset(("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"))
MARKETS = frozenset((
    "ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP", "PERIOD",
    "ALTERNATE", "ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET",
    "NRFI", "YRFI", "HR", "SOG", "SAVES", "OUTRIGHT", "MATCHUP",
    "FIRST_ROUND_LEADER", "ROUND_SCORE", "SGP", "DFS", "OTHER",
))
OFFER_STATES = frozenset(("OBSERVED_PRICE", "NOT_CAPTURED", "REJECTED"))
REASONS = frozenset((
    "NO_PRICE", "NO_MODEL", "NO_PROVENANCE", "UNSUPPORTED", "STALE",
    "IDENTITY_MISMATCH", "OUT_OF_WINDOW", "INJURY_UNCONFIRMED", "OTHER",
))
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_./+~-]{0,95}$")
AMERICAN = re.compile(r"^[+-]?[0-9]{3,7}$")
MAX_SOURCE_BYTES = 10_000_000
MAX_INPUT_ROWS = 50000


class ManualCaptureError(ValueError):
    pass


def _private_path(path, *, must_exist=False):
    lexical = Path(os.path.abspath(os.fspath(path)))
    resolved = lexical.resolve()
    for candidate in (lexical, resolved):
        if candidate == REPO_ROOT or REPO_ROOT in candidate.parents:
            raise ManualCaptureError("PUBLIC_GIT_REPOSITORY_PATH_REFUSED")
    if lexical.is_symlink() or any(parent.is_symlink() for parent in lexical.parents):
        raise ManualCaptureError("SYMLINK_PATH_REFUSED")
    if must_exist and (not lexical.is_file() or not lexical.exists()):
        raise ManualCaptureError("SOURCE_FILE_MISSING")
    return lexical


def _read_private_source(path):
    """Read one bounded source FD; deny symlink swap and changed file type."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise ManualCaptureError("SOURCE_MUST_BE_REGULAR_FILE")
        if details.st_mode & 0o077:
            raise ManualCaptureError("SOURCE_MUST_BE_OWNER_ONLY_0600")
        if details.st_size < 1 or details.st_size > MAX_SOURCE_BYTES:
            raise ManualCaptureError("ORIGINAL_CSV_EMPTY_OR_TOO_LARGE")
        with os.fdopen(fd, "rb") as source:
            fd = -1
            raw = source.read(MAX_SOURCE_BYTES + 1)
        if not raw or len(raw) > MAX_SOURCE_BYTES:
            raise ManualCaptureError("ORIGINAL_CSV_EMPTY_OR_TOO_LARGE")
        return raw
    finally:
        if fd >= 0:
            os.close(fd)


def _private_destination(path):
    parent = path.parent
    if not parent.is_dir():
        raise ManualCaptureError("DESTINATION_DIRECTORY_MISSING")
    if parent.stat().st_mode & 0o077:
        raise ManualCaptureError("DESTINATION_DIRECTORY_MUST_BE_0700")
    if path.exists():
        raise FileExistsError("ARCHIVE_REPORT_ALREADY_EXISTS")


def _utc(text, name):
    if not isinstance(text, str) or not text.endswith("Z"):
        raise ManualCaptureError("UTC_Z_REQUIRED:" + name)
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except (ValueError, OverflowError) as exc:
        raise ManualCaptureError("INVALID_UTC:" + name) from exc
    if dt.utcoffset().total_seconds() != 0:
        raise ManualCaptureError("NON_UTC:" + name)
    return dt


def _decimal(text, name):
    try:
        if not isinstance(text, str) or not text or text.strip() != text:
            raise ValueError
        value = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        raise ManualCaptureError("INVALID_" + name) from None
    if not value.is_finite():
        raise ManualCaptureError("INVALID_" + name)
    return value


def _price(text):
    if not isinstance(text, str) or not AMERICAN.fullmatch(text):
        raise ManualCaptureError("INVALID_AMERICAN_PRICE")
    number = int(text)
    if not 100 <= abs(number) <= 100000:
        raise ManualCaptureError("INVALID_AMERICAN_PRICE")
    return number


def _validate_row(row, captured):
    problems = []
    for field in ("sport", "event_id", "game_start_utc", "book",
                  "source_surface", "market_family", "period", "selection_id",
                  "side", "observed_at_utc", "offer_state"):
        if not row[field]:
            problems.append("MISSING_" + field.upper())
    if row["sport"] not in SPORTS:
        problems.append("UNSUPPORTED_SPORT")
    if row["market_family"] not in MARKETS:
        problems.append("UNKNOWN_MARKET_FAMILY")
    if row["offer_state"] not in OFFER_STATES:
        # Do not silently accept NOT_OFFERED from an unauthenticated UI.
        problems.append("UNAUTHENTICATED_OFFER_STATE")
    for field in ("event_id", "book", "source_surface", "provider_market_id",
                  "period", "selection_id", "side", "participant_id", "stat"):
        value = row[field]
        if value and not IDENTITY.fullmatch(value):
            problems.append("INVALID_" + field.upper())
    try:
        start = _utc(row["game_start_utc"], "GAME_START")
        observed = _utc(row["observed_at_utc"], "OBSERVED")
        if observed > captured:
            problems.append("OBSERVED_AFTER_LOCAL_CAPTURE")
        if observed >= start or captured >= start:
            problems.append("NOT_PREGAME_OBSERVATION")
        if (captured - observed).total_seconds() > 300:
            problems.append("STALE_MANUAL_OBSERVATION_OVER_300S")
    except ManualCaptureError as exc:
        problems.append(str(exc))
    if row["offer_state"] == "OBSERVED_PRICE":
        if row["exclusion_reason"]:
            problems.append("PRICED_ROW_HAS_EXCLUSION_REASON")
        try:
            _price(row["price_american"])
        except ManualCaptureError as exc:
            problems.append(str(exc))
        if row["market_family"] not in ("ML", "ATTD", "FIRST_TD", "TD_2PLUS",
                                        "FIRST_BASKET", "NRFI", "YRFI", "OUTRIGHT"):
            try:
                _decimal(row["line"], "LINE")
            except ManualCaptureError as exc:
                problems.append(str(exc))
    else:
        if row["price_american"]:
            problems.append("NONPRICED_ROW_CONTAINS_PRICE")
        if row["exclusion_reason"] not in REASONS:
            problems.append("INVALID_OR_MISSING_EXCLUSION_REASON")
    # We deliberately do not claim the completeness of a two-sided sportsbook
    # inventory or that a quote identifier is provider-authenticated.
    return sorted(set(problems))


def _records(raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ManualCaptureError("INVALID_CSV_ENCODING") from exc
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise ManualCaptureError("MISSING_OR_MALFORMED_HEADER") from exc
    if len(header) != len(HEADER) or set(header) != set(HEADER):
        raise ManualCaptureError("INVALID_OR_DUPLICATE_CSV_HEADER")
    parsed = []
    try:
        for row in reader:
            if len(parsed) >= MAX_INPUT_ROWS:
                raise ManualCaptureError("TOO_MANY_INPUT_ROWS")
            line_num = reader.line_num
            if len(row) != len(header):
                parsed.append((line_num, None, ["MALFORMED_CSV_FIELD_COUNT"], row))
            else:
                parsed.append((line_num, dict(zip(header, row)), [], row))
    except csv.Error as exc:
        raise ManualCaptureError("MALFORMED_CSV_QUOTING") from exc
    return parsed


def analyze(raw, *, captured_at_utc):
    """Read-only analysis. All input records are retained; never certifies A-E."""
    captured = _utc(captured_at_utc, "LOCAL_CAPTURE")
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ManualCaptureError("ORIGINAL_CSV_EMPTY_OR_TOO_LARGE")
    parsed = _records(raw)
    fingerprints = []
    for _, row, _, _ in parsed:
        if row is None or row.get("offer_state") != "OBSERVED_PRICE":
            fingerprints.append(None)
        else:
            fingerprints.append(tuple(row.get(k, "") for k in (
                "sport", "event_id", "book", "source_surface", "market_family",
                "provider_market_id", "period", "selection_id", "side",
                "participant_id", "stat", "line", "observed_at_utc",
            )))
    duplicates = Counter(k for k in fingerprints if k is not None)
    rows = []
    by_market = Counter()
    for index, (line_num, row, pre, raw_fields) in enumerate(parsed):
        problems = list(pre)
        if row is not None:
            problems.extend(_validate_row(row, captured))
        if fingerprints[index] is not None and duplicates[fingerprints[index]] > 1:
            problems.append("DUPLICATE_MANUAL_QUOTE_SNAPSHOT")
        reasons = sorted(set(problems))
        state = "BLOCKED" if reasons else "PAPER_UNVERIFIED"
        if row is None:
            payload = {"original_fields": raw_fields}
        else:
            payload = row
            by_market[(row["sport"], row["market_family"], row["offer_state"])] += 1
        rows.append({"input_index": index, "csv_line_number": line_num,
                     "original_record": payload, "state": state,
                     "reasons": reasons + ["MANUAL_SOURCE_NOT_INDEPENDENTLY_AUTHENTICATED"],
                     "approved_stake_u": 0, "official_counted": 0})
    return {
        "schema": SCHEMA, "created_at_utc": captured_at_utc,
        "original_csv_sha256": "sha256:" + sha256(raw).hexdigest(),
        "original_csv_bytes": len(raw),
        "capture_method": "USER_ENTERED_MANUAL_OFFLINE_UNVERIFIED",
        "provider_original_bytes_attested": False,
        "trusted_provider_timestamp_attested": False,
        "complete_market_inventory_authenticated": False,
        "dual_independent_book_chain_authenticated": False,
        "gate_a_closed": False,
        "other_gates_closed": False,
        "official_market_count": 0, "approved_stake_u": 0,
        "status": "PAPER_0U_MANUAL_SOURCE_UNVERIFIED",
        "total_records": len(rows),
        "paper_unverified_rows": sum(r["state"] == "PAPER_UNVERIFIED" for r in rows),
        "blocked_rows": sum(r["state"] == "BLOCKED" for r in rows),
        "by_sport_market_offer_state": [
            {"sport": sport, "market_family": market,
             "offer_state": offer, "count": n}
            for (sport, market, offer), n in sorted(by_market.items())
        ],
        "rows": rows,
    }


def archive(source, destination, *, captured_at_utc=None):
    """Create only one private mode-0600 JSON report; leave source untouched."""
    src = _private_path(source, must_exist=True)
    dst = _private_path(destination)
    if src == dst:
        raise ManualCaptureError("SOURCE_EQUALS_OUTPUT")
    _private_destination(dst)
    raw = _read_private_source(src)
    if captured_at_utc is None:
        captured_at_utc = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    result = analyze(raw, captured_at_utc=captured_at_utc)
    data = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    fd = os.open(dst, os.O_CREAT | os.O_WRONLY | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as target:
            fd = -1
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_csv")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    result = archive(args.original_csv, args.report)
    print(json.dumps({k: result[k] for k in (
        "status", "total_records", "paper_unverified_rows", "blocked_rows",
        "gate_a_closed", "approved_stake_u")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
