"""Synthetic regression tests: source time, availability, classification, controls."""
import unittest

from epa_ridge_pit import build_ratings, utc


ASOF = "2026-11-15T18:00:00Z"
OBSERVED = "2026-11-15T17:00:00Z"
GAME1 = {
    "kickoff_utc": "2026-11-01T18:00:00Z",
    "final_utc": "2026-11-01T22:00:00Z",
    "data_available_utc": "2026-11-02T07:00:00Z",
}
GAME2 = {
    "kickoff_utc": "2026-11-08T18:00:00Z",
    "final_utc": "2026-11-08T22:00:00Z",
    "data_available_utc": "2026-11-09T07:00:00Z",
}
FUTURE = {
    "kickoff_utc": "2026-11-16T01:00:00Z",
    "final_utc": "2026-11-16T05:00:00Z",
    "data_available_utc": "2026-11-16T07:00:00Z",
}


def play(game_id, offense, defense, kind, epa, wp="0.5"):
    return {
        "game_id": game_id,
        "play_id": f"{game_id}:{offense}:{defense}:{kind}:{epa}",
        "drive": "1",
        "posteam": offense,
        "defteam": defense,
        "pass": "1" if kind == "pass" else "0",
        "rush": "1" if kind == "rush" else "0",
        "epa": str(epa),
        "wp": str(wp),
    }


def fixture():
    return [
        play("g1", "SEA", "LV", "pass", 0.7),
        play("g1", "LV", "SEA", "pass", -0.2),
        play("g1", "SEA", "LV", "rush", 0.1),
        play("g1", "LV", "SEA", "rush", -0.3),
        play("g2", "LV", "SEA", "pass", 0.0),
        play("g2", "SEA", "LV", "pass", 0.4),
        play("g2", "LV", "SEA", "rush", -0.1),
        play("g2", "SEA", "LV", "rush", 0.2),
    ]


def model(rows=None, games=None, **kw):
    return build_ratings(
        fixture() if rows is None else rows,
        {"g1": GAME1, "g2": GAME2} if games is None else games,
        asof_utc=kw.pop("asof_utc", ASOF),
        source_observed_utc=kw.pop("source_observed_utc", OBSERVED),
        **kw,
    )


