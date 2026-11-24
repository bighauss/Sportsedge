"""Tests for the CBB end-to-end fixes (SYNTHETIC fixtures; PAPER / 0u; not predictive validation):
totals-order binding to the board format, DK event ID + tip-time match, SD constants, blend config,
blowout guard, ladder / team-total pricing, run receipt."""
import csv, json, math, os, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1]))
import cbb_run_it as R
import cbb_pricing as PR
import cbbd_native_score_model as NM
import test_cbb_run_it as T
import cbbd_paper_synthetic as S

def row(market, line, pa="-110", pb="-110", home="Synthetic 1", away="Synthetic 2", **kw):
    return {"sport": "CBB", "home": home, "away": away, "market": market, "line": line,
            "price_a": pa, "price_b": pb, **kw}

def go(board, **kw):
    with tempfile.TemporaryDirectory() as d:
        return T.run(d, board_rows=board, **kw)

def m_of(card, gid, market):
    return next(m for r in card["rows"] if r["game_id"] == gid for m in r["markets"] if m["market"] == market)

class TotalsBinding(unittest.TestCase):
    def test_global_constant_stays_false_and_totals_withheld_by_default(self):
        self.assertFalse(R.TOTALS_ORDER_VERIFIED)
        card, _, extra = go([row("TOTAL", "140.5")])
        self.assertEqual(m_of(card, "9001", "total")["status"], "PASS")
        self.assertTrue(any(w[1] == "TOTAL" for w in extra["quotes_unmatched"]))

    def test_run_level_format_flag_prices_totals(self):
        card, _, _ = go([row("TOTAL", "140.5")], totals_order_verified=True)
        self.assertEqual(m_of(card, "9001", "total")["status"], "PRICED_PAPER")

    def test_row_level_format_column(self):
        card, _, _ = go([row("TOTAL", "140.5", totals_order="over_under")])
        self.assertEqual(m_of(card, "9001", "total")["status"], "PRICED_PAPER")

    def test_under_over_format_swaps_prices(self):
        card, _, _ = go([row("TOTAL", "140.5", "-120", "100", totals_order="under_over")])
        q = m_of(card, "9001", "total")["quote"]
        self.assertEqual((q["price_a"], q["price_b"]), (100, -120))   # price_a = over after swap

    def test_flag_does_not_leak_to_spreads_or_other_rows(self):
        q, un = R.board_quotes([row("TOTAL", "140.5"), row("TOTAL", "141.5", totals_order="over_under")],
                               R.slate(T.provider()[0], T.NOW.date(), T.NOW, S.SEASON), "2026-11-21T14:30:00Z")
        self.assertEqual([x["line"] for x in q], ["141.5"]); self.assertEqual(len(un), 1)

class RowCaptureProvenance(unittest.TestCase):
    def test_main_quote_uses_row_timestamp_and_rejects_future_quote(self):
        board = [row("SPREAD", "-3.5", captured_utc="2026-11-21T15:01:00Z"),
                 row("TOTAL", "140.5", totals_order="over_under",
                     captured_utc="2026-11-21T14:20:00Z")]
        card, _, _ = go(board)
        self.assertEqual(m_of(card, "9001", "spread")["status"], "PASS")
        total = m_of(card, "9001", "total")
        self.assertEqual(total["status"], "PRICED_PAPER")
        self.assertEqual(total["quote"]["captured_utc"], "2026-11-21T14:20:00Z")

    def test_explicit_invalid_order_cannot_be_overridden_by_format_flag(self):
        card, _, extra = go([row("TOTAL", "140.5", totals_order="unknown"),
                             row("TT_HOME", "72.5", totals_order="unknown")],
                            totals_order_verified=True, config=LOOSE)
        self.assertEqual(m_of(card, "9001", "total")["status"], "PASS")
        self.assertEqual(extra["ladders"], [])
        self.assertTrue(any("TOTALS_ORDER_UNVERIFIED" in w[2] for w in extra["ladders_skipped"]))

    def test_ladder_preserves_row_timestamp(self):
        _, _, extra = go([row("TT_HOME", "72.5", totals_order="over_under",
                              captured_utc="2026-11-21T14:20:00Z",
                              dk_event_id="E1", tip_utc=S.TIP)])
        self.assertEqual(len(extra["ladders"]), 1)
        self.assertEqual(extra["ladders"][0]["captured_utc"], "2026-11-21T14:20:00Z")
        self.assertEqual(extra["ladders"][0]["dk_event_id"], "E1")


