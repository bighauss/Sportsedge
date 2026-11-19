"""Synthetic-only PIT player pair tests: no real data or wagering claims."""
import copy
from datetime import datetime, timedelta, timezone
import unittest

from research.prop_pairs.joint_prop_audit import evaluate


def t(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


B = datetime(2026, 11, 18, 16, tzinfo=timezone.utc)


def row(game="g1", **updates):
    a = {"player_id": "p1", "team_id": "A", "market": "PLAYER_PROP",
         "stat": "REC_YDS", "line": "60.5", "side": "OVER"}
    b = {"player_id": "p2", "team_id": "A", "market": "PLAYER_PROP",
         "stat": "RECEPTIONS", "line": "4.5", "side": "OVER"}
    original = {
        "sport": "NFL", "event_id": game, "period": "FG",
        "settlement": "INCLUDES_OT", "a": a, "b": b,
        "pa": 0.5, "pb": 0.5, "ya": 1, "yb": 1,
        "model_fitted_until_utc": t(B-timedelta(days=1)),
        "rules_effective_utc": t(B-timedelta(days=2)),
        "a_published_utc": t(B-timedelta(hours=3)),
        "a_captured_utc": t(B-timedelta(hours=2)),
        "b_published_utc": t(B-timedelta(hours=3)),
        "b_captured_utc": t(B-timedelta(hours=2)),
        "forecast_utc": t(B), "tipoff_utc": t(B+timedelta(hours=2)),
        "final_published_utc": t(B+timedelta(hours=7)),
        "final_captured_utc": t(B+timedelta(hours=8)),
        "a_source_sha256": "a"*64, "b_source_sha256": "b"*64,
        "model_sha256": "c"*64, "rules_sha256": "e"*64,
        "universe_sha256": "f"*64, "universe_complete_claim": True,
        "final_sha256": "d"*64
    }
    original.update(updates)
    return original


class JointPropPITTests(unittest.TestCase):
    def test_independence_brier_without_joint_candidate(self):
        z = evaluate([row("g1"), row("g2", ya=0)])
        self.assertEqual(z["games"], 2)
        self.assertAlmostEqual(z["independence_brier"], (0.75**2+0.25**2)/2)
        self.assertIsNone(z["joint_model_brier"])
        self.assertIsNone(z["delta_ci95"])
        self.assertFalse(z["certified"])
        self.assertFalse(z["source_authenticated"])
        self.assertEqual(z["approved_stake_u"], 0)

    def test_joint_brier_and_frechet_bound(self):
        z = evaluate([row(joint_p=0.3)])
        self.assertAlmostEqual(z["joint_model_brier"], 0.49)
        with self.assertRaisesRegex(ValueError, "INCOHERENT_JOINT_PROBABILITY"):
            evaluate([row(joint_p=0.8)])

    def test_duplicate_event_fails_whole_sample(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_EVENT"):
            evaluate([row(), row()])

    def test_missing_final_or_feature_receipt_blocks(self):
        for key in ("b_source_sha256", "final_sha256", "a_captured_utc", "forecast_utc"):
            e = row()
            del e[key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "EXACT_PIT_PAIR_SCHEMA"):
                evaluate([e])
        e = row(final_sha256="F"*64)
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_SHA_SHAPE"):
            evaluate([e])

    def test_future_feature_and_result_lookahead(self):
        e = row(a_captured_utc=t(B+timedelta(minutes=3)))
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            evaluate([e])
        e = row(model_fitted_until_utc=t(B+timedelta(minutes=1)))
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            evaluate([e])
        e = row(final_published_utc=t(B+timedelta(hours=1)))
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            evaluate([e])
        e = row(final_captured_utc=t(B+timedelta(hours=3)))
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            evaluate([e])

    def test_no_mixed_sport_period_pair_or_line(self):
        with self.assertRaisesRegex(ValueError, "MIXED_SPORT_PERIOD"):
            evaluate([row("g1"), row("g2", sport="NBA")])
        with self.assertRaisesRegex(ValueError, "PERIOD_SETTLEMENT"):
            evaluate([row("g1", period="1H")])
        e = row("g2", a=dict(row("g2")["a"], line="61.5"))
        with self.assertRaisesRegex(ValueError, "MIXED_SPORT_PERIOD"):
            evaluate([row("g1"), e])

    def test_leg_swap_symmetry(self):
        e = row(pa=0.2, pb=0.7, ya=1, yb=0, joint_p=0.1)
        swapped = copy.deepcopy(e)
        for x,y in (("a","b"), ("pa","pb"), ("ya","yb"),
                    ("a_source_sha256","b_source_sha256"),
                    ("a_published_utc","b_published_utc"),
                    ("a_captured_utc","b_captured_utc")):
            swapped[x],swapped[y] = swapped[y],swapped[x]
        self.assertEqual(evaluate([e]), evaluate([swapped]))

    def test_missing_outcome_and_pushes_refused(self):
        for y in (None, "P", 0.5, True):
            with self.subTest(value=y), self.assertRaisesRegex(ValueError, "INVALID_OR_PUSHABLE_SETTLEMENT"):
                evaluate([row(ya=y)])

    def test_partial_joint_forecasts_refused(self):
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_JOINT"):
            evaluate([row("g1", joint_p=0.3), row("g2")])

    def test_probability_and_line_invalid(self):
        with self.assertRaisesRegex(ValueError, "INVALID_PROBABILITY"):
            evaluate([row(pa=float("nan"))])
        with self.assertRaisesRegex(ValueError, "INVALID_PROP_LINE"):
            evaluate([row(a=dict(row()["a"], line="not-a-line"))])
        with self.assertRaisesRegex(ValueError, "EXACT_LEG_IDENTITY"):
            evaluate([row(a={"player_id":"p1"})])

    def test_observed_covariance_not_joint_probability(self):
        z = evaluate([row("g1"), row("g2", ya=0, yb=0)])
        self.assertAlmostEqual(z["observed_joint_rate"], 0.5)
        self.assertAlmostEqual(z["observed_bernoulli_covariance"], 0.25)

    def test_large_sample_ci_not_certification(self):
        rows = [row(f"g{i}", joint_p=0.25, ya=int(i%2==0), yb=int(i%3==0))
                for i in range(35)]
        z = evaluate(rows)
        self.assertEqual(z["games"], 35)
        self.assertEqual(len(z["delta_ci95"]), 2)
        self.assertEqual(z["sample_warning"], "EXPLORATORY_SAMPLE")
        self.assertFalse(z["certified"])
        self.assertEqual(z["official_counted"], 0)

    def test_no_retroactive_qualification_or_weak_universe(self):
        e = row(rules_effective_utc=t(B+timedelta(minutes=1)))
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            evaluate([e])
        e = row(universe_complete_claim=False)
        with self.assertRaisesRegex(ValueError, "FULL_ORIGINAL_SELECTION_UNIVERSE"):
            evaluate([e])
        e = row(universe_sha256="missing")
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_SHA_SHAPE"):
            evaluate([e])

    def test_no_mixed_model_or_rule_versions_in_one_pair_backtest(self):
        e1 = row("g1")
        e2 = row("g2", model_sha256="1"*64)
        with self.assertRaisesRegex(ValueError, "MIXED_SPORT_PERIOD"):
            evaluate([e1, e2])
        e2 = row("g2", rules_sha256="2"*64)
        with self.assertRaisesRegex(ValueError, "MIXED_SPORT_PERIOD"):
            evaluate([e1, e2])

    def test_no_data_retains_denominator_and_no_authentication(self):
        z = evaluate([])
        self.assertEqual(z["games"], 0)
        self.assertIsNone(z["pair"])
        self.assertEqual(z["approved_stake_u"], 0)
        with self.assertRaisesRegex(ValueError, "FULL_PAIRED_LEDGER"):
            evaluate(iter([row()]))


if __name__ == "__main__":
    unittest.main()
