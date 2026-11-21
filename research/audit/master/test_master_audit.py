"""Synthetic regression tests for the master audit layer. Run:
    python -m research.audit.master.test_master_audit
"""
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from research.audit.master import odds, stats, audits, props_corr as pc, projections as pj, pipeline  # noqa: E402

T0 = "2026-11-16T12:00:00-06:00"
KO = "2026-11-16T15:25:00-06:00"


def row(i, p=.55, o=-110, res="W", **kw):
    base = {"pred_id": f"p{i}", "game_id": f"g{i // 3}", "sport": "NFL", "market": "spread", "side": "home",
            "model_prob": p, "odds": o, "book": "DK", "odds_ts": T0, "pred_ts": T0, "kickoff_ts": KO,
            "result": res, "rule_version": "v1", "inputs": [{"name": "epa", "value": 0.1, "ts": T0}]}
    base.update(kw)
    return base


class Odds(unittest.TestCase):
    def test_conversions(self):
        self.assertAlmostEqual(odds.american_to_decimal(-110), 1.90909, 4)
        self.assertAlmostEqual(odds.american_to_decimal(150), 2.5)
        self.assertAlmostEqual(odds.decimal_to_american(2.5), 150)
        self.assertAlmostEqual(odds.implied_prob(-110), .52381, 4)
        self.assertEqual(odds.decimal_to_fractional(2.5), "3/2")
        with self.assertRaises(ValueError):
            odds.american_to_decimal(50)

    def test_no_vig_sums_to_one(self):
        for m in ("multiplicative", "additive", "power", "shin"):
            self.assertAlmostEqual(sum(odds.no_vig([-110, -110], m)), 1, 4)
            self.assertAlmostEqual(odds.no_vig([-110, -110], m)[0], .5, 4)
        self.assertAlmostEqual(odds.overround([-110, -110]), .04762, 4)

    def test_ev_and_kelly(self):
        self.assertAlmostEqual(odds.ev_per_unit(.5, 100), 0)
        self.assertAlmostEqual(odds.ev_per_unit(.55, -110), .05, 3)
        self.assertGreater(odds.ev_per_unit(.5, 100, p_push=.1), -1e-9)
        self.assertAlmostEqual(odds.kelly_fraction(.55, 100), .10)
        self.assertEqual(odds.kelly_fraction(.4, -110), 0)
        self.assertAlmostEqual(odds.breakeven_prob(-110), .52381, 4)

    def test_line_shop_clv(self):
        r = odds.line_shopping({"A": -115, "B": -108, "C": -110})
        self.assertEqual(r["best_book"], "B")
        c = odds.clv(-110, -130, 110)
        self.assertGreater(c["clv_prob"], 0)
        self.assertTrue(c["beat_close"])
        self.assertEqual(odds.spread_clv_points(-3, -4), 1)

    def test_alt_lines(self):
        pmf = {1: .1, 3: .15, 4: .1, 7: .1, 10: .2, 14: .35}
        rows = odds.alt_line_value(-3.5, -110, [(-2.5, -135), (-3, -120)], pmf)
        by = {r["line"]: r for r in rows}
        self.assertAlmostEqual(by[-3]["p_push"], .15)
        self.assertAlmostEqual(by[-2.5]["p_cover"], .9)


class Stats(unittest.TestCase):
    def test_calibration(self):
        rng = random.Random(1)
        p = [rng.uniform(.3, .8) for _ in range(3000)]
        o = [int(rng.random() < x) for x in p]
        self.assertLess(stats.ece(p, o), .04)
        over = [min(.99, x + .15) for x in p]
        tbl = stats.calibration_table(over, o)
        self.assertTrue(any(r["verdict"] == "OVERCONFIDENT" for r in tbl))
        self.assertIn("<svg", stats.reliability_svg(tbl))
        a, b = stats.platt_fit(over[:800], o[:800], iters=300)
        self.assertLess(b, 0)

    def test_performance_keeps_losses(self):
        bets = [row(i, res=r) for i, r in enumerate("WWLLLPW")]
        p = stats.performance(bets)
        self.assertEqual(p["losses"], 3)
        self.assertEqual(p["longest_losing_streak"], 3)
        self.assertAlmostEqual(p["max_drawdown"], 3)
        self.assertAlmostEqual(p["units"], 3 * (100 / 110) - 3)

    def test_bootstrap_and_streaks(self):
        rng = random.Random(2)
        bets = [row(i, res="W" if rng.random() < .52 else "L") for i in range(300)]
        b = stats.bootstrap_roi(bets, iters=500)
        self.assertLess(b["roi_ci95"][0], b["roi_ci95"][1])
        self.assertTrue(0 <= b["p_roi_le_0"] <= 1)
        self.assertGreater(stats.streak_probability(.55, 7, 500, iters=2000), .5)
        sim = stats.bankroll_sim(.55, -110, .02, n_bets=200, iters=300)
        half = stats.bankroll_sim(.55, -110, .02, n_bets=200, iters=300, true_p=.5)
        self.assertGreater(sim["median_final"], half["median_final"])
        self.assertEqual(stats.edge_decay([(60, 100), (50, 100), (40, 100)])["verdict"], "DECAY_LIKELY")


