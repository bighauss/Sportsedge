"""Synthetic PIT score-conversion regressions: no odds, no promoted picks."""
from datetime import datetime, timedelta, timezone
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from score_walkforward_pit import walkforward, private_evidence_path, create_private_output, REPO_ROOT, main


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def fixtures(n=12):
    start = datetime(2026, 9, 1, 20, tzinfo=timezone.utc)
    rows, outcomes = [], []
    for i in range(n):
        kickoff = start + timedelta(days=7*i)
        # Strict snapshot obtained before each historical game's own kickoff.
        rows.append({
            "game_id": "g" + str(i),
            "home_team": "SEA" if i % 2 == 0 else "LV",
            "away_team": "LV" if i % 2 == 0 else "SEA",
            "kickoff_utc": iso(kickoff),
            "forecast_asof_utc": iso(kickoff - timedelta(hours=2)),
            "source_observed_utc": iso(kickoff - timedelta(hours=4)),
            "epa_ratings_sha256": "sha256:" + ("%064x" % (i + 1)),
            "home_off_pass": str((i % 4) / 10),
            "home_def_allow_pass": str((i % 3) / 20),
            "home_off_rush": str((i % 2) / 15),
            "home_def_allow_rush": str((i % 5) / 100),
            "away_off_pass": str((i % 6) / 15),
            "away_def_allow_pass": str((i % 3) / 10),
            "away_off_rush": str((i % 7) / 12),
            "away_def_allow_rush": str((i % 5) / 20),
        })
        outcomes.append({
            "game_id": "g" + str(i),
            "home_score": str(16 + 2 * (i % 7)),
            "away_score": str(13 + 3 * (i % 4)),
            "final_utc": iso(kickoff + timedelta(hours=4)),
            "result_available_utc": iso(kickoff + timedelta(hours=6)),
        })
    return rows, outcomes


def get(rows, outcomes, **kwargs):
    return walkforward(rows, outcomes,
                       ridge=kwargs.pop("ridge", 25.0),
                       min_train_games=kwargs.pop("min_train_games", 3),
                       **kwargs)


