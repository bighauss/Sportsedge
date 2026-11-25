"""RUN IT CBB full pipeline (cbb_run_it_pipeline): offline unit tests. Synthetic fixtures only;
these test wiring, contracts and arithmetic, NOT predictive quality. PAPER/0u, NON_COUNTED."""
import csv, json, math, os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1]))
import contracts as C
import cbb_run_it_pipeline as P
import cbb_pricing as PR

CFG = PR.make_config()


def proj(gid="g1", hp=75.0, ap=70.0):
    return C.Projection(gid, "INDEPENDENT", hp, ap, hp - ap, hp + ap, CFG["sd_margin"], CFG["sd_total"], "t", "PROJECTED")


def quote(market, line, pa, pb, period="FG", i=0):
    sides = {"ML": ("home", "away"), "SPREAD": ("home", "away"), "ALT_SPREAD": ("home", "away")}.get(market, ("over", "under"))
    return C.MarketQuote(i, period, market, "Home U", "Away U", line, pa, pb, sides[0], sides[1], "123", None,
                         "2026-11-25T12:00:00Z", "2026-11-25T20:00:00Z", False, "UNAUTHENTICATED_PDF")


class Contracts(unittest.TestCase):
    def test_canonical_nine_weights(self):
        self.assertEqual(C.CANONICAL_BLEND_WEIGHTS, (1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0))

    def test_catalog_covers_all_families(self):
        fams = set(C.MARKET_CATALOG)
        for per in ("FG", "1H", "2H_PREGAME", "2H_HALFTIME_ADJUSTED"):
            for m in ("SPREAD", "TOTAL", "ML", "TT_HOME", "TT_AWAY"):
                self.assertIn((per, m), fams)
        for s in ("PTS", "REB", "AST", "3PM", "PRA", "PR", "PA", "RA"):
            self.assertTrue(any(m.startswith(f"PLAYER_{s}_") for _, m in fams), s)

    def test_every_priced_row_is_paper(self):
        q = quote("SPREAD", -3.5, -110, -110)
        sims = {"g1": P.simulate(proj(), 4000, 1)}
        priced, _, _ = P.price([(q, "g1")], {"g1": proj()}, sims, 0.25, CFG)
        for r, _ in priced:
            self.assertEqual((r.label, r.counted, r.approved_stake_u), (C.PAPER_0U, C.NON_COUNTED, 0))


class SimPricing(unittest.TestCase):
    def setUp(self):
        self.pj = proj()
        self.sim = P.simulate(self.pj, 20000, 7)

    def test_sim_matches_closed_form(self):
        for m, line in (("SPREAD", -4.5), ("TOTAL", 145.5), ("ML", None)):
            s = P.sim_probs(self.sim, m, line)[0]
            c = P.closed_probs(self.pj, m, line, CFG)[0]
            self.assertLess(abs(s - c), 0.02, (m, s, c))

    def test_integer_line_has_push_mass(self):
        pa, pp, pb = P.sim_probs(self.sim, "SPREAD", -5.0)
        self.assertGreater(pp, 0.0)
        self.assertAlmostEqual(pa + pp + pb, 1.0, places=9)

    def test_ev_over_30_is_flagged_not_capped(self):
        q = quote("ML", None, -2000, 1500)           # longshot away vs a near-even projection
        priced, _, _ = P.price([(q, "g1")], {"g1": proj(hp=72, ap=70)}, {"g1": self.sim}, 0.25, CFG)
        away = next(r for r, _ in priced if r.side == "away")
        self.assertGreater(away.ev_model, 0.30)
        self.assertIn("FROZEN_EV_GT_30_PCT", away.audit_flags)
        p = away.prob_model
        self.assertAlmostEqual(away.ev_model, p * 15.0 - (1 - p), places=9)   # unaltered EV
        self.assertTrue(away.hybrid_method.startswith("LINEAR_BLEND_FROZEN"))

    def test_outcome_push_on_integer(self):
        self.assertEqual(P.outcome("SPREAD", -5.0, 75, 70), "push")
        self.assertEqual(P.outcome("TOTAL", 145.0, 75, 70), "push")
        self.assertEqual(P.outcome("ML", None, 70, 75), "away")


