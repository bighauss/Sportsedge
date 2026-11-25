"""stdlib unittest for the full-game CHALLENGER (run from models/cbb: python -m unittest -v fullgame.test_fullgame)."""
import math
import re
import random
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parents[2]))

from fullgame import pricing as P, ratings as R, sdv_loader as L, espn_odds as O, evaluate as E  # noqa: E402
from fullgame import nov24_diagnosis as D, context as C, adjustments as A  # noqa: E402
import cbb_pricing as PR  # noqa: E402

CARD = HERE.parents[2] / "outputs" / "cbb" / "card_2026-11-24_45452279760_1.md"


def game(i, day, home, away, hp, ap, site="HOME_VERIFIED", poss=70.0, season=2027):
    return {"game_id": str(i), "season": season, "date": day, "tip_utc": day + "T23:00Z", "home": home,
            "away": away, "site": site, "neutral": site == "NEUTRAL", "home_points": hp, "away_points": ap,
            "possessions": poss, "home_d1": True, "away_d1": True}


def league(seed=1, days=30, teams=12, season=2027):
    rnd = random.Random(seed)
    strength = {str(t): rnd.gauss(0, 8) for t in range(teams)}
    gs, i = [], 0
    for d in range(days):
        day = "2026-11-%02d" % (d + 1) if d < 30 else "2026-12-%02d" % (d - 29)
        ts = list(strength); rnd.shuffle(ts)
        for a, b in zip(ts[::2], ts[1::2]):
            site = rnd.choice(["HOME_VERIFIED", "HOME_VERIFIED", "NEUTRAL", "UNVERIFIED"])
            m = strength[a] - strength[b] + (3 if site == "HOME_VERIFIED" else 0) + rnd.gauss(0, 10)
            base = 70 + rnd.gauss(0, 8)
            hp, ap = int(round(base + m / 2)), int(round(base - m / 2))
            if hp == ap:
                hp += 1
            i += 1
            gs.append(game(i, day, a, b, hp, ap, site, 66 + rnd.random() * 8, season))
    return gs


class TCdf(unittest.TestCase):
    def test_matches_reference_values(self):
        # reference values from scipy.stats.t.cdf
        self.assertAlmostEqual(P.t_cdf(1.0, 5), 0.8183912661754386, places=10)
        self.assertAlmostEqual(P.t_cdf(-2.0, 10), 0.03669401738537018, places=10)
        self.assertAlmostEqual(P.t_cdf(0.3, None), 0.5 * math.erfc(-0.3 / math.sqrt(2)), places=12)

    def test_dist_sd_is_the_residual_sd(self):
        d = P.Dist(0.0, 11.0, 6.0)
        self.assertAlmostEqual(d.scale, 11.0 * math.sqrt(4 / 6))
        with self.assertRaises(ValueError):
            P.Dist(0.0, 11.0, 2.0)