class Audits(unittest.TestCase):
    def test_leakage(self):
        rs = [row(0), row(1, odds_ts="2026-11-16T13:00:00-06:00"),
              row(2, pred_ts="2026-11-16T16:00:00-06:00"),
              row(3, inputs=[{"name": "inj", "value": 1, "ts": "2026-11-16T14:00:00-06:00"}]),
              row(4, inputs=[{"name": "close_odds", "value": -120, "ts": T0}])]
        codes = {f["pred_id"]: f["code"] for f in audits.leakage_audit(rs)}
        self.assertNotIn("p0", codes)
        self.assertEqual(codes["p1"], "ODDS_AFTER_PRED")
        self.assertIn(codes["p2"], ("PRED_AFTER_KICKOFF", "FUTURE_INPUT", "ODDS_AFTER_PRED"))
        self.assertEqual(codes["p3"], "FUTURE_INPUT")
        self.assertEqual(codes["p4"], "POSTGAME_FIELD_AS_INPUT")
        with self.assertRaises(AssertionError):
            audits.assert_no_leakage(rs)
        audits.assert_no_leakage([row(0)])

    def test_quality_never_deletes(self):
        rs = [row(0), row(0), row(1, model_prob=1.4), row(2, player=" Josh Allen "), row(3, player="Josh Allen.")]
        q = audits.data_quality(rs)
        self.assertEqual(q["n_rows_out"], q["n_rows_in"])
        codes = {i["code"] for i in q["issues"]}
        self.assertTrue({"DUPLICATE", "PROB_OUT_OF_RANGE", "INCONSISTENT_ID"} <= codes)
        self.assertEqual(q["corrections"][0]["to"], "Josh Allen")

    def test_largest_edge(self):
        rs = [row(i, p=.5 + i / 100) for i in range(30)]
        rs.append(row(99, p=.9, o=150, odds_ts="2026-11-16T09:00:00-06:00", inputs=[]))
        r = audits.largest_edge_stress(rs, top=5)
        self.assertEqual(r["top"][0]["pred_id"], "p99")
        self.assertIn("STALE_ODDS", r["top"][0]["flags"])
        self.assertIn("NO_INPUT_LINEAGE", r["top"][0]["flags"])
        self.assertFalse(r["converged"])

    def test_backtest_versions_and_append_only(self):
        rules = [{"rule_version": "v1", "active_ts": "2026-11-01T00:00:00-06:00"},
                 {"rule_version": "v2", "active_ts": "2026-11-20T00:00:00-06:00"}]
        rs = [row(0), row(1, rule_version="v2"), row(2, rule_version="vX")]
        b = audits.backtest_audit(rs, rules)
        self.assertEqual(b["prospective"]["n"], 1)
        self.assertEqual(b["retrospective"]["n"], 2)
        new = [row(0, model_prob=.6), row(1)]
        codes = [f["code"] for f in audits.append_only_check(rs, new)]
        self.assertIn("ROW_REWRITTEN", codes)
        self.assertIn("ROW_REMOVED", codes)

    def test_bias_disagreement_clv_ev(self):
        rs = [row(i, projection=60 + i % 5, actual=50, line=55.5, player="A", result="L") for i in range(40)]
        bb = audits.bias_breakdown(rs)
        self.assertEqual(bb["player"][0]["direction"], "OVER_PROJECTS")
        self.assertTrue(bb["player"][0]["repeatable"])
        self.assertTrue(audits.market_disagreement(rs))
        c = audits.clv_report([row(0, close_odds=-130, close_other_odds=110), row(1)])
        self.assertEqual(c["n"], 1)
        ev = audits.ev_inspector([row(0, p=.5, prices={"DK": 105, "FD": -115})], benchmark_book="FD")
        self.assertEqual(ev["edges_that_disappear"][0]["why"], "EDGE_ONLY_AT_BEST_BOOK")


