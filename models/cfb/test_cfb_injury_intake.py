"""Offline tests for the manual CFB injury intake (no provider calls)."""
import copy, datetime as dt, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfb_injury_intake as INJ
import cfb_run_it as R
import test_cfb_run_it as F

NOW = "2026-11-21T17:00:00+00:00"
DOC = {"schema": INJ.SCHEMA, "reviewed_utc": "2026-11-21T15:00:00Z", "teams_reviewed": ["Michigan"],
       "injuries": [{"team": "Michigan", "player": "Q One", "position": "QB", "status": "OUT"},
                    {"team": "Michigan", "player": "W Two", "position": "WR", "status": "OUT"},
                    {"team": "Michigan", "player": "R Three", "position": "RB", "starter": True, "status": "QUESTIONABLE"},
                    {"team": "Michigan", "player": "K Four", "position": "K", "status": "OUT"}]}

def write(d):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(d, f); f.close(); return f.name

def go(doc=DOC, intake=None):
    i = copy.deepcopy(intake or F.INTAKE); cap = F.fixture()
    out = R.run(i, cap, dt.datetime.fromisoformat(NOW), lambda *_: cap["_weather"], injury_file=(doc, "x.json"))
    return out, i

class T(unittest.TestCase):
    def test_roles_only_from_position(self):
        self.assertEqual(INJ.role_for("QB", None), "QB")
        self.assertIsNone(INJ.role_for("WR", None)); self.assertIsNone(INJ.role_for("WR", "yes"))
        self.assertEqual(INJ.role_for("te", True), "STAR_SKILL")
        self.assertEqual(INJ.role_for("CB", False), "DB"); self.assertEqual(INJ.role_for("OT", None), "OL")
        self.assertIsNone(INJ.role_for("K", True))

    def test_only_out_applied_and_sources_shown(self):
        (card, projs, wh, ctx), i = go()
        self.assertEqual([(r["player"], r["role"]) for r in ctx["injuries"]], [("Q One", "QB")])
        notes = " | ".join(projs[0]["notes"])
        self.assertIn("Q One OUT applied QB [manual:x.json]", notes)
        self.assertIn("R Three QUESTIONABLE listed only", notes)
        self.assertIn("W Two OUT listed only", notes)        # WR without starter flag
        self.assertIn("injury coverage missing: UCLA", notes)

    def test_applied_qb_moves_projection(self):
        (_, base, _, _), _ = go(dict(DOC, injuries=[]))
        (_, hit, _, _), _ = go()
        self.assertNotEqual(base[0]["margin"], hit[0]["margin"])

    def test_coverage_partial_in_eligibility(self):
        (card, projs, wh, ctx), i = go()
        e = R.to_doc(card, projs, wh, i, dt.datetime.fromisoformat(NOW), [])["card"]["eligibility"]
        self.assertIn("INJURY_COVERAGE_PARTIAL: UCLA", e["reasons"])
        (card, projs, wh, ctx), i = go(dict(DOC, teams_reviewed=["Michigan", "UCLA"]))
        e = R.to_doc(card, projs, wh, i, dt.datetime.fromisoformat(NOW), [])["card"]["eligibility"]
        self.assertFalse(any(r.startswith("INJURY_COVERAGE_PARTIAL") for r in e["reasons"]))

    def test_manual_overrides_inline(self):
        intake = dict(F.INTAKE, injuries=[{"team": "Michigan", "player": "Q One", "role": "QB", "status": "OUT"}])
        d = dict(DOC, injuries=[{"team": "Michigan", "player": "Q One", "position": "QB", "status": "PROBABLE"}])
        (_, _, _, ctx), i = go(d, intake)
        self.assertEqual(ctx["injuries"], [])
        self.assertEqual(i["injuries_listed"][0]["source"], "manual:x.json")

    def test_unmatched_team_never_applied(self):
        d = dict(DOC, teams_reviewed=["Michigan", "Nowhere State"],
                 injuries=[{"team": "Nowhere State", "player": "Z", "position": "QB", "status": "OUT"}])
        (_, _, _, ctx), i = go(d)
        self.assertEqual(ctx["injuries"], []); self.assertTrue(i["injuries_listed"][0]["unmatched_team"])

    def test_load_validates_and_receipts(self):
        d, rec = INJ.load_manual(write(DOC)); self.assertEqual(len(rec["sha256"]), 64)
        for bad in (dict(DOC, schema="x"), dict(DOC, reviewed_utc="soon"),
                    dict(DOC, injuries=[{"team": "Ohio State", "player": "A", "status": "OUT"}]),
                    dict(DOC, injuries=[{"team": "Michigan", "player": "A", "status": "GTD"}])):
            with self.assertRaises(INJ.InjuryFileError): INJ.load_manual(write(bad))

    def test_example_file_valid(self):
        INJ.load_manual(os.path.join(os.path.dirname(__file__), "injuries", "EXAMPLE.json"))

    def test_no_coverage_list_keeps_legacy_eligibility(self):
        fresh = {"injuries": [], "injuries_reviewed_utc": "2026-11-21T14:00:00Z"}
        self.assertEqual(R.eligibility(fresh, dt.datetime.fromisoformat(NOW), ["UCLA"])["reasons"],
                         ["MODEL_UNVALIDATED_PAPER_0U"])

if __name__ == "__main__":
    unittest.main()