class Matching(unittest.TestCase):
    def slate(self):
        return R.slate(T.provider()[0], T.NOW.date(), T.NOW, S.SEASON)

    def test_tip_time_within_window_matches_and_outside_does_not(self):
        s = self.slate()
        ok, _ = R._match(s, "Synthetic 1", "Synthetic 2", {"tip_utc": S.TIP})
        self.assertEqual(ok["game_id"], "9001")
        bad, why = R._match(s, "Synthetic 1", "Synthetic 2", {"tip_utc": "2026-11-21T20:00:00Z"})
        self.assertIsNone(bad); self.assertIn("15 min", why)
        bad, why = R._match(s, "Synthetic 1", "Synthetic 2", {"tip_utc": "garbage"})
        self.assertIsNone(bad); self.assertIn("unparsable", why)

    def test_tip_time_separates_same_name_doubleheader(self):
        s = self.slate(); twin = dict(s[0], game_id="9099", tipoff_utc="2026-11-21T20:00:00Z")
        g, why = R._match(s + [twin], "Synthetic 1", "Synthetic 2", None)
        self.assertEqual(why, "ambiguous CBBD game")
        g, _ = R._match(s + [twin], "Synthetic 1", "Synthetic 2", {"tip_utc": "2026-11-21T20:05:00Z"})
        self.assertEqual(g["game_id"], "9099")

    def test_dk_event_id_conflict_quarantines_rows(self):
        s = self.slate()
        board = [row("SPREAD", "-3.5", dk_event_id="E1"), row("ML", "", "-150", "130", dk_event_id="E2")]
        q, un = R.board_quotes(board, s, "2026-11-21T14:30:00Z")
        self.assertEqual(q, []); self.assertEqual({w[2] for w in un}, {"DK event id conflict"})
        board = [row("SPREAD", "-3.5", dk_event_id="E1"), row("ML", "", "-150", "130", dk_event_id="E1")]
        q, un = R.board_quotes(board, s, "2026-11-21T14:30:00Z")
        self.assertEqual(len(q), 2)

    def test_names_only_boards_still_work(self):
        q, _ = R.board_quotes([row("SPREAD", "-3.5")], self.slate(), "2026-11-21T14:30:00Z")
        self.assertEqual(len(q), 1)

