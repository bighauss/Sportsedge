"""Synthetic-only test fixtures for the NFL prop market-baseline audit."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prop_baseline_compare as C


def row(game, sel, pm, pk, qualifies=False, status="negative_ev", kind="prop"):
    return {
        "game": game, "selection": sel, "model_p": pm, "market_p": pk,
        "qualifies": qualifies, "status": status, "kind": kind,
    }


class Census(unittest.TestCase):
    def test_pending_and_rejected_counted_not_scored(self):
        rs = [
            row("A@B", "x", .6, .5),
            row("A@B", "y", .6, .5),
            row("A@B", "z", .6, .5, status="rejected_input"),
            row("A@B", "g", .6, .5, kind="game"),
        ]
        rep = C.compare(rs, {("A@B", "x"): True})["priced"]
        self.assertEqual(rep["census"]["attempted"], 3)
        self.assertEqual(rep["census"]["graded"], 1)
        self.assertEqual(rep["census"]["pending"], 1)
        self.assertEqual(rep["census"]["blocked"], 1)
        self.assertEqual(rep["n"], 1)

    def test_boolean_result_only_for_binary_settlement(self):
        with self.assertRaisesRegex(ValueError, "RESULT_MUST_BE_BOOL"):
            C.compare([row("A@B", "x", .6, .5)],
                      {("A@B", "x"): 0})

    def test_pushed_and_void_outcomes_not_scored_as_misses(self):
        rows = [row("A@B", "x", .6, .5),
                row("A@B", "y", .6, .5),
                row("A@B", "z", .6, .5)]
        r = C.compare(rows, {("A@B", "x"): True,
                             ("A@B", "y"): "PUSH",
                             ("A@B", "z"): "VOID"})["priced"]
        self.assertEqual(r["census"]["graded"], 1)
        self.assertEqual(r["census"]["push"], 1)
        self.assertEqual(r["census"]["void"], 1)
        self.assertEqual(r["census"]["attempted"], 3)

    def test_invalid_probability_and_inf_not_graded(self):
        rs = [row("A@B", "x", float("nan"), .5),
              row("A@B", "y", .6, float("inf")),
              row("A@B", "z", .6, .5)]
        r = C.compare(rs, {("A@B", "x"): True, ("A@B", "y"): True,
                            ("A@B", "z"): False})["priced"]
        self.assertEqual(r["census"]["invalid_prob"], 2)
        self.assertEqual(r["n"], 1)

    def test_collision_does_not_duplicate_a_single_result(self):
        rs = [row("A@B", "x", .6, .5),
              row("A@B", "x", .7, .5),
              row("A@B", "y", .3, .5)]
        r = C.compare(rs, {("A@B", "x"): True, ("A@B", "y"): False})["priced"]
        self.assertEqual(r["census"]["ambiguous_identity"], 2)
        self.assertEqual(r["census"]["graded"], 1)
        self.assertEqual(r["census"]["attempted"], 3)

    def test_on_card_duplicate_hidden_outside_cohort_still_blocks(self):
        rs = [row("A@B", "x", .7, .5, qualifies=True),
              row("A@B", "x", .6, .5, qualifies=False)]
        r = C.compare(rs, {("A@B", "x"): True})
        self.assertEqual(r["priced"]["census"]["ambiguous_identity"], 2)
        self.assertEqual(r["on_card"]["census"]["ambiguous_identity"], 1)
        self.assertEqual(r["on_card"]["census"]["graded"], 0)

    def test_bad_identity_unresolvable(self):
        r = C.compare([row("A@B", "", .6, .5)], {})["priced"]
        self.assertEqual(r["census"]["ambiguous_identity"], 1)
        self.assertEqual(r["status"], "NO_GRADED_ROWS")

    def test_no_rows(self):
        self.assertEqual(C.compare([], {})["on_card"]["status"],
                         "NO_GRADED_ROWS")

    def test_on_card_subset(self):
        rs = [row("A@B", "x", .8, .5, qualifies=True),
              row("C@D", "y", .2, .5)]
        rep = C.compare(rs, {("A@B", "x"): True, ("C@D", "y"): False})
        self.assertEqual(rep["priced"]["n"], 2)
        self.assertEqual(rep["on_card"]["n"], 1)
        self.assertEqual(rep["on_card"]["status"],
                         "INSUFFICIENT_GAMES_OR_ROWS_FOR_CI")


class Scoring(unittest.TestCase):
    def test_identical_rows_brier_and_log_loss(self):
        rs = [row("A@B", "x", .8, .5), row("C@D", "y", .2, .5)]
        r = C.compare(rs, {("A@B", "x"): True, ("C@D", "y"): False})["priced"]
        self.assertAlmostEqual(r["brier_model"], .04)
        self.assertAlmostEqual(r["brier_market"], .25)
        self.assertLess(r["logloss_diff"], 0)
        self.assertFalse(r["model_validated"])

    def test_tiny_sample_never_claims_significant_better(self):
        rs = [row("G1", "a", .999, .5), row("G2", "b", .999, .5)]
        r = C.compare(rs, {("G1", "a"): True, ("G2", "b"): True})["priced"]
        self.assertEqual(r["status"], "INSUFFICIENT_GAMES_OR_ROWS_FOR_CI")
        self.assertNotIn("brier_diff_ci95_game_cluster", r)

    def test_market_truth_flags_market_better_with_sufficient_games(self):
        rng = random.Random(1)
        rs, outcomes = [], {}
        for g in range(60):
            shift = rng.choice((-.12, .12))
            for i in range(5):
                pk = rng.uniform(.3, .6)
                rs.append(row(f"G{g}", f"p{i}",
                              min(.97, max(.03, pk + shift)), pk))
                outcomes[(f"G{g}", f"p{i}")] = rng.random() < pk
        r = C.compare(rs, outcomes, reps=500)["priced"]
        self.assertEqual(r["status"], "MARKET_BETTER_RESEARCH_ONLY")
        self.assertGreater(r["brier_diff_ci95_game_cluster"][0], 0)

    def test_cluster_bootstrap_reproducible(self):
        rs = [row(f"G{g}", "x", .6, .5) for g in range(5)]
        outcome = {(f"G{g}", "x"): g % 2 == 0 for g in range(5)}
        a = C.compare(rs, outcome, reps=200, seed=3, min_games=2,
                      min_rows=1)["priced"]["brier_diff_ci95_game_cluster"]
        b = C.compare(rs, outcome, reps=200, seed=3, min_games=2,
                      min_rows=1)["priced"]["brier_diff_ci95_game_cluster"]
        self.assertEqual(a, b)

    def test_invalid_bootstrap_configuration_refused(self):
        with self.assertRaises(ValueError):
            C.compare([], {}, reps=10)
        with self.assertRaises(ValueError):
            C.compare([], {}, min_games=1)

    def test_no_official_count_or_fake_source_verification(self):
        r = C.compare([row("A@B", "x", .5, .5)], {})["priced"]
        self.assertEqual(r["official_counted"], 0)
        self.assertEqual(r["approved_stake_u"], 0)
        self.assertFalse(r["source_authenticated"])
        self.assertFalse(r["calibration_verified"])


if __name__ == "__main__":
    unittest.main()
