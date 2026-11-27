"""#455: pinned CFB prop forecasts depend on the posted quote; the challenger's do not.

Synthetic deterministic fixtures only. Characterization tests describe the pinned model's CURRENT
behaviour and are expected to change only when a reviewed fix replaces that model.
"""
import hashlib, inspect, math, sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sportsedge_cfb_model as M
import cfb_prop_independent as P

PINNED_BLOB = "a07f4cd429e344e8ee0d131bdfa8e1ef7a91da20"
USAGE = {"player": "QB One", "team": "Home U", "pos": "QB", "market": "pass_yds",
         "share": 0.95, "eff": 7.2, "games": 10}
GAME = {"id": 1, "homeTeam": "Home U", "awayTeam": "Away U", "week": 10, "neutralSite": False, "venue": "V"}


def _side(ppa):
    return {"plays": 700, "drives": 120, "ppa": ppa, "successRate": 0.42, "explosiveness": 1.2,
            "pointsPerOpportunity": 4.5, "fieldPosition": {"averageStart": 30.0},
            "havoc": {"total": 0.15}, "rushingPlays": {"ppa": 0.05, "successRate": 0.4, "rate": 0.5},
            "passingPlays": {"ppa": 0.15, "successRate": 0.4, "rate": 0.5}}


def _ctx(usage=(USAGE,)):
    adv = [{"team": t, "games": 10, "offense": _side(p), "defense": _side(p)}
           for t, p in (("Home U", 0.12), ("Away U", 0.02))]
    return {"adv": M.by(adv, "team"), "lm": M.league_means(adv), "talent": {}, "ret": {},
            "ratings": {}, "teams": {}, "venues": {}, "injuries": [], "weather": {}, "rest": {},
            "cross": {}, "usage": list(usage)}


def _prop(line=245.5, over=-110, under=-110, **kw):
    d = {"gameId": 1, "player": "QB One", "market": "pass_yds", "line": line,
         "overOdds": over, "underOdds": under}
    d.update(kw)
    return d


def _proj(ctx=None):
    return M.run_game(GAME, ctx or _ctx())


class PinnedModelCircularity(unittest.TestCase):
    def test_forecast_mean_moves_with_price_at_fixed_line_and_inputs(self):
        ctx, proj = _ctx(), _proj()
        a = M.price_props(proj, ctx, [_prop(over=-110, under=-110)])
        b = M.price_props(proj, ctx, [_prop(over=-160, under=135)])
        self.assertEqual((len(a), len(b)), (2, 2))
        self.assertNotAlmostEqual(a[0]["proj"], b[0]["proj"], places=3)
        self.assertNotAlmostEqual(a[0]["p_model"], b[0]["p_model"], places=4)

    def test_forecast_mean_moves_with_line_at_fixed_price(self):
        ctx, proj = _ctx(), _proj()
        a = M.price_props(proj, ctx, [_prop(line=245.5)])
        b = M.price_props(proj, ctx, [_prop(line=285.5)])
        self.assertAlmostEqual(b[0]["proj"] - a[0]["proj"], 0.3 * 40.0, places=6)

    def test_pinned_mean_is_exactly_model_plus_market_implied_blend(self):
        ctx, proj = _ctx(), _proj()
        mm, _ = M.project_prop(USAGE, proj, ctx)
        row = M.price_props(proj, ctx, [_prop(over=-160, under=135)])[0]
        implied = P.market_implied_mean("pass_yds", 245.5, -160, 135)
        self.assertAlmostEqual(row["proj"], P.hybrid_mean(mm, implied), places=9)

    def test_second_market_blend_is_applied_to_probability(self):
        ctx, proj = _ctx(), _proj()
        row = M.price_props(proj, ctx, [_prop(over=-160, under=135)])[0]
        self.assertAlmostEqual(row["p_blend"], 0.3 * row["p_model"] + 0.7 * row["p_market"], places=12)