class PricingConfig(unittest.TestCase):
    def test_sd_constants_default_and_configurable(self):
        card, _, _ = go([row("SPREAD", "-3.5")])
        p = next(r for r in card["rows"] if r["game_id"] == "9001")["projection"]
        self.assertEqual((p["sd_margin"], p["sd_total"]), (12.5, 17.0))
        self.assertEqual(p["sd_basis"], "CONFIG_CONSTANT_NOT_FITTED")
        card, _, _ = go([row("SPREAD", "-3.5")], config={"sd_margin": 11.0, "sd_total": 15.0})
        p = next(r for r in card["rows"] if r["game_id"] == "9001")["projection"]
        self.assertEqual((p["sd_margin"], p["sd_total"]), (11.0, 15.0))

    def test_patch_is_restored(self):
        orig = R.PC.project
        go([row("SPREAD", "-3.5")])
        self.assertIs(R.PC.project, orig)

    def test_blend_default_labeled_and_configurable(self):
        self.assertEqual(PR.DEFAULT_CONFIG["blend_weight_model"], 0.25)
        card, _, _ = go([row("SPREAD", "-3.5")])
        m = m_of(card, "9001", "spread"); b = m["blend"]
        self.assertEqual((b["label"], b["weight_model"]), ("EXPERIMENTAL", 0.25))
        want = 0.25 * m["model_prob"]["home"] + 0.75 * m["market_novig_prob"]["home"]
        self.assertAlmostEqual(b["prob"]["home"], want)
        card, _, _ = go([row("SPREAD", "-3.5")], config={"blend_weight_model": 1.0})
        m = m_of(card, "9001", "spread")
        self.assertAlmostEqual(m["blend"]["prob"]["home"], m["model_prob"]["home"])
        self.assertAlmostEqual(m["blend"]["paper_ev_per_1u_at_price"]["home"], m["paper_ev_per_1u_at_price"]["home"])
        for bad in (-0.1, 1.1):
            with self.assertRaises(ValueError): PR.make_config(blend_weight_model=bad)
        self.assertIn(0.25, PR.CANDIDATE_BLEND_WEIGHTS); self.assertEqual(len(PR.CANDIDATE_BLEND_WEIGHTS), 9)

    def test_push_aware_blend_all_nine_weights(self):
        for w in PR.CANDIDATE_BLEND_WEIGHTS:
            for market, line in (("SPREAD", "-3"), ("TOTAL", "140")):
                with self.subTest(weight=w, market=market):
                    card, _, _ = go([row(market, line, "-120", "100")],
                                    totals_order_verified=True,
                                    config={"blend_weight_model": w})
                    m = m_of(card, "9001", {"SPREAD": "spread", "TOTAL": "total"}[market])
                    pm, mk, b = m["model_prob"], m["market_novig_prob"], m["blend"]
                    self.assertGreater(pm["push"], 0)
                    self.assertAlmostEqual(sum(b["prob"].values()) + b["push"], 1)
                    for side, price in zip(m["sides"], (-120, 100)):
                        want = w * pm[side] + (1-w) * (1-pm["push"]) * mk[side]
                        self.assertAlmostEqual(b["prob"][side], want)
                        self.assertAlmostEqual(b["paper_ev_per_1u_at_price"][side],
                                               NM.ev_per_unit(want, pm["push"], price))

    def test_push_aware_ladder_ev(self):
        for w in PR.CANDIDATE_BLEND_WEIGHTS:
            _, _, extra = go([row("TOTAL", "140.5"), row("ALT_TOTAL", "145", "+130", "-150")],
                             totals_order_verified=True, config={"blend_weight_model": w, **LOOSE})
            L = extra["ladders"][0]
            self.assertGreater(L["push"], 0)
            self.assertAlmostEqual(sum(L["model_prob"]) + L["push"], 1)
            for i, price in enumerate((130, -150)):
                want = w * L["model_prob"][i] + (1-w) * (1-L["push"]) * L["market_novig"][i]
                self.assertAlmostEqual(L["blend_ev"][i], NM.ev_per_unit(want, L["push"], price))

    def test_blowout_guard(self):
        card, names, extra = go([row("SPREAD", "-16.5")])
        self.assertTrue(m_of(card, "9001", "spread")["blowout_excluded"])
        md = R.render(card, names, extra)
        self.assertIn("excluded from best plays", md)
        best = md.split("## Priced markets")[1].split("## ")[0]
        self.assertNotIn("| spread |", best)
        card, names, extra = go([row("SPREAD", "-15")])             # boundary: not > 15
        self.assertFalse(m_of(card, "9001", "spread")["blowout_excluded"])
        card, _, _ = go([row("SPREAD", "14.5")]); self.assertFalse(m_of(card, "9001", "spread")["blowout_excluded"])
        card, _, _ = go([row("SPREAD", "15.5")]); self.assertTrue(m_of(card, "9001", "spread")["blowout_excluded"])

