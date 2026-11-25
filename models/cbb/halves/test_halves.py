"""Unit tests for the CBB halves runtime (stdlib only, offline). PAPER/0u, NON_COUNTED.

Run from models/cbb:  python -m unittest -v halves.test_halves
"""
import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from halves import halves_model as HM  # noqa: E402
from halves import halves_pricing as HP  # noqa: E402


def _variant(mean_feats, mean_coef, sd_feats, sd_coef, shape=None, requires=(), name="base", beta=0.5):
    return {"name": name, "requires": list(requires),
            "mean": {"features": mean_feats, "coef": mean_coef},
            "sd": {"features": sd_feats, "coef": sd_coef},
            "shape": shape or {"kind": "normal"},
            "beta_fg": beta, "fg_resid_sd_fit": 13.0, "cond_resid_sd": 6.0}


def synthetic_coefficients():
    """Hand-built coefficients (not fitted) so the runtime contract is tested independently."""
    emp = {"kind": "empirical", "z_knots": [-3.0, -1.0, 0.0, 1.0, 3.0],
           "p_knots": [0.002, 0.16, 0.5, 0.84, 0.998]}
    t = {}
    for p, share in (("H1", 0.47), ("H2", 0.53), ("H2REG", 0.51)):
        t[p + "_MARGIN"] = {"variants": [_variant(["M"], [share], ["1"], [math.log(8.0)])]}
        t[p + "_TOTAL"] = {"variants": [
            _variant(["T", "poss_dev"], [share, 0.3], ["1"], [math.log(10.0)], requires=["poss"], name="pace"),
            _variant(["T"], [share], ["1"], [math.log(10.5)], shape=emp)]}
        t[p + "_TEAM"] = {"variants": [_variant(None, None, ["1"], [math.log(6.5)])]}
    for p in ("HT_H2", "HT_H2REG"):
        t[p + "_MARGIN"] = {"variants": [_variant(["M", "m1"], [0.5, -0.05], ["1", "abs_m1_10"], [math.log(8.0), 0.0], beta=None)]}
        t[p + "_TOTAL"] = {"variants": [_variant(["1", "T", "t1"], [10.0, 0.4, 0.1], ["1"], [math.log(10.0)], beta=None)]}
        t[p + "_TEAM"] = {"variants": [_variant(None, None, ["1"], [math.log(6.5)], beta=None)]}
    return {"model_version": "synthetic-test", "label": "PAPER_0U", "counting": "NON_COUNTED",
            "default_early": 0.1, "targets": t, "_sha256": "synthetic"}


C = synthetic_coefficients()


def dist(period="H1", **kw):
    return HM.project_period(period, kw.pop("fg_home", 75.0), kw.pop("fg_away", 70.0), coefficients=C, **kw)


class PMFTests(unittest.TestCase):
    def test_pmf_normalised_and_centered(self):
        for shape in ({"kind": "normal"}, C["targets"]["H1_TOTAL"]["variants"][1]["shape"]):
            p = HM.IntegerPMF(33.3, 7.0, shape)
            self.assertAlmostEqual(sum(p.p), 1.0, places=12)
            self.assertLess(abs(p.mean() - 33.3), 0.35)

    def test_prob_partition(self):
        p = HM.IntegerPMF(2.4, 8.0, {"kind": "normal"})
        for x in (-3, -2.5, 0, 0.5, 7):
            self.assertAlmostEqual(p.prob_gt(x) + p.prob_eq(x) + p.prob_lt(x), 1.0, places=12)
        self.assertEqual(p.prob_eq(2.5), 0.0)
        self.assertGreater(p.prob_eq(2), 0.0)

    def test_empirical_shape_monotone_with_tails(self):
        sh = C["targets"]["H1_TOTAL"]["variants"][1]["shape"]
        zs = [-8, -3.5, -3, -1, 0, 0.5, 1, 3, 3.5, 8]
        vals = [HM.shape_cdf(sh, z) for z in zs]
        self.assertEqual(vals, sorted(vals))
        self.assertTrue(0 < vals[0] < 1e-6 and 1 - 1e-6 < vals[-1] < 1)
        self.assertAlmostEqual(HM.shape_cdf(sh, 0.0), 0.5)

    def test_invalid_sd(self):
        with self.assertRaises(HM.HalvesHold):
            HM.IntegerPMF(1.0, 0.0, {"kind": "normal"})


