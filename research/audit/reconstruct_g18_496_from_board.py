#!/usr/bin/env python3
"""Reconstruct a DERIVED 496-side research census from original Nov 9 248-row board.

NEVER claim this is the unrecovered original engine picks.csv or legitimate
decision-time offered quotes. Input original Google Drive revision must be
privately exported and SHA-checked; no fetch/credentials in this script.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat

REPO = Path(__file__).resolve().parents[2]
ORIGINAL_BOARD_SHA256 = "922f6a10b1c038a15ba0469d344b5015b767dca6c41a791110aa083fd9027ea4"
ORIGINAL_REVISION = "0Bz5GGyFPXJYyTGFSZ3dlZzlIMW8vY0pmVHNldlZxdXVMT3hvPQ"
FIELDS = ("sport", "home", "away", "home_proj", "away_proj", "player", "team",
          "proj", "market", "line", "price_a", "price_b", "sgp", "side",
          "home_score", "away_score", "remaining")
EXPECTED = {"SPREAD": 75, "TOTAL": 75, "HOME_TT": 43, "AWAY_TT": 43,
            "ML": 2, "1H_ML": 2, "1H_SPREAD": 2, "1H_TOTAL": 2,
            "1H_HOME_TT": 2, "1H_AWAY_TT": 2}


class ReconstructionError(ValueError):
    pass


def _decimal(value, allow_blank=False):
    if allow_blank and value == "":
        return None
    try:
        d = Decimal(value)
    except (ValueError, InvalidOperation, TypeError) as e:
        raise ReconstructionError("INVALID_OR_MISSING_LINE") from e
    if not d.is_finite() or not (-10000 < d < 10000):
        raise ReconstructionError("INVALID_LINE")
    return d


def _price(value):
    if not isinstance(value, str) or not re.fullmatch(r"[+-]?[0-9]{3,6}", value.strip()):
        raise ReconstructionError("INVALID_PRICE")
    num = int(value.strip())
    if not 100 <= abs(num) <= 100000:
        raise ReconstructionError("INVALID_PRICE")
    return ("+" if num > 0 else "") + str(num)


def _pick_pair(row):
    market, home, away = row["market"], row["home"], row["away"]
    first = market.startswith("1H_")
    family = market[3:] if first else market
    prefix = "1H " if first else ""
    line = _decimal(row["line"], allow_blank=family=="ML")
    if family == "ML":
        if line is not None:
            raise ReconstructionError("MONEYLINE_MUST_HAVE_NO_LINE")
        return prefix + home + " ML", prefix + away + " ML"
    if line is None:
        raise ReconstructionError("LINE_REQUIRED")
    if family == "SPREAD":
        return prefix + home + " " + format(line, "+"), prefix + away + " " + format(-line, "+")
    if family == "TOTAL":
        if line < 0:
            raise ReconstructionError("NEGATIVE_TOTAL")
        return prefix + "Over " + str(line), prefix + "Under " + str(line)
    if family in ("HOME_TT", "AWAY_TT"):
        if line < 0:
            raise ReconstructionError("NEGATIVE_TEAM_TOTAL")
        team = home if family == "HOME_TT" else away
        return prefix + team + " Over " + str(line), prefix + team + " Under " + str(line)
    raise ReconstructionError("UNKNOWN_FAMILY:" + family)


def reconstruct(board_bytes: bytes, *, strict_nov9=True):
    try:
        board = board_bytes.decode("utf-8-sig")
    except UnicodeError as e:
        raise ReconstructionError("BOARD_NOT_UTF8") from e
    reader = csv.DictReader(io.StringIO(board, newline=""), restkey="__extra__")
    if reader.fieldnames is None or tuple(reader.fieldnames) != FIELDS:
        raise ReconstructionError("ORIGINAL_BOARD_FIELDS_DO_NOT_MATCH")
    derived, census = [], Counter()
    for i, row in enumerate(reader, start=2):
        if "__extra__" in row or any(v is None for v in row.values()):
            raise ReconstructionError("RAGGED_BOARD_ROW:" + str(i))
        if row["sport"] != "CBB" or not row["home"] or not row["away"] or row["home"] == row["away"]:
            raise ReconstructionError("INVALID_EVENT:" + str(i))
        if any(row[k] for k in ("player", "team", "proj", "sgp", "side", "home_score", "away_score", "remaining")):
            raise ReconstructionError("UNEXPECTED_POPULATED_BOARD_FIELD:" + str(i))
        census[row["market"]] += 1
        home_label, away_label = _pick_pair(row)
        game = row["away"] + " @ " + row["home"]
        derived.extend(((game, home_label, _price(row["price_a"])),
                        (game, away_label, _price(row["price_b"]))))
    if strict_nov9 and (sum(census.values()) != 248 or dict(census) != EXPECTED or len(derived) != 496):
        raise ReconstructionError("ORIGINAL_NOV9_248_496_CENSUS_MISMATCH")
    s = io.StringIO(newline="")
    writer = csv.writer(s, lineterminator="\n")
    writer.writerow(("game", "pick", "price"))
    writer.writerows(derived)
    csv_bytes = s.getvalue().encode("utf-8")
    report = {"classification": "DERIVED_FROM_BOARD_NOT_ORIGINAL_ENGINE_PICKS",
              "original_board_revision": ORIGINAL_REVISION,
              "input_sha256": hashlib.sha256(board_bytes).hexdigest(),
              "derived_sha256": hashlib.sha256(csv_bytes).hexdigest(),
              "market_rows": sum(census.values()), "derived_priced_sides": len(derived),
              "team_total_sides": 2*sum(v for k, v in census.items() if k.endswith("_TT")),
              "market_row_counts": dict(sorted(census.items())),
              "original_engine_picks_recovered": False,
              "original_run7_finals_recovered": False,
              "gate_a_authenticated": False, "official_counted": 0,
              "approved_stake_u": 0}
    return csv_bytes, report


def private(value):
    lexical = Path(os.path.abspath(Path(value).expanduser()))
    resolved = lexical.resolve()
    if lexical == REPO or REPO in lexical.parents or resolved == REPO or REPO in resolved.parents:
        raise ReconstructionError("PRIVATE_OUTSIDE_PUBLIC_GIT_REQUIRED")
    if lexical.is_symlink() or any(p.is_symlink() for p in lexical.parents):
        raise ReconstructionError("SYMLINK_SOURCE_OR_REPORT_REFUSED")
    return lexical


def _exclusive(path, body):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--board", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--expected-board-sha256", default=ORIGINAL_BOARD_SHA256)
    a = p.parse_args()
    board, out = private(a.board), private(a.out)
    if not board.is_file() or stat.S_IMODE(board.stat().st_mode) & 0o077:
        raise ReconstructionError("ORIGINAL_BOARD_MUST_BE_PRIVATE_MODE_0600")
    if not out.parent.is_dir() or stat.S_IMODE(out.parent.stat().st_mode) & 0o077:
        raise ReconstructionError("REPORT_DIRECTORY_MODE_0700_REQUIRED")
    raw = board.read_bytes()
    if hashlib.sha256(raw).hexdigest() != a.expected_board_sha256:
        raise ReconstructionError("ORIGINAL_BOARD_SHA256_MISMATCH")
    csv_out, report = reconstruct(raw)
    sidecar = out.with_suffix(out.suffix + ".derived_manifest.json")
    if out.exists() or sidecar.exists():
        raise ReconstructionError("ORIGINAL_DERIVED_OUTPUT_ALREADY_EXISTS")
    _exclusive(out, csv_out)
    try:
        _exclusive(sidecar, (json.dumps(report, indent=2, sort_keys=True) + "\n").encode())
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    print(json.dumps({k: report[k] for k in ("classification", "market_rows",
                                           "derived_priced_sides", "team_total_sides",
                                           "input_sha256", "derived_sha256")}, sort_keys=True))


if __name__ == "__main__":
    main()