class TPricing(unittest.TestCase):
    def test_push_aware_integer_line(self):
        d = P.Dist(0.0, 11.0, 8.0)
        a, push, b = P.line_probs(d, 3.2, 3)
        self.assertGreater(push, 0.02)
        self.assertAlmostEqual(a + push + b, 1.0, places=12)
        a, push, b = P.line_probs(d, 3.2, 3.5)
        self.assertEqual(push, 0.0)
        self.assertAlmostEqual(a + b, 1.0, places=12)

    def test_push_refunds_in_ev(self):
        self.assertAlmostEqual(P.ev(0.45, 0.10, -110), 0.45 * (100 / 110) - 0.45)

    def test_ml_symmetry(self):
        d = P.Dist(0.0, 11.0, 10.0)
        self.assertAlmostEqual(P.ml_probs(d, 0.0)[0], 0.5)
        h, a = P.ml_probs(d, 7.0)
        self.assertAlmostEqual(h, 1 - P.ml_probs(d, -7.0)[0])
        self.assertAlmostEqual(h + a, 1.0)

    def test_location_debias_shifts_probability(self):
        self.assertGreater(P.line_probs(P.Dist(1.0, 11.0), 0.0, 0.5)[0], P.line_probs(P.Dist(0.0, 11.0), 0.0, 0.5)[0])

    def test_fit_dist_detects_tails(self):
        rnd = random.Random(3)
        normal = [rnd.gauss(0, 11) for _ in range(5000)]
        heavy = [rnd.gauss(0, 11) * (3 if rnd.random() < 0.1 else 1) for _ in range(5000)]
        self.assertTrue(P.fit_dist(normal).df is None or P.fit_dist(normal).df > 30)
        self.assertLess(P.fit_dist(heavy).df, 12)
        with self.assertRaises(ValueError):
            P.fit_dist(normal[:10])

    def test_phase_dists_borrow_when_thin(self):
        rows = [{"phase": 5, "margin": random.Random(i).gauss(0, 10)} for i in range(400)]
        d = P.fit_phase_dists(rows, "margin")
        self.assertIs(d[0], d[5])

    def test_audit_flags_but_never_caps(self):
        row = {"ev": 3.408, "price": 3500, "p_model": 0.122, "p_novig": 0.027}
        before = dict(row)
        codes = P.ev_audit(row)
        self.assertEqual(row, before)
        self.assertIn("EV_GT_30_PCT", codes)
        self.assertIn("LONGSHOT_PRICE_GE_PLUS500", codes)
        self.assertIn("MODEL_PROB_GE_2X_NOVIG", codes)
        self.assertEqual(P.ev_audit({"ev": 0.05, "price": -110, "p_model": 0.55, "p_novig": 0.5}), [])

    def test_logit_recal_recovers_slope(self):
        rnd = random.Random(5)
        pairs = []
        for _ in range(20000):
            x = rnd.uniform(-3, 3)
            q = 1 / (1 + math.exp(-(0.2 + 0.7 * x)))
            pairs.append((1 / (1 + math.exp(-x)), int(rnd.random() < q)))
        r = P.fit_logit_recal(pairs)
        self.assertAlmostEqual(r["b"], 0.7, delta=0.05)
        self.assertAlmostEqual(r["a"], 0.2, delta=0.06)

    def test_fair_american(self):
        self.assertEqual(P.fair_american(0.5), -100)
        self.assertEqual(P.fair_american(0.2), 400)


class TSites(unittest.TestCase):
    def test_home_court_only_at_verified_home_venue(self):
        self.assertEqual(L.site_class(True, 5, 5), "NEUTRAL")
        self.assertEqual(L.site_class(False, 3604, 3604.0), "HOME_VERIFIED")
        self.assertEqual(L.site_class(False, 3604, 2126.0), "UNVERIFIED")
        self.assertEqual(L.site_class(False, None, 2126.0), "UNVERIFIED")
        self.assertEqual(L.site_class(None, 1, 1), "UNVERIFIED")

    def test_possessions(self):
        self.assertAlmostEqual(L.possessions(60, 10, 12, 20), 60 - 10 + 12 + 9.5)
        self.assertIsNone(L.possessions(10, 0, 0, 0))
        self.assertIsNone(L.possessions(float("nan"), 1, 1, 1))


class TRatings(unittest.TestCase):
    def test_hca_applied_only_at_home_verified(self):
        f = R.AdjustedFit(lam=2.0).fit(league(), R._d("2026-12-31"))
        self.assertGreater(f.h, 0)
        n = f.project("0", "1", "NEUTRAL"); u = f.project("0", "1", "UNVERIFIED"); h = f.project("0", "1", "HOME_VERIFIED")
        self.assertAlmostEqual(n[0] - n[1], u[0] - u[1])
        self.assertGreater(h[0] - h[1], n[0] - n[1])

    def test_walk_forward_uses_only_strictly_prior_dates(self):
        gs = league()
        last = max(g["date"] for g in gs)
        base, _ = R.walk_forward(gs, ["RAW", "SA"])
        # changing every result ON the last date cannot change that date's forecasts
        mutated = [dict(g, home_points=g["home_points"] + 40) if g["date"] == last else g for g in gs]
        alt, _ = R.walk_forward(mutated, ["RAW", "SA"])
        b = {r["game_id"]: r["f"] for r in base if r["date"] == last}
        a = {r["game_id"]: r["f"] for r in alt if r["date"] == last}
        self.assertTrue(any(b.values()))
        self.assertEqual(a, b)

    def test_non_d1_rows_are_excluded(self):
        g = game(1, "2026-11-01", "a", "b", 90, 40)
        self.assertTrue(R.usable(g))
        self.assertFalse(R.usable(dict(g, away_d1=False)))
        self.assertFalse(R.usable(dict(g, possessions=None)))

    def test_prior_carries_over(self):
        f = R.AdjustedFit(lam=2.0, iters=30).fit(league(seed=2), R._d("2026-12-31"))
        prior, new = R.make_prior(f.final_state(), 0.5)
        t = next(iter(prior))
        self.assertAlmostEqual(prior[t][0], 0.5 * f.o[t])
        self.assertEqual(len(new), 3)


