"""Offline regression tests for the CBB rolling-origin backtest (stdlib unittest + numpy)."""
import math
import random
import unittest
from datetime import date, timedelta

from research.cbb_backtest import harness as H, models as M, data as D


def synth(season=2024, n_teams=40, days=70, seed=3, hca=3.0):
    rng = random.Random(seed)
    strength = {str(100 + i): rng.gauss(0, 6) for i in range(n_teams)}
    games, gid = [], 1
    start = date(season - 1, 11, 4)
    for d in range(days):
        teams = list(strength); rng.shuffle(teams)
        for i in range(0, len(teams) - 1, 2):
            h, a = teams[i], teams[i + 1]
            neutral = rng.random() < .15
            poss = 68 + rng.gauss(0, 3)
            m = strength[h] - strength[a] + (0 if neutral else hca) + rng.gauss(0, 10)
            t = 140 + rng.gauss(0, 12)
            hp, ap = max(30, round((t + m) / 2)), max(30, round((t - m) / 2))
            if hp == ap:
                hp += 1
            games.append(dict(event_id=str(gid), day=start + timedelta(days=d), home=h, away=a, neutral=neutral,
                              home_points=hp, away_points=ap, margin=hp - ap, total=hp + ap,
                              possessions=poss, box_hold=None, season=season))
            gid += 1
    return games


class Math(unittest.TestCase):
    def test_line_probs_push_and_symmetry(self):
        o, p, u = H.line_probs(0, 10, 0)
        self.assertAlmostEqual(o, u); self.assertGreater(p, 0); self.assertAlmostEqual(o + p + u, 1)
        o, p, u = H.line_probs(0, 10, .5)
        self.assertEqual(p, 0.0)

    def test_novig(self):
        self.assertAlmostEqual(H.novig(-110, -110), .5)
        self.assertGreater(H.novig(-200, 170), .6)
        self.assertIsNone(H.novig(None, -110))

    def test_max_drawdown(self):
        self.assertEqual(H.max_drawdown([1, -1, -1, 2, -3]), 3)
        self.assertEqual(H.max_drawdown([1, 1]), 0)

    def test_ece_perfect(self):
        e, bins = H.ece([(.25, 0), (.25, 0), (.25, 0), (.25, 1)])
        self.assertAlmostEqual(e, 0)

    def test_cluster_boot_by_date(self):
        days = [date(2024, 1, i % 20 + 1) for i in range(200)]
        lo, hi = H.cluster_boot(days, [1.0] * 200, reps=50)
        self.assertEqual((lo, hi), (1.0, 1.0))
        self.assertEqual(H.cluster_boot(days[:5], [1.0] * 5), (None, None))

    def test_blend_grid_is_owner_canonical(self):
        self.assertEqual(H.BLEND_WEIGHTS, (1.0, .875, .75, .625, .5, .375, .25, .125, 0.0))
        self.assertEqual(len(H.BLEND_WEIGHTS), 9)

    def test_splits_disjoint_and_ordered(self):
        v, t, tr = set(H.SPLITS["validation"]), set(H.SPLITS["test"]), set(H.SPLITS["train"])
        self.assertFalse(v & t or v & tr or t & tr)
        self.assertLess(max(tr), min(v)); self.assertLess(max(v), min(t))


class Odds(unittest.TestCase):
    def item(self, pid, **kw):
        base = {"provider_id": pid, "provider": pid, "not_a_book": False}
        base.update(kw)
        return base

    def test_preference_and_exclusions(self):
        items = [self.item("1003", close_spread_home=-9.0), self.item("59", close_spread_home=20.0),
                 self.item("200", close_spread_home=15.0), self.item("58", close_spread_home=-3.5, close_total=140.5),
                 self.item("100", close_spread_home=-4.5, close_total=141.5, close_ml_home=-200, close_ml_away=170)]
        m = D.select_market(items)
        self.assertEqual(m["provider_id"], "100")
        m = D.select_market(items[:4])
        self.assertEqual(m["provider_id"], "58")
        self.assertIsNone(D.select_market(items[:3]))

    def test_current_fallback_flagged_never_invented(self):
        m = D.select_market([self.item("40", current_spread_home=-2.5, current_total=None)])
        self.assertTrue(m["close_from_current_fallback"])
        self.assertEqual(m["close_spread_home"], -2.5)
        self.assertIsNone(m["close_total"]); self.assertIsNone(m["close_ml_home"])

    def test_bad_price_dropped(self):
        m = D.select_market([self.item("40", close_spread_home=-1.5, close_ml_home=50, close_ml_away=-110)])
        self.assertIsNone(m["close_ml_home"]); self.assertEqual(m["close_ml_away"], -110)


