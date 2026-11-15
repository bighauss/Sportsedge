"""Deterministic, offline regression tests for research-only v2.1 repair."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import se_repair_layer as legacy
from v21_fail_closed_repair import audit_one, canonical_key, odds_payout, repair_rows, run


def sample(**changes):
    row = dict(
        sport="NFL", game="Away @ Home", event_id="match-20261115-1", mode="PROJECTION",
        bet_type="ML|0|", pick="Home ML", price="+120", model_p="0.6", market_p="0.55",
        book="DK", quote_sha256="a" * 64, source_authenticated="true",
        no_vig_source_verified="true", model_version_verified="true",
        model_asof_utc="2026-11-15T15:00:00Z", captured_utc="2026-11-15T15:10:00Z",
        game_start_utc="2026-11-15T18:00:00Z", settlement_kind="BINARY_NO_PUSH",
    )
    row.update(changes)
    return row


def checked(**changes):
    return audit_one(sample(**changes), line=2, duplicate=False)


def has(row, flag):
    return flag in row["v21_reasons"].split(";")


class ProfessionalRepairTests(unittest.TestCase):
    def test_legacy_no_market_is_actually_fail_open(self):
        original = {"sport": "NFL", "game": "A @ B", "mode": "PROJECTION", "bet_type": "ML|0|",
                    "model_p": "0.95", "market_p": "", "price": "+120"}
        self.assertEqual(legacy.repair([original])[0]["r2_keep"], 1)
        result = audit_one(original, line=2, duplicate=False)
        self.assertTrue(has(result, "MARKET_PROBABILITY_MISSING_OR_INVALID"))
        self.assertEqual(result["v21_push_aware_ev"], "")
        self.assertEqual(result["v21_approved_stake_u"], "0")

    def test_legacy_anchor_period_is_actually_fail_open(self):
        original = {"sport": "NFL", "game": "A @ B", "mode": "ANCHOR", "bet_type": "1H_ML|0|",
                    "model_p": "0.68", "market_p": "0.55", "price": "+160"}
        self.assertEqual(legacy.repair([original])[0]["r2_keep"], 1)
        result = audit_one(original, line=2, duplicate=False)
        self.assertTrue(has(result, "NO_INDEPENDENT_PROJECTION"))
        self.assertTrue(has(result, "PERIOD_DERIVED_ANCHOR"))

    def test_legacy_nonfinite_is_actually_bad(self):
        original = {"sport": "NFL", "game": "A @ B", "mode": "PROJECTION", "bet_type": "ML|0|",
                    "model_p": "nan", "market_p": "0.4", "price": "+100"}
        self.assertEqual(str(legacy.repair([original])[0]["pooled_p"]), "nan")
        self.assertTrue(has(audit_one(original, line=2, duplicate=False), "MODEL_PROBABILITY_INVALID"))

    def test_probability_linear_formula_and_profit(self):
        r = checked()
        self.assertEqual(r["v21_linear_win_p"], "0.56500000")
        self.assertEqual(r["v21_binary_ev_illustrative"], "0.24300000")
        self.assertEqual(r["v21_push_aware_ev"], "0.24300000")
        self.assertEqual(r["v21_status"], "PAPER_HOLD_0U")
        self.assertTrue(has(r, "NO_INDEPENDENT_MARKET_PROMOTION"))
        self.assertEqual(r["v21_approved_stake_u"], "0")

    def test_push_aware_ev(self):
        r = checked(bet_type="SPREAD|-3|", settlement_kind="WIN_LOSS_PUSH",
                    model_push_p="0.03", market_push_p="0.01")
        self.assertEqual(r["v21_linear_push_p"], "0.01600000")
        self.assertEqual(r["v21_push_aware_ev"], "0.25900000")

    def test_spread_no_push_data_refused(self):
        r = checked(bet_type="SPREAD|-3|", settlement_kind="WIN_LOSS_PUSH")
        self.assertTrue(has(r, "PUSH_PROBABILITY_MISSING_OR_INVALID"))
        self.assertEqual(r["v21_push_aware_ev"], "")
        self.assertTrue(r["v21_binary_ev_illustrative"])

    def test_no_settlement_refused(self):
        r = checked(settlement_kind="")
        self.assertTrue(has(r, "SETTLEMENT_UNVERIFIED"))
        self.assertEqual(r["v21_push_aware_ev"], "")

    def test_no_market_refused(self):
        r = checked(market_p="")
        self.assertTrue(has(r, "MARKET_PROBABILITY_MISSING_OR_INVALID"))
        self.assertEqual(r["v21_linear_win_p"], "")
        self.assertEqual(r["v21_binary_ev_illustrative"], "")

    def test_invalid_probability_variants(self):
        for bad in ("nan", "NaN", "Infinity", "-inf", "0", "1", "-0.1", "1.1", "text", ""):
            with self.subTest(bad=bad):
                r = checked(model_p=bad)
                self.assertTrue(has(r, "MODEL_PROBABILITY_INVALID"))
                self.assertEqual(r["v21_linear_win_p"], "")

    def test_invalid_market_variants(self):
        for bad in ("nan", "-Infinity", "0", "1", "2", ""):
            with self.subTest(bad=bad):
                self.assertTrue(has(checked(market_p=bad), "MARKET_PROBABILITY_MISSING_OR_INVALID"))

    def test_invalid_odds_variants(self):
        for bad in ("0", "+99", "-99", "nan", "Inf", "-0", "hello", "-105.3", ""):
            with self.subTest(bad=bad):
                self.assertTrue(has(checked(price=bad), "AMERICAN_ODDS_INVALID"))
                self.assertEqual(checked(price=bad)["v21_push_aware_ev"], "")

    def test_valid_odds_formats(self):
        self.assertEqual(odds_payout("+200"), 2)
        self.assertEqual(str(odds_payout("−125")), "0.8")
        self.assertEqual(odds_payout("-100"), 1)

    def test_mode_anchor_always_refused(self):
        self.assertTrue(has(checked(mode="ANCHOR", bet_type="1H_TOTAL|19.5|"), "NO_INDEPENDENT_PROJECTION"))
        self.assertTrue(has(checked(mode="ANCHOR", bet_type="1H_TOTAL|19.5|"), "PERIOD_DERIVED_ANCHOR"))

    def test_missing_event_id_refused(self):
        self.assertTrue(has(checked(event_id=""), "EVENT_ID_UNVERIFIED"))

    def test_missing_player_id_refused(self):
        self.assertTrue(has(checked(player="Test Player"), "PLAYER_ID_UNVERIFIED"))

    def test_wrong_book_refused(self):
        self.assertTrue(has(checked(book="BESTBOOK"), "DK_BOOK_NOT_VERIFIED"))

    def test_timestamp_naive_refused(self):
        self.assertTrue(has(checked(captured_utc="2026-11-15T15:10:00"), "PREGAME_TIMESTAMPS_UNVERIFIED"))

    def test_timestamp_after_start_refused(self):
        self.assertTrue(has(checked(captured_utc="2026-11-15T18:00:00Z"), "ASOF_OR_PREGAME_TIME_VIOLATION"))

    def test_model_asof_after_capture_refused(self):
        self.assertTrue(has(checked(model_asof_utc="2026-11-15T17:30:00Z"), "ASOF_OR_PREGAME_TIME_VIOLATION"))

    def test_missing_source_verification_refused(self):
        self.assertTrue(has(checked(source_authenticated="false"), "QUOTE_NOT_AUTHENTICATED"))
        self.assertTrue(has(checked(no_vig_source_verified="false"), "NO_VIG_SOURCE_UNVERIFIED"))
        self.assertTrue(has(checked(model_version_verified="false"), "MODEL_VERSION_UNVERIFIED"))

    def test_wrong_sha_refused(self):
        self.assertTrue(has(checked(quote_sha256="a"*63), "QUOTE_HASH_MISSING_OR_INVALID"))

    def test_model_market_15pp(self):
        self.assertTrue(has(checked(model_p="0.9", market_p="0.55"), "MODEL_MARKET_GAP_GT15PP"))

    def test_duplicate_preserves_all_rows(self):
        rows, report = repair_rows([sample(), sample()])
        self.assertEqual(len(rows), 2)
        self.assertEqual(report["source_rows"], 2)
        self.assertEqual(report["output_rows"], 2)
        self.assertTrue(has(rows[1], "DUPLICATE_SELECTION"))
        self.assertEqual(report["actionable_rows"], 0)

    def test_canonical_key_distinguishes_side_line_and_event(self):
        a = sample()
        self.assertNotEqual(canonical_key(a), canonical_key(sample(pick="Away ML")))
        self.assertNotEqual(canonical_key(a), canonical_key(sample(bet_type="SPREAD|-3|")))
        self.assertNotEqual(canonical_key(a), canonical_key(sample(event_id="different-game")))

    def test_create_only_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/"in.csv"
            out = Path(td)/"annotated.csv"
            rpt = Path(td)/"report.json"
            with source.open("w", newline="") as f:
                writer=csv.DictWriter(f, fieldnames=list(sample()))
                writer.writeheader()
                writer.writerow(sample())
                writer.writerow(sample(price="+140"))
            original=source.read_bytes()
            report=run(str(source),str(out),str(rpt))
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(report["source_sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(report["output_rows"], 2)
            with out.open() as f:
                self.assertEqual(len(list(csv.DictReader(f))), 2)
            self.assertEqual(json.loads(rpt.read_text())["actionable_rows"], 0)
            with self.assertRaises(FileExistsError):run(str(source),str(out),str(rpt))

    def test_output_create_only_is_transactional(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"input.csv"
            with source.open("w",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=list(sample()))
                writer.writeheader();writer.writerow(sample())
            output=Path(td)/"new.csv"
            existing_report=Path(td)/"report.json"
            existing_report.write_text("existing")
            with self.assertRaises(FileExistsError):
                run(str(source),str(output),str(existing_report))
            self.assertFalse(output.exists())
            self.assertEqual(existing_report.read_text(),"existing")

    def test_duplicate_quotes_even_when_price_differs(self):
        rows,_=repair_rows([sample(),sample(price="+140")])
        self.assertTrue(has(rows[1],"DUPLICATE_SELECTION"))

    def test_no_claim_of_source_auth_with_hash_alone(self):
        r=checked(source_authenticated="false",quote_sha256="b"*64)
        self.assertTrue(has(r,"QUOTE_NOT_AUTHENTICATED"))
        self.assertEqual(r["v21_approved_stake_u"],"0")

    def test_no_overwrite_source(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/"in.csv";source.write_text("model_p,market_p,price\n.6,.5,+120\n")
            with self.assertRaises(ValueError):run(str(source),str(source),str(Path(td)/"r.json"))

    def test_no_header_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/"in.csv";f.write_text("")
            with self.assertRaises(ValueError):run(str(f),str(Path(td)/"o.csv"),str(Path(td)/"r.json"))

    def test_no_field_collision(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/"in.csv";f.write_text("model_p,v21_status\n0.4,OTHER\n")
            with self.assertRaises(ValueError):run(str(f),str(Path(td)/"o.csv"),str(Path(td)/"r.json"))

    def test_rows_immutable(self):
        original=sample()
        before=original.copy()
        repair_rows([original])
        self.assertEqual(original,before)

    def test_every_output_is_paper_and_zero_units(self):
        rows,report=repair_rows([sample(model_p="0.2"), sample(price="bad"),sample()])
        self.assertEqual(report["actionable_rows"],0)
        for r in rows:
            self.assertEqual(r["v21_approved_stake_u"],"0")
            self.assertEqual(r["v21_status"],"PAPER_HOLD_0U")

if __name__ == "__main__":
    unittest.main(verbosity=2)