class StubChallenger:
    """Minimal challenger: fixed probabilities; exercises the price() wiring only."""
    dists = None

    def probs(self, proj_, market, line):
        return (0.70, 0.0, 0.30) if market == "ML" else (0.60, 0.05, 0.35)

    def logit_blend(self, p_model, p_market, w, *, push=0.0):
        return PR_logit_blend(p_model, p_market, w, push=push)

    def audit(self, ev, price, p_model, p_novig):
        return ["EV_GT_30_PCT"] if ev > 0.30 else []


def PR_logit_blend(p_model, p_market, w, *, push=0.0):
    pm = min(1 - 1e-12, max(1e-12, p_model / (1 - push)))
    z = w * math.log(pm / (1 - pm)) + (1 - w) * math.log(p_market / (1 - p_market))
    return (1 / (1 + math.exp(-z))) * (1 - push)


class ChallengerWiring(unittest.TestCase):
    def test_hybrid_uses_validation_selected_weights(self):
        sim = P.simulate(proj(), 4000, 3)
        qs = [(quote("SPREAD", -4.0, -110, -110, i=0), "g1"), (quote("ML", None, -200, 170, i=1), "g1")]
        priced, rej, _ = P.price(qs, {"g1": proj()}, {"g1": sim}, 0.25, CFG, challenger=StubChallenger(),
                                 challenger_proj={"g1": {}})
        self.assertFalse(rej)
        sp = next(r for r, _ in priced if r.market == "SPREAD" and r.side == "home")
        # spread weight 0 -> hybrid is the no-vig market (times 1 - challenger push)
        self.assertAlmostEqual(sp.prob_hybrid, sp.prob_market_novig * (1 - 0.05), places=9)
        self.assertIn("W0_VALIDATION_SELECTED_OPEN", sp.hybrid_method)
        self.assertAlmostEqual(sp.prob_challenger, 0.60)
        ml = next(r for r, _ in priced if r.market == "ML" and r.side == "home")
        self.assertIn("W0.125_VALIDATION_SELECTED_OPEN", ml.hybrid_method)
        self.assertNotEqual(round(ml.prob_hybrid, 6), round(ml.prob_market_novig, 6))
        # the default (frozen) probabilities are untouched by the challenger
        self.assertNotAlmostEqual(sp.prob_model, 0.60, places=3)

    def test_challenger_only_on_full_game(self):
        sim = P.simulate(proj(), 2000, 3)
        q = quote("SPREAD", -2.0, -110, -110, period="1H")
        priced, rej, _ = P.price([(q, "g1")], {"g1": proj()}, {"g1": sim}, 0.25, CFG, challenger=StubChallenger(),
                                 challenger_proj={"g1": {}})
        self.assertEqual([r.reason_code for r in rej], ["PERIOD_NOT_IMPLEMENTED"])   # no halves adapter given

    def test_adapter_flags(self):
        st, act = P.load_adapter_flags({"fullgame", "halves"}, {"fullgame": object(), "halves": "ADAPTER_NOT_LANDED"})
        self.assertEqual(st["fullgame"], "ACTIVE_CHALLENGER_DEFAULT_STAYS_FROZEN")
        self.assertEqual(st["halves"], "ADAPTER_NOT_LANDED")
        self.assertEqual(st["players"], "OFF")
        self.assertEqual(act, {"fullgame"})


