"""P0 regressions: player identity, game identity, injury eligibility, freeze recheck,
evidence receipts, raw/market separation. Frozen model unchanged."""
import copy, datetime as dt, json, os, subprocess, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cfb_run_it as R
import test_cfb_run_it as F

NOW = dt.datetime.fromisoformat("2026-11-21T15:00:00+00:00")
def go(intake=None, cap=None, now=NOW):
    cap = cap or F.fixture(); intake = intake or copy.deepcopy(F.INTAKE)
    return R.run(intake, cap, now, lambda *_: cap["_weather"])
def mich(p): return [x for x in p if x["home"] == "Michigan"]
def reasons(wh): return " | ".join(f"{a}: {b}" for a, b in wh)
def prop_rows(card): return [r for r in card if r["market"].startswith("Prop")]

class PlayerIdentity(unittest.TestCase):
    def priced(self, cap, intake):
        card, _, wh, _ = go(intake, cap)
        return [r for r in card if r["market"].startswith("Prop")], reasons(wh)

    def test_prop_bound_to_provider_id(self):
        cap = F.fixture()
        t = R.player_table(cap)
        self.assertIn(("Michigan", "501"), t)
        self.assertEqual(R.match_player("Wayne Knight", ("UCLA", "Michigan"), t), ("Michigan", "501"))

    def test_rename_does_not_remap(self):
        t = R.player_table(F.fixture())
        self.assertIsNone(R.match_player("Wayne Knights", ("UCLA", "Michigan"), t))       # not a prefix remap
        self.assertIsNone(R.match_player("Wayne", ("UCLA", "Michigan"), t))               # prefix needs truncation flag
        self.assertEqual(R.match_player("Wayne", ("UCLA", "Michigan"), t, truncated=True), ("Michigan", "501"))

    def test_missing_id_and_conflicting_id_quarantined(self):
        cap = F.fixture()
        cap["player_rushing"].append({"team": "UCLA", "player": "No Id", "playerId": None, "category": "rushing",
                                      "statType": "CAR", "stat": 10})
        cap["player_rushing"].append({"team": "UCLA", "player": "Wayne Knight", "playerId": "501",
                                      "category": "rushing", "statType": "CAR", "stat": 5})   # same ID, other team
        t = R.player_table(cap)
        self.assertFalse(any(v["name"] == "No Id" for v in t.values()))
        self.assertNotIn(("Michigan", "501"), t)

    def test_wrong_team_not_matched(self):
        t = R.player_table(F.fixture())
        self.assertIsNone(R.match_player("Wayne Knight", ("LSU", "Tennessee"), t))

    def test_duplicate_names_two_ids_withheld(self):
        cap = F.fixture()
        cap["player_rushing"] += [{"team": "UCLA", "player": "Wayne Knight", "playerId": "777", "category": "rushing",
                                   "statType": s, "stat": v} for s, v in (("CAR", 50), ("YDS", 200))]
        self.assertIsNone(R.match_player("Wayne Knight", ("UCLA", "Michigan"), R.player_table(cap)))

class GameIdentity(unittest.TestCase):
    def test_orientation_swap_withheld(self):
        i = copy.deepcopy(F.INTAKE); i["lines"][0]["awayTeam"], i["lines"][0]["homeTeam"] = "Michigan", "UCLA"
        _, p, wh, _ = go(i); self.assertIn("orientation mismatch", reasons(wh)); self.assertEqual(mich(p), [])

    def test_kickoff_mismatch_withheld(self):
        i = copy.deepcopy(F.INTAKE); i["lines"][0]["kickoff_ct"] = "11:00 AM"
        _, p, wh, _ = go(i); self.assertIn("kickoff mismatch", reasons(wh))
        i["lines"][0]["kickoff_ct"] = "2:30 PM"
        _, p, _, _ = go(i); self.assertEqual(len(mich(p)), 1)

    def test_pinned_game_id_blocks_rename_to_other_event(self):
        i = copy.deepcopy(F.INTAKE); i["lines"][0]["cfbd_game_id"] = 2          # LSU@Tenn id, UCLA@Mich names
        _, p, wh, _ = go(i); self.assertIn("intake game id 2 != CFBD 1", reasons(wh)); self.assertEqual(mich(p), [])

    def test_duplicate_event_withheld(self):
        cap = F.fixture(); cap["games"].append(dict(cap["games"][0], id=99))
        _, p, wh, _ = go(cap=cap); self.assertIn("no CFBD game record", reasons(wh)); self.assertEqual(mich(p), [])

