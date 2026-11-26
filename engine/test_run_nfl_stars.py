"""Regression: run_nfl must never emit EV-derived star ratings (stars need validated calibration)."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_nfl  # noqa: E402
import test_run_nfl as base  # noqa: E402


class StarsUncalibrated(unittest.TestCase):
    def test_guard_zeroes_stars_for_blended_model_only_and_non_nfl_rows(self):
        for kw in (dict(), dict(market_p=None, ev=0.2, price=200), dict(sport="CBB")):
            with self.subTest(kw=kw):
                o = base.row(stars=3, score=9.0, **kw)
                g = run_nfl.guard(o, {})
                self.assertEqual(g["stars"], 0)
                self.assertEqual(g["stars_label"], run_nfl.STARS_LABEL)
                self.assertEqual(g["approved_stake_u"], 0)

    def test_label_text(self):
        self.assertEqual(run_nfl.STARS_LABEL, "N/A \u2014 uncalibrated")

    def test_build_and_table_never_print_asterisk_stars(self):
        cwd = os.getcwd()
        os.chdir(tempfile.mkdtemp())
        try:
            r = run_nfl.build(base.board(base.game(24, 20)))
            self.assertTrue(r["out"])
            self.assertTrue(all(o["stars"] == 0 and o["stars_label"] == run_nfl.STARS_LABEL for o in r["out"]))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run_nfl.table(r["out"][:3])
            text = buf.getvalue()
            self.assertIn(run_nfl.STARS_LABEL, text)
            self.assertNotIn("*", text)
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