class IndependentChallenger(unittest.TestCase):
    QUOTES = [(245.5, -110, -110), (245.5, -160, 135), (245.5, 120, -150),
              (285.5, -110, -110), (205.5, -200, 170)]

    def test_distribution_hash_identical_across_prices_and_lines(self):
        ctx, proj = _ctx(), _proj()
        out = [P.price_props_independent(proj, ctx, [_prop(l, o, u)]) for l, o, u in self.QUOTES]
        self.assertEqual(len({r["distribution_set_sha256"] for r in out}), 1)
        self.assertEqual(len({r["rows"][0]["dist_sha256"] for r in out}), 1)
        self.assertEqual(len({r["rows"][0]["mean"] for r in out}), 1)
        self.assertEqual(len({r["rows"][0]["sd"] for r in out}), 1)

    def test_threshold_probability_and_ev_change_legitimately(self):
        ctx, proj = _ctx(), _proj()
        out = [P.price_props_independent(proj, ctx, [_prop(l, o, u)])["rows"][0] for l, o, u in self.QUOTES]
        self.assertGreater(len({r["p_over"] for r in out}), 1)
        self.assertGreater(len({r["ev_over"] for r in out}), 1)
        lo = P.price_props_independent(proj, ctx, [_prop(245.5, -110, -110)])["rows"][0]
        hi = P.price_props_independent(proj, ctx, [_prop(245.5, 120, -110)])["rows"][0]
        self.assertEqual(lo["p_over"], hi["p_over"])
        self.assertGreater(hi["ev_over"], lo["ev_over"])

    def test_forecast_function_is_structurally_market_blind(self):
        params = list(inspect.signature(P.independent_distribution).parameters)
        self.assertEqual(params, ["u", "proj", "ctx"])
        for fn in (P.independent_distribution, P.freeze_distributions):
            src = inspect.getsource(fn).lower()
            for banned in ("odds", "novig", "line", "quote", "implied", "price"):
                self.assertNotIn(banned, src)

    def test_invalid_quote_is_withheld_without_touching_distribution(self):
        ctx, proj = _ctx(), _proj()
        good = P.price_props_independent(proj, ctx, [_prop()])
        bad = P.price_props_independent(proj, ctx, [_prop(over=0), _prop(line=float("nan")), _prop(under=True)])
        self.assertEqual(bad["rows"], [])
        self.assertEqual([w["reason"] for w in bad["withheld"]], ["INVALID_QUOTE"] * 3)
        self.assertEqual(bad["distribution_set_sha256"], good["distribution_set_sha256"])

    def test_unsupported_market_and_bad_usage_are_withheld(self):
        for patch, reason in ((dict(market="rec_td"), "UNSUPPORTED_STAT_MARKET"),
                              (dict(share=0), "INVALID_USAGE_NUMBER"),
                              (dict(eff=float("nan")), "INVALID_USAGE_NUMBER"),
                              (dict(share=True), "INVALID_USAGE_NUMBER")):
            ctx = _ctx((dict(USAGE, **patch),))
            res = P.price_props_independent(_proj(ctx), ctx, [_prop(market=patch.get("market", "pass_yds"))])
            self.assertEqual(res["rows"], [])
            self.assertEqual(res["withheld"][0]["reason"], reason)

    def test_duplicate_usage_rows_are_withheld_not_last_wins(self):
        ctx = _ctx((USAGE, dict(USAGE, share=0.5)))
        res = P.price_props_independent(_proj(ctx), ctx, [_prop()])
        self.assertEqual(res["withheld"][0]["reason"], "DUPLICATE_USAGE_ROW")

    def test_rows_are_paper_zero_stake_and_labeled(self):
        ctx, proj = _ctx(), _proj()
        r = P.price_props_independent(proj, ctx, [_prop()])["rows"][0]
        self.assertEqual((r["approved_stake_u"], r["official_counted"]), (0, 0))
        self.assertEqual(r["label"], P.LABEL)

    def test_market_anchored_helpers_are_not_reachable_from_pricing_path(self):
        src = inspect.getsource(P.price_props_independent)
        self.assertNotIn("market_implied_mean", src)
        self.assertNotIn("hybrid_mean", src)

    def test_pinned_model_file_is_unchanged(self):
        data = Path(M.__file__).read_bytes()
        blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        self.assertEqual(blob, PINNED_BLOB)


if __name__ == "__main__":
    unittest.main()
