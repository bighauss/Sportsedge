"""Synthetic Gate C red-team for final-availability leakage and game cohorts."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from sportsedge.markets.chronological_calibration import (
    FrozenGame, walk_forward_score_audit,
)

BASE = datetime(2025, 8, 1, 16, tzinfo=timezone.utc)
HASH = "sha256:" + "a"*64


def games(count=110):
    items=[]
    for i in range(count):
        start=BASE + timedelta(days=i)
        items.append(FrozenGame(
            event_id=f"E{i:04d}",sport="CBB",
            start_at_utc=start,
            features_asof_utc=start-timedelta(hours=3),
            fitted_until_utc=start-timedelta(days=2),
            projection_home=72.0, projection_away=68.0,
            final_home=70+(i%11), final_away=63+(i%7),
            forecast_sha256=HASH,
            final_published_utc=start+timedelta(hours=3),
            final_captured_utc=start+timedelta(hours=4),
        ))
    return items


class OriginalResultChronology(unittest.TestCase):
    def test_first_fold_uses_only_final_results_available_before_holdout(self):
        data=games()
        r=walk_forward_score_audit(data,minimum_training=50,
                                   holdout_per_fold=10,minimum_folds=3)
        self.assertEqual(r["status"],"RESEARCH_HOLDOUT_REVIEW")
        self.assertGreaterEqual(r["completed_folds"],3)
        self.assertEqual(r["input_games"],110)
        self.assertEqual(r["official_counted"],0)
        self.assertEqual(r["approved_stake_u"],0)
        self.assertFalse(r["independent_source_attested"])
        self.assertEqual(r["folds"][0]["training_n"],50)
        for f in r["folds"]:
            self.assertLess(f["train_latest_final_captured_utc"],
                            f["evaluation_starts_utc"])
            self.assertEqual(f["holdout_n"],10)

    def test_late_final_excluded_until_available(self):
        data=games()
        # A historical game can start earlier yet publish 60 days later.
        late=data[0]
        data[0]=replace(late,final_published_utc=BASE+timedelta(days=61),
                        final_captured_utc=BASE+timedelta(days=62))
        r=walk_forward_score_audit(data,minimum_training=50,
                                   holdout_per_fold=10,minimum_folds=3)
        self.assertEqual(r["status"],"RESEARCH_HOLDOUT_REVIEW")
        self.assertTrue(r["folds"])
        first=r["folds"][0]
        self.assertEqual(first["training_n"],50)
        self.assertGreater(first["evaluation_starts_utc"],
                           (BASE+timedelta(days=50)).isoformat())
        for f in r["folds"]:
            self.assertLess(f["train_latest_final_captured_utc"],
                            f["evaluation_starts_utc"])

    def test_no_final_timestamp_means_no_valid_calibration(self):
        data=games()
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FINAL_AVAILABILITY_REQUIRED"):
            replace(data[0],final_captured_utc=None)
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FINAL_AVAILABILITY_REQUIRED"):
            replace(data[0],final_published_utc=None)

    def test_future_final_capture_and_backdated_receipts_rejected(self):
        data=games()
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FINAL_CHRONOLOGY_INVALID"):
            replace(data[0],final_captured_utc=data[0].start_at_utc-timedelta(minutes=1))
        with self.assertRaisesRegex(ValueError,"ORIGINAL_FINAL_CHRONOLOGY_INVALID"):
            replace(data[0],final_published_utc=data[0].final_captured_utc+timedelta(seconds=1))

    def test_same_start_cohort_not_split_into_training_or_multiple_folds(self):
        data=games(122)
        shared=BASE+timedelta(days=69)
        data[59:72]=[
            replace(g,start_at_utc=shared,
                    features_asof_utc=shared-timedelta(hours=3),
                    fitted_until_utc=shared-timedelta(days=2),
                    final_published_utc=shared+timedelta(hours=3),
                    final_captured_utc=shared+timedelta(hours=4))
            for g in data[59:72]
        ]
        r=walk_forward_score_audit(data,minimum_training=50,
                                   holdout_per_fold=10,minimum_folds=3)
        covered=[f for f in r["folds"] if
                 f["evaluation_starts_utc"]<=shared.isoformat()<=
                 f["evaluation_ends_utc"]]
        self.assertEqual(len(covered),1)
        self.assertGreaterEqual(covered[0]["holdout_n"],13)

    def test_duplicate_case_and_space_event_ids_rejected(self):
        data=games()
        data[1]=replace(data[1],event_id=" E0000 ")
        with self.assertRaisesRegex(ValueError,"DUPLICATE_EVENTS_OR_MIXED_SPORT"):
            walk_forward_score_audit(data,minimum_training=50,
                                     holdout_per_fold=10,minimum_folds=3)

    def test_no_model_promotion_even_for_perfect_synthetic_scores(self):
        r=walk_forward_score_audit(games(),minimum_training=50,
                                   holdout_per_fold=10,minimum_folds=3)
        self.assertEqual(r["official_counted"],0)
        self.assertEqual(r["approved_stake_u"],0)
        self.assertIn("NO_INDEPENDENT_SOURCE_ATTESTATION_FROM_THIS_MODULE",r["reasons"])

    def test_not_enough_folds_retains_all_input_census(self):
        data=games(65)
        r=walk_forward_score_audit(data,minimum_training=50,
                                  holdout_per_fold=10,minimum_folds=3)
        self.assertEqual(r["input_games"],65)
        self.assertEqual(r["status"],"INSUFFICIENT_CHRONOLOGICAL_FOLDS")
        self.assertEqual(r["completed_folds"],1)


if __name__=="__main__":
    unittest.main()
