"""Unit tests for CBB pure independent pricing path."""
import unittest
import math

import cbb_independent_pricing as IP
import cbbd_native_score_model as NM


class TestIndependentPricing(unittest.TestCase):
    def test_independent_config_forces_weight_one(self):
        cfg = IP.independent_config()
        self.assertEqual(cfg["blend_weight_model"], 1.0)

    def test_independent_ev_matches_native(self):
        p_win, p_push, price = 0.55, 0.0, -110
        expected = NM.ev_per_unit(p_win, p_push, price)
        self.assertAlmostEqual(IP.independent_ev(p_win, p_push, price), expected)

    def test_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            IP.independent_ev(float("nan"), 0.0, -110)

    def test_rejects_mass_exceeds_one(self):
        with self.assertRaises(ValueError):
            IP.independent_ev(0.6, 0.5, -110)

    def test_price_independent_requires_weight_one(self):
        cfg = IP.independent_config()
        cfg["blend_weight_model"] = 0.5
        proj = {"margin": 5.0, "total": 150.0, "home_points": 77.5, "away_points": 72.5}
        quote = {"market": "spread", "line": -3.5, "price_a": -110, "price_b": -110}
        with self.assertRaises(ValueError):
            IP.price_independent(proj, quote, cfg)


if __name__ == "__main__":
    unittest.main()