class ProjectionTests(unittest.TestCase):
    def test_h1_means_and_labels(self):
        d = dist()
        self.assertEqual(d["label"], "PAPER_0U"); self.assertEqual(d["counting"], "NON_COUNTED")
        self.assertEqual(d["kind"], "PREGAME")
        self.assertAlmostEqual(d["mean"]["margin"], 0.47 * 5)
        self.assertAlmostEqual(d["mean"]["total"], 0.47 * 145)
        self.assertAlmostEqual(d["mean"]["home"] + d["mean"]["away"], d["mean"]["total"])
        self.assertAlmostEqual(d["mean"]["home"] - d["mean"]["away"], d["mean"]["margin"])
        self.assertEqual(d["variants"]["total"], "base")

    def test_variant_selection_uses_pace_when_given(self):
        d = dist(fg_poss=72.0)
        self.assertEqual(d["variants"]["total"], "pace")
        self.assertAlmostEqual(d["mean"]["total"], 0.47 * 145 + 0.3 * 4)

    def test_pregame_and_halftime_are_distinct_and_guarded(self):
        pre = dist("H2")
        self.assertEqual(pre["kind"], "PREGAME"); self.assertTrue(pre["overtime_included"])
        with self.assertRaises(HM.HalvesHold):
            dist("H2", h1_home=40, h1_away=30)  # pregame must not see the H1 score
        with self.assertRaises(HM.HalvesHold):
            dist("HT_H2")  # halftime requires the H1 score
        ht = dist("HT_H2", h1_home=40, h1_away=30)
        self.assertEqual(ht["kind"], "HALFTIME_ADJUSTED")
        self.assertAlmostEqual(ht["mean"]["margin"], 0.5 * 5 - 0.05 * 10)
        self.assertAlmostEqual(ht["mean"]["total"], 10 + 0.4 * 145 + 0.1 * 70)
        self.assertFalse(dist("H2REG")["overtime_included"])
        self.assertFalse(dist("HT_H2REG", h1_home=1, h1_away=0)["overtime_included"])

    def test_input_validation(self):
        for bad in (dict(fg_home=float("nan")), dict(fg_home=5.0), dict(min_games=-1)):
            with self.assertRaises(HM.HalvesHold):
                dist(**bad)
        with self.assertRaises(HM.HalvesHold):
            dist("HT_H2", h1_home=40.5, h1_away=30)
        with self.assertRaises(HM.HalvesHold):
            HM.project_period("Q1", 70, 70, coefficients=C)

    def test_fg_sd_override_rescales(self):
        base = dist()["sd"]["margin"]
        wider = dist(fg_margin_sd=16.0)["sd"]["margin"]
        narrower = dist(fg_margin_sd=10.0)["sd"]["margin"]
        self.assertAlmostEqual(wider, math.sqrt(64 + 0.25 * (256 - 169)))
        self.assertLess(narrower, base); self.assertGreater(wider, base)
        self.assertGreaterEqual(dist(fg_margin_sd=0.1)["sd"]["margin"], 6.0)  # floored at conditional noise

    def test_coefficients_label_guard(self):
        bad = copy.deepcopy(C); bad.pop("_sha256"); bad["label"] = "LIVE"
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "c.json"; f.write_text(json.dumps(bad))
            with self.assertRaises(HM.HalvesHold):
                HM.load_coefficients(f)
            bad["label"] = "PAPER_0U"; f.write_text(json.dumps(bad))
            self.assertEqual(len(HM.load_coefficients(f)["_sha256"]), 64)