class Ladders(unittest.TestCase):
    def test_ladders_use_same_mean_and_sd(self):
        board = [row("SPREAD", "-3.5"), row("ALT_SPREAD", "-6.5", "+150", "-190"),
                 row("ALT_TOTAL", "145.5", "+120", "-150"), row("TT_HOME", "72.5"), row("TT_AWAY", "68.5"),
                 row("TT_AWAY", "", "-110", "-110"), row("ALT_TOTAL", "150.5", "+200", "n/a"), row("TOTAL", "140.5")]
        card, names, extra = go(board, totals_order_verified=True, config=LOOSE)
        p = next(r for r in card["rows"] if r["game_id"] == "9001")["projection"]
        L = {(x["kind"], x["line"]): x for x in extra["ladders"]}
        self.assertEqual(len(extra["ladders"]), 4); self.assertEqual(len(extra["ladders_skipped"]), 2)
        a = L[("alt_spread", -6.5)]
        self.assertAlmostEqual(a["model_prob"][0], 1 - NM._cdf((6.5 - p["margin"]) / 12.5))
        t = L[("alt_total", 145.5)]
        self.assertAlmostEqual(t["model_prob"][0], 1 - NM._cdf((145.5 - p["total"]) / 17.0))
        h = L[("team_total_home", 72.5)]
        self.assertAlmostEqual(h["model_prob"][0], 1 - NM._cdf((72.5 - p["home_points"]) / (17.0 / math.sqrt(2))))
        md = R.render(card, names, extra)
        self.assertIn("Alt ladders and team totals", md); self.assertIn("ladder row skipped", md)

    def test_alt_blowout_rung_flagged_and_unposted_skipped(self):
        card, _, extra = go([row("SPREAD", "-3.5"), row("ALT_SPREAD", "-20.5", "+300", "-400"), row("TT_HOME", "")],
                              totals_order_verified=True, config=LOOSE)
        self.assertTrue(extra["ladders"][0]["blowout_excluded"]); self.assertEqual(len(extra["ladders_skipped"]), 1)

    def test_ladders_never_enter_ledger_card_rows(self):
        card, _, _ = go([row("TOTAL", "140.5"), row("ALT_TOTAL", "145.5", "+120", "-150")], totals_order_verified=True, config=LOOSE)
        self.assertEqual({m["market"] for r in card["rows"] for m in r["markets"]}, {"moneyline", "spread", "total"})

LOOSE = {"require_event_and_tip": False}      # name-only boards; strict event+tip mode is tested separately

def ladders(board, **kw):
    kw.setdefault("totals_order_verified", True)
    kw["config"] = {**LOOSE, **kw.get("config", {})}
    _, _, extra = go(board, **kw)
    return {(x["kind"], x["line"]) for x in extra["ladders"]}, [w[2] for w in extra["ladders_skipped"]]

MAIN = [row("SPREAD", "-3.5"), row("TOTAL", "140.5")]

