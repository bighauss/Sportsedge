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
        hi = P.price_props_independent(proj, ctx, [_prop(245.5, 120, -140)])["rows"][0]  # +120/-110 is a negative-overround pair, now withheld
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


AWAY_SAME_NAME = dict(USAGE, team="Away U", eff=5.1, share=0.9)


class IdentityDuplicatesPush(unittest.TestCase):
    """Adversarial regressions added by Claude on top of #558."""

    def test_same_name_players_on_both_teams_do_not_collide(self):
        ctx = _ctx((USAGE, AWAY_SAME_NAME))
        proj = _proj(ctx)
        res = P.price_props_independent(proj, ctx, [_prop()])
        self.assertNotIn("DUPLICATE_USAGE_ROW", [d.get("reason") for d in res["distributions"]])
        self.assertEqual(res["rows"], [])
        self.assertEqual(res["withheld"][0]["reason"], "AMBIGUOUS_PLAYER_IDENTITY")

    def test_team_scoped_quote_prices_the_correct_player(self):
        ctx = _ctx((USAGE, AWAY_SAME_NAME))
        proj = _proj(ctx)
        home = P.price_props_independent(proj, ctx, [_prop(team="Home U")])["rows"][0]
        away = P.price_props_independent(proj, ctx, [_prop(team="Away U")])["rows"][0]
        self.assertEqual((home["team"], away["team"]), ("Home U", "Away U"))
        self.assertNotEqual(home["dist_sha256"], away["dist_sha256"])
        self.assertNotAlmostEqual(home["mean"], away["mean"], places=3)

    def test_unknown_team_on_quote_is_withheld(self):
        ctx, proj = _ctx(), _proj()
        res = P.price_props_independent(proj, ctx, [_prop(team="Other U")])
        self.assertEqual(res["rows"], [])
        self.assertEqual(res["withheld"][0]["reason"], "NO_USAGE_ROW")

    def test_identical_duplicate_quotes_collapse_to_one_row(self):
        ctx, proj = _ctx(), _proj()
        res = P.price_props_independent(proj, ctx, [_prop(), _prop(), _prop()])
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual(res["rows"][0]["duplicates_collapsed"], 2)

    def test_conflicting_duplicate_quotes_are_withheld(self):
        ctx, proj = _ctx(), _proj()
        res = P.price_props_independent(proj, ctx, [_prop(over=-110), _prop(over=-125, under=105)])
        self.assertEqual(res["rows"], [])
        self.assertEqual([w["reason"] for w in res["withheld"]], ["DUPLICATE_CONFLICTING_QUOTE"])

    def test_quote_order_does_not_change_output(self):
        ctx, proj = _ctx(), _proj()
        qs = [_prop(245.5), _prop(285.5, -120, 100), _prop(205.5, -200, 170)]
        a = P.price_props_independent(proj, ctx, qs)
        b = P.price_props_independent(proj, ctx, list(reversed(qs)))
        key = lambda r: r["line"]
        self.assertEqual(sorted(a["rows"], key=key), sorted(b["rows"], key=key))
        self.assertEqual(a["distribution_set_sha256"], b["distribution_set_sha256"])

    def test_whole_number_threshold_has_push_and_probabilities_sum_to_one(self):
        ctx, proj = _ctx(), _proj()
        mean = P.price_props_independent(proj, ctx, [_prop()])["rows"][0]["mean"]
        whole = float(round(mean))
        r = P.price_props_independent(proj, ctx, [_prop(line=whole)])["rows"][0]
        self.assertGreater(r["p_push"], 0.0)
        self.assertAlmostEqual(r["p_over"] + r["p_push"] + r["p_under"], 1.0, places=12)

    def test_half_point_threshold_has_zero_push(self):
        ctx, proj = _ctx(), _proj()
        r = P.price_props_independent(proj, ctx, [_prop(245.5)])["rows"][0]
        self.assertEqual(r["p_push"], 0.0)
        self.assertAlmostEqual(r["p_over"] + r["p_under"], 1.0, places=12)

    def test_push_aware_ev_returns_stake_on_push(self):
        # Even money, 40% win / 20% push / 40% loss -> EV exactly 0 (push returns stake).
        self.assertAlmostEqual(P.push_aware_ev(0.4, 0.4, 100), 0.0, places=12)
        # Naive formula p_win*dec - 1 would wrongly give -0.2.
        self.assertAlmostEqual(0.4 * M.dec(100) - 1, -0.2, places=12)

    def test_whole_number_ev_matches_push_aware_formula(self):
        ctx, proj = _ctx(), _proj()
        mean = P.price_props_independent(proj, ctx, [_prop()])["rows"][0]["mean"]
        r = P.price_props_independent(proj, ctx, [_prop(line=float(round(mean)))])["rows"][0]
        self.assertAlmostEqual(r["ev_over"], r["p_over"] * (M.dec(-110) - 1) - r["p_under"], places=12)
        self.assertAlmostEqual(r["ev_under"], r["p_under"] * (M.dec(-110) - 1) - r["p_over"], places=12)


