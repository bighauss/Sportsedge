"""Step 1 input audit: hand-calculated checks of every source -> model-input transformation
in cfb_run_it.py. The frozen model is imported unchanged and pinned by hash."""
import copy, datetime as dt, hashlib, os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb_run_it as R
import sportsedge_cfb_model as M
import test_cfb_run_it as F

FROZEN_MODEL_SHA256 = "1f24cf1a925147a1601d0ba2f04ada30c4cf25173ab6df73bcb16016cff735be"
NOW = dt.datetime.fromisoformat("2026-11-21T15:00:00+00:00")

class FrozenModel(unittest.TestCase):
    def test_model_file_unchanged(self):
        b = open(os.path.join(HERE, "sportsedge_cfb_model.py"), "rb").read()
        self.assertEqual(hashlib.sha256(b).hexdigest(), FROZEN_MODEL_SHA256)

class SPPlus(unittest.TestCase):
    def test_centering_sign_and_national_average_row(self):
        rows = [{"team": "A", "offense": {"rating": 40.0}, "defense": {"rating": 15.0}},   # good O, good D
                {"team": "B", "offense": {"rating": 20.0}, "defense": {"rating": 35.0}},   # bad O, bad D
                {"team": "nationalAverages", "offense": {"rating": 99.0}, "defense": {"rating": 99.0}}]
        r = R.sp_relative(rows)
        self.assertNotIn("nationalAverages", r)                    # summary row never centres the scale
        self.assertEqual(M.g(r["A"], "offense.rating"), 10.0)      # 40 - mean(40,20)
        self.assertEqual(M.g(r["A"], "defense.rating"), -10.0)     # 15 - mean(15,35): lower = better
        # model: points = 28 + own offense + opponent defense  -> A scores more, allows less
        self.assertEqual(M.ratings_points(r["A"], r["B"]), 28 + 10 + 10)
        self.assertEqual(M.ratings_points(r["B"], r["A"]), 28 - 10 - 10)

class PPAUnits(unittest.TestCase):
    def test_ppa_is_per_play_and_scales_with_plays(self):
        adv = [F.adv("X", .30, .10), F.adv("Y", .10, .10)]
        lm = M.league_means(adv)
        hi, _ = M.matchup_points(adv[0], adv[1], lm, 13, 0, 0, 70)
        lo, _ = M.matchup_points(adv[1], adv[1], lm, 13, 0, 0, 70)
        self.assertGreater(hi, lo)                                  # better offense PPA -> more points
        hi2, _ = M.matchup_points(adv[0], adv[1], lm, 13, 0, 0, 80)
        self.assertGreater(hi2 - lo, hi - lo - 1e-9)               # per-play edge grows with plays

class GamesDenominator(unittest.TestCase):
    def test_games_count_is_point_in_time(self):
        games = [{"id": 1, "homeTeam": "X", "awayTeam": "Y", "startDate": "2026-11-14T18:00:00Z", "completed": True},
                 {"id": 2, "homeTeam": "X", "awayTeam": "Z", "startDate": "2026-11-21T16:00:00Z", "completed": True},  # starts after cutoff
                 {"id": 3, "homeTeam": "X", "awayTeam": "W", "startDate": "2026-11-28T18:00:00Z", "completed": False}]
        gp = R.games_played(games, NOW)
        self.assertEqual(gp, {"X": 1, "Y": 1})

    def test_explicit_games_replaces_drives_fallback(self):
        r = F.adv("X", .2, .1)                       # plays 700, drives 120
        self.assertAlmostEqual(M.team_games_plays(r)[0], 10.0)             # drives/12 fallback
        self.assertAlmostEqual(R.with_games([r], {"X": 9})[0]["games"], 9)
        self.assertAlmostEqual(M.team_games_plays(R.with_games([r], {"X": 9})[0])[1], 700 / 9)
        self.assertNotIn("games", r)                                        # source row not mutated

class Usage(unittest.TestCase):
    def test_denominators_match_category(self):
        vol = {"T": {"rushingAttempts": 400.0, "passAttempts": 300.0}}
        st = {"rushing.CAR": 100.0, "rushing.YDS": 550.0, "passing.ATT": 270.0, "passing.YDS": 2160.0,
              "receiving.REC": 45.0, "receiving.YDS": 630.0}
        self.assertEqual(R.usage_row("p", "T", "rush_yds", st, vol), {"share": .25, "eff": 5.5})
        self.assertEqual(R.usage_row("p", "T", "pass_yds", st, vol), {"share": .9, "eff": 8.0})
        self.assertEqual(R.usage_row("p", "T", "rec_yds", st, vol), {"share": .15, "eff": 14.0})
        self.assertEqual(R.usage_row("p", "T", "receptions", st, vol), {"share": .15, "eff": 1.0})
        self.assertIsNone(R.usage_row("p", "U", "rush_yds", st, vol))       # no team totals -> no prop

class FailClosed(unittest.TestCase):
    def test_missing_required_field_withholds_game(self):
        cap = F.fixture(); del cap["advanced"][1]["offense"]["ppa"]       # Michigan offense PPA missing
        _, projs, wh, _ = R.run(F.INTAKE, cap, NOW, lambda *_: cap["_weather"])
        self.assertFalse(any(p["home"] == "Michigan" for p in projs))
        self.assertTrue(any("Michigan: offense.ppa" in r for _, r in wh))

    def test_unknown_games_played_withholds_game(self):
        cap = F.fixture(); cap["games"] = cap["games"][:2]                 # no completed history
        _, projs, wh, _ = R.run(F.INTAKE, cap, NOW, lambda *_: cap["_weather"])
        self.assertEqual(projs, [])
        self.assertTrue(any("games played unknown" in r for _, r in wh))

class Comparison(unittest.TestCase):
    def test_legacy_vs_corrected_same_frozen_model(self):
        cap = F.fixture()
        for t in cap["advanced"]:
            t["offense"]["drives"] = 130                                    # 13 drives/game over 10 games
        _, old, _, _ = R.run(F.INTAKE, copy.deepcopy(cap), NOW, lambda *_: cap["_weather"], legacy_inputs=True)
        _, new, _, _ = R.run(F.INTAKE, copy.deepcopy(cap), NOW, lambda *_: cap["_weather"])
        self.assertAlmostEqual(old[0]["plays"], 700 / (130 / 12))          # 64.6: drives/12 says 10.8 games
        self.assertAlmostEqual(new[0]["plays"], 70.0)                      # actual 10 games

if __name__ == "__main__":
    unittest.main()