class AltQuoteValidation(unittest.TestCase):
    def test_one_sided_or_missing_price_skipped(self):
        got, why = ladders(MAIN + [row("ALT_SPREAD", "-6.5", "+150", ""), row("ALT_SPREAD", "-7.5", "", "-190"),
                                   row("ALT_TOTAL", "145.5", "+120", "n/a"), row("ALT_TOTAL", "", "+120", "-150")])
        self.assertEqual(got, set()); self.assertEqual(len(why), 4)

    def test_implausible_prices_and_no_vig_sum_rejected(self):
        got, why = ladders(MAIN + [row("ALT_SPREAD", "-6.5", "+150", "+150"),      # sum < 1 (arb-like)
                                   row("ALT_SPREAD", "-7.5", "-400", "-400"),      # overround ~ 0.6
                                   row("ALT_SPREAD", "-8.5", "+9000", "-9500"),    # absurd magnitude
                                   row("ALT_SPREAD", "-5.5", "+120", "-150")])     # fine
        self.assertEqual(got, {("alt_spread", -5.5)}); self.assertEqual(len(why), 3)
        self.assertTrue(any("NOVIG_SUM_OUT_OF_RANGE" in w for w in why)); self.assertTrue(any("IMPLAUSIBLE_PRICE_MAGNITUDE" in w for w in why))

    def test_line_grid_and_bounds(self):
        got, why = ladders(MAIN + [row("ALT_SPREAD", "-6.3", "+150", "-190"), row("ALT_TOTAL", "10.5", "+120", "-150")])
        self.assertEqual(got, set()); self.assertEqual(len(why), 2)

    def test_unposted_rungs_are_never_priced(self):
        got, _ = ladders(MAIN)
        self.assertEqual(got, set())

    def test_orientation_must_agree_with_main_line(self):
        # home laying MORE points (-8.5) but priced SHORTER than the -3.5 main line: reversed order
        got, why = ladders(MAIN + [row("ALT_SPREAD", "-8.5", "-250", "+200")])
        self.assertEqual(got, set()); self.assertTrue(any("ORIENTATION_INCONSISTENT" in w for w in why))
        got, _ = ladders(MAIN + [row("ALT_SPREAD", "-8.5", "+200", "-250")]); self.assertEqual(got, {("alt_spread", -8.5)})
        # over at a HIGHER total priced shorter than the main over: reversed
        got, why = ladders(MAIN + [row("ALT_TOTAL", "150.5", "-250", "+200")])
        self.assertEqual(got, set()); self.assertTrue(any("ORIENTATION_INCONSISTENT" in w for w in why))
        got, _ = ladders(MAIN + [row("ALT_TOTAL", "150.5", "+200", "-250")]); self.assertEqual(got, {("alt_total", 150.5)})

    def test_alt_without_main_line_not_priced(self):
        got, why = ladders([row("ALT_SPREAD", "-6.5", "+150", "-190")])
        self.assertEqual(got, set()); self.assertTrue(any("NO_MAIN_LINE" in w for w in why))

    def test_team_total_ladder_must_be_monotone(self):
        got, _ = ladders([row("TT_HOME", "70.5", "-150", "+120"), row("TT_HOME", "75.5", "+150", "-190")])
        self.assertEqual(got, {("team_total_home", 70.5), ("team_total_home", 75.5)})
        got, why = ladders([row("TT_HOME", "70.5", "+150", "-190"), row("TT_HOME", "75.5", "-150", "+120")])
        self.assertEqual(got, set()); self.assertEqual(len(why), 2)

    def test_duplicate_rung_quarantined(self):
        got, why = ladders(MAIN + [row("ALT_SPREAD", "-6.5", "+150", "-190"), row("ALT_SPREAD", "-6.5", "+140", "-180")])
        self.assertEqual(got, set()); self.assertEqual(len(why), 2)

    def test_totals_orientation_binds_ladders_too(self):
        got, why = ladders(MAIN + [row("ALT_TOTAL", "145.5", "+120", "-150"), row("TT_HOME", "72.5")], totals_order_verified=False)
        self.assertEqual(got, set()); self.assertEqual(len(why), 2)
        got, _ = ladders([row("SPREAD", "-3.5"), row("TOTAL", "140.5", totals_order="over_under"),
                          row("ALT_TOTAL", "145.5", "-150", "+120", totals_order="under_over")], totals_order_verified=False)
        self.assertEqual(got, {("alt_total", 145.5)})

    def test_event_id_binding_for_ladders(self):
        main = [row("SPREAD", "-3.5", dk_event_id="E1"), row("TOTAL", "140.5", dk_event_id="E1")]
        got, _ = ladders(main + [row("ALT_SPREAD", "-6.5", "+150", "-190", dk_event_id="E1")]); self.assertEqual(len(got), 1)
        got, why = ladders(main + [row("ALT_SPREAD", "-6.5", "+150", "-190", dk_event_id="E2")])
        self.assertEqual(got, set()); self.assertTrue(any("EVENT_BINDING_CONFLICT" in w for w in why))
        got, why = ladders(main + [row("ALT_SPREAD", "-6.5", "+150", "-190")])       # event id missing on the rung
        self.assertEqual(got, set())

    def test_tip_time_mismatch_and_stale_or_post_freeze_board(self):
        got, why = ladders(MAIN + [row("ALT_SPREAD", "-6.5", "+150", "-190", tip_utc="2026-11-21T20:00:00Z")])
        self.assertEqual(got, set()); self.assertTrue(any("15 min" in w for w in why))
        for stamp in ("2026-11-21T15:30:00Z", "2026-11-19T15:00:00Z"):                  # after freeze / >24h old
            _, _, extra = go(MAIN + [row("ALT_SPREAD", "-6.5", "+150", "-190")], board_captured_utc=stamp, config=LOOSE)
            self.assertEqual(extra["ladders"], []); self.assertTrue(extra["ladders_skipped"])

