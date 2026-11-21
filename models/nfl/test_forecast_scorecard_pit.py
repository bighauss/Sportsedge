"""Synthetic/offline NFL matched three-model forecast evaluation tests."""
import csv
import math
import tempfile
import unittest
from pathlib import Path

from forecast_scorecard_pit import (FORECAST_FIELDS, GAME_FIELDS, Inadmissible,
                                    rows_from_csv, score)


def game(gid, home="Alpha", away="Beta", home_score="24", away_score="20"):
    return dict(game_id=gid, season="2026", week="11", home=home, away=away,
                kickoff_utc="2026-11-15T18:00:00Z",
                final_available_utc="2026-11-16T00:00:00Z",
                home_score=home_score, away_score=away_score)


def prediction(gid, model, margin=4.0, total=44.0, p=0.8):
    return dict(game_id=gid, model=model, forecast_utc="2026-11-15T17:00:00Z",
                source_available_utc="2026-11-15T16:00:00Z",
                training_cutoff_utc="2026-11-14T20:00:00Z",
                model_version_sha256="a" * 64, input_sha256="b" * 64,
                home_margin=str(margin), total=str(total), home_win_prob=str(p))


def two_games():
    games = [game("g1"), game("g2", home_score="13", away_score="20")]
    forecasts = [prediction("g1", "ridge", 4, 44, .8),
                 prediction("g2", "ridge", -7, 33, .2),
                 prediction("g1", "elo", 2, 40, .6),
                 prediction("g2", "elo", -3, 36, .4),
                 prediction("g1", "epa", 3, 43, .7),
                 prediction("g2", "epa", -6, 34, .3)]
    return games, forecasts


