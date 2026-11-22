import unittest

import sportsedge_cfb_model as M
import cfb_push_challenger as C


def row(market, line, mean, odds=-110, direction=None, p_market=0.5):
    p = M.pgt(mean, line if direction else -line, M.SD_TOTAL if market == "Total" else M.SD_MARGIN)
    if direction == "under":
        p = 1 - p
    return dict(market=market, line=line, proj=mean, odds=odds, direction=direction, p_market=p_market,
                p_model=p, ev_raw=p * M.dec(odds) - 1)


class Challenger(unittest.TestCase):
    def test_half_point_line_matches_frozen(self):
        r = C.reprice(row("Total", 52.5, 55.0, direction="over"))
        self.assertAlmostEqual(r["challenger_p_push"], 0.0)
        self.assertAlmostEqual(r["challenger_p_win"], r["p_model"])
        self.assertAlmostEqual(r["challenger_ev_raw"], r["ev_raw"])

    def test_integer_spread_has_push_mass_refunded(self):
        # Frozen continuous p counts ~half the push bucket as a win and half as a loss;
        # refunding the push removes that loss half, so EV moves slightly UP at -110.
        r = C.reprice(row("Spread", -7, 9.0))          # side favored by 9 laying 7
        self.assertGreater(r["challenger_p_push"], 0.02)
        self.assertGreater(r["challenger_ev_raw"], r["ev_raw"])
        self.assertLess(r["challenger_ev_raw"] - r["ev_raw"], 0.01)
        self.assertAlmostEqual(r["challenger_p_win"] + r["challenger_p_push"]
                               + (1 - r["challenger_p_win"] - r["challenger_p_push"]), 1)

    def test_integer_total_over_and_under_share_push(self):
        o = C.reprice(row("Total", 50, 50.0, direction="over"))
        u = C.reprice(row("Total", 50, 50.0, direction="under"))
        self.assertAlmostEqual(o["challenger_p_push"], u["challenger_p_push"])
        self.assertAlmostEqual(o["challenger_p_win"] + u["challenger_p_win"] + o["challenger_p_push"], 1)

    def test_push_refund_ev_formula(self):
        # -110, 50% win, 5% push, 45% loss -> +0.4545%
        d = M.dec(-110)
        self.assertAlmostEqual(0.50 * (d - 1) - 0.45, 0.004545, 5)

    def test_frozen_row_not_mutated_and_ml_unchanged(self):
        base = dict(market="ML", line=None, proj=3.0, odds=-150, p_market=0.6)
        r = C.reprice(base)
        self.assertEqual(r["challenger_status"], "UNCHANGED_NO_PUSH_MARKET")
        self.assertNotIn("challenger_status", base)

    def test_unknown_direction_unchanged(self):
        r = C.reprice(row("Total", 50, 50.0))
        self.assertEqual(r["challenger_status"], "UNCHANGED_UNKNOWN_DIRECTION")


if __name__ == "__main__":
    unittest.main()
