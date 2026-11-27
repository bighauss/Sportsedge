"""Offline end-to-end test: fixture CFBD capture -> unmodified model -> card."""
import json, os, subprocess, sys, tempfile, unittest, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cfb_run_it as R
import sportsedge_cfb_model as M

def adv(team, ppa_o, ppa_d):
    side = lambda p: {"plays": 700, "drives": 120, "ppa": p, "successRate": .42, "explosiveness": 1.2,
                      "pointsPerOpportunity": 4.0, "fieldPosition": {"averageStart": 70},
                      "havoc": {"total": .17}, "rushingPlays": {"ppa": p, "successRate": .42, "rate": .5},
                      "passingPlays": {"ppa": p, "successRate": .42, "rate": .5}}
    return {"team": team, "offense": side(ppa_o), "defense": side(ppa_d)}

def fixture():
    teams = ["UCLA", "Michigan", "LSU", "Tennessee"]
    pl = lambda cat, team, player, st, v, pid="501": {"team": team, "player": player, "playerId": pid,
                                                        "category": cat, "statType": st, "stat": v}
    return {
        "games": [{"id": 1, "season": 2026, "week": 13, "homeTeam": "Michigan", "awayTeam": "UCLA",
                   "neutralSite": False, "venueId": 10, "venue": "Michigan Stadium",
                   "startDate": "2026-11-21T20:30:00Z", "completed": False},
                  {"id": 2, "season": 2026, "week": 13, "homeTeam": "Tennessee", "awayTeam": "LSU",
                   "neutralSite": False, "venueId": 11, "venue": "Neyland", "startDate": "2026-11-21T16:00:00Z",
                   "completed": False}] + [
            {"id": 100 + 10 * j + i, "homeTeam": t, "awayTeam": "Filler", "startDate": f"2026-10-{i+1:02d}T18:00:00Z",
             "completed": True} for j, t in enumerate(teams) for i in range(10)],
        "advanced": [adv("UCLA", .25, .10), adv("Michigan", .05, .12), adv("LSU", .2, .1), adv("Tennessee", .2, .1)],
        "team_stats": [{"team": t, "statName": n, "statValue": v} for t in teams
                       for n, v in (("rushingAttempts", 400), ("passAttempts", 350))],
        "talent": [{"team": t, "talent": 800} for t in teams], "returning": [],
        "ratings": [{"team": t, "rating": 10, "offense": {"rating": 30}, "defense": {"rating": 20}} for t in teams],
        "teams": [], "venues": [{"id": 10, "dome": False, "location": {"x": 42.26, "y": -83.75}},
                                {"id": 11, "dome": False, "latitude": 35.95, "longitude": -83.92}],
        "player_rushing": [pl("rushing", "Michigan", "Wayne Knight", "CAR", 150), pl("rushing", "Michigan", "Wayne Knight", "YDS", 800)],
        "player_passing": [], "player_receiving": [],
        "_weather": {"windSpeed": 8, "precipitation_type": "none", "isForecast": True}}

INTAKE = {"captured": "fixture", "injuries": [], "lines": [
    {"awayTeam": "UCLA", "homeTeam": "Michigan", "spread": 3.5, "spreadHomeOdds": -110, "spreadAwayOdds": -110,
     "overUnder": 36.5, "overOdds": -110, "underOdds": -110, "homeMoneyline": 150, "awayMoneyline": -180},
    {"awayTeam": "LSU", "homeTeam": "Tenness ee", "spread": 1.5, "spreadHomeOdds": -115, "spreadAwayOdds": -105,
     "overUnder": 45.5, "overOdds": -108, "underOdds": -112, "homeMoneyline": -105, "awayMoneyline": -115},
    {"awayTeam": "Wofford", "homeTeam": "Ole Miss", "spread": -49.5, "spreadHomeOdds": -102, "spreadAwayOdds": -118}],
    "props": [{"away": "UCLA", "home": "Michigan", "player": "Wayne Knight", "market": "rush_yds", "line": 69.5, "overOdds": 100},
              {"away": "UCLA", "home": "Michigan", "player": "Nobody Here", "market": "rush_yds", "line": 9.5, "overOdds": 100}]}