class ScorecardTests(unittest.TestCase):
    def test_all_three_models_same_games_and_metrics(self):
        games, f = two_games()
        x = score(games, f, min_paired=2)
        self.assertEqual(x["paired_n"], 2)
        self.assertEqual(x["blocked_n"], 0)
        self.assertEqual(x["paired_game_ids"], ["g1", "g2"])
        self.assertEqual(x["interpretation"], "PAIRED_RESEARCH_DESCRIPTIVE_ONLY")
        for model in ("ridge", "elo", "epa"):
            self.assertEqual(x["scores"][model]["n"], 2)
        self.assertAlmostEqual(x["scores"]["ridge"]["margin_mae"], 0)
        self.assertAlmostEqual(x["scores"]["ridge"]["brier"], .04)
        self.assertAlmostEqual(x["scores"]["ridge"]["log_loss"], -math.log(.8), places=5)
        self.assertAlmostEqual(x["scores"]["elo"]["margin_mae"], 3)
        self.assertAlmostEqual(x["scores"]["elo"]["total_mae"], 3.5)
        self.assertAlmostEqual(x["scores"]["elo"]["brier"], .16)
        self.assertFalse(x["betting_authorized"])
        self.assertEqual(x["stake_u"], 0)

    def test_missing_epa_excludes_game_from_all_models(self):
        games, forecasts = two_games()
        f = [x for x in forecasts if not (x["game_id"] == "g2" and x["model"] == "epa")]
        r = score(games, f, min_paired=2)
        self.assertEqual(r["paired_n"], 1)
        self.assertEqual(r["per_model_pregame_eligible"], {"ridge": 2, "elo": 2, "epa": 1})
        self.assertEqual([r["scores"][m]["n"] for m in ("ridge", "elo", "epa")], [1, 1, 1])
        self.assertEqual(r["blocked_reasons"]["epa:MISSING_FORECAST"], 1)
        self.assertEqual(r["interpretation"], "INSUFFICIENT_PAIRED_SAMPLE")

    def test_empty_forecasts_no_fabricated_predictions(self):
        x = score([game("g")], [])
        self.assertEqual(x["paired_n"], 0)
        self.assertEqual(x["blocked_n"], 1)
        self.assertEqual(x["scores"], dict.fromkeys(("ridge", "elo", "epa"), None))

    def test_source_after_prediction_fails_closed(self):
        g, forecasts = two_games()
        forecasts[0]["source_available_utc"] = "2026-11-15T17:10:00Z"
        r = score(g, forecasts, min_paired=1)
        self.assertEqual(r["paired_n"], 1)
        self.assertEqual(r["blocked_reasons"]["ridge:NOT_STRICTLY_PREGAME"], 1)

    def test_future_training_cutoff_fails(self):
        g, forecasts = two_games()
        forecasts[0]["training_cutoff_utc"] = "2026-11-16T18:00:00Z"
        self.assertIn("ridge:NOT_STRICTLY_PREGAME",
                      score(g, forecasts)["blocked_reasons"])

    def test_source_observed_after_kickoff_fails(self):
        g, forecasts = two_games()
        forecasts[0]["source_available_utc"] = "2026-11-16T19:00:00Z"
        self.assertIn("ridge:NOT_STRICTLY_PREGAME",
                      score(g, forecasts)["blocked_reasons"])

    def test_prediction_after_kickoff_fails(self):
        g, forecasts = two_games()
        forecasts[0]["forecast_utc"] = "2026-11-16T12:00:00Z"
        self.assertIn("ridge:NOT_STRICTLY_PREGAME",
                      score(g, forecasts)["blocked_reasons"])

    def test_missing_custody_hash_is_blocked(self):
        g, forecasts = two_games()
        forecasts[0]["input_sha256"] = ""
        self.assertEqual(score(g, forecasts)["blocked_reasons"]
                         ["ridge:INPUT_MISSING_OR_NOT_SHA256"], 1)

    def test_nonfinite_probability_is_blocked(self):
        g, forecasts = two_games()
        forecasts[0]["home_win_prob"] = "nan"
        self.assertEqual(score(g, forecasts)["blocked_reasons"]
                         ["ridge:HOME_WIN_PROB_NONFINITE"], 1)

    def test_probability_endpoint_is_blocked(self):
        g, forecasts = two_games()
        forecasts[0]["home_win_prob"] = "1"
        self.assertEqual(score(g, forecasts)["blocked_reasons"]
                         ["ridge:FORECAST_OUT_OF_RANGE"], 1)

    def test_impossible_score_geometry_is_blocked(self):
        g, forecasts = two_games()
        forecasts[0]["home_margin"] = "50"
        forecasts[0]["total"] = "35"
        self.assertEqual(score(g, forecasts)["blocked_reasons"]
                         ["ridge:IMPOSSIBLE_POINTS_GEOMETRY"], 1)

    def test_duplicate_forecast_refused(self):
        g, f = two_games()
        with self.assertRaisesRegex(Inadmissible, "DUPLICATE_FORECAST"):
            score(g, f + [dict(f[0])])

    def test_orphan_forecast_refused(self):
        g, f = two_games()
        f.append(prediction("unknown", "elo"))
        with self.assertRaisesRegex(Inadmissible, "ORPHAN_FORECAST"):
            score(g, f)

    def test_ties_block_binary_win_scoring(self):
        g, f = two_games()
        g[0]["away_score"] = g[0]["home_score"]
        result = score(g, f)
        self.assertIn("outcome:TIED_NFL_RESULT_NO_BINARY_HOME_WIN", result["blocked_reasons"])
        self.assertEqual(result["paired_n"], 1)

    def test_malformed_headers_refused(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        p = Path(t.name) / "sample.csv"
        p.write_text("game_id,game_id\nx,y\n")
        with self.assertRaisesRegex(Inadmissible, "AMBIGUOUS_HEADER"):
            rows_from_csv(p, GAME_FIELDS, "GAMES")

    def test_quoted_embedded_newline_preserved(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        p = Path(t.name) / "sample.csv"
        with p.open("w", newline="") as h:
            w = csv.DictWriter(h, fieldnames=GAME_FIELDS)
            w.writeheader()
            row = game("test")
            row["home"] = "A\nB"
            w.writerow(row)
        rows, digest = rows_from_csv(p, GAME_FIELDS, "GAMES")
        self.assertEqual(rows[0]["home"], "A\nB")
        self.assertEqual(len(digest), 64)

    def test_ragged_csv_refused(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        p = Path(t.name) / "sample.csv"
        p.write_text("game_id,season\n1,2026,extra\n")
        with self.assertRaisesRegex(Inadmissible, "MALFORMED_ROW"):
            rows_from_csv(p, ["game_id", "season"], "GAMES")

    def test_bad_game_final_clock_refused(self):
        g, f = two_games()
        g[0]["final_available_utc"] = "2026-11-15T17:00:00Z"
        with self.assertRaisesRegex(Inadmissible, "OUTCOME_AVAILABLE_BEFORE_KICKOFF"):
            score(g, f)

    def test_late_game_results_do_not_prevent_research_only(self):
        g, f = two_games()
        x = score(g, f, min_paired=1)
        self.assertFalse(x["official_model_admitted"])
        self.assertTrue(any("authentication" in z for z in x["limitations"]))
        self.assertEqual(set(x["models"]), {"ridge", "elo", "epa"})

    def test_minimum_sample_must_be_positive(self):
        g, f = two_games()
        with self.assertRaisesRegex(Inadmissible, "MIN_PAIRED_MUST_BE_POSITIVE"):
            score(g, f, min_paired=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
