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
    pl = lambda cat, team, player, st, v: {"team": team, "player": player, "category": cat, "statType": st, "stat": v}
    return {
        "games": [{"id": 1, "season": 2026, "week": 13, "homeTeam": "Michigan", "awayTeam": "UCLA",
                   "neutralSite": False, "venueId": 10, "venue": "Michigan Stadium",
                   "startDate": "2026-11-21T20:30:00Z", "completed": False},
                  {"id": 2, "season": 2026, "week": 13, "homeTeam": "Tennessee", "awayTeam": "LSU",
                   "neutralSite": False, "venueId": 11, "venue": "Neyland", "startDate": "2026-11-21T16:00:00Z",
                   "completed": False}] + [
            {"id": 100 + i, "homeTeam": t, "awayTeam": "Filler", "startDate": f"2026-10-{i+1:02d}T18:00:00Z",
             "completed": True} for t in teams for i in range(10)],
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

if __name__ == "__main__":
    unittest.main()