class Eligibility(unittest.TestCase):
    def test_never_official_and_reasons(self):
        e = R.eligibility({"lines": []}, NOW)
        self.assertEqual((e["state"], e["approved_stake_u"]), ("RESEARCH_ONLY", 0))
        self.assertIn("INJURY_INTAKE_MISSING", e["reasons"])
        self.assertIn("INJURY_REVIEW_TIME_MISSING", R.eligibility({"injuries": []}, NOW)["reasons"])
        stale = {"injuries": [], "injuries_reviewed_utc": "2026-11-21T05:00:00Z"}
        self.assertIn("INJURY_REVIEW_STALE", R.eligibility(stale, NOW)["reasons"])
        fresh = {"injuries": [], "injuries_reviewed_utc": "2026-11-21T14:00:00Z"}
        self.assertEqual(R.eligibility(fresh, NOW)["reasons"], ["MODEL_UNVALIDATED_PAPER_0U"])

class FreezeAndEvidence(unittest.TestCase):
    def cli(self, d, *extra, now="2026-11-21T15:00:00+00:00"):
        f = os.path.join(d, "i.json"); json.dump(F.INTAKE, open(f, "w"))
        fx = os.path.join(d, "fx.json"); json.dump(F.fixture(), open(fx, "w"))
        return subprocess.run([sys.executable, os.path.join(HERE, "cfb_run_it.py"), f, "--season", "2026",
                               "--out", d, "--fixture", fx, "--now", now, *extra], capture_output=True, text=True), fx

    def test_receipts_raw_and_market_separate(self):
        with tempfile.TemporaryDirectory() as d:
            r, fx = self.cli(d, "--private-dir", os.path.join(d, "priv"))
            self.assertEqual(r.returncode, 0, r.stderr)
            doc = json.load(open(os.path.join(d, "cfb_run_it.json")))
            self.assertEqual(doc["card"]["receipts"][0]["sha256"], R.sha256(open(fx, "rb").read()))
            self.assertEqual(R.sha256(open(os.path.join(d, "priv", "fixture.json"), "rb").read()),
                             doc["card"]["receipts"][0]["sha256"])                  # archived bytes == receipt
            g = doc["model_projections"]["games"][0]
            self.assertNotIn("p_blend", g); self.assertIn("total", g)                # raw record has no market
            self.assertEqual(doc["card"]["eligibility"]["state"], "RESEARCH_ONLY")

    def test_recheck_removes_started_games(self):
        with tempfile.TemporaryDirectory() as d:
            r, _ = self.cli(d)
            self.assertEqual(r.returncode, 0, r.stderr)
            r2 = subprocess.run([sys.executable, os.path.join(HERE, "cfb_run_it.py"), "--recheck", "--out", d,
                                 "--now", "2026-11-21T21:00:00+00:00"], capture_output=True, text=True)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            doc = json.load(open(os.path.join(d, "cfb_run_it.json")))
            self.assertEqual(doc["card"]["rows"], [])
            self.assertIn("kicked off before publication", open(os.path.join(d, "cfb_card.md")).read())

    def test_live_requires_private_dir(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "i.json"); json.dump(F.INTAKE, open(f, "w"))
            r = subprocess.run([sys.executable, os.path.join(HERE, "cfb_run_it.py"), f, "--season", "2026", "--out", d],
                               env={**os.environ, "CFBD_API_KEY": "x"}, capture_output=True, text=True)
            self.assertEqual(r.returncode, 2); self.assertIn("PRIVATE_DIR_REQUIRED", r.stderr)

if __name__ == "__main__":
    unittest.main()