class QuoteValidation(unittest.TestCase):
    """#565 review: malformed quotes must be withheld before pricing (CBB rule parity)."""

    def withheld(self, **kw):
        ctx, proj = _ctx(), _proj()
        res = P.price_props_independent(proj, ctx, [_prop(**kw)])
        return res["rows"], [w.get("detail") for w in res["withheld"]], res["distribution_set_sha256"]

    def test_malformed_quotes_withheld(self):
        cases = [(dict(over=20000, under=-110), "IMPLAUSIBLE_PRICE_MAGNITUDE"),
                 (dict(over=150, under=150), "NOVIG_SUM_OUT_OF_RANGE"),
                 (dict(over=-110, under=900), "NOVIG_SUM_OUT_OF_RANGE"),
                 (dict(line=245.25), "LINE_OFF_HALF_POINT_GRID"),
                 (dict(line=245.75), "LINE_OFF_HALF_POINT_GRID"),
                 (dict(over=-110.5), "INVALID_AMERICAN_ODDS"),
                 (dict(under=99), "INVALID_AMERICAN_ODDS"),
                 (dict(line=0), "LINE_OFF_HALF_POINT_GRID")]
        for kw, reason in cases:
            with self.subTest(**kw):
                rows, details, _ = self.withheld(**kw)
                self.assertEqual(rows, [])
                self.assertEqual(details, [reason])

    def test_normal_quotes_still_priced(self):
        for kw in (dict(), dict(over=-150, under=125), dict(over=250, under=-320), dict(line=245.0)):
            with self.subTest(**kw):
                rows, _, _ = self.withheld(**kw)
                self.assertEqual(len(rows), 1)

    def test_rejection_does_not_change_distributions(self):
        _, _, good = self.withheld()
        _, _, bad = self.withheld(over=20000, under=-110)
        self.assertEqual(good, bad)

    def test_rule_matches_cbb_pricing_bounds(self):
        self.assertEqual(P.MAX_ABS_PRICE, 5000)
        self.assertEqual(P.OVERROUND_RANGE, (-0.005, 0.25))


