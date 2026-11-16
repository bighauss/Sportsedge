"""Synthetic-only regression tests: no access to live sports books or Torvik."""
import copy
import math
import unittest

from torvik_point_in_time_baseline import Blocked, project, research_board

H = "a" * 64


def evidence(team_id, **extra):
    return {
        "team_id": team_id, "season": 2027,
        "data_through_utc": "2026-11-14T23:00:00Z",
        "published_utc": "2026-11-15T10:00:00Z",
        "captured_utc": "2026-11-15T11:00:00Z",
        "source_sha256": H, **extra,
    }


def setup():
    game = {
        "game_id": "D1:1", "season": 2027,
        "home_team_id": "H001", "away_team_id": "A001",
        "neutral": False,
        "freeze_utc": "2026-11-15T18:00:00Z",
        "tipoff_utc": "2026-11-15T20:00:00Z",
        "model_sha256": H,
    }
    home = evidence("H001", adj_o=115, adj_d=95, adj_tempo=70)
    away = evidence("A001", adj_o=108, adj_d=105, adj_tempo=66)
    league = evidence("LEAGUE", league_adj_o=105, league_tempo=68)
    hca = evidence("H001", home_court_points=3.36)
    return {"game": game, "home": home, "away": away, "league": league, "hca": hca}


class TestResearchBaseline(unittest.TestCase):
    def run_one(self, record=None, **kwargs):
        r = copy.deepcopy(record or setup())
        return project(r["game"], r["home"], r["away"], r["league"], r["hca"], **kwargs)

    def test_expected_score_and_margin(self):
        o = self.run_one()
        self.assertAlmostEqual(o["possessions"], 68)
        self.assertAlmostEqual(o["home_points"], 68 * 115 / 100 + 1.68)
        self.assertAlmostEqual(o["away_points"], 68 * (108 * 95 / 105) / 100 - 1.68)
        self.assertAlmostEqual(o["total"], o["home_points"] + o["away_points"])
        self.assertAlmostEqual(o["margin_home"], o["home_points"] - o["away_points"])
        self.assertEqual(o["status"], "PAPER_NON_COUNTED_UNCALIBRATED")
        self.assertEqual(o["stake_u"], 0)
        self.assertIsNone(o["ml_probability"])
        self.assertIsNone(o["expected_value"])

    def test_neutral_zero_hca(self):
        r = setup()
        r["game"]["neutral"] = True
        self.assertGreater(project(r["game"], r["home"], r["away"], r["league"])["total"], 0)
        with self.assertRaisesRegex(Blocked, "NEUTRAL_GAME"):
            self.run_one(r)

    def test_non_neutral_requires_hca_evidence(self):
        r = setup()
        r["hca"] = None
        with self.assertRaisesRegex(Blocked, "HCA_EVIDENCE_REQUIRED"):
            self.run_one(r)

    def test_future_rating_is_rejected_not_retroactively_used(self):
        r = setup()
        r["home"]["published_utc"] = "2026-11-15T19:30:00Z"
        r["home"]["captured_utc"] = "2026-11-15T19:40:00Z"
        with self.assertRaisesRegex(Blocked, "FUTURE_OR_OUT_OF_ORDER"):
            self.run_one(r)

    def test_future_underlying_game_data_rejected(self):
        r = setup()
        r["away"]["data_through_utc"] = "2026-11-15T21:00:00Z"
        with self.assertRaisesRegex(Blocked, "FUTURE_OR_OUT_OF_ORDER"):
            self.run_one(r)

    def test_source_captured_before_published_rejected(self):
        r = setup()
        r["home"]["captured_utc"] = "2026-11-15T09:00:00Z"
        with self.assertRaisesRegex(Blocked, "FUTURE_OR_OUT_OF_ORDER"):
            self.run_one(r)

    def test_naive_timestamp_rejected(self):
        r = setup()
        r["game"]["freeze_utc"] = "2026-11-15T18:00:00"
        with self.assertRaisesRegex(Blocked, "UTC_Z_TIMESTAMP_REQUIRED"):
            self.run_one(r)

    def test_current_game_freeze_after_tip_rejected(self):
        r = setup()
        r["game"]["freeze_utc"] = "2026-11-15T20:01:00Z"
        with self.assertRaisesRegex(Blocked, "MODEL_NOT_FROZEN"):
            self.run_one(r)

    def test_team_or_season_mismatch_rejected(self):
        r = setup()
        r["home"]["season"] = 2026
        with self.assertRaisesRegex(Blocked, "WRONG_TEAM_OR_SEASON"):
            self.run_one(r)
        r = setup()
        r["away"]["team_id"] = "H001"
        with self.assertRaisesRegex(Blocked, "WRONG_TEAM_OR_SEASON"):
            self.run_one(r)

    def test_invalid_model_or_source_hash_rejected(self):
        r = setup()
        r["home"]["source_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(Blocked, "SOURCE_SHA256_REQUIRED"):
            self.run_one(r)
        r = setup()
        r["game"]["model_sha256"] = "bad"
        with self.assertRaisesRegex(Blocked, "MODEL_SHA256_REQUIRED"):
            self.run_one(r)

    def test_bad_efficiencies_and_nans_rejected(self):
        r = setup()
        r["home"]["adj_o"] = math.nan
        with self.assertRaisesRegex(Blocked, "OUT_OF_RANGE"):
            self.run_one(r)
        r = setup()
        r["home"]["adj_tempo"] = True
        with self.assertRaisesRegex(Blocked, "BAD_NUMBER"):
            self.run_one(r)

    def test_freshness_policy_must_be_explicit(self):
        with self.assertRaisesRegex(Blocked, "STALE_CAPTURE"):
            self.run_one(max_age_hours=2)
        self.assertGreater(self.run_one(max_age_hours=12)["total"], 0)

    def test_board_preserves_blocked_and_duplicate_rows(self):
        good = setup()
        late = setup()
        late["game"]["game_id"] = "D1:2"
        late["home"]["captured_utc"] = "2026-11-15T20:30:00Z"
        rows = research_board([good, late, good, {"game": None}])
        self.assertEqual(len(rows), 4)
        self.assertEqual([r["status"] for r in rows],
                         ["BLOCKED", "BLOCKED", "BLOCKED", "BLOCKED"])
        self.assertIn("DUPLICATE_GAME_ID", rows[0]["reason"])
        self.assertIn("DUPLICATE_GAME_ID", rows[2]["reason"])
        self.assertEqual([r["input_index"] for r in rows], list(range(4)))

    def test_duplicate_order_independent_and_retains_denominator(self):
        first = setup()
        second = setup()
        second["home"]["adj_o"] = 140  # contradictory same-event forecast
        third = setup()
        third["game"]["game_id"] = "D1:3"
        for board in ([first, second, third], [third, second, first]):
            result = research_board(board)
            self.assertEqual(len(result), 3)
            for r in result:
                if r["game_id"] == "D1:1":
                    self.assertEqual(r["status"], "BLOCKED")
                    self.assertIn("DUPLICATE_GAME_ID", r["reason"])
                else:
                    self.assertEqual(r["status"], "PAPER_NON_COUNTED_UNCALIBRATED")

    def test_no_wager_claim_even_with_complete_clock_evidence(self):
        r = self.run_one()
        self.assertFalse(r["official"])
        self.assertTrue(r["blockers_to_bet"])
        self.assertNotIn("win_probability", r)
        self.assertTrue(all("sha256" in x for x in r["source_clock_consistent_not_authenticated"].values()))


if __name__ == "__main__":
    unittest.main()
