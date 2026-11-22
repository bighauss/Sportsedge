import random
import unittest

import prop_baseline_compare as C


def row(game, sel, pm, pk, qualifies=False, status="negative_ev", kind="prop"):
    return dict(game=game, selection=sel, model_p=pm, market_p=pk, qualifies=qualifies,
                status=status, kind=kind)


class Census(unittest.TestCase):
    def test_pending_and_rejected_never_graded_as_miss(self):
        rows = [row("A@B", "x", .6, .5), row("A@B", "y", .6, .5),
                row("A@B", "z", .6, .5, status="rejected_input"),
                row("A@B", "g", .6, .5, kind="game")]
        r = C.compare(rows, {("A@B", "x"): True}, reps=50)["priced"]
        self.assertEqual(r["census"], dict(attempted=2, graded=1, pending=1, invalid_prob=0))
        self.assertEqual(r["n"], 1)

    def test_non_bool_result_refused(self):
        with self.assertRaises(ValueError):
            C.compare([row("A@B", "x", .6, .5)], {("A@B", "x"): 0}, reps=10)

    def test_invalid_probability_counted_not_scored(self):
        rows = [row("A@B", "x", float("nan"), .5), row("A@B", "y", .6, .5)]
        r = C.compare(rows, {("A@B", "x"): True, ("A@B", "y"): False}, reps=10)["priced"]
        self.assertEqual(r["census"]["invalid_prob"], 1)
        self.assertEqual(r["n"], 1)

    def test_no_rows(self):
        self.assertEqual(C.compare([], {})["on_card"]["status"], "NO_GRADED_ROWS")


class Scoring(unittest.TestCase):
    def test_identical_rows_and_known_brier(self):
        rows = [row("A@B", "x", .8, .5), row("C@D", "y", .2, .5)]
        r = C.compare(rows, {("A@B", "x"): True, ("C@D", "y"): False}, reps=200)["priced"]
        self.assertAlmostEqual(r["brier_model"], .04)
        self.assertAlmostEqual(r["brier_market"], .25)
        self.assertLess(r["brier_diff"], 0)

    def test_on_card_cohort_is_subset(self):
        rows = [row("A@B", "x", .8, .5, qualifies=True), row("C@D", "y", .2, .5)]
        r = C.compare(rows, {("A@B", "x"): True, ("C@D", "y"): False}, reps=50)
        self.assertEqual(r["on_card"]["n"], 1)
        self.assertEqual(r["on_card"]["status"], "INSUFFICIENT_GAMES_FOR_CI")

    def test_market_truth_flags_market_better(self):
        # outcomes drawn from the market probability; model adds a shared per-game shift
        rng = random.Random(1)
        rows, res = [], {}
        for g in range(60):
            shift = rng.choice((-.12, .12))
            for i in range(5):
                pk = rng.uniform(.3, .6)
                rows.append(row(f"G{g}", f"p{i}", min(.97, max(.03, pk + shift)), pk))
                res[(f"G{g}", f"p{i}")] = rng.random() < pk
        r = C.compare(rows, res, reps=500)["priced"]
        self.assertEqual(r["status"], "MARKET_BETTER")

    def test_cluster_bootstrap_is_deterministic(self):
        rows = [row(f"G{g}", "x", .6, .5) for g in range(5)]
        res = {(f"G{g}", "x"): g % 2 == 0 for g in range(5)}
        a = C.compare(rows, res, reps=100, seed=3)["priced"]["brier_diff_ci95_game_cluster"]
        b = C.compare(rows, res, reps=100, seed=3)["priced"]["brier_diff_ci95_game_cluster"]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
