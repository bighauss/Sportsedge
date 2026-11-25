import unittest
from dataclasses import replace
from cbb_player_residual_pricing import Forecast, Observation, predictive_draws, price

ASOF = "2026-11-25T12:00:00Z"
MEANS = {"PTS": 12, "REB": 5, "AST": 3, "3PM": 2}
TARGET = Forecast("target", "t", "p", "2026-11-25T20:00:00Z",
                  "2026-11-25T10:00:00Z", MEANS, "v1")


def sample(i, actual):
    f = Forecast(str(i), "t", "p", f"2026-11-{i:02d}T20:00:00Z",
                 f"2026-11-{i:02d}T10:00:00Z", MEANS, "v1")
    return Observation(f, f"2026-11-{i:02d}T23:00:00Z", actual, True)


class PlayerPricing(unittest.TestCase):
    def setUp(self):
        self.rows = [sample(1, {"PTS": 15, "REB": 7, "AST": 3, "3PM": 2}),
                     sample(2, {"PTS": 9, "REB": 3, "AST": 3, "3PM": 1})]

    def draws(self, rows=None):
        return predictive_draws(TARGET, self.rows if rows is None else rows,
                                as_of_utc=ASOF, min_samples=2)

    def test_joint_combos_and_push(self):
        d = self.draws()
        self.assertEqual(d["draws"], ((15, 7, 3, 2), (9, 3, 3, 1)))
        self.assertEqual(price(d, "PRA", "OU", 25)["p_push"], 0.5)
        self.assertEqual(price(d, "PRA", "AT_LEAST", 25)["p_a"], 0.5)
        for s in ("PTS", "REB", "AST", "3PM", "PRA", "PR", "PA", "RA"):
            for kind in ("OU", "AT_LEAST"):
                p = price(d, s, kind, 5)
                self.assertAlmostEqual(p["p_a"] + p["p_b"] + p["p_push"], 1)
                self.assertEqual(p["approved_stake_u"], 0)

    def test_no_future_other_player_or_dnp(self):
        row = self.rows[1]
        variants = [replace(row, observed_final_utc=ASOF),
                    replace(row, forecast=replace(row.forecast, player_id="other")),
                    replace(row, participated=False)]
        for v in variants:
            with self.assertRaisesRegex(ValueError, "INSUFFICIENT_PRIOR"):
                self.draws([self.rows[0], v])

    def test_duplicate_and_target_excluded(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            self.draws(self.rows + [self.rows[0]])
        with self.assertRaisesRegex(ValueError, "TARGET_IN_HISTORY"):
            self.draws(self.rows + [replace(self.rows[0], forecast=TARGET)])

    def test_bad_clock_and_stat(self):
        with self.assertRaisesRegex(ValueError, "FINAL_NOT_AFTER_TIP"):
            self.draws([replace(self.rows[0], observed_final_utc="2026-11-01T19:00:00Z"), self.rows[1]])
        with self.assertRaisesRegex(ValueError, "THREES_EXCEED_POINTS"):
            self.draws([replace(self.rows[0], actual={"PTS": 2, "REB": 2, "AST": 2, "3PM": 2}), self.rows[1]])
        with self.assertRaisesRegex(ValueError, "INVALID_CONTRACT"):
            price(self.draws(), "PTS", "AT_LEAST", 2.5)


if __name__ == "__main__":
    unittest.main()