class Leakage(unittest.TestCase):
    def test_future_outcomes_do_not_change_forecasts(self):
        g = synth()
        leak = {"origins": 0, "violations": []}
        base = H.forecast_season(g, {}, list(M.BUILTIN), leak)
        cut = date(2023, 12, 25)
        g2 = [dict(x, home_points=x["home_points"] + 40, margin=x["margin"] + 40, total=x["total"] + 40)
              if x["day"] >= cut else x for x in g]
        alt = H.forecast_season(g2, {}, list(M.BUILTIN), {"origins": 0, "violations": []})
        a = {r["event_id"]: r["f"] for r in base if r["origin"] <= cut}
        b = {r["event_id"]: r["f"] for r in alt if r["origin"] <= cut}
        self.assertTrue(any(a.values()))
        self.assertEqual(a, b)
        self.assertEqual(leak["violations"], [])

    def test_origin_rule(self):
        g = synth(days=30)
        rows = H.forecast_season(g, {}, ["raw"], {"origins": 0, "violations": []})
        for r in rows:
            self.assertGreaterEqual(r["day"], r["origin"])
            self.assertLess(r["day"], r["origin"] + timedelta(days=7))
            self.assertEqual(r["origin"].weekday(), 0)

    def test_sd_uses_only_prior_residuals(self):
        g = synth()
        rows = H.forecast_season(g, {}, ["raw"], {"origins": 0, "violations": []})
        H.attach_sd_fast(rows, ["raw"])
        got = [r for r in rows if "sd_margin" in r["f"].get("raw", {})]
        self.assertTrue(got)
        for r in got:
            self.assertLess(r["f"]["raw"]["sd_max_day"], r["origin"])
        # slow reference implementation agrees
        rows2 = H.forecast_season(g, {}, ["raw"], {"origins": 0, "violations": []})
        H.attach_sd(rows2, ["raw"])
        for x, y in zip(rows, rows2):
            self.assertEqual(x["f"].get("raw", {}).get("sd_margin"), y["f"].get("raw", {}).get("sd_margin"))


class Models(unittest.TestCase):
    def test_all_builtins_forecast_and_native_parity(self):
        g = synth()
        prior = [x for x in g if x["day"] < date(2024, 1, 1)]
        for name in M.BUILTIN:
            p = M.MODELS[name](prior, {})(g[-1]["home"], g[-1]["away"], False)
            for k in ("home_points", "away_points", "margin", "total"):
                self.assertTrue(math.isfinite(p[k]))
            self.assertAlmostEqual(p["margin"], p["home_points"] - p["away_points"])
        import cbbd_native_score_model as native
        from research.cbb_hca.public_factorial_backtest import context
        ctx = context(prior, M.SHRINK_GAMES)
        ref = native.project(ctx, g[-1]["home"], g[-1]["away"], neutral=True, _need_sd=False)
        got = M.MODELS["native_frozen"](prior, {})(g[-1]["home"], g[-1]["away"], True)
        self.assertEqual(ref["margin"], got["margin"]); self.assertEqual(got["hca_applied"], 0)

    def test_sched_adj_recovers_hca_and_strength(self):
        g = synth(days=90, hca=3.0)
        prior = [x for x in g]
        lg, pace = M._league(prior)
        ratings, h = M.schedule_adjusted(prior, {}, lg, pace, k=0)
        self.assertAlmostEqual(h * pace / 100, 3.0, delta=1.0)

    def test_challenger_plugin(self):
        name = "test_const_" + str(random.random())[2:8]
        M.register(name, lambda prior, carry: (lambda h, a, n: dict(home_points=70.0, away_points=68.0, margin=2.0, total=138.0)))
        try:
            rows = H.forecast_season(synth(days=30), {}, ["raw", name], {"origins": 0, "violations": []})
            self.assertTrue(any(name in r["f"] for r in rows))
            with self.assertRaises(ValueError):
                M.register(name, None)
        finally:
            M.MODELS.pop(name)


class HcaRepair(unittest.TestCase):
    def test_buy_game_visitors_do_not_inflate_repaired_hca(self):
        g = synth(days=40, hca=3.0)
        start = g[0]["day"]
        gid = 10 ** 6
        # 60 one-game visitors lose by ~45 at D1 homes (non-D1 buy games)
        for i in range(60):
            h = str(100 + i % 40)
            g.append(dict(event_id=str(gid + i), day=start + timedelta(days=i % 30), home=h, away=str(9000 + i),
                          neutral=False, home_points=95, away_points=50, margin=45, total=145,
                          possessions=68.0, box_hold=None, season=2024))
        prior = sorted(g, key=lambda x: x["day"])
        native_rule = M.MODELS["native_frozen"](prior, {}).ctx["hca"]["value"]
        repaired = M.repaired_hca(prior)["value"]
        self.assertGreater(native_rule, repaired + 2.0)  # reproduces the confound
        self.assertAlmostEqual(repaired, 3.0, delta=1.5)

    def test_native_frozen_keeps_native_rule(self):
        g = synth(days=40)
        from research.cbb_hca.public_factorial_backtest import context
        self.assertEqual(M.MODELS["native_frozen"](g, {}).ctx["hca"], context(g, M.SHRINK_GAMES)["hca"])


