"""Synthetic only. No external ratings, team data, betting odds or network."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from cfb_no_key_ratings_adapter import Rejected, read_csv, stage


class TestNoKeyCFBAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        self.ratings = self.d / "ratings.csv"
        self.crosswalk = self.d / "crosswalk.csv"
        self.games = self.d / "games.csv"
        self.manifest = self.d / "manifest.json"
        self.ratings.write_text("season,through_week,team_id,games,adj_off_epa,adj_def_epa,off_pace\n2026,11,1,9,.15,-.2,69\n2026,11,2,9,.05,.1,65\n")
        self.crosswalk.write_text("team_id,team\n1,Alpha\n2,Beta\n")
        self.games.write_text("game_id,season,week,kickoff_utc,home_team_id,away_team_id,home,away\ng1,2026,12,2026-11-21T18:00:00Z,1,2,Alpha,Beta\n")
        self.meta = {"source_kind": "sportsdataverse_cfb_ratings_weekly",
                     "source_url": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_ratings_weekly/ratings.csv",
                     "published_utc": "2026-11-18T10:00:00Z", "captured_utc": "2026-11-20T12:00:00Z",
                     "data_through_utc": "2026-11-17T23:00:00Z", "model_asof_utc": "2026-11-21T13:00:00Z"}
        self.write_meta()

    def write_meta(self):
        self.meta["source_sha256"] = self.meta.get("source_sha256") or hashlib.sha256(self.ratings.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(self.meta))

    def check(self):
        return stage(self.ratings, self.crosswalk, self.games, self.manifest)

    def test_offline_stage_never_prices(self):
        r = self.check()
        self.assertEqual((r["n_ratings"], r["n_staged"], r["n_blocked"]), (2, 1, 0))
        x = r["rows"][0]
        self.assertEqual(x["rating_inputs"]["home"]["off_pace"], 69)
        self.assertFalse(x["wager_eligible"])
        self.assertEqual(x["stake_u"], 0)
        self.assertIn("EPA_TO_POINTS_MAPPING_UNVALIDATED", x["reason_codes"])

    def test_fail_sha(self):
        self.meta["source_sha256"] = "0" * 64
        self.write_meta()
        with self.assertRaisesRegex(Rejected, "SHA256_MISMATCH"):
            self.check()

    def test_no_future_snapshot_week(self):
        self.ratings.write_text(self.ratings.read_text().replace(",11,", ",12,"))
        self.meta["source_sha256"] = hashlib.sha256(self.ratings.read_bytes()).hexdigest()
        self.write_meta()
        r = self.check()["rows"][0]
        self.assertEqual(r["status"], "BLOCKED")
        self.assertIn("HOME_NO_PRIOR_WEEK_RATING", r["reason_codes"])

    def test_fail_publication_after_capture(self):
        self.meta["published_utc"] = "2026-11-22T00:00:00Z"
        self.write_meta()
        with self.assertRaisesRegex(Rejected, "CLOCKS_OUT_OF_ORDER"):
            self.check()

    def test_fail_unzoned_clock(self):
        self.meta["model_asof_utc"] = "2026-11-21T13:00:00"
        self.write_meta()
        with self.assertRaisesRegex(Rejected, "CLOCK_NEEDS_OFFSET"):
            self.check()

    def test_fail_duplicate_rating_week(self):
        self.ratings.write_text(self.ratings.read_text() + "2026,11,1,9,.2,.1,68\n")
        self.meta["source_sha256"] = hashlib.sha256(self.ratings.read_bytes()).hexdigest()
        self.write_meta()
        with self.assertRaisesRegex(Rejected, "DUPLICATE_TEAM_WEEK_RATING"):
            self.check()

    def test_fail_duplicate_crosswalk(self):
        self.crosswalk.write_text(self.crosswalk.read_text() + "1,Another\n")
        with self.assertRaisesRegex(Rejected, "DUPLICATE_OR_BLANK_CROSSWALK"):
            self.check()

    def test_game_identity_mismatch_blocks(self):
        self.games.write_text(self.games.read_text().replace(",Alpha,Beta", ",Gamma,Beta"))
        r = self.check()["rows"][0]
        self.assertEqual(r["status"], "BLOCKED")
        self.assertIn("HOME_IDENTITY_UNVERIFIED", r["reason_codes"])
        self.assertIsNone(r["rating_inputs"])

    def test_future_asof_blocks(self):
        self.meta["model_asof_utc"] = "2026-11-21T19:00:00Z"
        self.write_meta()
        r = self.check()["rows"][0]
        self.assertIn("ASOF_NOT_BEFORE_KICKOFF", r["reason_codes"])
        self.assertFalse(r["wager_eligible"])

    def test_quoted_newline_survives(self):
        p = self.d / "notes.csv"
        p.write_text('team_id,team\n1,"Alpha\nTeam"\n')
        rows, _ = read_csv(p, ("team_id", "team"), "CROSSWALK")
        self.assertEqual(rows[0]["team"], "Alpha\nTeam")

    def test_ragged_csv_rejected(self):
        self.crosswalk.write_text("team_id,team\n1,Alpha,EXTRA\n")
        with self.assertRaisesRegex(Rejected, "BAD_RECORD"):
            self.check()

    def test_invalid_own_units_rejected(self):
        self.ratings.write_text(self.ratings.read_text().replace(".15", "nan"))
        self.meta["source_sha256"] = hashlib.sha256(self.ratings.read_bytes()).hexdigest()
        self.write_meta()
        with self.assertRaisesRegex(Rejected, "NONFINITE_OR_OUT_OF_RANGE"):
            self.check()

    def test_stale_zero_games_blocked(self):
        self.ratings.write_text(self.ratings.read_text().replace(",1,9,", ",1,0,"))
        self.meta["source_sha256"] = hashlib.sha256(self.ratings.read_bytes()).hexdigest()
        self.write_meta()
        r = self.check()["rows"][0]
        self.assertIn("HOME_NO_GAMES_PLAYED", r["reason_codes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
