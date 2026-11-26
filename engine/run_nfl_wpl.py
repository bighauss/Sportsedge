#!/usr/bin/env python3
"""NFL RUN IT with simulator win/push/loss pricing. Run as its own process; frozen v5 untouched.

Usage:  python engine/run_nfl_wpl.py board.csv

The board is validated STRICTLY before frozen v5 reads it, against the market catalog of frozen v5 itself
(sportsedge_v5.PROPS["drive"], TD_NAMES, PERIODS, split_market) rather than a separate hand-kept list.
Rejected, with a named error: duplicate or missing required header columns; rows with extra cells, no home team,
no market, or neither price; odds that are not exact signed integers (v5 would turn "1+10" into +110); lines,
projections, scores and 'remaining' that are not plain decimals ("4+4" or "2+7" would become 44 / 27 because v5
deletes every '+'); spread/total/team-total rows without a line (v5 would default it to 0); game-line rows carrying a
player; player rows whose market v5 does not price, or stat props without a line; and unknown game-level markets.

PROVENANCE (fail closed). After pricing, every NFL row is classified by engine/nfl_provenance.py from the board and the
signed evidence supplied OUTSIDE the board (env SPORTSEDGE_EVIDENCE_MANIFEST = manifest JSON path,
SPORTSEDGE_EVIDENCE_KEY = HMAC key; the key is never a CLI argument). Rows whose provenance is not VERIFIED_PIT
(unverified projection, ANCHOR, MIXED, AMBIGUOUS, INVALID_INPUT, or no entry) are HELD at 0u with the class and reason, so
a market-fitted or unproven number can never reach the card or the 'selected_for_card' marker. With no evidence supplied
every row is held: an empty independent card is the intended default.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_provenance  # noqa: E402
import nfl_wpl_capture  # noqa: E402
import run_nfl  # noqa: E402
import sportsedge_v5 as v5  # noqa: E402

PRICE = re.compile(r"^[+-]?[1-9][0-9]*$")
LINE = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$")
DECIMAL = re.compile(r"^[+-]?(?:[0-9]{1,6}(?:\.[0-9]{1,6})?|\.[0-9]{1,6})$")
NUMERIC_COLS = ("home_proj", "away_proj", "proj", "home_score", "away_score", "remaining")
NEEDS_LINE = {"SPREAD", "TOTAL", "HOME_TT", "AWAY_TT"}
PERIOD_OK = NEEDS_LINE | {"ML"}                                   # allowed with a period prefix
FULL_GAME_ONLY = {"OT", "BTTS", "REG_HOME", "REG_AWAY", "REG_DRAW"}  # v5 prices these only without a prefix
REQUIRED_COLUMNS = ("sport", "home", "away", "market")
ENV_MANIFEST, ENV_KEY = "SPORTSEDGE_EVIDENCE_MANIFEST", "SPORTSEDGE_EVIDENCE_KEY"


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
    odds, lines, shape, nums, live = [], [], [], [], []
    nfl_rows = 0
    for n, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        if cell(r, "sport").upper() != "NFL":
            shape.append("line %d is not an NFL row" % n)
            continue
        nfl_rows += 1
        if len(r) != len(header):
            shape.append("line %d has %d cells for %d columns" % (n, len(r), len(header)))
            continue
        market, player = cell(r, "market").upper(), cell(r, "player")
        if not cell(r, "home"):
            shape.append("line %d has no home team" % n)
        if not cell(r, "away"):
            shape.append("line %d has no away team" % n)
        if cell(r, "home").casefold() == cell(r, "away").casefold():
            shape.append("line %d must have distinct teams" % n)
        if any(cell(r, col) for col in ("remaining", "home_score", "away_score")):
            live.append("line %d has live score/remaining data" % n)
        if not market:
            shape.append("line %d has no market" % n)
            continue
        pre, base = v5.split_market("NFL", market)
        for col in NUMERIC_COLS:
            v = cell(r, col)
            if v and (len(v) > 16 or not DECIMAL.fullmatch(v)):
                nums.append("line %d %s=%r" % (n, col, v))
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
    if not nfl_rows:
        shape.append("board has no NFL rows")
    if shape:
        raise ValueError("malformed NFL board structure: " + "; ".join(shape[:20]))
    if odds:
        raise ValueError("invalid American odds on NFL rows: " + "; ".join(odds[:20]))
    if nums:
        raise ValueError("non-canonical projection/score on NFL rows: " + "; ".join(nums[:20]))
    if lines:
        raise ValueError("non-canonical line on NFL rows: " + "; ".join(lines[:20]))
    if live:
        raise ValueError("pregame-only NFL board: " + "; ".join(live[:20]))


def apply_provenance(o, prov):
    """Annotate one priced NFL row with its provenance class and HOLD it unless every dependency is VERIFIED_PIT.
    prov is classify()'s mapping, or None when classification itself failed (every row is then held)."""
    if o.get("sport") != "NFL":
        return o
    parts = str(o.get("bet_type", "")).split("|")
    market, sgp = parts[0], (parts[2] if len(parts) > 2 else "")
    game = str(o.get("game", "")).replace(" (LIVE)", "")
    if prov is None:
        cls, why = nfl_provenance.AMBIGUOUS, "provenance classification failed"
    else:
        cls, why = prov.get((game, market, o.get("player", "") or "", sgp),
                            (nfl_provenance.AMBIGUOUS, "no provenance entry for this row"))
    o["provenance"], o["provenance_reason"] = cls, why
    if not nfl_provenance.eligible(cls):
        reasons = [x for x in str(o.get("held", "")).split("; ") if x]
        reasons.append("provenance %s: not an independent verified forecast%s" % (cls, " (%s)" % why if why else ""))
        o["held"] = "; ".join(reasons)
    return o


def main(path, manifest=None, key=None):
    validate_input(path)
    if manifest is None and os.environ.get(ENV_MANIFEST):
        manifest = nfl_provenance.load_manifest(os.environ[ENV_MANIFEST])
    key = key or os.environ.get(ENV_KEY)
    try:
        prov = nfl_provenance.classify(path, manifest, key)
    except Exception:                                   # fail closed: every row held
        prov = None
    with nfl_wpl_capture.installed():
        inner = run_nfl.guard

        def guard(o, gaps):
            return apply_provenance(inner(o, gaps), prov)

        run_nfl.guard = guard
        try:
            return run_nfl.main(path)
        finally:
            run_nfl.guard = inner


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "board.csv")
