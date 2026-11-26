#!/usr/bin/env python3
"""NFL RUN IT with simulator win/push/loss pricing. Run as its own process; frozen v5 untouched.

Usage:  python engine/run_nfl_wpl.py board.csv

The board is validated STRICTLY before frozen v5 reads it. Rejected, with a named error: duplicate or missing
required header columns; rows with extra cells, no home team, no market, or neither price; odds that are not exact
signed integers (v5 would turn "1+10" into +110); lines that are not plain decimals ("4+4" would become 44);
spread/total/team-total rows without a line (v5 would default it to 0); game-line rows carrying a player; player
props without a line (except ATD/FTD/TD2); and unknown game-level markets.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_wpl_capture  # noqa: E402
import run_nfl  # noqa: E402

PRICE = re.compile(r"^[+-]?[1-9][0-9]*$")
LINE = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$")
NEEDS_LINE = {"SPREAD", "TOTAL", "HOME_TT", "AWAY_TT"}
GAME_BASES = NEEDS_LINE | {"ML"}
LINELESS_PROPS = {"ATD", "FTD", "TD2"}
REQUIRED_COLUMNS = ("sport", "home", "market")
PERIODS = {"1Q", "2Q", "3Q", "4Q", "1H", "2H"}


def _base(market):
    head, _, rest = market.upper().partition("_")
    return rest if rest and head in PERIODS else market.upper()


def validate_input(path):
    """Strict structural validation of the raw CSV text; raises ValueError naming every offending cell."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError("empty board")
    header = [h.strip().lower() for h in rows[0]]
    dups = sorted({h for h in header if h and header.count(h) > 1})
    if dups:
        raise ValueError("duplicate column(s) in board header: " + ", ".join(dups))
    absent = [c for c in REQUIRED_COLUMNS if c not in header]
    if absent:
        raise ValueError("missing required column(s) in board header: " + ", ".join(absent))
    ix = {h: i for i, h in enumerate(header) if h}
    cell = lambda r, k: (r[ix[k]].strip() if k in ix and ix[k] < len(r) else "")  # noqa: E731
    odds, lines, shape = [], [], []
    for n, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r) or cell(r, "sport").upper() != "NFL":
            continue
        if any(c.strip() for c in r[len(header):]):
            shape.append("line %d has %d cells for %d columns" % (n, len(r), len(header)))
            continue
        market, player = cell(r, "market"), cell(r, "player")
        if not cell(r, "home"):
            shape.append("line %d has no home team" % n)
        if not market:
            shape.append("line %d has no market" % n)
            continue
        base = _base(market)
        for col in ("price_a", "price_b"):
            v = cell(r, col)
            if v and (not PRICE.fullmatch(v) or abs(int(v)) < 100):
                odds.append("line %d %s=%r" % (n, col, v))
        if not cell(r, "price_a") and not cell(r, "price_b"):
            odds.append("line %d has neither price_a nor price_b" % n)
        v = cell(r, "line")
        if v and not LINE.fullmatch(v):
            lines.append("line %d line=%r" % (n, v))
        elif base in GAME_BASES:
            if player:
                shape.append("line %d game-line market %s carries player %r" % (n, market, player))
            if base in NEEDS_LINE and not v:
                lines.append("line %d market=%s has no line" % (n, market))
        elif not player:
            shape.append("line %d unknown game-level market %r" % (n, market))
        elif not v and market.upper() not in LINELESS_PROPS:
            lines.append("line %d player market=%s has no line" % (n, market))
    if shape:
        raise ValueError("malformed NFL board structure: " + "; ".join(shape[:20]))
    if odds:
        raise ValueError("invalid American odds on NFL rows: " + "; ".join(odds[:20]))
    if lines:
        raise ValueError("non-canonical line on NFL rows: " + "; ".join(lines[:20]))


def main(path):
    validate_input(path)
    with nfl_wpl_capture.installed():
        return run_nfl.main(path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "board.csv")