class PointInTimeScoreWalkforwardTests(unittest.TestCase):
    def test_chronology_and_paper_scoring(self):
        rows, outcomes = fixtures()
        result = get(rows, outcomes)
        self.assertEqual(result["withheld_insufficient_history"], 3)
        self.assertEqual(result["score_metrics"]["fully_walkforward_evaluated_games"], 9)
        self.assertEqual(result["predictions"][3]["training_games"], 3)
        self.assertIsNotNone(result["predictions"][3]["projected_home_score"])
        self.assertEqual(result["predictions"][3]["approved_stake_u"], 0)
        self.assertEqual(result["predictions"][3]["status"], "PAPER_HOLD_0U")
        self.assertIsNone(result["predictions"][3]["expected_value"])
        self.assertIsNone(result["predictions"][3]["win_probability"])
        self.assertIsNotNone(result["score_metrics"]["model_score_rmse"])

    def test_this_game_score_never_in_own_forecast(self):
        rows, outcomes = fixtures()
        prior = get(rows, outcomes)
        changed = copy.deepcopy(outcomes)
        changed[8]["home_score"] = "400"
        changed[8]["away_score"] = "200"
        new = get(rows, changed)
        self.assertEqual(prior["predictions"][8], new["predictions"][8])
        self.assertNotEqual(prior["predictions"][9]["projected_home_score"],
                            new["predictions"][9]["projected_home_score"])

    def test_future_outcome_does_not_change_earlier_scores(self):
        rows, outcomes = fixtures()
        original = get(rows, outcomes)
        changed = copy.deepcopy(outcomes)
        changed[-1]["home_score"] = "200"
        revised = get(rows, changed)
        self.assertEqual(original["predictions"], revised["predictions"])

    def test_late_result_cannot_enter_training_even_when_played(self):
        rows, outcomes = fixtures()
        previous = get(rows, outcomes)
        delayed = copy.deepcopy(outcomes)
        delayed[2]["result_available_utc"] = rows[9]["kickoff_utc"]
        altered = get(rows, delayed)
        self.assertEqual(previous["predictions"][3]["training_games"], 3)
        self.assertEqual(altered["predictions"][3]["training_games"], 2)
        self.assertIsNone(altered["predictions"][3]["projected_home_score"])
        self.assertEqual(altered["predictions"][9]["training_games"], 8)

    def test_missing_score_keeps_prediction_but_no_grade(self):
        rows, outcomes = fixtures()
        ungraded = get(rows, outcomes[:-1])
        self.assertIsNotNone(ungraded["predictions"][-1]["projected_home_score"])
        self.assertEqual(ungraded["score_metrics"]["fully_walkforward_evaluated_games"], 8)

    def test_late_feature_snapshot_rejected_even_if_score_historical(self):
        rows, outcomes = fixtures()
        rows[2]["forecast_asof_utc"] = rows[2]["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "PREGAME_FEATURES_OR_SOURCE_CUTOFF"):
            get(rows, outcomes)

    def test_source_seen_after_forecast_rejected(self):
        rows, outcomes = fixtures()
        rows[2]["source_observed_utc"] = rows[2]["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "PREGAME_FEATURES_OR_SOURCE_CUTOFF"):
            get(rows, outcomes)

    def test_feature_schema_is_strict_no_results_or_odds(self):
        rows, outcomes = fixtures()
        rows[0]["closing_spread"] = "-3"
        with self.assertRaisesRegex(ValueError, "FEATURE_SCHEMA_VIOLATION"):
            get(rows, outcomes)

    def test_duplicate_event_and_bad_teams_rejected(self):
        rows, outcomes = fixtures()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_EMPTY_GAME_ID"):
            get(rows + [copy.deepcopy(rows[0])], outcomes)
        rows[0]["away_team"] = rows[0]["home_team"]
        with self.assertRaisesRegex(ValueError, "INVALID_TEAM_MAPPING"):
            get(rows, outcomes)

    def test_result_cannot_precede_game_end(self):
        rows, outcomes = fixtures()
        outcomes[0]["result_available_utc"] = rows[0]["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "RESULT_CHRONOLOGY"):
            get(rows, outcomes)

    def test_unknown_result_and_duplicate_refused(self):
        rows, outcomes = fixtures()
        unexpected = copy.deepcopy(outcomes[0])
        unexpected["game_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "RESULT_DUPLICATE_OR_UNKNOWN"):
            get(rows, outcomes + [unexpected])
        with self.assertRaisesRegex(ValueError, "RESULT_DUPLICATE_OR_UNKNOWN"):
            get(rows, outcomes + [copy.deepcopy(outcomes[0])])

    def test_invalid_score_malformed(self):
        rows, outcomes = fixtures()
        outcomes[0]["home_score"] = "-2"
        with self.assertRaisesRegex(ValueError, "RESULT_SCORE_INVALID"):
            get(rows, outcomes)
        outcomes[0]["home_score"] = "nan"
        with self.assertRaisesRegex(ValueError, "RESULT_SCORE_NOT_INTEGER"):
            get(rows, outcomes)

    def test_nonfinite_features_and_sha_refused(self):
        rows, outcomes = fixtures()
        rows[0]["home_off_pass"] = "NaN"
        with self.assertRaisesRegex(ValueError, "NONFINITE_NUMERIC"):
            get(rows, outcomes)
        rows[0]["home_off_pass"] = "0.25"
        rows[0]["epa_ratings_sha256"] = "nonsense"
        with self.assertRaisesRegex(ValueError, "INVALID_EPA_RATINGS_FINGERPRINT"):
            get(rows, outcomes)

    def test_tiny_history_refused_and_all_rows_visible(self):
        rows, outcomes = fixtures()
        result = get(rows, outcomes, min_train_games=15)
        self.assertEqual(result["withheld_insufficient_history"], 12)
        self.assertEqual(len(result["predictions"]), 12)
        self.assertIsNone(result["score_metrics"]["model_score_mae"])
        self.assertTrue(all(p["approved_stake_u"] == 0 for p in result["predictions"]))

    def test_private_research_path_guards_repo_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory)
            self.assertEqual(private_evidence_path(external / "safe.csv"),
                             (external / "safe.csv").resolve())
            with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                private_evidence_path(REPO_ROOT / "models" / "nfl" / "private.csv")
            alias = external / "repo_link"
            alias.symlink_to(REPO_ROOT, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                private_evidence_path(alias / "models" / "nfl" / "private.csv")

    def test_repo_local_symlink_outward_is_not_a_private_evidence_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_checkout = root / "public_checkout"
            protected = root / "restricted"
            fake_checkout.mkdir()
            protected.mkdir()
            alias = fake_checkout / "outward"
            alias.symlink_to(protected, target_is_directory=True)
            with patch("score_walkforward_pit.REPO_ROOT", fake_checkout):
                with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                    private_evidence_path(alias / "source.json")
                with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                    create_private_output(alias / "new.json", b"private")
            self.assertFalse((protected / "new.json").exists())

    def test_private_output_0600_exclusive_and_no_partial_on_fsync_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "results.json"
            self.assertEqual(create_private_output(output, b'{"status":"PAPER"}'), output.resolve())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(output.read_bytes(), b'{"status":"PAPER"}')
            with self.assertRaises(FileExistsError):
                create_private_output(output, b"replacement")
            self.assertEqual(output.read_bytes(), b'{"status":"PAPER"}')
            interrupted = root / "interrupted.json"
            with patch("score_walkforward_pit.os.fsync", side_effect=OSError("injected fsync failure")):
                with self.assertRaisesRegex(OSError, "injected fsync failure"):
                    create_private_output(interrupted, b"incomplete")
            self.assertFalse(interrupted.exists())

    def test_score_cli_success_writes_private_0600_json(self):
        rows, scores = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            features = root / "features.csv"
            results = root / "results.csv"
            output = root / "walkforward.json"
            for target, records in ((features, rows), (results, scores)):
                with target.open("w", encoding="utf-8", newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=records[0].keys())
                    writer.writeheader()
                    writer.writerows(records)
            argv = ["score_walkforward_pit.py", "--features", str(features),
                    "--results", str(results), "--out", str(output)]
            with patch("sys.argv", argv):
                main()
            report = json.loads(output.read_text())
            self.assertEqual(report["approved_stake_u"], 0)
            self.assertEqual(report["status"], "PAPER_HOLD_0U")
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with patch("sys.argv", argv), self.assertRaises(FileExistsError):
                main()
            self.assertEqual(report, json.loads(output.read_text()))

    def test_score_cli_refuses_public_repo_input_and_output_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            cases = (
                (str(REPO_ROOT / "data.csv"), str(private / "out.csv")),
                (str(private / "data.csv"), str(REPO_ROOT / "models" / "nfl" / "new_scores.json")),
            )
            for feature, output in cases:
                with self.subTest(feature=feature, output=output):
                    argv = ["score_walkforward_pit.py", "--features", feature,
                            "--results", str(private / "results.csv"), "--out", output]
                    with patch("sys.argv", argv):
                        with self.assertRaisesRegex(ValueError, "PRIVATE_EVIDENCE_INSIDE_PUBLIC_REPO"):
                            main()

    def test_training_parameter_must_be_safe(self):
        rows, outcomes = fixtures()
        with self.assertRaisesRegex(ValueError, "RIDGE_MUST_BE_POSITIVE"):
            get(rows, outcomes, ridge=0)
        with self.assertRaisesRegex(ValueError, "INVALID_MINIMUM_TRAIN_GAMES"):
            get(rows, outcomes, min_train_games=1)


if __name__ == "__main__":
    unittest.main()