class TRecalibration(unittest.TestCase):
    def _seasons(self):
        out = {}
        for s in (2023, 2024, 2025, 2026):
            gs = league(seed=s, days=20, season=s)
            rows, _ = R.walk_forward(gs, ["SA"])
            out[s] = rows
        return out

    def test_only_strictly_earlier_seasons(self):
        data = self._seasons()
        coefs = E.add_recalibrated(data, "SA", min_prior_seasons=2, min_rows=20)
        self.assertNotIn(2023, coefs); self.assertNotIn(2024, coefs)
        self.assertIn(2025, coefs)
        self.assertTrue(all("SAC" in r["f"] for r in data[2025] if "SA" in r["f"]))
        before = coefs[2025]
        data2 = self._seasons()
        for r in data2[2026]:
            r["home_points"] += 30
        self.assertEqual(E.add_recalibrated(data2, "SA", min_prior_seasons=2, min_rows=20)[2025], before)


class TOdds(unittest.TestCase):
    def _item(self, pid="100", ps="-5.5", aps="+5.5", total="143.5", hml="-240", aml="+200"):
        side = lambda p, ml: {"close": {"ps": p, "sp": "-110", "ml": ml}, "open": {"ps": p, "sp": "-110", "ml": ml}}
        return {"pid": pid, "provider": "x", "home": side(ps, hml), "away": side(aps, aml),
                "tot": {"close": {"total": total, "over": "-110", "under": "-110"}, "open": {"total": total, "over": "-105", "under": "-115"}}}

    def test_prefers_draftkings_and_skips_live(self):
        q, _ = O.extract([self._item(pid="59", ps="-9.5", aps="+9.5"), self._item(pid="58", ps="-4.5", aps="+4.5"), self._item()])
        self.assertEqual((q["pid"], q["spread_home"]), ("100", -5.5))
        q, why = O.extract([self._item(pid="59")])
        self.assertIsNone(q); self.assertEqual(why, "NO_PREFERRED_PREGAME_PROVIDER")

    def test_price_in_spread_field_rejected(self):
        q, _ = O.extract([self._item(ps="-115", aps="+115")])
        self.assertIsNone(q["spread_home"])

    def test_orientation_contradiction_rejected(self):
        q, _ = O.extract([self._item(ps="+5.5", aps="-5.5")])   # home +5.5 but home is the ML favourite
        self.assertIsNone(q["spread_home"])

    def test_open_vs_close(self):
        q, _ = O.extract([self._item()], which="open")
        self.assertEqual(q["over_price"], -105)
        with self.assertRaises(ValueError):
            O.extract([self._item()], which="live")


class TBlendAndAudit(unittest.TestCase):
    def test_owner_grid(self):
        self.assertEqual(PR.OWNER_BLEND_WEIGHTS, (1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0))
        self.assertEqual(PR.DEFAULT_CONFIG["blend_weight_model"], 0.25)   # production config untouched

    def test_logit_blend(self):
        self.assertAlmostEqual(PR.logit_blend(0.122, 0.027, 0.0), 0.027)
        self.assertAlmostEqual(PR.logit_blend(0.122, 0.027, 1.0), 0.122)
        self.assertLess(PR.logit_blend(0.122, 0.027, 0.125), PR.blend(0.122, 0.027, 0.125))
        self.assertAlmostEqual(PR.logit_blend(0.45, 0.5, 0.3, push=0.1), 0.45)
        with self.assertRaises(ValueError):
            PR.logit_blend(0.5, 0.0, 0.5)

    def test_card_audit_does_not_mutate(self):
        card = {"rows": [{"game_id": "1", "markets": [{"status": "PRICED_PAPER", "market": "moneyline",
                 "sides": ["home", "away"], "quote": {"price_a": -5000, "price_b": 3500},
                 "model_prob": {"home": 0.878, "push": 0.0, "away": 0.122},
                 "market_novig_prob": {"home": 0.973, "away": 0.027},
                 "paper_ev_per_1u_at_price": {"home": -0.10, "away": 3.392}}]}]}
        import copy
        before = copy.deepcopy(card)
        flags = PR.ev_sanity_audit(card)
        self.assertEqual(card, before)
        self.assertEqual([(f["side"], f["paper_ev"]) for f in flags], [("away", 3.392)])


