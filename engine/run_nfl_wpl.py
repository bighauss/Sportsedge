#!/usr/bin/env python3
"""NFL RUN IT with simulator win/push/loss pricing. Run as its own process; frozen v5 untouched.

Usage:  python engine/run_nfl_wpl.py board.csv

The board is validated STRICTLY before frozen v5 reads it, against the market catalog of frozen v5 itself
(sportsedge_v5.PROPS["drive"], TD_NAMES, PERIODS, split_market) rather than a separate hand-kept list.
Rejected, with a named error: duplicate or missing required header columns; rows with extra cells, no home team,
no market, or neither price; odds that are not exact signed integers (v5 would turn "1+10" into +110); lines that
are not plain decimals ("4+4" would become 44); spread/total/team-total rows without a line (v5 would default it to
0); game-line rows carrying a player; player rows whose market v5 does not price, or stat props without a line; and
unknown game-level markets.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_wpl_capture  # noqa: E402
import run_nfl  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

PRICE = re.compile(r"^[+-]?[1-9][0-9]*$")
LINE = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$")
NEEDS_LINE = {"SPREAD", "TOTAL", "HOME_TT", "AWAY_TT"}
PERIOD_OK = NEEDS_LINE | {"ML"}                                   # allowed with a period prefix
FULL_GAME_ONLY = {"OT", "BTTS", "REG_HOME", "REG_AWAY", "REG_DRAW"}  # v5 prices these only without a prefix
REQUIRED_COLUMNS = ("sport", "home", "market")


def player_markets():
    """NFL player markets frozen v5 prices: stat props (line required) and touchdown markets (no line)."""
    return set(v5.PROPS["drive"]), set(v5.TD_NAMES)


def game_market_ok(market):
    pre, base = v5.split_market("NFL", market)
    if base in PERIOD_OK:
        return True
    if pre:
        return False
    return base in FULL_GAME_ONLY or base == "SGP" or base.startswith(("HOME_BY_", "AWAY_BY_"))


def validate_input(path):
    """Strict structural validation of the raw CSV text; raises ValueError naming every offending cell."""
    stat_props, td_props = player_markets()
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
        market, player = cell(r, "market").upper(), cell(r, "player")
        if not cell(r, "home"):
            shape.append("line %d has no home team" % n)
        if not market:
            shape.append("line %d has no market" % n)
            continue
        pre, base = v5.split_market("NFL", market)
        for col in ("price_a", "price_b"):
            v = cell(r, col)
            if v and (not PRICE.fullmatch(v) or abs(int(v)) < 100):
                odds.append("line %d %s=%r" % (n, col, v))
        if not cell(r, "price_a") and not cell(r, "price_b"):
            odds.append("line %d has neither price_a nor price_b" % n)
        v = cell(r, "line")
        if v and not LINE.fullmatch(v):
            lines.append("line %d line=%r" % (n, v))
        elif player:
            if base in PERIOD_OK or game_market_ok(market):
                shape.append("line %d game-line market %s carries player %r" % (n, market, player))
            elif pre or (market not in stat_props and market not in td_props):
                shape.append("line %d player market %r is not priced by frozen v5" % (n, market))
            elif market in stat_props and not v:
                lines.append("line %d player market=%s has no line" % (n, market))
        else:
            if not game_market_ok(market):
                shape.append("line %d unknown game-level market %r" % (n, market))
            elif base in NEEDS_LINE and not v:
                lines.append("line %d market=%s has no line" % (n, market))
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