class EndToEnd(unittest.TestCase):
    def test_blend_selection_never_uses_test(self):
        # Rows from a validation season and a test season with synthetic market: selection uses validation only.
        rows = []
        rng = random.Random(1)
        for s in (2023, 2025):
            for i in range(400):
                truth = rng.gauss(0, 10)
                r = {"event_id": f"{s}-{i}", "season": s, "day": date(s, 1, 1) + timedelta(days=i % 60),
                     "origin": date(s, 1, 1), "margin": round(truth + rng.gauss(0, 1)) or 1, "total": 140,
                     "home_points": 0, "away_points": 0, "neutral": False,
                     "f": {"raw": {"margin": truth, "total": 140, "sd_margin": 10, "sd_total": 15}},
                     "mkt": {"close_ml_home": -110, "close_ml_away": -110, "close_spread_home": None, "close_total": None,
                             "close_spread_price_home": None, "close_spread_price_away": None,
                             "close_over_price": None, "close_under_price": None}}
                r["p"] = {"raw": H.probabilities(r, "raw")}
                rows.append(r)
        val = [r for r in rows if r["season"] == 2023]
        best = min(H.BLEND_WEIGHTS, key=lambda w: H.blend_ll(val, "raw", "ml", w)["log_loss"])
        self.assertEqual(best, 1.0)  # informative model beats a flat 50/50 market on validation
        res = H.bet_eval(rows, "raw", "ml", 1.0, "close")[0]
        self.assertGreater(res["n_bets"], 0)
        self.assertGreaterEqual(res["max_drawdown_u"], 0)



class ThreeOutcomeScores(unittest.TestCase):
    def test_push_is_scored_not_dropped(self):
        from research.cbb_backtest import push_scores as P
        row = {"season": 2024, "event_id": "1", "total": 140,
               "mkt": {"close_total": 140},
               "p": {"a": {"total": (.45, .10)}, "b": {"total": (.49, .02)}}}
        got = P.matched_scores([row], ["a", "b"], "total")
        self.assertEqual([r["n"] for r in got], [1, 1])
        self.assertEqual([r["observed_pushes"] for r in got], [1, 1])
        self.assertLess(got[0]["log_loss_3class_eps_clipped"],
                        got[1]["log_loss_3class_eps_clipped"])
        self.assertLess(got[0]["brier_3class_sum"], got[1]["brier_3class_sum"])
        self.assertAlmostEqual(got[0]["push_brier"], .81)

    def test_paired_hold_and_duplicate(self):
        from research.cbb_backtest import push_scores as P
        row = {"season": 2024, "event_id": "1", "margin": 5,
               "mkt": {"close_spread_home": -4.5},
               "p": {"a": {"spread": (.6, 0)}, "b": {"spread": (.7, 0)}}}
        missing = dict(row, event_id="2", p={"a": row["p"]["a"]})
        got = P.matched_scores([row, missing], ["a", "b"], "spread")
        self.assertEqual([(x["n"], x["held_events"]) for x in got], [(1, 1), (1, 1)])
        self.assertAlmostEqual(got[0]["brier_3class_sum"], .32)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_EVENT"):
            P.matched_scores([row, row], ["a", "b"], "spread")

    def test_reject_invalid_probabilities_and_score_exact(self):
        from research.cbb_backtest import push_scores as P
        self.assertEqual(P.score((0, 1, 0), 1), (0, 0))
        for prob in ((.5, .4, .4), (.5, float("nan"), .5), (-.1, .2, .9)):
            with self.assertRaises(ValueError):
                P.score(prob, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class DataQuality(unittest.TestCase):
    def test_quarantine_2023_spread_total_and_all_opens(self):
        m = {"close_spread_home": -3.5, "close_spread_price_home": -110, "close_spread_price_away": -110,
             "close_total": 140.5, "close_over_price": -110, "close_under_price": -110,
             "close_ml_home": -150, "close_ml_away": 130, "open_total": 1.909, "open_spread_home": 2.0}
        q = D.quarantine(m, 2023)
        self.assertIsNone(q["close_spread_home"]); self.assertIsNone(q["close_total"])
        self.assertEqual(q["close_ml_home"], -150)
        self.assertIsNone(q["open_total"]); self.assertIsNone(q["open_spread_home"])
        q = D.quarantine(m, 2024)
        self.assertEqual(q["close_total"], 140.5); self.assertIsNone(q["open_total"])
        self.assertIsNone(D.quarantine(None, 2023))

    def test_site_class_matches_fullgame_rule(self):
        self.assertEqual(D.site_class(True, 1, 1), "NEUTRAL")
        self.assertEqual(D.site_class(False, "3604.0", 3604), "HOME_VERIFIED")
        self.assertEqual(D.site_class(False, 1, 2), "UNVERIFIED")
        self.assertEqual(D.site_class(False, None, 2), "UNVERIFIED")

    def test_d1_set_uses_completed_season_counts(self):
        g = synth(days=40)
        s = M.d1_set(g)
        self.assertTrue(s)
        self.assertFalse(M.d1_set(g[:10]))


class Fg1Adapter(unittest.TestCase):
    def test_requires_previous_season(self):
        from research.cbb_backtest import fg1_adapter as A
        try:
            A._fg()
        except ImportError:
            self.skipTest("models.cbb.fullgame not on this branch (lives on grok-cbb/fullgame-ev-20261125)")
        with self.assertRaises(ValueError):
            A.build_fg1(synth(days=20), {"_history": {}, "_season": 2024})
