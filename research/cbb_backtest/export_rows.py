"""Deterministic export of the committed `identical_rows_{season}.csv` evidence files.

Input: rows_paired_forecasts.csv written by harness._report (every forecast row, all models).
Rule: keep rows with identical_row == True (all models forecast with a predictive SD), keep the
fixed column list below, preserve harness row order, write LF line endings. No values are altered.
"""
import csv
import sys
from pathlib import Path

import numpy as np

MODELS = ("native_frozen", "raw", "regularized", "sched_adj", "native_hca_repaired", "FG1")
COLS = (["event_id", "season", "day", "origin", "home", "away", "neutral", "home_points", "away_points"]
        + [f"{m}_{k}" for m in MODELS for k in ("margin", "total")]
        + ["FG1_sd_margin", "native_frozen_sd_margin", "mkt_provider", "mkt_close_spread_home", "mkt_close_total",
           "mkt_close_ml_home", "mkt_close_ml_away", "mkt_close_spread_price_home", "mkt_close_spread_price_away",
           "mkt_close_over_price", "mkt_close_under_price"])


# Evidence-file formatting (fixed; this is how the committed files were written): model margin/total/SD
# columns rounded to 2 decimals (numpy half-even on the stored binary value), market numbers as floats
# (blank when missing). Source values come from rows_paired_forecasts.csv, which holds 3 decimals.
_ROUND2 = {c for c in COLS if c.endswith(("_margin", "_total")) and not c.startswith("mkt_")} | {"FG1_sd_margin", "native_frozen_sd_margin"}
_FLOATS = {c for c in COLS if c.startswith("mkt_") and c != "mkt_provider"}


def fmt(col, v):
    if v == "":
        return ""
    if col in _ROUND2:
        return repr(float(np.round(float(v), 2)))
    if col in _FLOATS:
        return repr(float(v))
    return v


def project(rows):
    """Yield formatted evidence rows (list of strings) for identical_row == True rows."""
    for r in rows:
        if r["identical_row"] == "True":
            yield [fmt(c, r.get(c, "")) for c in COLS]


def export(paired_csv, out_dir):
    by = {}
    with open(paired_csv, newline="") as f:
        for r in csv.DictReader(f):
            for out in project([r]):
                by.setdefault(r["season"], []).append(out)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    for s, rows in sorted(by.items()):
        with open(out_dir / f"identical_rows_{s}.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(COLS)
            w.writerows(rows)
    return sorted(by)


if __name__ == "__main__":
    print(export(Path(sys.argv[1]), Path(sys.argv[2])))