@unittest.skipUnless(CARD.exists(), "committed Nov 24 card not present")
class TNov24Card(unittest.TestCase):
    def test_reproduces_48_of_167(self):
        rows, excluded = D.parse_card(str(CARD))
        self.assertEqual(len(rows), 167)
        self.assertEqual(sum(r["ev"] > 0.30 for r in rows), 48)
        lip = next(r for r in rows if r["game"] == "Lipscomb @ Auburn" and r["market"] == "moneyline")
        self.assertEqual((lip["price"], lip["p_model"], lip["p_novig"]), (3500, 0.122, 0.027))
        self.assertEqual(excluded["Lipscomb @ Auburn"], -25.5)

    def test_card_margin_recovery(self):
        rows, _ = D.parse_card(str(CARD))
        g = D.card_projection(rows)["Lipscomb @ Auburn"]
        # p_away 0.122 at SD 12.5 -> home margin ~ +14.6 against a -25.5 market line
        self.assertAlmostEqual(g["card_margin"], 12.5 * D.N.inv_cdf(0.878), places=6)
        self.assertLess(g["card_margin"], 16)


class TContext(unittest.TestCase):
    def _games(self):
        # season opener, then a back-to-back on the road, then a same-city rematch
        lookup = {"1": {"city": "Durham", "state": "NC"},
                  "2": {"city": "Lexington", "state": "KY"},
                  "3": {"city": "Nassau", "state": "Bahamas"}}
        games = [
            {"game_id": "a", "date": "2021-11-09", "tip_utc": "2021-11-09T00:00Z",
             "home": "H", "away": "A", "site": "HOME_VERIFIED", "venue_id": "1",
             "home_venue_id": "1", "away_home_venue_id": "2"},
            {"game_id": "b", "date": "2021-11-10", "tip_utc": "2021-11-10T00:00Z",
             "home": "A", "away": "H", "site": "HOME_VERIFIED", "venue_id": "2",
             "home_venue_id": "2", "away_home_venue_id": "1"},
            {"game_id": "c", "date": "2021-11-20", "tip_utc": "2021-11-20T00:00Z",
             "home": "H", "away": "A", "site": "NEUTRAL", "venue_id": "3",
             "home_venue_id": "1", "away_home_venue_id": "2"},
        ]
        return C.attach_context(games, venue_lookup=lookup), lookup

    def test_opener_is_capped_and_flagged(self):
        rows, _ = self._games()
        self.assertEqual(rows[0]["home_rest"], C.REST_CAP)
        self.assertEqual(rows[0]["away_rest"], C.REST_CAP)
        self.assertEqual((rows[0]["home_opener"], rows[0]["away_opener"]), (1, 1))
        self.assertEqual((rows[0]["home_b2b"], rows[0]["away_b2b"]), (0, 0))

    def test_b2b_and_rest_use_only_prior_games(self):
        rows, _ = self._games()
        # game b is the next day for both teams
        self.assertEqual(rows[1]["home_rest"], 1)
        self.assertEqual(rows[1]["away_rest"], 1)
        self.assertEqual((rows[1]["home_b2b"], rows[1]["away_b2b"]), (1, 1))
        self.assertEqual((rows[1]["home_opener"], rows[1]["away_opener"]), (0, 0))
        # game c is 10 days after b
        self.assertEqual(rows[2]["home_rest"], 10)
        self.assertEqual(rows[2]["away_rest"], 10)
        self.assertEqual(rows[2]["is_neutral"], 1)

    def test_same_city_travel_is_zero_and_cross_region_is_positive(self):
        self.assertEqual(C.travel_miles("Durham", "NC", "durham", "NC"), 0.0)
        self.assertEqual(C.travel_miles("Charlotte", "NC", "Durham", "NC"), C.INTRA_STATE_MILES)
        miles = C.travel_miles("Durham", "NC", "Nassau", "Bahamas")
        self.assertIsNotNone(miles)
        self.assertGreater(miles, 500)
        rows, _ = self._games()
        # game a: home at home venue -> 0 miles; away from KY to NC is interstate
        self.assertEqual(rows[0]["home_miles"], 0.0)
        self.assertGreater(rows[0]["away_miles"], 200)

    def test_future_game_does_not_affect_earlier_rest(self):
        rows, lookup = self._games()
        # attaching again in shuffled input order must still sort and ignore the future
        shuffled = [rows[2], rows[0], rows[1]]
        # strip fields and re-run
        raw = [{k: g[k] for k in ("game_id", "date", "tip_utc", "home", "away", "site",
                                  "venue_id", "home_venue_id", "away_home_venue_id")} for g in shuffled]
        out = {g["game_id"]: g for g in C.attach_context(raw, venue_lookup=lookup)}
        self.assertEqual(out["a"]["home_rest"], C.REST_CAP)
        self.assertEqual(out["b"]["home_rest"], 1)


