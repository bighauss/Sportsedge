"""Offline CFB RUN IT integration: actual legacy rows reach master quant odds."""
import copy
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfb_run_it as R
import sportsedge_cfb_model as M
import test_cfb_run_it as F


class QuantRunnerAudit(unittest.TestCase):
    def test_real_runner_fixture_audits_before_selection(self):
        cap = F.fixture()
        card, _, _, ctx = R.run(copy.deepcopy(F.INTAKE), cap,
                                dt.datetime.fromisoformat("2026-11-21T17:00:00+00:00"),
                                lambda *_: cap["_weather"])
        a = ctx["quant_arithmetic_audit"]
        self.assertEqual(a["priced_rows"], a["arithmetic_checked"])
        self.assertGreater(a["priced_rows"], len(card))
        self.assertGreater(a["nonpositive_blended_ev_rows"], 0)
        self.assertEqual(a["market_anchored_prop_rows"], 1)
        self.assertEqual(a["approved_stake_u"], 0)
        self.assertFalse(a["release_ready"])
        self.assertEqual(len(a["master_odds_sha256"]), 64)

    def row(self):
        rows = []
        M.bet(rows, None, "Total", "Over 50", 50, -110, .6, .5)
        return rows[0]

    def test_integer_line_reports_unmodelled_push(self):
        a = R.quant_arithmetic_audit([self.row()])
        self.assertEqual(a["integer_line_push_unmodelled"], 1)
        self.assertEqual(a["arithmetic_convention"], "LEGACY_ZERO_PUSH_ASSUMPTION")

    def test_bad_ev_and_probability_fail_closed(self):
        for key, value in (("ev_blend", 42), ("p_model", float("nan")),
                           ("odds", 0), ("p_blend", .99)):
            with self.subTest(key=key):
                row = self.row()
                row[key] = value
                with self.assertRaisesRegex(R.Fail, "QUANT_ARITHMETIC_MISMATCH"):
                    R.quant_arithmetic_audit([row])


if __name__ == "__main__":
    unittest.main()
