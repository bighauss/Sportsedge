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


class PlayerFailClosed(unittest.TestCase):
    def test_loaded_player_adapter_cannot_claim_active(self):
        status, active = P.load_adapter_flags({"players"}, {"players": object()})
        self.assertEqual(status["players"], "PLAYER_MODEL_NOT_IMPLEMENTED")
        self.assertNotIn("players", active)

    def test_active_flag_cannot_admit_player_into_game_pricer(self):
        from dataclasses import replace
        q = replace(quote("PLAYER_PTS_OU", 19.5, -110, -110), player="P1")
        meta = {"raw": {}, "price_bad": False, "line_bad": False, "order": "over_under"}
        accepted, rejects = P.validate([(q, meta)], [], "2026-11-25T13:00:00Z",
                                       totals_order_verified=True, match=None, adapters={"players"})
        self.assertEqual(accepted, [])
        self.assertEqual([r.reason_code for r in rejects], ["PLAYER_MODEL_NOT_IMPLEMENTED"])
        priced, rejects, parity = P.price([(q, "g1")], {"g1": proj()}, {}, 0.25, CFG)
        self.assertEqual((priced, parity), ([], []))
        self.assertEqual([r.reason_code for r in rejects], ["PLAYER_MODEL_NOT_IMPLEMENTED"])
        coverage, _ = P.coverage([(q, meta)], [], [], rejects, [], {"players"})
        row = next(r for r in coverage if r["market"] == q.market and r["period"] == q.period)
        self.assertEqual(row["status"], "NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED")

    def test_game_market_with_player_is_rejected_at_both_boundaries(self):
        from dataclasses import replace
        q = replace(quote("TOTAL", 144.5, -110, -110), player="P1")
        meta = {"raw": {}, "price_bad": False, "line_bad": False, "order": "over_under"}
        accepted, rejects = P.validate([(q, meta)], [], "2026-11-25T13:00:00Z",
                                       totals_order_verified=True, match=None, adapters=set())
        self.assertEqual(accepted, [])
        self.assertEqual([r.reason_code for r in rejects], ["UNSUPPORTED_MARKET"])
        priced, rejects, _ = P.price([(q, "g1")], {"g1": proj()}, {}, 0.25, CFG)
        self.assertEqual(priced, [])
        self.assertEqual([r.reason_code for r in rejects], ["UNSUPPORTED_MARKET"])


