"""Unit test for the CBB independent projection freeze adapter."""
import unittest
import math

import cbb_independent_runner_adapter as A


class TestIndependentFreeze(unittest.TestCase):
    def test_freeze_receipt_is_hashed_and_weight_one(self):
        proj = {
            "margin": 4.2,
            "total": 148.5,
            "home_points": 76.35,
            "away_points": 72.15,
            "poss": 68.0,
        }
        rec = A.freeze_independent_receipt(proj)
        self.assertEqual(rec["blend_weight_model"], 1.0)
        self.assertEqual(len(rec["sha256"]), 64)
        self.assertFalse(rec["release_ready"])
        self.assertEqual(rec["approved_stake_u"], 0)

    def test_attach_produces_one_receipt_per_projection(self):
        projs = [
            {"margin": 3.0, "total": 140.0, "home_points": 71.5, "away_points": 68.5, "poss": 65.0},
            {"margin": -2.1, "total": 155.0, "home_points": 76.45, "away_points": 78.55, "poss": 70.0},
        ]
        receipts = A.attach_independent_receipts(projs)
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(r["sha256"] for r in receipts))

    def test_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            A.freeze_independent_receipt({"margin": float("nan"), "total": 150.0})


if __name__ == "__main__":
    unittest.main()