class HalvesWiring(unittest.TestCase):
    def test_half_market_priced_by_halves_adapter(self):
        calls = []
        HM = SimpleNamespace(project_period=lambda per, h, a, coefficients=None: calls.append(per) or {"per": per})

        def price_half_market(d, market, side, line, tie_rule=None):
            if market == "MONEYLINE" and tie_rule is None:
                raise ValueError("TIE_RULE_REQUIRED")
            return {"p_win": 0.55 if side in ("home", "over") else 0.40, "p_push": 0.05}
        halves = {"HM": HM, "HP": SimpleNamespace(price_half_market=price_half_market), "coef": {}, "sha256": "x",
                  "version": "test-halves"}
        sim = P.simulate(proj(), 2000, 3)
        qs = [(quote("SPREAD", -2.0, -110, -110, period="1H", i=0), "g1"),
              (quote("ML", None, -130, 110, period="1H", i=1), "g1"),
              (quote("TOTAL", 70.5, -110, -110, period="2H_HALFTIME_ADJUSTED", i=2), "g1")]
        priced, rej, _ = P.price(qs, {"g1": proj()}, {"g1": sim}, 0.25, CFG, halves=halves)
        self.assertEqual(calls, ["H1"])                                   # cached per game/period
        self.assertTrue(all(r.prob_source == "HALVES_test-halves" for r, _ in priced))
        self.assertEqual(len(priced), 4)
        self.assertEqual([r.reason_code for r in rej], ["PERIOD_NOT_IMPLEMENTED"])   # halftime-adjusted not wired


class PublicRatings(unittest.TestCase):
    def test_hca_recovered_with_equal_teams(self):
        teams = [str(i) for i in range(6)]
        prior, k = [], 0
        for rnd in range(6):
            for i in range(6):
                for j in range(6):
                    if i != j and (i + j + rnd) % 3 == 0:
                        k += 1
                        prior.append({"id": str(k), "home_id": teams[i], "away_id": teams[j], "home_score": 74,
                                      "away_score": 70, "possessions": 68.0, "neutral": False,
                                      "tip_utc": f"2026-11-{1 + rnd:02d}T20:00:00Z"})
        body, lg = P.public_ratings(prior, 2027)
        # equal teams, home always +4 on 68 possessions: the whole edge is home court (sign-fix regression)
        self.assertAlmostEqual(P.public_ratings.last_home_edge_per100, 400 / 68, places=3)
        for t in json.loads(body):
            self.assertAlmostEqual(t["netRating"], 0.0, places=2)


def _fullgame_root():
    root = Path(os.environ.get("CBB_FULLGAME_ROOT", HERE))
    if not (root / "fullgame" / "ratings.py").exists():
        return None
    return root


