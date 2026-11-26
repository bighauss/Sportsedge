"""Regression: exported artifacts. Frozen v5 may write its own legacy picks.csv (with EV-derived stars);
run_nfl must contain that output and never overwrite an existing file."""
import contextlib
import csv
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_nfl  # noqa: E402
import test_run_nfl as base  # noqa: E402


class Artifacts(unittest.TestCase):
    def test_build_leaves_cwd_and_board_dir_clean_and_keeps_existing_picks_csv(self):
        work = tempfile.mkdtemp()
        sentinel = os.path.join(work, "picks.csv")
        with open(sentinel, "w") as f:
            f.write("SENTINEL")
        board = base.board(base.game(24, 20))
        before_board_dir = set(os.listdir(os.path.dirname(board)))
        cwd = os.getcwd()
        os.chdir(work)
        try:
            before = set(os.listdir(work))
            run_nfl.build(board)
            self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(work))
            self.assertEqual(set(os.listdir(work)), before)
            with open(sentinel) as f:
                self.assertEqual(f.read(), "SENTINEL")
        finally:
            os.chdir(cwd)
        self.assertEqual(set(os.listdir(os.path.dirname(board))), before_board_dir)

    def test_cwd_restored_when_v5_raises(self):
        work = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(work)
        try:
            with self.assertRaises(Exception):
                run_nfl.build(os.path.join(work, "missing_board.csv"))
            self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(work))
        finally:
            os.chdir(cwd)

    def test_exported_csv_has_no_stars_and_nothing_is_overwritten(self):
        work = tempfile.mkdtemp()
        sentinel = os.path.join(work, "picks.csv")
        with open(sentinel, "w") as f:
            f.write("SENTINEL")
        board = base.board(base.game(24, 20))
        cwd = os.getcwd()
        os.chdir(work)
        try:
            for _ in range(2):
                with contextlib.redirect_stdout(io.StringIO()):
                    run_nfl.main(board)
            files = sorted(x for x in os.listdir(work) if x != "picks.csv")
            self.assertEqual(len(files), 2)
            self.assertTrue(all(x.startswith("picks_nfl_") and x.endswith(".csv") for x in files))
            for name in files:
                with open(name, newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                self.assertTrue(rows)
                self.assertTrue(all(r["stars"] == "0" for r in rows))
                self.assertTrue(all(r["stars_label"] == run_nfl.STARS_LABEL for r in rows))
                self.assertTrue(all(r["approved_stake_u"] == "0" for r in rows))
            with open(sentinel) as f:
                self.assertEqual(f.read(), "SENTINEL")
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
