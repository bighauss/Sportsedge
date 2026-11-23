import os, unittest
import torvik_trank_intake as T
import cbb_game_mc as G
import cbb_league_context as C
import sportsedge_cbb_model as M

FIX = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "trank_2027_extract.txt")).read()
CAP, TIP = "2026-11-23T12:30:00Z", "2026-11-23T19:00:00Z"
R = T.intake(FIX, CAP, TIP); TEAMS = {k: T.to_model_team(v) for k, v in R["rows"].items()}
BLOWOUTS = (("Colorado St.", "Arizona"), ("Washington", "BYU"))   # (away, home), neutral

class Intake(unittest.TestCase):
    def test_league_header(self):
        L = R["league"]; self.assertEqual((L["oe"], L["tempo"]), (107.3, 69.3)); self.assertAlmostEqual(L["efg"], .507)
    def test_wrapped_rows_recovered(self):
        self.assertEqual(R["rows"]["VCU"]["drb"], 32.7); self.assertEqual(R["rows"]["Appalachian St."]["tord"], 13.6)
    def test_contaminated_labels_cleaned_and_flagged(self):
        for n in ("Nebraska", "UCLA"): self.assertTrue(R["rows"][n]["label_cleaned"])
        self.assertNotIn("Nebraska vs. 90 Butler", R["rows"])
    def test_bad_rows_quarantined_not_guessed(self):
        reasons = " ".join(q["reason"] for q in R["quarantine"])
        self.assertIn("nonfinite", reasons); self.assertIn("expected 24 cells", reasons); self.assertNotIn("Bad Row", R["rows"])
    def test_capture_must_precede_tipoff(self):
        with self.assertRaises(T.Blocked): T.intake(FIX, "2026-11-23T19:00:00Z", TIP)
        with self.assertRaises(T.Blocked): T.intake(FIX, "2026-11-23T12:30:00", TIP)
    def test_provenance_unauthenticated(self):
        self.assertEqual(R["provenance"], "EXTRACTED_TEXT_NOT_BYTE_AUTHENTICATED"); self.assertEqual(len(R["source_text_sha256"]), 64)
    def test_model_mapping_rebounds(self):
        m = T.to_model_team(R["rows"]["VCU"]); self.assertAlmostEqual(m["orb_d"], 67.3); self.assertEqual(m["adj_t"], 69.2)
    def test_team_resolution_blocks_unknown(self):
        self.assertEqual(T.resolve_team("OleMiss", R["rows"]), "Mississippi")
        with self.assertRaises(T.Blocked): T.resolve_team("Nonexistent U", R["rows"])

class LeagueContext(unittest.TestCase):
    def test_context_changes_and_restores_constants(self):
        g = dict(game_id="x", home="Arizona", away="Colorado St.", neutral=1)
        before = dict(M.LEAGUE); stale = C.project(g, TEAMS); fresh = C.project(g, TEAMS, R["league"])
        self.assertEqual(M.LEAGUE, before); self.assertLess(fresh["total"], stale["total"] - 2)

class MarginShrink(unittest.TestCase):
    """Blowout margin must keep >=90% of the ratings gap (owner condition). Incumbent is characterized, variant is gated."""
    def _ratio(self, fn, away, home):
        g = dict(game_id="x", home=home, away=away, neutral=1)
        gap = C.ratings_gap_margin(g, TEAMS, R["league"]); return fn(g) / gap, gap
    def test_incumbent_blend_shrinks_blowouts_known_defect(self):
        for a, h in BLOWOUTS:
            ratio, gap = self._ratio(lambda g: C.project(g, TEAMS, R["league"])["margin"], a, h)
            self.assertGreater(gap, 8); self.assertLess(ratio, 0.9, f"{h} incumbent ratio {ratio:.2f}")
    def test_research_variant_keeps_at_least_90pct_of_ratings_gap(self):
        for a, h in BLOWOUTS:
            ratio, _ = self._ratio(lambda g: C.project_ratings_anchored(g, TEAMS, R["league"])["margin"], a, h)
            self.assertGreaterEqual(ratio, 0.90, f"{h} variant ratio {ratio:.2f}")
    def test_variant_w_zero_equals_ratings_gap(self):
        g = dict(game_id="x", home="BYU", away="Washington", neutral=1)
        self.assertAlmostEqual(C.project_ratings_anchored(g, TEAMS, R["league"], 0.0)["margin"], C.ratings_gap_margin(g, TEAMS, R["league"]))
    def test_variant_rejects_bad_weight(self):
        with self.assertRaises(ValueError): C.project_ratings_anchored(dict(game_id="x", home="BYU", away="Washington", neutral=1), TEAMS, R["league"], 1.5)

class MC(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.s = G.simulate("g", 80.0, 74.0, 70.0, .10, .10, 11.0, 2.5, n=4000, seed=3)
    def test_ml_sums_to_one_no_unresolved(self):
        a, b = G.price(self.s, "ML", "home"), G.price(self.s, "ML", "away"); self.assertEqual(self.s["unresolved"], 0); self.assertAlmostEqual(a["win"] + b["win"], 1)
    def test_adversarial_inputs_blocked(self):
        for bad in (("ML", "garbage", None), ("TOTAL", "home", 150.5), ("NOPE", "home", None), ("TOTAL", "over", float("nan")), ("TOTAL", "over", None)):
            with self.assertRaises(G.Blocked): G.price(self.s, *bad)
        with self.assertRaises(G.Blocked): G.simulate("g", 80.0, 74.0, 70.0, .1, .1, 11.0, 2.5, n=-1)
        with self.assertRaises(G.Blocked): G.simulate("g", float("nan"), 74.0, 70.0, .1, .1, 11.0, 2.5, n=500)
    def test_h1_ml_requires_explicit_tie_rule(self):
        with self.assertRaises(G.Blocked): G.price(self.s, "H1_ML", "home")
        lose = G.price(self.s, "H1_ML", "home", tie_rule="LOSE_3WAY"); ref = G.price(self.s, "H1_ML", "home", tie_rule="REFUND")
        self.assertEqual(lose["push"], 0); self.assertGreater(ref["push"], 0)
    def test_integer_push_and_half_point_none(self):
        self.assertGreater(G.price(self.s, "TOTAL", "over", 154)["push"] + G.price(self.s, "SPREAD", "home", -6)["push"], 0)
        self.assertEqual(G.price(self.s, "TOTAL", "over", 154.5)["push"], 0)
    def test_determinism_and_hashes(self):
        a = G.simulate("g", 80.0, 74.0, 70.0, .1, .1, 11.0, 2.5, n=500, seed=9); b = G.simulate("g", 80.0, 74.0, 70.0, .1, .1, 11.0, 2.5, n=500, seed=9)
        c = G.simulate("g", 80.0, 74.0, 70.0, .1, .1, 11.0, 2.5, n=500, seed=10)
        self.assertEqual((a["scenario_sha256"], a["config_sha256"]), (b["scenario_sha256"], b["config_sha256"])); self.assertNotEqual(a["scenario_sha256"], c["scenario_sha256"])
    def test_p3_cap_and_infeasible(self):
        s = G.simulate("g", 80.0, 74.0, 70.0, .30, .10, 11.0, 2.5, n=200, seed=1); self.assertTrue(s["p3_caps"]["home"]["capped"])
        with self.assertRaises(G.Blocked): G.pmf_from_moments(1.0, 0.0001, 0.2)
    def test_props_blocked(self): self.assertEqual(self.s["blocked"]["PLAYER_PROPS"], "NO_PLAYER_FORECAST")

if __name__ == "__main__": unittest.main()