class T(unittest.TestCase):
    def go(self, intake=INTAKE, now="2026-11-21T17:00:00+00:00", **kw):
        import datetime as dt
        cap = fixture()
        return R.run(intake, cap, dt.datetime.fromisoformat(now), lambda *_: cap["_weather"], **kw)

    def test_model_file_unchanged_and_used(self):
        card, projs, wh, ctx = self.go()
        self.assertEqual(len(projs), 1)                       # UCLA@Mich only
        p = projs[0]; g = fixture()
        direct = M.run_game(g["games"][0], ctx)               # same numbers as calling the model directly
        self.assertAlmostEqual(p["margin"], direct["margin"]); self.assertAlmostEqual(p["total"], direct["total"])
        for r in card:
            self.assertGreater(r["ev_blend"], 0)
            self.assertAlmostEqual(r["ev_blend"], r["p_blend"] * M.dec(r["odds"]) - 1)

    def test_fail_closed(self):
        _, _, wh, _ = self.go()
        reasons = " | ".join(f"{a}: {b}" for a, b in wh)
        self.assertIn("LSU @ Tenness ee: kicked off", reasons)
        self.assertIn("Wofford @ Ole Miss: team not in CFBD", reasons)
        self.assertIn("Nobody Here rush_yds: player identity not unique", reasons)
        with self.assertRaises(R.Fail):
            self.go(intake={k: v for k, v in INTAKE.items() if k != "injuries"})

    def test_prop_priced_from_usage_one_sided(self):
        card, *_ = self.go(now="2026-11-21T15:00:00+00:00")
        props = [r for r in card if r["market"].startswith("Prop")]
        self.assertTrue(all("Under" not in r["pick"] for r in props))

    def test_cli_no_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "i.json"); json.dump(INTAKE, open(f, "w"))
            env = {k: v for k, v in os.environ.items() if k != "CFBD_API_KEY"}
            r = subprocess.run([sys.executable, os.path.join(HERE, "cfb_run_it.py"), f, "--season", "2026", "--out", d],
                               env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 2); self.assertIn("CFBD_API_KEY_ABSENT", r.stderr)

    def test_cli_fixture_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "i.json"); json.dump(INTAKE, open(f, "w"))
            fx = os.path.join(d, "fx.json"); json.dump(fixture(), open(fx, "w"))
            r = subprocess.run([sys.executable, os.path.join(HERE, "cfb_run_it.py"), f, "--season", "2026",
                                "--out", d, "--fixture", fx, "--now", "2026-11-21T15:00:00+00:00"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            md = open(os.path.join(d, "cfb_card.md")).read()
            self.assertIn("UCLA @ Michigan", md); self.assertIn("## Withheld", md); self.assertIn("CT", md)
            with open(os.path.join(d, "cfb_run_it.json")) as handle:
                audit = json.load(handle)["original_run_quant_arithmetic_audit"]
            self.assertGreater(audit["priced_rows"], 0)
            self.assertEqual(audit["priced_rows"], audit["arithmetic_checked"])
            self.assertFalse(audit["release_ready"])
            with open(os.path.join(d, "cfb_run_it.json")) as handle:
                shadow = json.load(handle)["original_run_shadow_prop_means"]
            self.assertEqual(shadow["attempts"], shadow["mean_only"] + shadow["blocked"])
            self.assertEqual(shadow["mean_only"], 1)
            self.assertEqual(shadow["blocked"], 1)
            self.assertFalse(shadow["release_ready"])
            self.assertEqual(len(shadow["rows"]), shadow["attempts"])

class QuantRunnerAudit(unittest.TestCase):
    def test_real_runner_fixture_audits_before_selection(self):
        import copy
        import datetime as dt
        cap = fixture()
        card, _, _, ctx = R.run(copy.deepcopy(INTAKE), cap,
                                dt.datetime.fromisoformat("2026-11-21T17:00:00+00:00"),
                                lambda *_: cap["_weather"])
        a = ctx["quant_arithmetic_audit"]
        self.assertEqual(a["priced_rows"], a["arithmetic_checked"])
        self.assertGreater(a["priced_rows"], len(card))
        self.assertGreater(a["nonpositive_blended_ev_rows"], 0)
        self.assertEqual(a["market_anchored_prop_rows"], 1)
        self.assertEqual(a["approved_stake_u"], 0)
        self.assertFalse(a["release_ready"])
        self.assertEqual(len(a["master_odds_sha256"]), 64)
        self.assertTrue(card)
        for row in card:
            self.assertEqual(row["stars"], 0)
            self.assertEqual(row["flames"], "")
            self.assertEqual(row["stars_label"], "N/A — uncalibrated")
            self.assertEqual(row["settlement_model"], "LEGACY_ZERO_PUSH_ASSUMPTION")
            self.assertEqual(row["projection_mode"],
                             "MARKET_ANCHORED_RESEARCH" if row["market"].startswith("Prop")
                             else "LEGACY_GAME_RESEARCH")

    def row(self):
        rows = []
        M.bet(rows, None, "Total", "Over 50", 50, -110, .6, .5)
        return rows[0]

    def test_integer_line_reports_unmodelled_push(self):
        a = R.quant_arithmetic_audit([self.row()])
        self.assertEqual(a["integer_line_push_unmodelled"], 1)
        self.assertEqual(a["arithmetic_convention"], "LEGACY_ZERO_PUSH_ASSUMPTION")

    def test_bad_ev_and_probability_fail_closed(self):
        for key, value in (("ev_blend", 42), ("p_model", float("nan")),
                           ("odds", 0), ("p_blend", .99)):
            with self.subTest(key=key):
                row = self.row()
                row[key] = value
                with self.assertRaisesRegex(R.Fail, "QUANT_ARITHMETIC_MISMATCH"):
                    R.quant_arithmetic_audit([row])


class ShadowPropMeans(unittest.TestCase):
    def run_shadow(self, intake, cap):
        import datetime as dt
        _, _, _, ctx = R.run(intake, cap,
                              dt.datetime.fromisoformat("2026-11-21T17:00:00+00:00"),
                              lambda *_: cap["_weather"])
        return ctx["shadow_prop_means"]

    def test_odds_and_line_perturbation_do_not_change_shadow(self):
        import copy
        original = self.run_shadow(copy.deepcopy(INTAKE), fixture())
        changed = copy.deepcopy(INTAKE)
        changed["props"][0]["overOdds"] = -150
        changed["props"][0]["line"] = 80.5
        result = self.run_shadow(changed, fixture())
        self.assertEqual(original, result)
        self.assertEqual(original["attempts"], 2)
        self.assertEqual(original["mean_only"], 1)
        self.assertEqual(original["blocked"], 1)
        mean = next(r for r in original["rows"] if r["status"] == "MEAN_ONLY")
        self.assertEqual(len(mean["feature_values_sha256"]), 64)
        self.assertFalse(mean["pit_verified"])
        self.assertIsNone(mean["distribution"])
        self.assertFalse(mean["release_ready"])

    def test_all_game_quote_perturbations_preserve_forecasts(self):
        import copy
        import datetime as dt
        original = copy.deepcopy(INTAKE)
        original["lines"][0].update({
            "homeTT": 20.5, "homeTTOver": -110, "homeTTUnder": -110,
            "awayTT": 17.5, "awayTTOver": -105, "awayTTUnder": -115,
            "h1Spread": 1.5, "h1HomeOdds": -110, "h1AwayOdds": -110,
            "h1Total": 18.5, "h1Over": -110, "h1Under": -110,
        })
        changed = copy.deepcopy(original)
        thresholds = {"spread", "overUnder", "homeTT", "awayTT",
                      "h1Spread", "h1Total"}
        prices = {"spreadHomeOdds", "spreadAwayOdds", "overOdds",
                  "underOdds", "homeMoneyline", "awayMoneyline",
                  "homeTTOver", "homeTTUnder", "awayTTOver", "awayTTUnder",
                  "h1HomeOdds", "h1AwayOdds", "h1Over", "h1Under"}
        for line in changed["lines"]:
            for key in thresholds & line.keys():
                line[key] += 7
            for key in prices & line.keys():
                line[key] = 145 if line[key] < 0 else -160
        for prop in changed["props"]:
            prop["line"] += 10
            prop["overOdds"] = -150
        self.assertNotEqual(original["lines"], changed["lines"])
        self.assertNotEqual(original["props"], changed["props"])

        def run(intake):
            cap = fixture()
            return R.run(intake, cap,
                         dt.datetime.fromisoformat("2026-11-21T17:00:00+00:00"),
                         lambda *_: cap["_weather"])

        _, forecasts_a, _, ctx_a = run(original)
        _, forecasts_b, _, ctx_b = run(changed)
        self.assertEqual(len(forecasts_a), 1)
        self.assertEqual(forecasts_a, forecasts_b)
        self.assertEqual(ctx_a["shadow_prop_means"], ctx_b["shadow_prop_means"])
        self.assertEqual(ctx_a["shadow_prop_means"]["mean_only"], 1)
        self.assertEqual(ctx_a["shadow_prop_means"]["blocked"], 1)

    def test_feature_change_changes_hash_and_mean(self):
        import copy
        old = self.run_shadow(copy.deepcopy(INTAKE), fixture())
        cap = fixture()
        for r in cap["player_rushing"]:
            if r["statType"] == "YDS":
                r["stat"] = 900
        new = self.run_shadow(copy.deepcopy(INTAKE), cap)
        before = next(r for r in old["rows"] if r["status"] == "MEAN_ONLY")
        after = next(r for r in new["rows"] if r["status"] == "MEAN_ONLY")
        self.assertNotEqual(before["feature_values_sha256"], after["feature_values_sha256"])
        self.assertGreater(after["mean"], before["mean"])

    def test_missing_or_duplicate_yardage_blocks_shadow(self):
        import copy
        for duplicate in (False, True):
            cap = fixture()
            source = cap["player_rushing"]
            yard = next(r for r in source if r["statType"] == "YDS")
            if duplicate:
                source.append(copy.deepcopy(yard))
            else:
                source.remove(yard)
            result = self.run_shadow(copy.deepcopy(INTAKE), cap)
            self.assertEqual(result["mean_only"], 0)
            self.assertEqual(result["blocked"], 2)
            self.assertTrue(any("SOURCE_INPUT_INVALID" in r["reason"]
                                for r in result["rows"]))


if __name__ == "__main__":
    unittest.main()