class PricingTests(unittest.TestCase):
    def test_spread_symmetry_and_push(self):
        d = dist()
        h = HP.price_half_market(d, market="SPREAD", side="home", line=-3.5, american=-110)
        a = HP.price_half_market(d, market="SPREAD", side="away", line=3.5, american=-110)
        self.assertEqual(h["p_push"], 0.0)
        self.assertAlmostEqual(h["p_win"], a["p_loss"]); self.assertAlmostEqual(h["p_loss"], a["p_win"])
        hi = HP.price_half_market(d, market="SPREAD", side="home", line=-2)
        self.assertAlmostEqual(hi["p_push"], d["pmf"]["margin"].pmf(2))
        self.assertAlmostEqual(hi["p_win"] + hi["p_push"] + hi["p_loss"], 1.0)
        self.assertAlmostEqual(hi["p_win"], d["pmf"]["margin"].prob_gt(2))

    def test_total_and_team_totals(self):
        d = dist()
        o = HP.price_half_market(d, market="TOTAL", side="over", line=68)
        u = HP.price_half_market(d, market="TOTAL", side="under", line=68)
        self.assertAlmostEqual(o["p_win"], u["p_loss"]); self.assertAlmostEqual(o["p_push"], u["p_push"])
        self.assertGreater(o["p_push"], 0)
        th = HP.price_half_market(d, market="TEAM_TOTAL_HOME", side="over", line=35.5)
        ta = HP.price_half_market(d, market="TEAM_TOTAL_AWAY", side="over", line=35.5)
        self.assertGreater(th["p_win"], ta["p_win"])  # home projected higher
        self.assertEqual(th["p_push"], 0.0)

    def test_moneyline_tie_rules(self):
        d = dist(fg_home=72, fg_away=72)
        with self.assertRaises(HM.HalvesHold):
            HP.price_half_market(d, market="MONEYLINE", side="home")
        pt = d["pmf"]["margin"].pmf(0)
        push = HP.price_half_market(d, market="MONEYLINE", side="home", tie_rule="TIE_PUSH")
        lose = HP.price_half_market(d, market="MONEYLINE", side="home", tie_rule="TIE_LOSES")
        tie = HP.price_half_market(d, market="MONEYLINE", side="tie", tie_rule="THREE_WAY")
        self.assertAlmostEqual(push["p_push"], pt); self.assertEqual(lose["p_push"], 0.0)
        self.assertAlmostEqual(lose["p_loss"], push["p_loss"] + pt)
        self.assertAlmostEqual(tie["p_win"], pt)
        self.assertGreater(pt, 0.02)
        with self.assertRaises(HM.HalvesHold):
            HP.price_half_market(d, market="MONEYLINE", side="tie", tie_rule="TIE_PUSH")

    def test_ev_formula_push_aware_and_uncapped(self):
        d = dist()
        q = HP.price_half_market(d, market="SPREAD", side="home", line=-2, american=+150)
        self.assertAlmostEqual(q["ev_per_unit"], q["p_win"] * 1.5 - q["p_loss"])
        self.assertAlmostEqual(q["fair_american"], HP.prob_to_american(q["p_win"] / (q["p_win"] + q["p_loss"])))
        big = HP.price_half_market(d, market="SPREAD", side="home", line=+20.5, american=+500)
        self.assertGreater(big["ev_per_unit"], 3.0)  # no cap anywhere
        self.assertEqual(big["approved_stake_u"], 0)

    def test_line_and_price_validation(self):
        d = dist()
        for kw in (dict(market="SPREAD", side="home", line=-3.25), dict(market="TOTAL", side="over", line=0),
                   dict(market="TOTAL", side="home", line=60.5), dict(market="FOO", side="home", line=1.5),
                   dict(market="SPREAD", side="home", line=-3.5, american=50)):
            with self.assertRaises(HM.HalvesHold):
                HP.price_half_market(d, **kw)

    def test_no_vig(self):
        a, b = HP.no_vig_two_way(-110, -110)
        self.assertAlmostEqual(a, 0.5); self.assertAlmostEqual(a + b, 1.0)

    def test_board_row_helper(self):
        row = {"period": "HT_H2", "market": "TOTAL", "side": "under", "line": 75.5, "american": -105,
               "fg_home": 74, "fg_away": 66, "h1_home": 38, "h1_away": 30, "min_games": 3}
        q = HP.price_half_board_row(row, coefficients=C)
        self.assertEqual(q["kind"], "HALFTIME_ADJUSTED"); self.assertIn("ev_per_unit", q)


@unittest.skipUnless(HM.DEFAULT_COEFFICIENTS.exists(), "shipped coefficients not present")
class ShippedCoefficientsTests(unittest.TestCase):
    def test_shipped_file_contract(self):
        c = HM.load_coefficients()
        self.assertEqual(c["label"], "PAPER_0U"); self.assertEqual(c["counting"], "NON_COUNTED")
        self.assertEqual(c["approved_stake_u"], 0)
        self.assertNotIn(c["untouched_test_season"], c["trained_seasons"])
        for p in HM.PERIODS:
            for k in ("MARGIN", "TOTAL", "TEAM"):
                self.assertIn(f"{p}_{k}", c["targets"])

    def test_shipped_typical_game_is_sane(self):
        c = HM.load_coefficients()
        h1 = HM.project_period("H1", 76.0, 68.0, coefficients=c, min_games=10, fg_poss=68.0)
        h2 = HM.project_period("H2", 76.0, 68.0, coefficients=c, min_games=10, fg_poss=68.0)
        self.assertTrue(60 < h1["mean"]["total"] < 75 and 2 < h1["mean"]["margin"] < 6)
        self.assertTrue(66 < h2["mean"]["total"] < 82)
        self.assertTrue(5 < h1["sd"]["margin"] < 12 and 6 < h1["sd"]["total"] < 14)
        for p in ("H1", "H2"):
            d = h1 if p == "H1" else h2
            self.assertAlmostEqual(sum(d["pmf"]["margin"].p), 1.0, places=9)
        ht = HM.project_period("HT_H2", 76.0, 68.0, coefficients=c, min_games=10, fg_poss=68.0,
                               h1_home=30, h1_away=40, h1_poss=34.0)
        self.assertEqual(ht["variants"]["total"], "pace")
        self.assertNotAlmostEqual(ht["mean"]["margin"], h2["mean"]["margin"], places=3)

    def test_shipped_joint_matches_reported_hash_and_loads(self):
        from halves import halves_joint as HJ
        j = HJ.load_joint()
        self.assertEqual(j["label"], "PAPER_0U")
        self.assertNotIn(j["untouched_test_season"], j["trained_seasons"])
        self.assertIn("secondary_reuse_note", j)
        d = HJ.project_period_joint("H1", 76.0, 68.0, coefficients=HM.load_coefficients(),
                                    min_games=10, fg_poss=68.0, joint=j)
        self.assertIn("joint", d)
        self.assertEqual(d["mean"]["margin"], HM.project_period("H1", 76.0, 68.0, coefficients=HM.load_coefficients(),
                                                               min_games=10, fg_poss=68.0)["mean"]["margin"])