class InputContract(unittest.TestCase):
    """#565 re-review: malformed rows/identities, overflow and absurd thresholds fail closed."""

    def price(self, rows):
        ctx, proj = _ctx(), _proj()
        return P.price_props_independent(proj, ctx, rows)

    def test_non_dict_rows_withheld_not_crash(self):
        res = self.price([None, [], "x", 5, _prop()])
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual([w["reason"] for w in res["withheld"]], ["MALFORMED_PROP_ROW"] * 4)

    def test_non_list_input_withheld(self):
        for rows in (None, {"a": 1}, "abc"):
            with self.subTest(rows=rows):
                res = self.price(rows)
                self.assertEqual(res["rows"], [])
                self.assertEqual(res["withheld"][0]["reason"], "PROP_ROWS_NOT_A_LIST")

    def test_unhashable_or_wrong_type_identity_withheld(self):
        for kw in (dict(team=[]), dict(team={}), dict(player=["QB One"]), dict(player=None),
                   dict(player=" "), dict(market=["pass_yds"]), dict(market=None), dict(team=7)):
            with self.subTest(**{k: repr(v) for k, v in kw.items()}):
                res = self.price([_prop(**kw)])
                self.assertEqual(res["rows"], [])
                self.assertEqual(res["withheld"][0]["reason"], "MALFORMED_IDENTITY")

    def test_huge_integer_does_not_overflow(self):
        for kw in (dict(over=10 ** 400), dict(line=10 ** 400), dict(under=-(10 ** 400))):
            with self.subTest(key=list(kw)[0]):
                res = self.price([_prop(**kw)])
                self.assertEqual(res["rows"], [])
                self.assertEqual(res["withheld"][0]["reason"], "INVALID_QUOTE")

    def test_absurd_thresholds_withheld(self):
        for line in (1e12, 650.5, 999.5):
            with self.subTest(line=line):
                res = self.price([_prop(line=line)])
                self.assertEqual(res["rows"], [])
                self.assertEqual(res["withheld"][0]["detail"], "LINE_OUT_OF_MARKET_RANGE")

    def test_market_bounds_cover_every_supported_market(self):
        self.assertEqual(set(P.LINE_BOUNDS), set(P.SUPPORTED))

    def test_rejections_never_change_frozen_digest(self):
        good = self.price([_prop()])["distribution_set_sha256"]
        bad = self.price([None, _prop(team=[]), _prop(line=1e12), _prop(over=10 ** 400)])
        self.assertEqual(bad["distribution_set_sha256"], good)


class SkewDistributionOptIn(unittest.TestCase):
    """Opt-in CFB-only skew table (cfb-prop-skew-v1); default stays the normal."""

    def run_(self, dist=None, **kw):
        ctx, proj = _ctx(), _proj()
        args = {} if dist is None else {"distribution": dist}
        return P.price_props_independent(proj, ctx, [_prop(**kw)], **args)

    def test_default_unchanged(self):
        r = self.run_()
        self.assertEqual(r["distribution"], P.NORMAL_DIST)
        self.assertEqual(r["rows"][0]["distribution"], P.NORMAL_DIST)

    def test_skew_rows_versioned_and_sum_to_one(self):
        for line in (245.5, 245.0, 180.5, 320.5):
            with self.subTest(line=line):
                row = self.run_(P.SKEW_DIST, line=line)["rows"][0]
                self.assertEqual(row["distribution"], "cfb-prop-skew-v1")
                self.assertAlmostEqual(row["p_over"] + row["p_push"] + row["p_under"], 1.0, places=12)
                self.assertEqual(row["p_push"] > 0, float(line).is_integer())

    def test_skew_does_not_change_frozen_forecast(self):
        a, b = self.run_(), self.run_(P.SKEW_DIST)
        self.assertEqual(a["distribution_set_sha256"], b["distribution_set_sha256"])
        self.assertEqual(a["rows"][0]["mean"], b["rows"][0]["mean"])

    def test_alternate_lines_monotonic(self):
        ps = [self.run_(P.SKEW_DIST, line=L)["rows"][0]["p_over"] for L in (150.5, 200.5, 245.5, 290.5, 340.5)]
        self.assertEqual(ps, sorted(ps, reverse=True))

    def test_low_volume_withheld(self):
        ctx = _ctx((dict(USAGE, share=0.05),))
        res = P.price_props_independent(_proj(ctx), ctx, [_prop(line=20.5)], distribution=P.SKEW_DIST)
        self.assertEqual(res["rows"], [])
        self.assertEqual((res["withheld"][0]["reason"], res["withheld"][0]["detail"]),
                         ("DISTRIBUTION_REFUSED", "LOW_VOLUME_FORECAST"))

    def test_unknown_distribution_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_DISTRIBUTION"):
            self.run_("nfl-prop-skew-v1")

    def test_uses_cfb_table_not_another_sport(self):
        import json
        self.assertEqual(json.loads(P.SKEW_TABLE.read_text())["sport"], "CFB")


if __name__ == "__main__":
    unittest.main()
