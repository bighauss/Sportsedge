"""Provider-free admission regressions: UNKNOWN must never become a false neutral flag.

Runs only the existing CBB adapter with synthetic CBBD/ESPN inputs. Never
modifies the frozen model, existing cards, or paper ledger.
"""
import tempfile
import unittest

import test_cbb_run_it as fixtures
import cbb_run_it as runner

ESPN_UNKNOWN = "ESPN neutral-site flag missing or not boolean"


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
        self.assertIn((gid, ESPN_UNKNOWN), miss)

    def test_string_espn_neutral_is_not_cast_to_true(self):
        slate_games, _ = fixtures.provider()
        s = runner.slate(slate_games, fixtures.NOW.date(), fixtures.NOW, fixtures.S.SEASON)
        scoreboard = fixtures.espn()
        scoreboard["events"][0]["competitions"][0]["neutralSite"] = "false"
        rows, miss = runner.registry(s, scoreboard, "e" * 64, "2026-11-21T14:30:00Z")
        gid = s[0]["game_id"]
        self.assertNotIn(gid, {r["game_id"] for r in rows})
        self.assertIn((gid, ESPN_UNKNOWN), miss)

    def test_missing_espn_neutral_withholds_actual_model_card(self):
        scoreboard = fixtures.espn()
        scoreboard["events"][0]["competitions"][0].pop("neutralSite", None)
        with tempfile.TemporaryDirectory() as work:
            card, _, extra = fixtures.run(work, espn=scoreboard)
        row = next(r for r in card["rows"] if r["game_id"] == "9001")
        self.assertEqual(row["status"], "PASS")
        self.assertIn("NEUTRAL_SITE_UNVERIFIED", row["pass_reason"])
        self.assertIn(("9001", ESPN_UNKNOWN), extra["registry_unmatched"])

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


class NeutralOrientation(unittest.TestCase):
    def setup_inputs(self):
        games, _ = fixtures.provider()
        slate = runner.slate(games, fixtures.NOW.date(), fixtures.NOW, fixtures.S.SEASON)
        scoreboard = fixtures.espn()
        return slate, scoreboard

    def registry(self, slate, scoreboard):
        return runner.registry(slate, scoreboard, "e" * 64, "2026-11-21T14:30:00Z")

    def reverse(self, competition):
        for team in competition["competitors"]:
            team["homeAway"] = "away" if team["homeAway"] == "home" else "home"

    def test_explicit_neutral_reversal_preserves_venue_only(self):
        slate, scoreboard = self.setup_inputs()
        r = slate[0]
        r["neutral"] = "1"
        c = scoreboard["events"][0]["competitions"][0]
        c["neutralSite"] = True
        self.reverse(c)
        rows, _ = self.registry(slate, scoreboard)
        match = next(x for x in rows if x["game_id"] == r["game_id"])
        self.assertEqual(match["neutral"], "1")
        # Reversed sportsbook sides remain rejected by the quote matcher.
        hit, _ = runner._match(slate, r["_away"], r["_home"], {"tip_utc": r["tipoff_utc"]})
        self.assertIsNone(hit)

    def test_reverse_non_neutral_or_disagreement_stays_blocked(self):
        for cb, espn in (("0", False), ("0", True), ("1", False), ("1", None)):
            with self.subTest(cb=cb, espn=espn):
                slate, scoreboard = self.setup_inputs()
                slate[0]["neutral"] = cb
                c = scoreboard["events"][0]["competitions"][0]
                c["neutralSite"] = espn
                self.reverse(c)
                rows, _ = self.registry(slate, scoreboard)
                self.assertNotIn(slate[0]["game_id"], {x["game_id"] for x in rows})

    def test_reversed_duplicate_is_ambiguous(self):
        import copy
        slate, scoreboard = self.setup_inputs()
        slate[0]["neutral"] = "1"
        event = scoreboard["events"][0]
        event["competitions"][0]["neutralSite"] = True
        duplicate = copy.deepcopy(event)
        self.reverse(duplicate["competitions"][0])
        scoreboard["events"].append(duplicate)
        rows, _ = self.registry(slate, scoreboard)
        self.assertNotIn(slate[0]["game_id"], {x["game_id"] for x in rows})

    def test_outside_time_window_stays_blocked(self):
        slate, scoreboard = self.setup_inputs()
        slate[0]["neutral"] = "1"
        c = scoreboard["events"][0]["competitions"][0]
        c["neutralSite"] = True
        c["date"] = "2026-11-21T23:16:00Z"
        self.reverse(c)
        rows, _ = self.registry(slate, scoreboard)
        self.assertNotIn(slate[0]["game_id"], {x["game_id"] for x in rows})

    def test_one_espn_event_cannot_register_two_cbbd_games(self):
        slate, scoreboard = self.setup_inputs()
        slate.append(dict(slate[0], game_id="999999"))
        rows, miss = self.registry(slate, scoreboard)
        self.assertNotIn(slate[0]["game_id"], {x["game_id"] for x in rows})
        self.assertNotIn("999999", {x["game_id"] for x in rows})
        self.assertIn(("999999", "ESPN event reused across CBBD games"), miss)


if __name__ == "__main__":
    unittest.main()