class TAdjustments(unittest.TestCase):
    def test_ridge_recovers_rest_effect(self):
        # synthetic: margin residual = 1.5 * rest_diff, no noise
        rows = []
        for i, rd in enumerate((-3, -2, -1, 0, 1, 2, 3, 4)):
            rows.append({"n_home": 10, "n_away": 10, "rest_diff": rd, "home_b2b": 0, "away_b2b": 0,
                         "is_neutral": 0, "away_miles": 0, "home_miles": 0, "away_moved": 0, "home_moved": 0,
                         "home_points": 70 + 1.5 * rd, "away_points": 70,
                         "f": {"FG1": {"margin": 0.0, "total": 140.0, "home_points": 70, "away_points": 70}}})
        fit = A.fit_variant(rows, A.VARIANTS["rest"], "margin", lam=1e-6, min_n=8)
        self.assertIsNotNone(fit)
        # intercept ~0, rest_diff ~1.5
        coef = dict(zip(fit["names"], fit["coef"]))
        self.assertAlmostEqual(coef["rest_diff"], 1.5, places=1)
        self.assertAlmostEqual(coef["intercept"], 0.0, delta=0.2)
        adj = A.apply_fit(rows[-1], {"margin": fit, "total": None}, rows[-1]["f"]["FG1"])
        self.assertAlmostEqual(adj["margin"], 1.5 * 4, places=1)

    def test_longshot_shrinks_only_the_tail(self):
        # model says 0.04, actually 0.02 in the tail; interior 0.5 stays
        pairs = [(0.03, 0) for _ in range(40)] + [(0.03, 1) for _ in range(10)]  # rate 0.2? 10/50=0.2, model 0.03
        # wait we want model overstate: model 0.06 mean, rate 0.03
        pairs = [(0.06, 0) for _ in range(97)] + [(0.06, 1) for _ in range(3)]
        pairs += [(0.5, 0) for _ in range(50)] + [(0.5, 1) for _ in range(50)]
        cal = A.fit_longshot(pairs, edges=(0.08,))
        self.assertEqual(cal["primary"], 0.08)
        self.assertLess(cal["edges"]["0.08"]["rate"], cal["edges"]["0.08"]["model"])
        tail = A.apply_longshot(0.06, cal)
        mid = A.apply_longshot(0.5, cal)
        self.assertLess(tail, 0.06)
        self.assertAlmostEqual(mid, 0.5)

    def test_fav_bump_raises_underconfident_favourite(self):
        # model p_fav=0.60, actual rate 0.70
        pairs = [(0.60, 1) for _ in range(70)] + [(0.60, 0) for _ in range(30)]
        bump = A.fit_fav_bump(pairs)
        self.assertGreater(bump["delta"], 0.05)
        self.assertAlmostEqual(A.apply_fav_bump(0.60, bump), 0.60 + bump["delta"], places=6)
        # underdog side mirrored
        self.assertAlmostEqual(A.apply_fav_bump(0.40, bump), 0.40 - bump["delta"], places=6)

    def test_frozen_coefs_do_not_depend_on_later_rows(self):
        early = [{"n_home": 10, "n_away": 10, "rest_diff": 2, "home_b2b": 0, "away_b2b": 0,
                  "is_neutral": 0, "away_miles": 0, "home_miles": 0, "away_moved": 0, "home_moved": 0,
                  "home_points": 80, "away_points": 70,
                  "f": {"FG1": {"margin": 5.0, "total": 150.0, "home_points": 77.5, "away_points": 72.5}}}
                 for _ in range(80)]
        fit1 = A.fit_variant(early, A.VARIANTS["rest"], "margin", lam=1.0)
        later = dict(early[0])
        later["home_points"] = 200  # would wreck a refit
        fit2 = A.fit_variant(early, A.VARIANTS["rest"], "margin", lam=1.0)
        self.assertEqual(fit1["coef"], fit2["coef"])
        # applying the frozen fit to a later row does not refit
        adj = A.apply_fit(later, {"margin": fit1}, later["f"]["FG1"])
        self.assertTrue(math.isfinite(adj["margin"]))


