"""OFFLINE synthetic tests for the append-only CBBD paper ledger and evaluator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from cbbd_native_score_model import fit_context
from cbbd_paper_card import build_card
import cbbd_paper_ledger as L
from cbbd_prospective_capture import BASE, finals_from_capture
from cbbd_paper_synthetic import (BUILT, FREEZE, SEASON, TIP, full_quotes, prior_games,
                                  provider_games, quote, ratings_body, receipt, write_slate)

OBS = "2026-11-22T03:00:00.000000Z"
T_APPEND = datetime(2026, 11, 21, 15, 10, tzinfo=timezone.utc)
T_LATER = datetime(2026, 11, 22, 4, 0, tzinfo=timezone.utc)


class LedgerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.ledger = self.dir / "ledger.jsonl"
        self.body = ratings_body()

    def make_card(self, games=None, quotes=None, sub="a", **kw):
        d = self.dir / sub
        d.mkdir(exist_ok=True)
        slate, reg = write_slate(d, **({"games": games} if games else {}))
        q = quotes if quotes is not None else full_quotes("9001") + full_quotes("9002")
        return build_card(freeze_utc=kw.get("freeze", FREEZE), built_utc=kw.get("built", BUILT),
                          season=SEASON, slate_path=slate, registry_path=reg,
                          ratings_body=self.body, ratings_receipt=receipt(self.body),
                          prior_games=prior_games(), quotes=[(x, "OPERATOR") for x in q])

    def freeze(self, card, now=T_APPEND):
        return L.append(self.ledger, L.card_entries(card), clock=lambda: now)

    def finals(self, results, observed=OBS, tip=TIP, name="g"):
        raw = json.dumps(provider_games(results, tip=tip)).encode()
        rp, mp = self.dir / (name + ".raw.json"), self.dir / (name + ".manifest.json")
        rp.write_bytes(raw)
        mp.write_text(json.dumps({
            "format": "CBBD_GAMES_CAPTURE_V1", "provider": "collegebasketballdata",
            "documented_endpoint": BASE, "season": SEASON, "local_observed_utc": observed,
            "source_sha256": hashlib.sha256(raw).hexdigest(), "source_bytes": len(raw),
            "returned_rows": len(results), "credential_persisted": False}))
        out = self.dir / (name + ".finals.json")
        finals_from_capture(rp, mp, output_path=out)
        return json.loads(out.read_text()), rp, mp

    def attach(self, results, **kw):
        f, rp, mp = self.finals(results, **kw)
        return L.append(self.ledger, L.final_entries(f, rp, mp), clock=lambda: T_LATER)


class AppendOnlyTest(LedgerBase):
    def test_card_frozen_whole_with_passes(self):
        card = self.make_card()
        self.assertEqual(self.freeze(card)["appended"], 1)
        e = L.read(self.ledger)
        self.assertEqual(e[0]["payload"], card)
        self.assertEqual({r["status"] for r in e[0]["payload"]["rows"]}, {"PROJECTED", "PASS"})
        self.assertEqual(os.stat(self.ledger).st_mode & 0o777, 0o600)

    def test_tampering_any_line_breaks_chain(self):
        self.freeze(self.make_card())
        self.attach([("9001", 1, 2, 70, 80)])
        lines = self.ledger.read_bytes().splitlines(keepends=True)
        doc = json.loads(lines[0])
        doc["payload"]["rows"][0]["projection"]["margin"] = 99.0
        self.ledger.write_bytes(json.dumps(doc, sort_keys=True).encode() + b"\n" + lines[1])
        with self.assertRaisesRegex(L.LedgerError, "CHAIN_BROKEN"):
            L.read(self.ledger)
        with self.assertRaisesRegex(L.LedgerError, "CHAIN_BROKEN"):
            self.attach([("9002", 3, 4, 70, 80)], name="h")

    def test_reorder_or_delete_breaks_chain(self):
        self.freeze(self.make_card())
        self.attach([("9001", 1, 2, 70, 80)])
        lines = self.ledger.read_bytes().splitlines(keepends=True)
        self.ledger.write_bytes(lines[1])
        with self.assertRaises(L.LedgerError):
            L.read(self.ledger)

    def test_duplicate_card_overlap_and_tampered_card_refused(self):
        card = self.make_card()
        self.freeze(card)
        with self.assertRaisesRegex(L.LedgerError, "ALREADY_FROZEN"):
            self.freeze(card)
        refreeze = self.make_card(sub="b", built="2026-11-21T15:06:00Z")
        with self.assertRaisesRegex(L.LedgerError, "GAME_ALREADY_FROZEN"):
            self.freeze(refreeze)
        other = self.make_card(games=[("9100", "7", "8", "0")], sub="c")
        other["freeze_utc"] = "2026-11-21T14:00:00Z"
        with self.assertRaisesRegex(L.LedgerError, "SELF_HASH"):
            self.freeze(other)

    def test_non_paper_card_refused(self):
        card = self.make_card()
        card["approved_stake_u"] = 1
        with self.assertRaisesRegex(L.LedgerError, "NON_PAPER"):
            self.freeze(card)

    def test_first_line_bytes_unchanged_after_grading(self):
        self.freeze(self.make_card())
        first = self.ledger.read_bytes()
        self.attach([("9001", 1, 2, 70, 80), ("9002", 3, 4, 81, 79)])
        self.assertTrue(self.ledger.read_bytes().startswith(first))


class GradingTest(LedgerBase):
    def test_exact_id_grading_keeps_loss_push_pass_and_no_quote(self):
        q = [quote("9001", "spread", -3.0, -110, -110), quote("9001", "moneyline", None, -150, 130)]
        self.freeze(self.make_card(quotes=q))
        res = self.attach([("9001", 1, 2, 80, 77), ("9003", 5, 999, 60, 70), ("9004", 6, 300, 61, 60)])
        self.assertEqual(res["census"]["attached"], 3)
        self.assertEqual(res["census"]["pending_no_final"], 1)  # 9002
        g = {e["payload"]["game_id"]: e["payload"] for e in L.read(self.ledger)
             if e["kind"] == "FINAL_ATTACHED"}
        spread = next(x for x in g["9001"]["grades"] if x["market"] == "spread")
        self.assertEqual(spread["outcome"], "push")
        self.assertIn(spread["paper_result"], ("P", "NO_POSITIVE_PAPER_EV_SELECTION"))
        self.assertEqual(next(x for x in g["9001"]["grades"] if x["market"] == "total")["paper_result"],
                         "NO_QUOTE")
        self.assertTrue(all(x["paper_result"] == "PASS" for x in g["9003"]["grades"]))
        self.assertEqual(g["9003"]["card_pass_reason"], "UNMAPPED_CBBD_TEAM_ID")

    def test_regrading_is_idempotent_never_rewrites(self):
        self.freeze(self.make_card())
        self.attach([("9001", 1, 2, 70, 80)])
        res = self.attach([("9001", 1, 2, 90, 50)], name="again")
        self.assertEqual(res["appended"], 0)
        self.assertEqual(res["census"]["already_graded"], 1)
        g = [e for e in L.read(self.ledger) if e["kind"] == "FINAL_ATTACHED"]
        self.assertEqual(g[0]["payload"]["final"]["home_score"], 70)

    def test_wrong_team_ids_or_season_blocked(self):
        self.freeze(self.make_card())
        res = self.attach([("9001", 2, 1, 70, 80)])
        self.assertTrue(any("FINAL_IDENTITY_MISMATCH" in k for k in res["census"]))

    def test_future_or_not_final_game_not_attached(self):
        self.freeze(self.make_card())
        res = self.attach([("9001", 1, 2, 70, 80)], observed="2026-11-21T22:00:00.000000Z")
        self.assertEqual(res["appended"], 0)
        self.assertTrue(any(k.startswith("blocked:FINALS_SOURCE_NOT_FINAL") for k in res["census"]))

    def test_duplicate_provider_final_blocks_all_copies(self):
        self.freeze(self.make_card())
        res = self.attach([("9001", 1, 2, 70, 80), ("9001", 1, 2, 71, 80)])
        self.assertEqual(res["appended"], 0)

    def test_provider_bytes_must_match_derived_finals(self):
        self.freeze(self.make_card())
        f, rp, mp = self.finals([("9001", 1, 2, 70, 80)])
        f["rows"][0]["final"]["home_score"] = 99
        with self.assertRaises(ValueError):
            L.append(self.ledger, L.final_entries(f, rp, mp), clock=lambda: T_LATER)


class NineWeightTest(LedgerBase):
    def test_fixed_grid_uses_conditional_probabilities_and_same_denominator(self):
        rows = L.nine_weight_comparison([(0.6, 0.2, 0.4, 1)])
        self.assertEqual([x["weight_model_pct"] for x in rows], list(L.BLEND_GRID))
        self.assertTrue(all(x["n"] == 1 for x in rows))
        self.assertAlmostEqual(rows[0]["brier"], 0.36)
        self.assertAlmostEqual(rows[-1]["brier"], 0.0625)
        self.assertAlmostEqual(rows[2]["brier"], (0.575 - 1)**2)
        self.assertTrue(all(x["brier"] is None and x["n"] == 0 for x in L.nine_weight_comparison([])))

    def test_real_ledger_integration_endpoints_match_existing_metrics(self):
        self.freeze(self.make_card())
        self.attach([("9001", 1, 2, 70, 80), ("9002", 3, 4, 80, 77)])
        report = L.evaluate(L.read(self.ledger))
        for family, grid in report["nine_weight_same_book_comparison"]["families"].items():
            base = report["forecast_accuracy"][family + "_brier"]
            self.assertEqual(grid[0]["n"], base["n"])
            if base["n"]:
                self.assertAlmostEqual(grid[0]["brier"], base["market"])
                self.assertAlmostEqual(grid[-1]["brier"], base["model"])
        self.assertEqual(report["approved_stake_u"], 0)

    def test_invalid_probabilities_fail_closed(self):
        for pair in [(float("nan"), 0, .5, 1), (.9, .2, .5, 0), (.5, 1, .5, 1)]:
            with self.assertRaises(L.LedgerError):
                L.nine_weight_comparison([pair])


class CloseAndEvaluateTest(LedgerBase):
    def test_close_window_and_clv(self):
        self.freeze(self.make_card())
        closes = [quote("9001", "moneyline", None, -170, 150, "2026-11-21T22:59:00Z"),
                  quote("9001", "spread", -3.5, -115, -105, "2026-11-21T23:00:00Z"),  # at tip
                  quote("9001", "total", 140.5, -110, -110, "2026-11-21T14:59:00Z"),  # pre-freeze
                  quote("7777", "total", 140.5, -110, -110, "2026-11-21T22:00:00Z")]
        res = L.append(self.ledger, L.close_entries(closes), clock=lambda: T_LATER)
        self.assertEqual(res["census"]["recorded"], 1)
        self.assertEqual(res["census"]["rejected:CLOSE_NOT_BETWEEN_FREEZE_AND_TIP"], 2)
        self.assertEqual(res["census"]["rejected:GAME_NOT_ON_LEDGER_CARD"], 1)
        again = L.append(self.ledger, L.close_entries(closes[:1]), clock=lambda: T_LATER)
        self.assertEqual(again["census"]["rejected:CLOSE_ALREADY_RECORDED"], 1)
        self.attach([("9001", 1, 2, 70, 80), ("9002", 3, 4, 70, 80)])
        rep = L.evaluate(L.read(self.ledger))
        self.assertEqual(rep["approved_stake_u"], 0)
        self.assertIn("forecast_accuracy", rep)
        self.assertIn("paper_returns_separate_from_accuracy", rep)
        self.assertEqual(rep["census"]["graded_rows"], 2)
        self.assertEqual(rep["census"]["pending_final"], 2)
        self.assertEqual(rep["card_pass_reasons"], {"MISSING_PACE_HISTORY": 1, "UNMAPPED_CBBD_TEAM_ID": 1})
        self.assertEqual(rep["forecast_accuracy"]["moneyline_brier"]["n"], 2)
        self.assertIsNone(rep["forecast_accuracy"]["moneyline_brier"]["ci95"])  # n<30
        self.assertIsNotNone(rep["walkforward_reuse_point_in_time_score_walkforward"])
        self.assertEqual(len(rep["prospective_residuals"]), 2)

    def test_many_cards_chronological_ci_and_residual_feedback(self):
        """40 one-game cards on successive days; finals attach; CIs appear at n>=30."""
        t0 = datetime(2026, 11, 22, 15, tzinfo=timezone.utc)
        for d in range(40):
            freeze = t0 + timedelta(days=d)
            tip = freeze + timedelta(hours=8)
            z = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ")
            gid = str(20000 + d)
            sub = self.dir / f"d{d}"
            sub.mkdir()
            slate, reg = write_slate(sub, games=[(gid, str(1 + d % 20), str(21 + d % 20), "0")], tip=z(tip))
            # registry clocks must precede this card's freeze
            reg.write_text(reg.read_text().replace("2026-11-21T13:00:00Z", z(freeze - timedelta(hours=2)))
                           .replace("2026-11-21T14:00:00Z", z(freeze - timedelta(hours=1))))
            body = self.body
            rec = receipt(body, observed=z(freeze - timedelta(hours=1)))
            q = full_quotes(gid, captured=z(freeze - timedelta(minutes=30)))
            card = build_card(freeze_utc=z(freeze), built_utc=z(freeze + timedelta(minutes=1)),
                              season=SEASON, slate_path=slate, registry_path=reg, ratings_body=body,
                              ratings_receipt=rec, prior_games=prior_games(),
                              quotes=[(x, "OPERATOR") for x in q])
            self.assertEqual(card["projected_rows"], 1)
            self.freeze(card, now=freeze + timedelta(minutes=2))
            self.attach([(gid, 1 + d % 20, 21 + d % 20, 70 + d % 9, 70 + d % 9 + (5 if d % 2 else -6))],
                        observed=z(tip + timedelta(hours=3)) .replace("Z", ".000000Z"),
                        tip=z(tip), name=f"f{d}")
        rep = L.evaluate(L.read(self.ledger))
        fa = rep["forecast_accuracy"]
        self.assertEqual(fa["model_margin_mae"]["n"], 40)
        self.assertIsNotNone(fa["model_margin_mae"]["ci95"])
        self.assertIsNotNone(fa["moneyline_brier"]["ci95"])
        self.assertTrue(fa["calibration_side_a"]["moneyline"])
        wf = rep["walkforward_reuse_point_in_time_score_walkforward"]["spread"]
        self.assertEqual(wf["input_rows"], 40)
        self.assertGreater(wf["walkforward_evaluated_n"], 0)  # only after 30 prior releases
        self.assertLess(wf["walkforward_evaluated_n"], 40)
        # Residual export feeds later SDs only when captured before the new freeze.
        res = rep["prospective_residuals"]
        early = fit_context(self.body, prior_games(), season=SEASON, freeze_utc="2026-12-01T00:00:00Z",
                            prior_residuals=res)
        late = fit_context(self.body, prior_games(), season=SEASON, freeze_utc="2027-01-15T00:00:00Z",
                           prior_residuals=res)
        self.assertLess(early["sd"]["prospective_available"], 30)
        self.assertEqual(late["sd"]["basis"], "PROSPECTIVE_PRIOR_CARD_RESIDUALS")


if __name__ == "__main__":
    unittest.main()
