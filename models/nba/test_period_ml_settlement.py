"""Provider-free NBA two-way period moneyline push/refund regressions.

No real book prices, verified player scores, model promotion, or wagers.
A 3-way market with a Tie selection has a different settlement contract.
"""
import math
import unittest

import sportsedge_nba_model as m


def projection(margin=2.0):
    return {"margin": margin, "total": 226.0, "home": "H", "away": "A",
            "home_pts": 113.0 + margin / 2, "away_pts": 113.0 - margin / 2}


class TwoWayPeriodMoneyline(unittest.TestCase):
    def test_first_half_and_first_quarter_have_symmetric_push_mass(self):
        for seg in ("1H", "1Q"):
            p = projection()
            home, push_h, _, _ = m.price_game_market(
                {"market": f"{seg}_ML", "selection": "H", "line": ""}, p)
            away, push_a, _, _ = m.price_game_market(
                {"market": f"{seg}_ML", "selection": "A", "line": ""}, p)
            self.assertTrue(all(math.isfinite(q) and 0 <= q <= 1
                                for q in (home, away, push_h, push_a)))
            self.assertGreater(push_h, 0.02)
            self.assertAlmostEqual(push_h, push_a, places=12)
            self.assertAlmostEqual(home + away + push_h, 1, places=11)

    def test_period_ties_not_discarded_at_zero_mean(self):
        for seg in ("1H", "1Q"):
            home, push, _, _ = m.price_game_market(
                {"market": f"{seg}_ML", "selection": "H", "line": ""},
                projection(0.0))
            self.assertAlmostEqual(home, (1 - push) / 2, places=11)
            self.assertGreater(push, 0)

    def test_fullgame_has_overtime_and_no_model_push(self):
        home, push_h, _, _ = m.price_game_market(
            {"market": "ML", "selection": "H", "line": ""}, projection())
        away, push_a, _, _ = m.price_game_market(
            {"market": "ML", "selection": "A", "line": ""}, projection())
        self.assertEqual(push_h, 0)
        self.assertEqual(push_a, 0)
        self.assertAlmostEqual(home + away, 1, places=12)


if __name__ == "__main__":
    unittest.main()
