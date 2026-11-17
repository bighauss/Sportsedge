"""Synthetic contract tests; never evidence of real provider access or +EV."""
import unittest

from sportsedge.markets.independent_projection_gate import audit_projection, census

H = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
C = "sha256:" + "c" * 64


def candidate(sport="NFL", family="TOTAL", period="FG"):
    return {
        "market": {
            "sport": sport, "event_id": "synthetic-event-1",
            "family": family, "period": period,
            "settlement_id": "synthetic-regulation-rules",
        },
        "forecast": {
            "origin": "SPORTSEDGE_INDEPENDENT",
            "model_sha256": H, "feature_sha256": B,
            "distribution_sha256": C,
            "feature_frozen_utc": "2026-11-16T22:00:00Z",
            "generated_utc": "2026-11-16T22:01:00Z",
            "event_start_utc": "2026-11-17T01:00:00Z",
            "feature_sources": [
                {"kind": "HISTORICAL_GAME_STATS", "sha256": H,
                 "published_utc": "2026-11-16T21:59:00Z"},
            ],
            "p_win": 0.55, "p_push": 0.02,
            "projected_mean": 40.5,
        },
    }


class TestIndependentProjectionGate(unittest.TestCase):
    def assert_blocked(self, item, code, roster=None):
        result = audit_projection(item, roster)
        self.assertEqual(result["status"], "BLOCK")
        self.assertIn(code, result["reasons"])
        self.assertFalse(result["research_projection_usable"])
        self.assertEqual(result["approved_stake_u"], 0)
        self.assertEqual(result["official_counted"], 0)
        self.assertFalse(result["positive_ev_verified"])

    def test_all_seven_sports_have_a_research_contract_not_certification(self):
        for sport in ("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"):
            with self.subTest(sport=sport):
                out = audit_projection(candidate(sport=sport))
                self.assertEqual(out["status"], "PAPER_0U_MODEL_PROJECTION_UNVERIFIED")
                self.assertTrue(out["research_projection_usable"])
                self.assertFalse(out["source_authenticated"])
                self.assertFalse(out["calibration_verified"])
                self.assertFalse(out["positive_ev_verified"])

    def test_missing_forecast_never_becomes_market_projection(self):
        row = candidate()
        del row["forecast"]
        self.assert_blocked(row, "NO_INDEPENDENT_MODEL_PROJECTION")

    def test_market_anchor_rejected_even_with_perfect_probability(self):
        row = candidate()
        row["forecast"]["origin"] = "MARKET_ANCHOR"
        row["forecast"]["p_win"] = 0.99
        self.assert_blocked(row, "SPORTSBOOK_ANCHOR_NOT_INDEPENDENT")

    def test_finished_third_party_projection_is_not_our_model(self):
        row = candidate(sport="CBB")
        row["forecast"]["origin"] = "THIRD_PARTY_PROJECTION"
        self.assert_blocked(row, "THIRD_PARTY_FORECAST_NOT_SPORTSEDGE")

    def test_odds_and_third_party_predictions_are_forbidden_features(self):
        for role in ("SPORTSBOOK_ODDS", "THIRD_PARTY_FORECAST", "MARKET_ANCHOR"):
            row = candidate()
            row["forecast"]["feature_sources"][0]["kind"] = role
            with self.subTest(role=role):
                self.assert_blocked(row, "BOOKMAKER_OR_FOREIGN_FORECAST_FEATURE_FORBIDDEN")

    def test_future_published_feature_and_after_start_generation_rejected(self):
        row = candidate()
        row["forecast"]["feature_sources"][0]["published_utc"] = "2026-11-16T22:01:00Z"
        self.assert_blocked(row, "FEATURE_PUBLISHED_AFTER_MODEL_FREEZE")
        row = candidate()
        row["forecast"]["generated_utc"] = "2026-11-17T01:00:00Z"
        self.assert_blocked(row, "MODEL_NOT_FROZEN_BEFORE_START")

    def test_invalid_probability_and_bool_numeric_spoof_fail_closed(self):
        for win, push in ((True, 0), (float("nan"), 0), (.8, .3), (.6, -0.1)):
            row = candidate()
            row["forecast"]["p_win"] = win
            row["forecast"]["p_push"] = push
            with self.subTest(win=win, push=push):
                self.assert_blocked(row, "MODEL_WIN_PUSH_PROBABILITIES_INVALID")

    def test_player_prop_needs_stat_and_independent_frozen_roster(self):
        row = candidate(sport="NBA", family="PLAYER_PROP:POINTS")
        row["market"].update(player_id="player-1", team_id="team-1", stat="POINTS")
        self.assert_blocked(row, "PLAYER_TEAM_PIT_ROSTER_UNBOUND")
        out = audit_projection(row, {"player-1": "team-1"})
        self.assertTrue(out["research_projection_usable"])
        row["market"]["stat"] = ""
        self.assert_blocked(row, "PLAYER_STAT_IDENTITY_MISSING", {"player-1": "team-1"})

    def test_period_distribution_cannot_be_imputed_from_full_game(self):
        row = candidate(sport="NBA", period="4Q")
        self.assert_blocked(row, "INDEPENDENT_PERIOD_DISTRIBUTION_MISSING")
        row["forecast"]["period_distribution_sha256"] = H
        self.assertTrue(audit_projection(row)["research_projection_usable"])

    def test_first_event_and_multi_score_models_need_specific_evidence(self):
        row = candidate(family="FIRST_TD")
        row["market"].update(player_id="player-1", team_id="team-1")
        self.assert_blocked(row, "ORDERED_SCORING_EVENTS_MISSING",
                            {"player-1": "team-1"})
        row["forecast"]["ordered_events_sha256"] = H
        self.assertTrue(audit_projection(row, {"player-1": "team-1"})["research_projection_usable"])
        row = candidate(family="TD_2PLUS")
        row["market"].update(player_id="player-1", team_id="team-1")
        self.assert_blocked(row, "MULTI_EVENT_COUNT_DISTRIBUTION_MISSING",
                            {"player-1": "team-1"})

    def test_correlated_market_requires_joint_model(self):
        row = candidate(family="SGP")
        self.assert_blocked(row, "CORRELATED_EVENT_DISTRIBUTION_MISSING")
        row["forecast"]["joint_distribution_sha256"] = C
        self.assertTrue(audit_projection(row)["research_projection_usable"])

    def test_malformed_identity_and_feature_roles_block_without_crash(self):
        row = candidate()
        row["market"]["sport"] = ["NFL"]
        self.assert_blocked(row, "UNKNOWN_SPORT_OR_EVENT")
        self.assertEqual(census([row])["submitted"], 1)
        row = candidate()
        row["forecast"]["feature_sources"][0]["kind"] = ["SPORTSBOOK_ODDS"]
        self.assert_blocked(row, "BOOKMAKER_OR_FOREIGN_FORECAST_FEATURE_FORBIDDEN")

    def test_census_keeps_every_rejected_candidate_in_denominator(self):
        row1, row2, row3 = candidate("NFL"), candidate("NBA"), candidate("CBB")
        row2["forecast"]["origin"] = "MARKET_ANCHOR"
        row3["forecast"] = None
        result = census([row1, row2, row3])
        self.assertEqual(result["submitted"], 3)
        self.assertEqual(result["blocked"], 2)
        self.assertEqual(result["research_projections_with_valid_shape"], 1)
        self.assertEqual(len(result["rows"]), 3)
        self.assertEqual(result["official_counted"], 0)


if __name__ == "__main__":
    unittest.main()
