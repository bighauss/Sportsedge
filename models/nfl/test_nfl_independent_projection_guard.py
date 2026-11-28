"""Unit test for NFL independent projection freeze guard."""
import unittest

import nfl_independent_projection_guard as G


class TestNFLIndependentGuard(unittest.TestCase):
    def test_freeze_produces_hash_and_labels(self):
        proj = {"margin": 3.5, "total": 45.0, "home_points": 24.25, "away_points": 20.75, "plays": 65, "pass_rate": 0.58}
        rec = G.freeze_nfl_projection(proj)
        self.assertEqual(len(rec["sha256"]), 64)
        self.assertEqual(rec["label"], "PURE_INDEPENDENT_BEFORE_ODDS")
        self.assertFalse(rec["release_ready"])
        self.assertEqual(rec["approved_stake_u"], 0)

    def test_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            G.freeze_nfl_projection({"margin": float("inf"), "total": 45.0})

    def test_attach_one_per_projection(self):
        projs = [{"margin": 1.0, "total": 42.0}, {"margin": -4.0, "total": 48.0}]
        receipts = G.attach_nfl_independent_receipts(projs)
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all("sha256" in r for r in receipts))


if __name__ == "__main__":
    unittest.main()
