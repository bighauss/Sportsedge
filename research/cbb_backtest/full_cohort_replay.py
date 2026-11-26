"""Independent all-season comparison of the committed non-FG1 forecast evidence.

This replays normalized derivatives, not authenticated original sources. FG1 is
deliberately excluded because its external checkout must be pinned independently.
Compare the entire published paired cohort (not a chosen slice); report extra
eligible non-FG1 rows without claiming that the six-model cohort was reproduced.
PAPER / 0u / NON_COUNTED.
"""
import csv
import io
import json
import tempfile
from collections import Counter
from pathlib import Path

from . import export_rows as X
from . import harness as H
from . import inputs as I
from . import models as M

SEASONS = tuple(range(2019, 2027))
EXPECTED = 35791
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "results" / "run3_final" / "rows"


def canonical(rows):
    out = io.StringIO(newline="")
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue().encode("utf-8")


def indexed(rows):
    out = {}
    for row in rows:
        key = (row[1], row[0])
        if key in out:
            raise AssertionError(f"DUPLICATE_EVENT {key}")
        out[key] = row
    return out


def main():
    problems = I.verify_derivatives(I.DATA_DIR)
    if problems:
        raise AssertionError(problems)
    keep = [i for i, col in enumerate(X.COLS) if not col.startswith("FG1_")]
    expected = []
    for season in SEASONS:
        with (EVIDENCE / f"identical_rows_{season}.csv").open(newline="") as stream:
            reader = csv.reader(stream)
            if next(reader) != X.COLS:
                raise AssertionError("EVIDENCE_HEADER_DRIFT")
            for row in reader:
                if len(row) != len(X.COLS) or row[1] != str(season):
                    raise AssertionError(f"EVIDENCE_ROW_INVALID {season}")
                expected.append(row)
    if len(expected) != EXPECTED:
        raise AssertionError(f"EVIDENCE_COUNT {len(expected)}")
    expected_by = indexed(expected)
    names = [n for n in M.MODELS if n != "FG1"]
    if names != list(X.MODELS[:-1]):
        raise AssertionError("MODEL_REGISTRY_DRIFT")
    odds, _ = I.load_odds_normalized(I.DATA_DIR)
    leak = {"origins": 0, "violations": []}
    rows, ident, _ = H.build_rows(SEASONS, names, lambda s: I.load_games_normalized(I.DATA_DIR, s), odds, leak)
    if leak["violations"] or leak["origins"] != 175:
        raise AssertionError(f"CHRONOLOGY {leak}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "paired.csv"
        H._write(path, H.paired_rows(rows, ident, names))
        with path.open(newline="") as stream:
            actual = list(X.project(csv.DictReader(stream)))
    actual_by = indexed(actual)
    missing = set(expected_by) - set(actual_by)
    if missing:
        raise AssertionError(f"MISSING_COHORT_ROWS {len(missing)} examples={sorted(missing)[:5]}")
    cohort = [r for r in actual if (r[1], r[0]) in expected_by]
    for season in SEASONS:
        want = [[r[i] for i in keep] for r in expected if r[1] == str(season)]
        got = [[r[i] for i in keep] for r in cohort if r[1] == str(season)]
        if canonical(want) != canonical(got):
            mismatch = next(((a, b) for a, b in zip(want, got) if a != b), None)
            raise AssertionError(f"SEASON_REPLAY_MISMATCH {season} expected={len(want)} actual={len(got)} first={mismatch}")
        print(f"SEASON {season}: {len(want)} committed rows byte-identical (non-FG1 columns)", flush=True)
    print(json.dumps({"status": "NON_FG1_COMMITTED_COHORT_REPRODUCED",
                      "matched_rows": len(cohort), "extra_non_fg1_rows": len(actual) - len(cohort),
                      "total_forecast_rows": len(rows), "origins": leak["origins"],
                      "seasons": dict(Counter(r[1] for r in cohort)),
                      "fg1_verified": False, "raw_source_rederived": False,
                      "label": "NON_COUNTED", "approved_stake_u": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
