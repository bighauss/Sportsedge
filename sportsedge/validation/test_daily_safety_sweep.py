"""Fail-closed safety sweep of paper release matrix."""
import unittest
from copy import deepcopy

from sportsedge.validation.daily_safety_sweep import FAMILIES, SPORTS, inspect_matrix


def matrix():
    return {"schema": "sportsedge-market-release-matrix-v1",
            "markets": [{"sport": s, "market_family": f, "release_state": "PAPER_0U",
                         "gates": {g: False for g in "ABCDE"}, "approved_stake_u": 0,
                         "official_counted": 0, "reasons": ["A_UNVERIFIED"]}
                        for s in SPORTS for f in FAMILIES]}


class SafetySweepTest(unittest.TestCase):
    def test_normal_paper_matrix(self):
        self.assertEqual(inspect_matrix(matrix())["status"], "PAPER_0U_SAFE_MATRIX")

    def test_missing_sport_family_blocked(self):
        m = matrix()
        m["markets"].pop()
        self.assertEqual(inspect_matrix(m)["status"], "BLOCK")

    def test_declared_all_gates_still_not_official(self):
        m = matrix()
        m["markets"][0]["release_state"] = "OFFICIAL"
        m["markets"][0]["gates"] = {g: True for g in "ABCDE"}
        self.assertIn("UNSUPPORTED_OFFICIAL_RELEASE", str(inspect_matrix(m)["issues"]))

    def test_nonzero_approved_stake_rejected(self):
        m = matrix()
        m["markets"][0]["approved_stake_u"] = 0.25
        self.assertIn("NONZERO_STAKE_FORBIDDEN", str(inspect_matrix(m)["issues"]))

    def test_duplicate_market_rejected(self):
        m = matrix()
        m["markets"].append(deepcopy(m["markets"][0]))
        self.assertIn("DUPLICATE_MARKET", str(inspect_matrix(m)["issues"]))


if __name__ == "__main__":
    unittest.main()