CANONICAL_BLEND = (1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0)

class TCanonicalBlend(unittest.TestCase):
    def test_single_canonical_definition(self):
        self.assertEqual(PR.OWNER_BLEND_WEIGHTS, CANONICAL_BLEND)
        self.assertFalse(hasattr(PR, "CANDIDATE_BLEND_WEIGHTS"))
        # 100/0 ... 0/100 in model/market percent
        pct = [(100 * w, 100 * (1 - w)) for w in PR.OWNER_BLEND_WEIGHTS]
        self.assertEqual(pct, [(100, 0), (87.5, 12.5), (75, 25), (62.5, 37.5),
                               (50, 50), (37.5, 62.5), (25, 75), (12.5, 87.5), (0, 100)])

    def test_no_other_blend_grid_in_cbb_python(self):
        """Fail if the obsolete nine-weight grid or a second competing grid is reintroduced."""
        root = HERE.parent  # models/cbb
        obsolete_pat = re.compile(
            r"0\.0\s*,\s*0\.25\s*,\s*0\.5\s*,\s*0\.6\s*,\s*0\.75\s*,\s*0\.8\s*,\s*0\.9\s*,\s*0\.95\s*,\s*1\.0")
        obsolete_pct = re.compile(
            r"\(\s*0\s*,\s*25\s*,\s*50\s*,\s*60\s*,\s*75\s*,\s*80\s*,\s*90\s*,\s*95\s*,\s*100\s*\)")
        name_pat = re.compile(r"\bCANDIDATE_BLEND_WEIGHTS\b")
        # 9-float tuples assigned in source (0-1), other than the canonical grid
        lit = re.compile(
            r"=[^=]*?\(\s*(" + r"(?:[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*,\s*" * 8
            + r"(?:[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*)\)")
        hits = []
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(root))
            # Tests may name the forbidden identifier; production modules may not.
            if name_pat.search(text) and path.name != "test_fullgame.py" and not path.name.startswith("test_"):
                hits.append(f"{rel}: CANDIDATE_BLEND_WEIGHTS")
            if obsolete_pat.search(text) or obsolete_pct.search(text):
                hits.append(f"{rel}: obsolete 0/25/50/60/75/80/90/95/100 grid")
            for m in lit.finditer(text):
                nums = tuple(float(x) for x in re.split(r"\s*,\s*", m.group(1)))
                if len(nums) != 9:
                    continue
                if all(0 <= n <= 1 for n in nums):
                    # only the canonical 0-1 definition (and assertions of it) may appear
                    if nums == CANONICAL_BLEND:
                        continue
                    hits.append(f"{rel}: other 9-weight grid {nums}")
                elif all(0 <= n <= 100 for n in nums) and any(n > 1 for n in nums):
                    # percent form must be derived from OWNER_BLEND_WEIGHTS, never handwritten
                    hits.append(f"{rel}: handwritten 9-weight percent grid {nums}")
        self.assertEqual(hits, [], msg="non-canonical blend grid(s): " + "; ".join(hits))