class PlayerResearchWiring(unittest.TestCase):
    def test_real_residual_bundle_separates_same_named_players_and_holds_bad_bindings(self):
        from dataclasses import replace
        means = {"PTS": 12, "REB": 5, "AST": 3, "3PM": 2}
        freeze = "2026-11-25T13:00:00Z"
        tip = "2026-11-25T20:00:00Z"
        g = C.GameRow("g1", 2027, tip, "2 PM CT", "Home U", "Away U", "t", "u", False,
                      "UNVERIFIED_SINGLE_SOURCE_ESPN", dk_event_id="123", id_source="ESPN_PUBLIC_REPLAY")
        targets, history, quotes, bindings = [], [], [], {}
        for i, pid in enumerate(("p1", "p2")):
            target = dict(event_id="g1", team_id="t", player_id=pid, tip_utc=tip,
                          frozen_utc="2026-11-25T10:00:00Z", means=means, model_version="v1")
            targets.append(target)
            for day in range(1, 21):
                past = dict(target, event_id=str(day), tip_utc=f"2026-11-{day:02d}T20:00:00Z",
                            frozen_utc=f"2026-11-{day:02d}T10:00:00Z")
                actual = dict(means, PTS=12 if day <= 10 else (15 if i == 0 else 9))
                history.append(dict(forecast=past, observed_final_utc=f"2026-11-{day:02d}T23:00:00Z",
                                    actual=actual, participated=True))
            q = replace(quote("PLAYER_PTS_OU", 12.0, -110, -110, i=i), player="Same Name",
                        dk_market_id=f"market-{i}", source_sha256="a" * 64)
            quotes.append((q, {"raw": {}, "price_bad": False, "line_bad": False, "order": "over_under"}))
            bindings[i] = dict(game_id="g1", board_sha256=q.source_sha256, dk_event_id=q.dk_event_id,
                               dk_market_id=q.dk_market_id, player_name=q.player, market=q.market, line=q.line,
                               price_a=q.price_a, price_b=q.price_b, side_a=q.side_a, side_b=q.side_b,
                               namespace="ESPN", team_id="t", player_id=pid)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bundle.json"
            p.write_text(json.dumps(dict(schema="CBB_PLAYER_RESIDUAL_BUNDLE_V1", identity_namespace="ESPN",
                                         evidence_class="SYNTHETIC", targets=targets, history=history)))
            ctx = P.PlayerResearchContext(p, bindings, {"g1": g}, freeze)
            slate = [{"game_id": "g1", "tipoff_utc": tip}]
            match = lambda *args: (slate[0], None)
            accepted, rejects = P.validate(quotes, slate, freeze, totals_order_verified=False,
                                           match=match, adapters=set(), as_of_utc=freeze, player_context=ctx)
            self.assertFalse(rejects)
            self.assertEqual(len(accepted), 2)
            report, rejects = ctx.price_rows(accepted)
            self.assertFalse(rejects)
            self.assertEqual(len(report["rows"]), 4)
            over = {r["player_id"]: r for r in report["rows"] if r["side"] == "over"}
            self.assertEqual(over["p1"]["p_win_given_participation"], 0.5)
            self.assertEqual(over["p2"]["p_win_given_participation"], 0.0)
            self.assertTrue(all(r["p_push_given_participation"] == 0.5 for r in report["rows"]))
            self.assertTrue(all(r["samples"] == 20 and r["approved_stake_u"] == 0 and
                                r["counted"] == C.NON_COUNTED for r in report["rows"]))
            self.assertEqual(report["evidence_status"], "UNVERIFIED_RESEARCH_INPUTS")
            normal, _ = P.validate(quotes, slate, freeze, totals_order_verified=True, match=match, adapters={"players"})
            self.assertEqual(normal, [])
            self.assertEqual(P.price(accepted, {}, {}, 0.25, CFG)[0], [])
            wrong = dict(bindings)
            wrong[0] = dict(wrong[0], team_id="u")
            other = P.PlayerResearchContext(p, wrong, {"g1": g}, freeze)
            rejected, why = P.validate([quotes[0]], slate, freeze, totals_order_verified=True,
                                       match=match, adapters=set(), player_context=other)
            self.assertEqual(rejected, [])
            self.assertEqual(why[0].reason_code, "PLAYER_TEAM_UNKNOWN")
            q, meta = quotes[0]
            rejected, why = P.validate([(q, dict(meta, order=""))], slate, freeze, totals_order_verified=True,
                                       match=match, adapters=set(), player_context=ctx)
            self.assertEqual(rejected, [])
            self.assertEqual(why[0].reason_code, "TOTALS_ORDER_UNVERIFIED")
            changed = replace(q, price_a=-120)
            self.assertEqual(ctx.price_rows([(changed, "g1")])[0]["rows"], [])

            self.assertTrue(all(r["selected_for_card"] is False and r["wager_eligible"] is False
                                for r in report["rows"]))
            self.assertEqual(report["binding_evidence"], "CALLER_SUPPLIED_UNAUTHENTICATED")
            self.assertEqual(report["sample_threshold_status"], "UNVALIDATED_RESEARCH_FLOOR")
            with self.assertRaisesRegex(ValueError, "PLAYER_RESEARCH_RANK_ISOLATION"):
                P.rank([(report["rows"][0], q)])
            with self.assertRaisesRegex(ValueError, "PLAYER_RESEARCH_GRADE_ISOLATION"):
                P.grade({"priced": report["rows"]}, {"g1": {"home": 75, "away": 70}})

            # Full orchestration with real CSV, residual pricer, simulation, freeze
            # and grade. Only source capture / game projection / match are synthetic.
            from unittest import mock
            import cbb_run_it as R
            base = dict(sport="CBB", home="Home U", away="Away U", period="FG",
                        tip_utc=tip, captured_utc="2026-11-25T12:00:00Z",
                        price_a=-110, price_b=-110, totals_order="over_under")
            board_rows = [dict(base, market="TOTAL", line=144.5, dk_event_id="123"),
                          dict(base, market="PLAYER_PTS_OU", line=12.0, player="Same Name",
                               dk_event_id="123", dk_market_id="market-0"),
                          dict(base, market="PLAYER_PTS_OU", line=12.0, player="Same Name",
                               dk_event_id="999", dk_market_id="market-1")]
            bp = Path(tmp) / "board.csv"
            with bp.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=sorted({k for r in board_rows for k in r}))
                writer.writeheader()
                writer.writerows(board_rows)
            board_hash = P.sha_bytes(bp.read_bytes())
            real_bindings = {i + 1: dict(b, board_sha256=board_hash,
                                         dk_event_id=board_rows[i + 1]["dk_event_id"])
                             for i, b in bindings.items()}
            games = {"g1": dict(home="Home U", away="Away U", home_alt=["Home U"], away_alt=["Away U"],
                                home_id="t", away_id="u", neutral=False, tip_utc=tip, completed=True,
                                home_score=75, away_score=70)}
            kwargs = dict(date_ct="2026-11-25", board=str(bp),
                          board_captured_utc="2026-11-25T12:00:00Z", freeze_utc=freeze, season=2027,
                          raw_dir=tmp, totals_order_verified=True, n_sims=1000, fetch=False,
                          now=P.parse_z("2026-11-26T00:00:00Z"), grade_finals=True)
            off, on = Path(tmp) / "off", Path(tmp) / "on"
            with mock.patch.object(P, "espn_capture", return_value=[]), \
                    mock.patch.object(P, "espn_games", return_value=(games, [])), \
                    mock.patch.object(P, "public_replay_project", return_value=({"g1": proj()}, {}, b"fixture")), \
                    mock.patch.object(R, "_match", side_effect=lambda slate, *args: (slate[0], None)):
                P.run_public_replay(out_dir=off, **kwargs)
                summary = P.run_public_replay(out_dir=on, adapters_requested=("players",),
                                              player_bundle_path=p, player_bindings=real_bindings, **kwargs)
            before = json.loads((off / "pipeline_card.json").read_text())
            after = json.loads((on / "pipeline_card.json").read_text())
            self.assertTrue(before["priced"])
            # Compare deterministic serialized bytes of the actual game-only fields.
            # Full artifacts intentionally differ in research metadata and card digest.
            canonical = lambda x: json.dumps(x, sort_keys=True, separators=(",", ":"),
                                             allow_nan=False).encode("utf-8")
            for field in ("priced", "nine_weight_grid", "games", "projections"):
                self.assertEqual(canonical(before[field]), canonical(after[field]), field)
            self.assertEqual(summary["player_research_priced_sides"], 2)
            self.assertEqual({r["player_id"] for r in after["player_research"]["rows"]}, {"p1"})
            self.assertTrue(all(r["selected_for_card"] is False for r in after["player_research"]["rows"]))
            self.assertTrue(any(r["reason_code"] == "PLAYER_TEAM_UNKNOWN" and r["board_index"] == 2
                                for r in after["rejections"]))
            self.assertEqual(P.grade(before, {"g1": {"home": 75, "away": 70}}),
                             P.grade(after, {"g1": {"home": 75, "away": 70}}))
            grade_docs = [json.loads((directory / "grades.json").read_text()) for directory in (off, on)]
            for grades in grade_docs:
                self.assertTrue(grades["rows"])
                self.assertTrue(all(not r["market"].startswith("PLAYER_") for r in grades["rows"]))
            for field in ("rows", "summary"):
                self.assertEqual(canonical(grade_docs[0][field]), canonical(grade_docs[1][field]), field)


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


if __name__ == "__main__":
    unittest.main()