class PropsCorr(unittest.TestCase):
    def test_distributions(self):
        n = pc.over_under(65.5, 70, 20, "normal")
        self.assertAlmostEqual(n["over"] + n["under"] + n["push"], 1)
        self.assertGreater(n["over"], .5)
        p = pc.over_under(0.5, 0.6, dist="poisson")
        self.assertAlmostEqual(p["under"], 0.5488, 3)
        w = pc.over_under(5, 5.2, 2.5, "negbin")
        self.assertGreater(w["push"], 0)
        with self.assertRaises(ValueError):
            pc.over_under(60.5, 60, None, "normal")

    def test_projection_usage(self):
        pr = pc.prop_projection([20, 25, 30], [30, 32, 34], 33, opp_factor=1.2, opp_factor_n=20)
        self.assertAlmostEqual(pr["opp_adj_applied"], 1.1)
        u = pc.usage_redistribution(30, {"A": 25, "B": 15}, {"A": (25, 31, 12)})
        self.assertEqual(u["A"]["basis"], "HISTORICAL_n=12")
        self.assertEqual(u["B"]["basis"], "PROPORTIONAL_PRIOR")

    def test_correlation(self):
        rng = random.Random(4)
        rs = []
        for g in range(200):
            hit = rng.random() < .5
            rs.append({"game_id": g, "market": "rec_yds", "side": "over", "player": "X", "model_prob": .5, "result": "W" if hit else "L"})
            hit2 = hit if rng.random() < .8 else not hit
            rs.append({"game_id": g, "market": "receptions", "side": "over", "player": "X", "model_prob": .5, "result": "W" if hit2 else "L"})
        j = pc.joint_hit_rates(rs)
        self.assertGreater(j[0]["phi"], .4)
        self.assertLess(pc.effective_n(100, .5, 2), 100)
        e = pc.portfolio_exposure([{"id": "a", "game_id": 1, "model_prob": .55, "odds": -110},
                                   {"id": "b", "game_id": 1, "model_prob": .55, "odds": -110}], iters=2000)
        self.assertEqual(len(e["unknown_same_game_pairs"]), 1)
        self.assertEqual(pc.sgp_check([{"model_prob": .5}, {"model_prob": .5}], 250)["status"], "UNPRICED_CORRELATION")


class Projections(unittest.TestCase):
    def test_pace_and_spread(self):
        t = pj.pace_total(100, 100, 100, 115, 110, 110, 115, 112.5)
        self.assertAlmostEqual(t["possessions"], 100)
        self.assertGreater(t["margin_a"], 0)
        self.assertLess(pj.fair_spread(5, 0, 100, 2), 0)
        self.assertAlmostEqual(pj.cover_prob(0, 0, 13), .5)

    def test_elo(self):
        e = pj.Elo()
        self.assertGreater(e.win_prob("A", "B"), .5)
        e.update("A", "B", 30, 10)
        self.assertGreater(e.get("A"), 1500)

    def test_adjustment_registry_blocks_narratives(self):
        reg = pj.AdjustmentRegistry()
        reg.register("rest_diff_per_day", 0.4, 0.1, 1200, oos_confirmed=True)
        reg.register("altitude", 1.0, 0.3, 80, oos_confirmed=True)
        r = reg.apply(-3.0, {"rest_diff_per_day": 2, "revenge": 1, "altitude": 1})
        log = {l["adjustment"]: l for l in r["log"]}
        self.assertAlmostEqual(r["value"], -2.2)
        self.assertEqual(log["revenge"]["reason"], "NARRATIVE_UNQUANTIFIED")
        self.assertTrue(log["altitude"]["reason"].startswith("SAMPLE_"))
        self.assertEqual(len(pj.drop_contradictions([{"side": "Over", "projection": 40, "line": 44.5},
                                                      {"side": "Under", "projection": 40, "line": 44.5}])), 1)


class Pipeline(unittest.TestCase):
    def test_gates_and_ledger(self):
        now = "2026-11-16T12:10:00-06:00"
        cands = [row(0, p=.58, prices={"DK": -110, "FD": -105}, result=""), row(1, p=.45, result=""),
                 row(2, p=.6, odds_ts="2026-11-16T13:00:00-06:00", result=""), row(3, p=.75, o=100, result="")]
        res = pipeline.run_gates(cands, now=now)
        ids = {r["pred_id"]: r for r in res["candidates"] + res["blocked"]}
        self.assertEqual(ids["p0"]["best_book"], "FD")
        self.assertEqual(ids["p1"]["audit_status"], "BLOCKED")
        self.assertEqual(ids["p2"]["audit_status"], "BLOCKED")
        self.assertIn("LARGE_EDGE_REVIEW", ids["p3"]["reason_codes"])
        for r in res["candidates"]:
            for f in pipeline.REQUIRED_OUTPUT:
                self.assertIn(f, r)
        evs = [r["ev_per_unit"] for r in res["candidates"]]
        self.assertEqual(evs, sorted(evs, reverse=True))
        card = pipeline.card_view(res)
        self.assertNotIn("audit_status", card[0])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.csv")
            self.assertEqual(pipeline.ledger_append(path, res["candidates"] + res["blocked"]), 4)
            self.assertEqual(pipeline.ledger_append(path, res["candidates"]), 0)
            with self.assertRaises(ValueError):
                pipeline.ledger_append(path, [row(9, pred_ts=KO)])
            import csv
            with open(path) as fh:
                led = list(csv.DictReader(fh))
            g = pipeline.grade(led, {"p0": {"result": "W", "close_odds": -120}, "p1": {"result": "L"}})
            rep = pipeline.postgame_report(g)
            self.assertEqual(rep["graded"], 2)
            self.assertIn("performance_BLOCKED", rep)


if __name__ == "__main__":
    unittest.main(verbosity=1)
