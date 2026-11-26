#!/usr/bin/env python3
"""NFL RUN IT with simulator win/push/loss pricing. Run as its own process; frozen v5 untouched.

Usage:  python engine/run_nfl_wpl.py board.csv

The board is validated STRICTLY before frozen v5 reads it: duplicate header columns, odds that are not exact
signed integers (v5 would turn "1+10" into +110), lines that are not plain decimals ("4+4" would become 44), and
spread/total/team-total rows without a line (v5 would default it to 0) all stop the run with a named error.
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
    ix = {h: i for i, h in enumerate(header) if h}
    cell = lambda r, k: (r[ix[k]].strip() if k in ix and ix[k] < len(r) else "")  # noqa: E731
    odds, lines = [], []
    for n, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r) or cell(r, "sport").upper() != "NFL":
            continue
        for col in ("price_a", "price_b"):
            v = cell(r, col)
            if v and (not PRICE.fullmatch(v) or abs(int(v)) < 100):
                odds.append("line %d %s=%r" % (n, col, v))
        v, market = cell(r, "line"), cell(r, "market")
        if v and not LINE.fullmatch(v):
            lines.append("line %d line=%r" % (n, v))
        elif not v and market and _base(market) in NEEDS_LINE and not cell(r, "player"):
            lines.append("line %d market=%s has no line" % (n, market))
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