class EPAPITTests(unittest.TestCase):
    def test_outputs_are_features_not_bets(self):
        output = model()
        self.assertEqual(output["status"], "PAPER_HOLD_0U")
        self.assertEqual(output["approved_stake_u"], 0)
        self.assertIsNone(output["projected_points"])
        self.assertIsNone(output["market_ev"])
        self.assertEqual(output["games_used"], 2)
        self.assertEqual(output["census"]["source_rows"], 8)
        self.assertEqual(output["units"]["pass"]["play_count"], 4)
        self.assertEqual(output["units"]["rush"]["play_count"], 4)
        self.assertGreater(output["units"]["pass"]["offense_above_average_epa"]["SEA"], 0)
        self.assertGreater(output["units"]["rush"]["offense_above_average_epa"]["SEA"], 0)

    def test_future_games_never_change_past_ratings(self):
        original = model()
        rows = fixture() + [play("future", "SEA", "LV", "pass", 99999),
                            play("future", "SEA", "LV", "rush", 99999)]
        updated = model(rows, {"g1": GAME1, "g2": GAME2, "future": FUTURE})
        self.assertEqual(original["units"], updated["units"])
        self.assertEqual(updated["census"]["excluded_not_available_asof"], 2)

    def test_current_download_cannot_replay_history(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_OBSERVED_AFTER_FORECAST"):
            model(source_observed_utc="2026-11-16T20:00:00Z")

    def test_naive_and_bad_time_rejected(self):
        with self.assertRaisesRegex(ValueError, "NAIVE_TIMESTAMP"):
            utc("2026-11-15T10:00:00")
        with self.assertRaisesRegex(ValueError, "UTC_TIMESTAMP_INVALID"):
            utc("nonsense")

    def test_missing_and_invalid_game_manifest_refused(self):
        with self.assertRaisesRegex(ValueError, "PBP_GAME_MANIFEST_MISSING"):
            model(games={"g1": GAME1})
        wrong = dict(GAME1)
        wrong["final_utc"] = wrong["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "GAME_TIME_ORDER_INVALID"):
            model(games={"g1": wrong, "g2": GAME2})

    def test_late_data_rejected_not_retimed(self):
        late = dict(GAME1)
        late["data_available_utc"] = "2026-11-15T17:30:00Z"
        with self.assertRaisesRegex(ValueError, "GAME_DATA_NOT_YET_AVAILABLE"):
            model(games={"g1": late, "g2": GAME2})

    def test_wp_filter_is_optional_ablation(self):
        rows = fixture()
        rows[0]["wp"] = "0.99"
        self.assertEqual(model(rows)["units"]["pass"]["play_count"], 4)
        result = model(rows, wp_limits=(0.1, 0.9))
        self.assertEqual(result["units"]["pass"]["play_count"], 3)
        self.assertEqual(result["census"]["excluded_wp_filter"], 1)
        with self.assertRaisesRegex(ValueError, "BAD_WP_LIMITS"):
            model(wp_limits=(0.9, 0.1))

    def test_missing_epa_excluded_with_census_no_fill(self):
        rows = fixture()
        rows[0]["epa"] = ""
        result = model(rows)
        self.assertEqual(result["census"]["excluded_missing_epa"], 1)
        self.assertEqual(result["units"]["pass"]["play_count"], 3)

    def test_very_large_uncertain_edge_does_not_become_bet(self):
        rows = fixture()
        rows[0]["epa"] = "5000"
        result = model(rows)
        self.assertIsNone(result["win_probability"])
        self.assertEqual(result["approved_stake_u"], 0)

    def test_invalid_numeric_and_flags_refused(self):
        rows = fixture()
        rows[0]["epa"] = "NaN"
        with self.assertRaisesRegex(ValueError, "NONFINITE_EPA"):
            model(rows)
        rows = fixture()
        rows[0]["pass"] = "maybe"
        with self.assertRaisesRegex(ValueError, "INVALID_PASS_RUSH_FLAG"):
            model(rows)

    def test_duplicate_play_id_does_not_inflate_epa(self):
        rows = fixture()
        duplicate = dict(rows[0])
        duplicate["epa"] = "5000"  # contradictory copy, same source play ID
        rows.append(duplicate)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PBP_PLAY_ID"):
            model(rows)

    def test_missing_play_id_refused(self):
        rows = fixture()
        rows[0].pop("play_id")
        with self.assertRaisesRegex(ValueError, "PBP_PLAY_ID_MISSING"):
            model(rows)

    def test_same_play_id_on_different_drive_is_distinct(self):
        # Official nflfastR dictionary identifies plays by game+drive+play.
        rows = fixture()
        again = dict(rows[0])
        again["drive"] = "2"
        result = model(rows + [again])
        self.assertEqual(result["units"]["pass"]["play_count"], 5)

    def test_missing_drive_refused_on_scrimmage_play(self):
        rows = fixture()
        rows[0].pop("drive")
        with self.assertRaisesRegex(ValueError, "PBP_DRIVE_MISSING"):
            model(rows)

    def test_non_scrimmage_without_play_id_excluded(self):
        rows = fixture() + [{"game_id": "g1", "posteam": "SEA",
                             "defteam": "LV", "pass": "0", "rush": "0",
                             "epa": "0", "wp": "0.5"}]
        result = model(rows)
        self.assertEqual(result["census"]["excluded_non_scrimmage"], 1)
        self.assertEqual(result["units"]["pass"]["play_count"], 4)

    def test_wrong_team_identity_refused(self):
        rows = fixture()
        rows[0]["posteam"] = rows[0]["defteam"]
        with self.assertRaisesRegex(ValueError, "BAD_TEAM_ID"):
            model(rows)

    def test_no_history_must_not_emit_zero_rating(self):
        only_future = [play("future", "SEA", "LV", "pass", 1)]
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_PASS_RUSH"):
            model(only_future, {"future": FUTURE})


if __name__ == "__main__":
    unittest.main()