class TAmericanQuote(unittest.TestCase):
    def test_parse_accepts_exact_integers_and_signed_strings(self):
        for raw, want in ((110, 110), (-110, -110), ("+110", 110), ("-110", -110),
                          ("110", 110), (" +3500 ", 3500), (100, 100), (-10000, -10000)):
            self.assertEqual(PR.parse_american(raw), want)
            self.assertIsInstance(PR.parse_american(raw), int)
            self.assertEqual(P.parse_american(raw), want)

    def test_parse_rejects_floats_fractions_bools_and_malformed(self):
        # The pre-fix bug: int(110.7) == 110. The contract must raise instead.
        for raw, code in (
            (110.7, "NON_INTEGER_AMERICAN_PRICE"),
            (110.0, "NON_INTEGER_AMERICAN_PRICE"),
            (True, "NON_INTEGER_AMERICAN_PRICE"),
            (False, "NON_INTEGER_AMERICAN_PRICE"),
            (None, "NON_INTEGER_AMERICAN_PRICE"),
            ("110.7", "MALFORMED_AMERICAN_PRICE"),
            ("110.0", "MALFORMED_AMERICAN_PRICE"),
            ("0100", "MALFORMED_AMERICAN_PRICE"),
            ("+", "MALFORMED_AMERICAN_PRICE"),
            ("", "MALFORMED_AMERICAN_PRICE"),
            ("EVEN", "MALFORMED_AMERICAN_PRICE"),
            ("1e2", "MALFORMED_AMERICAN_PRICE"),
            ("+0", "MALFORMED_AMERICAN_PRICE"),
            (0, "INVALID_AMERICAN_PRICE"),
            (99, "INVALID_AMERICAN_PRICE"),
            (100001, "INVALID_AMERICAN_PRICE"),
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError) as ctx:
                    PR.parse_american(raw)
                self.assertEqual(str(ctx.exception), code)
                with self.assertRaises(ValueError):
                    P.decimal_odds(raw)

    def test_decimal_odds_matches_exact_int_and_refuses_truncation(self):
        self.assertAlmostEqual(P.decimal_odds(110), 2.1)
        self.assertAlmostEqual(P.decimal_odds(-110), 1 + 100 / 110)
        self.assertAlmostEqual(P.decimal_odds("+150"), 2.5)
        with self.assertRaises(ValueError):
            P.decimal_odds(110.7)
        # rungs reject a fractional American price with an explicit contract code
        kind = "alt_spread"
        board = {"line": "-3.5", "price_a": 110.7, "price_b": -130}
        rung, reason = PR._rung(board, kind)
        self.assertIsNone(rung)
        self.assertIn("NON_INTEGER_AMERICAN_PRICE", reason)
        board2 = {"line": "-3.5", "price_a": "110.5", "price_b": "-130"}
        rung, reason = PR._rung(board2, kind)
        self.assertIsNone(rung)
        self.assertIn("MALFORMED_AMERICAN_PRICE", reason)
        ok, reason = PR._rung({"line": "-3.5", "price_a": "+110", "price_b": "-130"}, kind)
        self.assertIsNotNone(ok)
        self.assertIsNone(reason)
        self.assertEqual(ok[1], 110)


class AdversarialPricing(unittest.TestCase):
    def test_invalid_distributions_and_quotes(self):
        for loc, sd, df in ((float("nan"),10,None),(0,0,None),(0,10,float("inf"))):
            with self.assertRaises(ValueError):
                P.Dist(loc,sd,df)
        for data in ([1]*200,[float("nan")]*200):
            with self.assertRaises(ValueError):
                P.fit_dist(data)
        d=P.Dist(0,10)
        for line in (1.25,float("nan"),float("inf"),True):
            with self.assertRaises(ValueError):
                P.line_probs(d,0,line)
        for win,push in ((.8,.3),(-.1,0),(float("nan"),0)):
            with self.assertRaises(ValueError):
                P.ev(win,push,-110)
        self.assertEqual(abs(P.fair_american(.45/.9)),100)
        self.assertAlmostEqual(P.ev(.45,.1,100),0)
        self.assertEqual(P.apply_logit_recal(.5,{"a":-1000,"b":1}),0)

    def test_future_season_venue_mutation_invariance(self):
        import tempfile
        from unittest.mock import patch
        from fullgame import improve_eval as I
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for year in (2020,2021,2022):
                (root/f"games_{year}.csv").touch()
            data = {
                2020:[dict(game(1,"2019-11-01","a","b",70,65,season=2020),venue_id="1",home_venue_id="1")],
                2021:[dict(game(2,"2020-11-01","b","a",70,65,season=2021),venue_id="2",home_venue_id="2")],
                2022:[dict(game(3,"2021-11-01","a","b",70,65,season=2022),venue_id="3",home_venue_id="3")]}
            def read(p):
                return [dict(row) for row in data[int(Path(p).stem.split("_")[-1])]]
            with patch.object(I.L,"read_csv",side_effect=read), patch.object(I,"venue_lookup_from_parquets",return_value={}):
                before,_=I.load_context(root,root)
                data[2022][0]["home_venue_id"]="999"
                after,_=I.load_context(root,root)
            self.assertEqual(before[2021],after[2021])
            self.assertEqual(before[2021]["2"]["away_home_venue_id"],"1")
            self.assertFalse(before[2020]["1"]["away_home_known"])


if __name__ == "__main__":
    unittest.main()