STRICT_BOARD = lambda **kw: [row("SPREAD", "-3.5", dk_event_id="E1", tip_utc=S.TIP),
                             row("TOTAL", "140.5", dk_event_id="E1", tip_utc=S.TIP),
                             row("ALT_SPREAD", "-6", "+150", "-190", dk_event_id="E1", tip_utc=S.TIP, **kw)]

def reasons(extra):
    return [w[2] for w in extra["ladders_skipped"]]

class ChecklistRequirements(unittest.TestCase):
    def test_event_id_teams_and_tip_all_required_and_matched(self):
        _, _, extra = go(STRICT_BOARD())                       # default config is strict
        self.assertEqual([(x["kind"], x["line"]) for x in extra["ladders"]], [("alt_spread", -6.0)])
        def one(**kw):
            b = [row("SPREAD", "-3.5", dk_event_id="E1", tip_utc=S.TIP), row("TOTAL", "140.5", dk_event_id="E1", tip_utc=S.TIP)]
            base = dict(dk_event_id="E1", tip_utc=S.TIP); base.update(kw)
            b.append(row("ALT_SPREAD", "-6", "+150", "-190", **{k: v for k, v in base.items() if v is not None}))
            return go(b)[2]
        e = one(dk_event_id=None); self.assertEqual(e["ladders"], []); self.assertTrue(reasons(e)[0].startswith("EVENT_ID_REQUIRED"))
        e = one(tip_utc=None); self.assertEqual(e["ladders"], []); self.assertTrue(reasons(e)[0].startswith("TIP_REQUIRED"))
        e = one(tip_utc="2026-11-21T20:00:00Z"); self.assertTrue(reasons(e)[0].startswith("NO_UNIQUE_GAME_MATCH"))
        e = one(dk_event_id="E9"); self.assertEqual(e["ladders"], []); self.assertTrue(reasons(e)[0].startswith("EVENT_BINDING_CONFLICT"))
        b = STRICT_BOARD(); b[2] = row("ALT_SPREAD", "-6", "+150", "-190", home="Synthetic 2", away="Synthetic 1", dk_event_id="E1", tip_utc=S.TIP)
        e = go(b)[2]; self.assertEqual(e["ladders"], []); self.assertTrue(reasons(e)[0].startswith("NO_UNIQUE_GAME_MATCH"))   # teams swapped

    def test_capture_must_be_fresh_and_pregame(self):
        def one(cap, **cfg):
            b = STRICT_BOARD(captured_utc=cap) if cap else STRICT_BOARD()
            return go(b, config=cfg or None)[2]
        self.assertEqual(len(one("2026-11-21T14:00:00Z")["ladders"]), 1)
        e = one("2026-11-21T23:30:00Z"); self.assertTrue(reasons(e)[0].startswith("CAPTURED_AFTER_TIP"))
        e = one("2026-11-21T15:30:00Z"); self.assertTrue(reasons(e)[0].startswith("CAPTURED_AFTER_FREEZE"))
        e = one("2026-11-20T10:00:00Z"); self.assertTrue(reasons(e)[0].startswith("STALE_QUOTE"))          # 29h old, max 24
        self.assertEqual(len(one("2026-11-20T10:00:00Z", max_quote_age_hours=48)["ladders"]), 1)           # configurable
        e = one("not-a-time"); self.assertTrue(reasons(e)[0].startswith("CAPTURE_TIME_INVALID"))
        with self.assertRaises(ValueError): PR.make_config(max_quote_age_hours=0)

    def test_duplicates_and_conflicts_quarantined_with_codes(self):
        b = STRICT_BOARD() + [row("ALT_SPREAD", "-6", "+140", "-180", dk_event_id="E1", tip_utc=S.TIP)]
        e = go(b)[2]; self.assertEqual(e["ladders"], [])
        self.assertEqual(len(reasons(e)), 2); self.assertTrue(all(r.startswith("DUPLICATE_RUNG") for r in reasons(e)))

    def test_every_rejection_is_kept_with_a_reason_code(self):
        import re
        b = STRICT_BOARD() + [row("ALT_SPREAD", "-7", "+150", "", dk_event_id="E1", tip_utc=S.TIP),
                              row("ALT_TOTAL", "145.5", "+120", "-150", dk_event_id="E1", tip_utc=S.TIP),   # totals unverified
                              row("TT_HOME", "72.5", "-110", "-110", dk_event_id="E1")]                      # no tip
        card, names, extra = go(b)
        codes = [r.split(":")[0] for r in reasons(extra)]
        self.assertEqual(len(codes), 3); self.assertTrue(all(re.fullmatch(r"[A-Z_]+", c) for c in codes))
        self.assertEqual(set(codes), {"NOT_POSTED_TWO_SIDED", "TOTALS_ORDER_UNVERIFIED", "TIP_REQUIRED"})
        md = R.render(card, names, extra)
        for c in codes: self.assertIn(f"ladder row skipped ({c}:", md)

    def test_push_aware_ev_all_nine_weights_on_integer_ladders(self):
        board = [row("SPREAD", "-3.5", dk_event_id="E1", tip_utc=S.TIP), row("TOTAL", "140.5", dk_event_id="E1", tip_utc=S.TIP),
                 row("ALT_SPREAD", "-6", "+150", "-190", dk_event_id="E1", tip_utc=S.TIP),
                 row("ALT_TOTAL", "145", "+130", "-150", dk_event_id="E1", tip_utc=S.TIP),
                 row("TT_HOME", "72", "-110", "-110", dk_event_id="E1", tip_utc=S.TIP)]
        for w in PR.CANDIDATE_BLEND_WEIGHTS:
            _, _, extra = go(board, totals_order_verified=True, config={"blend_weight_model": w})
            self.assertEqual(len(extra["ladders"]), 3)
            for L in extra["ladders"]:
                with self.subTest(weight=w, kind=L["kind"]):
                    self.assertGreater(L["push"], 0)
                    for i in (0, 1):
                        want = w * L["model_prob"][i] + (1 - w) * (1 - L["push"]) * L["market_novig"][i]
                        self.assertAlmostEqual(L["blend_ev"][i], NM.ev_per_unit(want, L["push"], L["price"][i]))
                        if w == 1.0: self.assertAlmostEqual(L["blend_ev"][i], L["paper_ev"][i])
                        if w == 0.0:
                            self.assertAlmostEqual(L["blend_ev"][i], NM.ev_per_unit((1 - L["push"]) * L["market_novig"][i], L["push"], L["price"][i]))

