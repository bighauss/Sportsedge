"""Provider-free admission regressions: UNKNOWN must never become a false neutral flag.

Runs only the existing CBB adapter with synthetic CBBD/ESPN inputs. Never
modifies the frozen model, existing cards, or paper ledger.
"""
import tempfile
import unittest

from models.cbb import test_cbb_run_it as fixtures
from models.cbb import cbb_run_it as runner


class NeutralUnknownAdmission(unittest.TestCase):
    def test_missing_prior_final_neutral_is_not_counted_as_home(self):
        games, boxes = fixtures.provider()
        prior = next(g for g in games if g["status"] == "final")
        gid = str(prior["id"])
        prior.pop("neutralSite", None)
        rows, census = runner.prior_games(games, boxes, fixtures.OBS, fixtures.S.SEASON)
        self.assertNotIn(gid, {r["game_id"] for r in rows})
        self.assertEqual(census["neutral_unknown"], 1)

    def test_null_prior_final_neutral_is_not_counted_as_home(self):
        games, boxes = fixtures.provider()
        prior = next(g for g in games if g["status"] == "final")
        gid = str(prior["id"])
        prior["neutralSite"] = None
        rows, census = runner.prior_games(games, boxes, fixtures.OBS, fixtures.S.SEASON)
        self.assertNotIn(gid, {r["game_id"] for r in rows})
        self.assertEqual(census["neutral_unknown"], 1)

    def test_missing_espn_neutral_does_not_assert_non_neutral(self):
        slate_games, _ = fixtures.provider()
        s = runner.slate(slate_games, fixtures.NOW.date(), fixtures.NOW, fixtures.S.SEASON)
        scoreboard = fixtures.espn()
        scoreboard["events"][0]["competitions"][0].pop("neutralSite", None)
        rows, miss = runner.registry(s, scoreboard, "e" * 64, "2026-11-21T14:30:00Z")
        gid = s[0]["game_id"]
        self.assertNotIn(gid, {r["game_id"] for r in rows})
        self.assertIn((gid, "ESPN neutral-site flag unknown"), miss)

    def test_string_espn_neutral_is_not_cast_to_true(self):
        slate_games, _ = fixtures.provider()
        s = runner.slate(slate_games, fixtures.NOW.date(), fixtures.NOW, fixtures.S.SEASON)
        scoreboard = fixtures.espn()
        scoreboard["events"][0]["competitions"][0]["neutralSite"] = "false"
        rows, miss = runner.registry(s, scoreboard, "e" * 64, "2026-11-21T14:30:00Z")
        gid = s[0]["game_id"]
        self.assertNotIn(gid, {r["game_id"] for r in rows})
        self.assertIn((gid, "ESPN neutral-site flag unknown"), miss)

    def test_missing_espn_neutral_withholds_actual_model_card(self):
        scoreboard = fixtures.espn()
        scoreboard["events"][0]["competitions"][0].pop("neutralSite", None)
        with tempfile.TemporaryDirectory() as work:
            card, _, extra = fixtures.run(work, espn=scoreboard)
        row = next(r for r in card["rows"] if r["game_id"] == "9001")
        self.assertEqual(row["status"], "PASS")
        self.assertIn("NEUTRAL_SITE_UNVERIFIED", row["pass_reason"])
        self.assertIn(("9001", "ESPN neutral-site flag unknown"), extra["registry_unmatched"])

    def test_explicit_false_and_true_are_preserved(self):
        games, boxes = fixtures.provider()
        priors = [g for g in games if g["status"] == "final"]
        priors[0]["neutralSite"] = False
        priors[1]["neutralSite"] = True
        rows, census = runner.prior_games(games, boxes, fixtures.OBS, fixtures.S.SEASON)
        have = {r["game_id"]: r["neutral"] for r in rows}
        self.assertIs(have[str(priors[0]["id"])], False)
        self.assertIs(have[str(priors[1]["id"])], True)
        self.assertEqual(census.get("neutral_unknown", 0), 0)


if __name__ == "__main__":
    unittest.main()