if __name__ == "__main__":
    unittest.main()


class JointTests(unittest.TestCase):
    def test_bivariate_normal_known_values(self):
        import math
        from halves import halves_joint as HJ
        self.assertAlmostEqual(HJ.bivariate_normal_cdf(0, 0, 0.0), 0.25)
        self.assertAlmostEqual(HJ.bivariate_normal_cdf(0, 0, 0.5),
                               0.25 + math.asin(0.5) / (2 * math.pi), places=9)
        self.assertAlmostEqual(HJ.bivariate_normal_cdf(0, 0, -0.5),
                               0.25 + math.asin(-0.5) / (2 * math.pi), places=9)
        self.assertAlmostEqual(HJ.bivariate_normal_cdf(8, 8, 0.3), 1.0, places=5)
        self.assertAlmostEqual(HJ.bivariate_normal_cdf(-8, 0, 0.3), 0.0, places=5)

    def test_independence_is_the_product(self):
        from halves import halves_joint as HJ
        d = dist()
        pm, pt = d["pmf"]["margin"], d["pmf"]["total"]
        for m in range(int(d["mean"]["margin"]) - 2, int(d["mean"]["margin"]) + 3):
            for t in range(int(d["mean"]["total"]) - 2, int(d["mean"]["total"]) + 3):
                p = HJ.joint_cell(pm, pt, m, t, "independent", {})
                self.assertAlmostEqual(p, pm.pmf(m) * pt.pmf(t), places=10)

    def test_positive_rho_increases_same_direction_mass(self):
        from halves import halves_joint as HJ
        d = dist()
        pm, pt = d["pmf"]["margin"], d["pmf"]["total"]
        m0, t0 = int(round(d["mean"]["margin"])), int(round(d["mean"]["total"]))
        pos = HJ.joint_cell(pm, pt, m0 + 6, t0 + 8, "gaussian", {"rho": 0.6})
        neg = HJ.joint_cell(pm, pt, m0 + 6, t0 + 8, "gaussian", {"rho": -0.6})
        ind = HJ.joint_cell(pm, pt, m0 + 6, t0 + 8, "independent", {})
        self.assertGreater(pos, ind)
        self.assertGreater(ind, neg)

    def test_joint_cells_sum_near_one(self):
        from halves import halves_joint as HJ
        d = dist()
        pm, pt = d["pmf"]["margin"], d["pmf"]["total"]
        acc = 0.0
        for m in range(pm.lo, pm.hi + 1):
            for t in range(pt.lo, pt.hi + 1):
                acc += HJ.joint_cell(pm, pt, m, t, "gaussian", {"rho": 0.25})
        self.assertAlmostEqual(acc, 1.0, places=2)

    def test_sample_h1_h2_period_guard(self):
        from halves import halves_joint as HJ
        import random
        h1, h2 = dist("H1"), dist("H2")
        with self.assertRaises(HM.HalvesHold):
            HJ.sample_h1_h2(h2, h1, {"h1_h2": {"kind": "gaussian", "corr": [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}},
                            random.Random(0))
        out = HJ.sample_h1_h2(h1, h2, {"h1_h2": {"kind": "gaussian",
                                                  "corr": [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}},
                              random.Random(1))
        self.assertEqual(out["H1"]["home"] + out["H1"]["away"], out["H1"]["total"])
        self.assertEqual(out["H1"]["home"] - out["H1"]["away"], out["H1"]["margin"])
        self.assertEqual(out["H2"]["home"] + out["H2"]["away"], out["H2"]["total"])

    def test_cholesky_shrinks_a_nearly_singular_matrix(self):
        from halves import halves_joint as HJ
        L = HJ.cholesky([[1.0, 0.99], [0.99, 1.0]])
        self.assertAlmostEqual(L[0][0] ** 2, 1.0, places=6)