class Receipt(unittest.TestCase):
    def _args(self, d, fx, board, extra=()):
        return ["--board", str(board), "--board-captured-utc", "2026-11-21T14:30:00Z", "--season", str(S.SEASON),
                "--private-dir", str(Path(d) / "priv"), "--out", str(Path(d) / "out"),
                "--ledger", str(Path(d) / "priv" / "ledger.jsonl"), "--fixture-dir", str(fx),
                "--now", "2026-11-21T15:00:00+00:00", "--run-id", "12345", *extra]

    def test_receipt_written_on_success_and_on_block(self):
        with tempfile.TemporaryDirectory() as d:
            fx = Path(d) / "fx"; fx.mkdir(); games, boxes = T.provider(); body = S.ratings_body()
            (fx / "ratings.json").write_bytes(body); (fx / "receipt.json").write_text(json.dumps(S.receipt(body)))
            (fx / "games.json").write_text(json.dumps(games)); (fx / "boxes.json").write_text(json.dumps(boxes))
            (fx / "espn.json").write_text(json.dumps(T.espn()))
            board = Path(d) / "b.csv"
            with open(board, "w", newline="") as f:
                w = csv.DictWriter(f, ["sport", "home", "away", "market", "line", "price_a", "price_b"]); w.writeheader(); w.writerows(T.BOARD)
            self.assertEqual(R.main(self._args(d, fx, board, ["--sd-margin", "13"])), 0)
            rec = json.loads((Path(d) / "out" / "run_receipt.json").read_text())
            self.assertEqual((rec["run_id"], rec["ok"], rec["errors"], rec["ledger_rows"]), ("12345", True, [], 1))
            self.assertEqual(rec["rows_pulled"]["board_rows"], len(T.BOARD)); self.assertEqual(rec["games_projected"], 2)
            self.assertIn("ladders_rejected_by_code", rec)
            self.assertEqual(rec["date_ct"], "2026-11-21"); self.assertEqual(rec["label"], "PAPER_0U")
            # second run refuses re-freeze -> BLOCKED receipt with error
            (Path(d) / "out" / "run_receipt.json").unlink()
            args = self._args(d, fx, board); args[args.index("--private-dir") + 1] = str(Path(d) / "priv2")
            args[args.index("--ledger") + 1] = str(Path(d) / "priv" / "ledger.jsonl")
            self.assertEqual(R.main(args), 2)
            rec = json.loads((Path(d) / "out" / "run_receipt.json").read_text())
            self.assertFalse(rec["ok"]); self.assertTrue(rec["errors"])