@unittest.skipIf(_fullgame_root() is None, "fullgame challenger stream not on this checkout (set CBB_FULLGAME_ROOT)")
class RealChallenger(unittest.TestCase):
    """The real models/cbb/fullgame code on a synthetic six-team league (wiring + parity, not quality)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        cols = ["game_id", "season", "date", "tip_utc", "home", "away", "home_name", "away_name", "site", "neutral",
                "venue_id", "home_venue_id", "home_points", "away_points", "possessions", "season_type", "home_d1",
                "away_d1"]
        rows, k = [], 0
        for day in range(1, 21):
            for i in range(6):
                j = (i + day) % 6
                if i == j or (i + day) % 2:
                    continue
                k += 1
                hp = 70 + 2 * (5 - i) + 3; ap = 70 + 2 * (5 - j)
                rows.append([str(k), 2027, f"2026-11-{day:02d}", f"2026-11-{day:02d}T20:00Z", f"t{i}", f"t{j}", "", "",
                             "HOME_VERIFIED", "False", f"v{i}", f"v{i}", hp, ap, 68.0, 2, "True", "True"])
        with open(self.tmp / "games.csv", "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(cols); w.writerows(rows)
        teams = {f"t{i}": [0.0, 0.0, 0.0] for i in range(6)}
        (self.tmp / "finals.json").write_text(json.dumps({"2026": [teams, 103.0, 68.0, 3.5], "2025": [teams, 103.0, 68.0, 3.0]}))
        d = {str(i): {"loc": 0.0, "sd": 11.0, "df": 20.0} for i in range(6)}
        d["all"] = {"loc": 0.0, "sd": 11.0, "df": 20.0}
        coef = {"margin": [0.0, 1.0], "total": [0.0, 1.0], "n": 1000}
        (self.tmp / "summary.json").write_text(json.dumps({
            "recalibration": {"2027": {"early": coef, "late": coef}},
            "dists_2027": {"FG1C": {"margin": d, "total": {**{str(i): {"loc": 0.0, "sd": 17.0, "df": 20.0} for i in range(6)},
                                                            "all": {"loc": 0.0, "sd": 17.0, "df": 20.0}},
                                    "team": {**{str(i): {"loc": 0.0, "sd": 10.0, "df": 20.0} for i in range(6)},
                                             "all": {"loc": 0.0, "sd": 10.0, "df": 20.0}}}}}))
        self.ch = P.Challenger(_fullgame_root(), self.tmp / "games.csv", self.tmp / "finals.json",
                               self.tmp / "summary.json", 2027, P.parse_z("2026-11-25T12:00:00Z"))

    def test_projection_and_probabilities(self):
        r = self.ch.project("t0", "t5", False, "v0")
        self.assertEqual(r["site"], "HOME_VERIFIED")
        self.assertGreater(r["margin"], 0)                 # stronger home team
        n = self.ch.project("t0", "t5", True, "v0")
        self.assertEqual(n["site"], "NEUTRAL")
        self.assertGreater(r["margin"], n["margin"])       # HCA applies only at the verified venue
        u = self.ch.project("t0", "t5", False, "elsewhere")
        self.assertEqual(u["site"], "UNVERIFIED")
        for m, line in (("SPREAD", -3.0), ("SPREAD", -3.5), ("TOTAL", 150.0), ("TT_HOME", 77.5), ("ML", None)):
            pa, pp, pb = self.ch.probs(r, m, line)
            self.assertAlmostEqual(pa + pp + pb, 1.0, places=9)
            self.assertEqual(pp > 0, line is not None and float(line).is_integer())
        self.assertGreater(self.ch.probs(r, "ML", None)[0], 0.5)

    def test_leakage_cutoff(self):
        self.assertLessEqual(self.ch.meta["max_prior_tip_utc"], "2026-11-25T09:00Z")
        early = P.Challenger(_fullgame_root(), self.tmp / "games.csv", self.tmp / "finals.json",
                             self.tmp / "summary.json", 2027, P.parse_z("2026-11-10T12:00:00Z"))
        self.assertLess(early.meta["prior_games"], self.ch.meta["prior_games"])

    def test_unrated_team_passes(self):
        with self.assertRaises(ValueError):
            self.ch.project("t0", "nobody", False, "v0")

    def test_logit_blend_and_audit_from_branch(self):
        self.assertAlmostEqual(self.ch.logit_blend(0.3, 0.4, 0.0), 0.4, places=12)
        self.assertAlmostEqual(self.ch.logit_blend(0.3, 0.4, 1.0), 0.3, places=12)
        self.assertIn("EV_GT_30_PCT", self.ch.audit(0.5, 1500, 0.2, 0.06))
        self.assertEqual(self.ch.audit(0.1, -110, 0.55, 0.5), [])



class UpstreamAdmission(unittest.TestCase):
    def check(self, market="TOTAL", order="over_under", **raw):
        q = quote(market, 145.5, -110, -110)
        metadata = {"raw": raw, "order": order, "price_bad": False, "line_bad": False}
        return P.validate([(q, metadata)], [], "2026-11-25T15:00:00Z",
                          totals_order_verified=True, adapters=set(),
                          match=lambda *args: ({"game_id": "g1", "tipoff_utc": q.tip_utc}, None))

    def test_upstream_hold_cannot_be_overridden(self):
        for disposition in ("HELD", "REJECTED", "SUPERSEDED", "UNKNOWN"):
            a, r = self.check(disposition=disposition, reason_codes="TOTALS_ORDER_UNVERIFIED")
            self.assertFalse(a)
            self.assertEqual(r[0].reason_code, "UPSTREAM_QUOTE_WITHHELD")

    def test_team_totals_require_explicit_order(self):
        a, r = self.check(market="TT_HOME", order="", disposition="ACCEPTED")
        self.assertFalse(a)
        self.assertEqual(r[0].reason_code, "TOTALS_ORDER_UNVERIFIED")
        a, r = self.check(market="TT_AWAY", disposition="ACCEPTED")
        self.assertEqual(len(a), 1)
        self.assertFalse(r)

    def test_evidence_clocks_must_be_available(self):
        for field in ("quote_available_utc", "as_of_utc"):
            for bad in ("2026-11-25T15:01:00Z", "2026-11-25T11:59:00Z", "not a clock"):
                a, r = self.check(disposition="ACCEPTED", **{field: bad})
                self.assertFalse(a)
                self.assertEqual(r[0].reason_code, "QUOTE_AFTER_FREEZE")
        a, r = self.check(disposition="ACCEPTED", quote_available_utc="2026-11-25T12:00:00Z")
        self.assertEqual(len(a), 1)
        self.assertFalse(r)

    def test_accepted_reason_and_explicit_live_rejected(self):
        for raw, reason in (({"disposition": "ACCEPTED", "reason_codes": "CONFLICT"},
                             "UPSTREAM_QUOTE_WITHHELD"), ({"live": "true"}, "LIVE_GAME")):
            a, r = self.check(**raw)
            self.assertFalse(a)
            self.assertEqual(r[0].reason_code, reason)

    def test_team_total_hybrid_label_not_validated(self):
        q = quote("TT_HOME", 74.5, -110, -110)
        priced, rejects, _ = P.price([(q, "g1")], {"g1": proj()},
            {"g1": P.simulate(proj(), 2000, 3)}, 0.25, CFG,
            challenger=StubChallenger(), challenger_proj={"g1": {}})
        self.assertFalse(rejects)
        self.assertEqual(len(priced), 2)
        self.assertTrue(all("UNVALIDATED_TEAM_TOTAL" in r.hybrid_method for r, _ in priced))



class PlayerRunnerWiring(unittest.TestCase):
    def test_two_players_same_line_do_not_collide(self):
        from dataclasses import replace
        q = replace(quote("PLAYER_PTS_OU", 12.5, -110, -110), player_id="p1", player_team_id="h")
        q2 = replace(q, board_index=1, player_id="p2")
        meta = {"raw": {}, "order": "over_under", "price_bad": False, "line_bad": False}
        accepted, rejects = P.validate([(q, meta), (q2, meta)], [], "2026-11-25T15:00:00Z",
            totals_order_verified=False, adapters={"players"},
            match=lambda *args: ({"game_id": "g1", "tipoff_utc": q.tip_utc}, None))
        self.assertFalse(rejects)
        self.assertEqual(len(accepted), 2)
        bundle = SimpleNamespace(probs=lambda *args: (0.6, 0.0, 0.4))
        game = SimpleNamespace(home_team_id="h", away_team_id="a", tipoff_utc=q.tip_utc)
        priced, rejected, parity = P.price(accepted, {}, {}, 0.25, CFG, players=bundle, games={"g1": game})
        self.assertEqual(len(priced), 4)
        self.assertFalse(rejected)
        self.assertFalse(parity)
        self.assertEqual({r.player_id for r, _ in priced}, {"p1", "p2"})
        self.assertTrue(all("CONDITIONAL_PARTICIPATION_UNVALIDATED" in r.audit_flags for r, _ in priced))
        grades, cal = P.grade({"priced": [C.row_dict(r) for r, _ in priced]}, {"g1": {"home": 70, "away": 65}})
        self.assertEqual(len(grades), 4)
        self.assertFalse(cal)
        self.assertEqual({r.player_id for r in grades}, {"p1", "p2"})
        self.assertTrue(all(r.result == "NOT_GRADABLE" for r in grades))

    def test_missing_wrong_team_and_missing_forecast(self):
        from dataclasses import replace
        q = replace(quote("PLAYER_PTS_OU", 12.5, -110, -110), player_id="p1", player_team_id="wrong")
        game = SimpleNamespace(home_team_id="h", away_team_id="a", tipoff_utc=q.tip_utc)
        def refuse(*args):
            raise ValueError("PLAYER_FORECAST_MISSING")
        bundle = SimpleNamespace(probs=refuse)
        for candidate, reason in ((q, "PLAYER_ID_UNKNOWN"), (replace(q, player_team_id="h"), "PLAYER_FORECAST_MISSING")):
            priced, rejected, _ = P.price([(candidate, "g1")], {}, {}, 0.25, CFG,
                players=bundle, games={"g1": game})
            self.assertFalse(priced)
            self.assertEqual(rejected[0].reason_code, reason)



class HalfGradeWiring(unittest.TestCase):
    def test_half_grade_uses_halftime_not_full_score(self):
        base = dict(game_id="g1", period="1H", market="TOTAL", line=70.0,
                    price=-110, prob_model=0.60, prob_push=0.05, prob_market_novig=0.5,
                    ev_model=0.15, side="under")
        other = dict(base, side="over", prob_model=0.35, ev_model=-0.2)
        card = {"priced": [base, other]}
        for h1, expected in (([32, 32], "W"), ([35, 35], "P"), ([40, 35], "L"),
                             (None, "NOT_GRADABLE"), ([100, 32], "NOT_GRADABLE")):
            grades, _ = P.grade(card, {"g1": {"home": 80, "away": 75, "h1": h1}})
            self.assertEqual(grades[0].result, expected)
            self.assertEqual(grades[0].period, "1H")
        tied_ml = dict(base, market="ML", line=None, side="home")
        grades, _ = P.grade({"priced": [tied_ml]}, {"g1": {"home": 80, "away": 75, "h1": [32, 32]}})
        self.assertEqual(grades[0].result, "NOT_GRADABLE")



class ConditionalPlayerGrade(unittest.TestCase):
    def test_conditional_stats_excluded_from_roi_and_all_calibration(self):
        row = dict(game_id="g1", period="FG", market="PLAYER_PRA_OU", line=25.0,
                   player_id="p", player_team_id="h", price=-110, side="over",
                   prob_model=0.6, prob_push=0.1, prob_market_novig=0.5, ev_model=0.15)
        card = {"priced": [row, dict(row, side="under", prob_model=0.3, ev_model=-0.5)]}
        finals = {"g1": {"home": 80, "away": 70}}
        stats = {"PTS": 16, "REB": 7, "AST": 3, "3PM": 2}
        grades, cal = P.grade(card, finals, player_finals={("g1", "h", "p"): stats})
        self.assertEqual([g.result for g in grades], ["CONDITIONAL_WIN", "CONDITIONAL_LOSS"])
        self.assertTrue(all(g.return_1u is None for g in grades))
        self.assertEqual(P.grade_summary(grades)["ALL"]["n"], 0)
        self.assertNotIn("ALL", P.calibration_summary(cal))
        self.assertIn("CONDITIONAL:PLAYER_PRA_OU", P.calibration_summary(cal))
        grades, cal = P.grade(card, finals, player_finals={("g1", "a", "p"): stats})
        self.assertTrue(all(g.result == "NOT_GRADABLE" for g in grades))
        self.assertFalse(cal)


if __name__ == "__main__":
    unittest.main()
