"""Rebuild a fixed slice of the committed evidence rows from the committed inputs (research only).

SLICE (fixed, part of the contract): season 2019, weekly origins from the first origin through
2018-12-17, i.e. every game with day < 2018-12-24. That window contains the first origins that
carry a predictive SD, so the rebuilt rows include forecast, SD and market columns. An origin's
fit uses only games before the origin and the SD uses only earlier forecast residuals, so
truncating after the last wanted window cannot change any value inside it.

rebuild_slice_rows() returns rows in the exact string format of results/run3_final/rows/*.csv.
"""
import csv
import tempfile
from datetime import date
from pathlib import Path

from . import export_rows as X
from . import harness as H
from . import inputs as I
from . import models as M

SLICE_SEASON = 2019
SLICE_CUTOFF_DAY = date(2018, 12, 24)
SLICE_LAST_ORIGIN = "2018-12-17"


def fg1_available():
    try:
        from . import fg1_adapter
        fg1_adapter._fg()
        return True
    except ImportError:
        return False


def rebuild_slice_rows(data_dir, include_fg1=None):
    """-> (columns, rows[list of str]) for identical rows of the slice. include_fg1=None means 'if importable'."""
    if include_fg1 is None:
        include_fg1 = fg1_available()
    if include_fg1 and "FG1" not in M.MODELS:
        from . import fg1_adapter
        M.register("FG1", fg1_adapter.build_fg1)
    names = [n for n in M.MODELS if n != "FG1" or include_fg1]
    odds, _ = I.load_odds_normalized(data_dir)
    leak = {"origins": 0, "violations": []}
    all_rows, ident, _ = H.build_rows([SLICE_SEASON], names, lambda s: I.load_games_normalized(data_dir, s), odds,
                                      leak, cutoff_day=SLICE_CUTOFF_DAY)
    if leak["violations"]:
        raise AssertionError(f"leakage violations in slice: {leak['violations'][:3]}")
    paired = H.paired_rows(all_rows, ident, names)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "paired.csv"
        H._write(p, paired)            # same writer as the full run (6-dp rounding, csv text)
        with open(p, newline="") as f:
            rows = list(X.project(csv.DictReader(f)))
    return list(X.COLS), rows


def committed_slice(rows_csv):
    """Committed identical rows (as strings) for the slice, in file order."""
    with open(rows_csv, newline="") as f:
        rd = csv.reader(f)
        cols = next(rd)
        if cols != list(X.COLS):
            raise AssertionError("committed rows header drifted")
        oi = cols.index("origin")
        return [r for r in rd if r[oi] <= SLICE_LAST_ORIGIN]