class BoardAndSeasonStart(unittest.TestCase):
    def test_missing_board_writes_receipt_error(self):
        os.environ.pop("CBBD_API_KEY", None)
        with tempfile.TemporaryDirectory() as d:
            for board in (None, str(Path(d) / "nope.csv")):
                args = ["--board-captured-utc", "2026-11-24T15:00:00Z", "--season", "2027",
                        "--private-dir", str(Path(d) / "p"), "--out", str(Path(d) / "o"), "--run-id", "7"]
                if board: args += ["--board", board]
                self.assertEqual(R.main(args), 2)
                rec = json.loads((Path(d) / "o" / "run_receipt.json").read_text())
                self.assertFalse(rec["ok"]); self.assertEqual(rec["run_id"], "7")
                self.assertEqual(rec["errors"], ["Hold: BOARD_REQUIRED" if board is None else "Hold: BOARD_FILE_MISSING"])
            self.assertFalse((Path(d) / "p").exists())

    def test_season_start_default_and_validation(self):
        os.environ.pop("CBBD_API_KEY", None)
        with tempfile.TemporaryDirectory() as d:
            b = Path(d) / "b.csv"; b.write_text("sport\n")
            base = ["--board", str(b), "--board-captured-utc", "2026-11-24T15:00:00Z", "--season", "2027",
                    "--private-dir", str(Path(d) / "p"), "--out", str(Path(d) / "o")]
            self.assertEqual(R.main(base + ["--season-start-utc", "11/01/2026"]), 2)
            self.assertEqual(json.loads((Path(d) / "o" / "run_receipt.json").read_text())["errors"],
                             ["Hold: SEASON_START_UTC_INVALID"])
            # a valid / default start proceeds past validation (then blocks on the absent key, not on the date)
            self.assertEqual(R.main(base), 2)
            self.assertEqual(json.loads((Path(d) / "o" / "run_receipt.json").read_text())["errors"],
                             ["Hold: CBBD_API_KEY_ABSENT"])

if __name__ == "__main__":
    unittest.main()
