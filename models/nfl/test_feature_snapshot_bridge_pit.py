"""Synthetic adapter tests, including fail-closed exact team and time joins."""
from copy import deepcopy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from feature_snapshot_bridge_pit import snapshots, main
from score_walkforward_pit import REPO_ROOT
from score_walkforward_pit import walkforward


HASH = "sha256:" + "a" * 64


def ratings():
    return {
        "status": "PAPER_HOLD_0U",
        "approved_stake_u": 0,
        "asof_utc": "2026-11-12T18:00:00Z",
        "source_observed_utc": "2026-11-12T17:00:00Z",
        "units": {
            "pass": {
                "offense_above_average_epa": {"SEA": 0.2, "LV": -0.1},
                "defense_allowed_above_average_epa": {"SEA": -0.15, "LV": 0.05},
            },
            "rush": {
                "offense_above_average_epa": {"SEA": 0.1, "LV": -0.05},
                "defense_allowed_above_average_epa": {"SEA": -0.02, "LV": 0.09},
            },
        },
    }


def event():
    return {
        "game_id": "2026_LV_SEA",
        "home_team": "SEA",
        "away_team": "LV",
        "kickoff_utc": "2026-11-15T19:00:00Z",
        "forecast_asof_utc": "2026-11-15T18:00:00Z",
    }


class ExactEPAFeatureBridgeTests(unittest.TestCase):
    def test_exact_mapping_and_defense_sign(self):
        row = snapshots(ratings(), [event()], ratings_sha256=HASH)[0]
        self.assertEqual(row["home_off_pass"], 0.2)
        self.assertEqual(row["home_def_allow_pass"], -0.15)
        self.assertEqual(row["away_def_allow_rush"], 0.09)
        self.assertEqual(row["epa_ratings_sha256"], HASH)
        self.assertEqual(row["source_observed_utc"], "2026-11-12T17:00:00Z")
        result = walkforward([row], [], min_train_games=2)
        self.assertEqual(result["predictions"][0]["status"], "PAPER_HOLD_0U")
        self.assertIsNone(result["predictions"][0]["projected_home_score"])

    def test_future_rating_cannot_reprice_past_frozen_matchup(self):
        rate = ratings()
        rate["asof_utc"] = "2026-11-15T18:30:00Z"
        with self.assertRaisesRegex(ValueError, "RATINGS_OR_FREEZE_LOOKAHEAD"):
            snapshots(rate, [event()], ratings_sha256=HASH)

    def test_source_after_rating_creation_refused(self):
        rate = ratings()
        rate["source_observed_utc"] = "2026-11-12T19:00:00Z"
        with self.assertRaisesRegex(ValueError, "RATINGS_SOURCE_AFTER_RATING_TIME"):
            snapshots(rate, [event()], ratings_sha256=HASH)

    def test_missing_team_has_no_fuzzy_fallback(self):
        e = event()
        e["home_team"] = "Seahawks"
        with self.assertRaisesRegex(ValueError, "TEAM_NOT_IN_FROZEN_RATINGS"):
            snapshots(ratings(), [e], ratings_sha256=HASH)

    def test_duplicate_events_refused(self):
        e = event()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_EMPTY_EVENT_ID"):
            snapshots(ratings(), [e, deepcopy(e)], ratings_sha256=HASH)

    def test_bad_hash_and_invalid_unit_block(self):
        with self.assertRaisesRegex(ValueError, "RATINGS_SHA_REQUIRED"):
            snapshots(ratings(), [event()], ratings_sha256="hash")
        rate = ratings()
        rate["units"].pop("rush")
        with self.assertRaisesRegex(ValueError, "PASS_AND_RUSH_RATINGS_REQUIRED"):
            snapshots(rate, [event()], ratings_sha256=HASH)

    def test_no_zero_fill_for_missing_or_invalid_rating(self):
        rate = ratings()
        rate["units"]["pass"]["offense_above_average_epa"].pop("LV")
        with self.assertRaisesRegex(ValueError, "TEAM_NOT_IN_FROZEN_RATINGS"):
            snapshots(rate, [event()], ratings_sha256=HASH)
        rate = ratings()
        rate["units"]["pass"]["offense_above_average_epa"]["LV"] = "NaN"
        with self.assertRaisesRegex(ValueError, "NONFINITE_RATING"):
            snapshots(rate, [event()], ratings_sha256=HASH)

    def test_dont_accept_promoted_upstream_status(self):
        rate = ratings()
        rate["approved_stake_u"] = 1
        with self.assertRaisesRegex(ValueError, "UNSAFE_UPSTREAM_RATINGS_STAKE"):
            snapshots(rate, [event()], ratings_sha256=HASH)
        rate = ratings()
        rate["status"] = "PRODUCTION"
        with self.assertRaisesRegex(ValueError, "RATINGS_STATUS_NOT_RESEARCH"):
            snapshots(rate, [event()], ratings_sha256=HASH)

    def test_bridge_cli_refuses_public_source_and_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            cases = (
                (str(REPO_ROOT / "rating_source.json"), str(private / "out.csv")),
                (str(private / "ratings.json"), str(REPO_ROOT / "models" / "nfl" / "private_features.csv")),
            )
            for ratings_path, output in cases:
                argv = ["feature_snapshot_bridge_pit.py", "--ratings", ratings_path,
                        "--events", str(private / "events.json"), "--out", output]
                with patch("sys.argv", argv):
                    with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                        main()

    def test_after_kickoff_freeze_refused(self):
        e = event()
        e["forecast_asof_utc"] = e["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "RATINGS_OR_FREEZE_LOOKAHEAD"):
            snapshots(ratings(), [e], ratings_sha256=HASH)


if __name__ == "__main__":
    unittest.main()
