"""Synthetic forensic red-team checks; no historic picks or prices shipped."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import json
import unittest

from top20_original_evidence_gate import (
    CLAIM_SCHEMA, FINAL_SCHEMA, EvidenceError, _parse, audit, audit_files,
)

H = "a" * 64
B = "b" * 64
C = "c" * 64


def claim(**kw):
    row = {
        "sport": "CBB", "event_id": "EXAMPLE_EVENT_A",
        "home_team_id": "HOME", "away_team_id": "AWAY",
        "event_start_utc": "2026-11-17T02:00:00Z",
        "period": "FG", "market": "TEAM_TOTAL", "side": "UNDER",
        "line": "85.5", "team_id": "HOME", "player_id": "",
        "p_model": 0.6, "price_american": 100,
        "saved_claimed_ev": 0.2, "historical_grade": "L",
        "book": "EXAMPLE_BOOK", "provider_market_id": "M-42",
        "provider_event_id": "PROVIDER_GAME_ID", "model_sha256": H,
        "model_input_sha256": B, "original_quote_sha256": C,
        "upstream_book_id": "EXAMPLE_BOOK", "source_transport_id": "SOURCE_TRANSPORT",
        "model_frozen_utc": "2026-11-17T00:00:00Z",
        "quote_captured_utc": "2026-11-17T01:51:00Z",
        "quote_published_utc": "2026-11-17T01:50:00Z",
        "selected_utc": "2026-11-17T01:55:00Z",
        "model_features_published_utc": "2026-11-16T23:00:00Z",
        "model_features_available_utc": "2026-11-16T23:01:00Z",
        "fitted_until_utc": "2026-11-16T22:00:00Z",
    }
    row.update(kw)
    return row


def final(**kw):
    row = {
        "sport": "CBB", "event_id": "EXAMPLE_EVENT_A",
        "home_team_id": "HOME", "away_team_id": "AWAY",
        "event_start_utc": "2026-11-17T02:00:00Z",
        "home_score": 80, "away_score": 60,
        "home_1h": 40, "away_1h": 30,
        "settled_utc": "2026-11-17T04:30:00Z", "source_sha256": H,
    }
    row.update(kw)
    return row


def raw_claim(rows):
    return json.dumps({"schema": CLAIM_SCHEMA, "rows": rows},
                      sort_keys=True, allow_nan=False).encode()


def raw_finals(rows):
    return json.dumps({"schema": FINAL_SCHEMA, "rows": rows},
                      sort_keys=True, allow_nan=False).encode()


def run(*rows, finals=None, top_n=20):
    return audit(raw_claim(list(rows)), raw_finals([final()] if finals is None else finals),
                 top_n=top_n)


class ForensicGateTests(unittest.TestCase):
    def test_g18_team_total_never_uses_game_total(self):
        a = run(claim())
        row = a["top_claims"][0]
        self.assertEqual(row["corrected_grade"], "W")
        self.assertEqual(row["historical_grade"], "L")
        self.assertIn("HISTORICAL_GRADING_DISAGREEMENT_G18_OR_OTHER", row["flags"])
        self.assertEqual(a["historical_grades_modified"], False)

    def test_team_total_over_not_falsely_awarded_from_game_total(self):
        row = run(claim(side="OVER", line="81.5", historical_grade="W"))["top_claims"][0]
        self.assertEqual(row["corrected_grade"], "L")

    def test_correct_team_is_used_for_team_total(self):
        row = run(claim(team_id="AWAY", side="UNDER", line="65.5", historical_grade="W"))["top_claims"][0]
        self.assertEqual(row["corrected_grade"], "W")

    def test_unmapped_team_total_cannot_be_graded(self):
        row = run(claim(team_id="OTHER"))["top_claims"][0]
        self.assertIsNone(row["corrected_grade"])
        self.assertIn("TEAM_TOTAL_TEAM_ID_NOT_BOUND_TO_EVENT", row["flags"])

    def test_price_implied_and_ev_display_originals(self):
        a = run(claim(historical_grade="W"))["top_claims"][0]
        self.assertAlmostEqual(a["raw_implied_probability"], .5)
        self.assertAlmostEqual(a["raw_binary_ev"], .2)
        self.assertAlmostEqual(a["reported_ev"], .2)
        self.assertNotIn("CLAIMED_EV_BINARY_ARITHMETIC_MISMATCH", a["flags"])

    def test_binary_arithmetic_mismatch_flag_without_rewrite(self):
        row = run(claim(saved_claimed_ev=1.4))["top_claims"][0]
        self.assertIn("CLAIMED_EV_BINARY_ARITHMETIC_MISMATCH", row["flags"])
        self.assertAlmostEqual(row["reported_ev"], 1.4)
        self.assertAlmostEqual(row["raw_binary_ev"], .2)

    def test_raw_claimed_ev_sorts_including_tampered_or_missing_receipts(self):
        r = run(claim(event_id="ONE", saved_claimed_ev=.1, original_quote_sha256=""),
                claim(event_id="TWO", saved_claimed_ev=9, original_quote_sha256=""),
                claim(event_id="THREE", saved_claimed_ev=2, original_quote_sha256=H),
                top_n=2)
        self.assertEqual([x["event_id"] for x in r["top_claims"]], ["TWO", "THREE"])
        self.assertIn("ORIGINAL_BOOK_QUOTE_BYTES_HASH_MISSING", r["top_claims"][0]["flags"])
        self.assertEqual(r["claimed_rows_total"], 3)
        self.assertEqual(len(r["all_original_claims_retained"]), 3)
        self.assertEqual(r["top_distinct_events"], 2)

    def test_alt_ladders_are_not_independent_games(self):
        a = run(claim(line="80.5", saved_claimed_ev=.4),
                claim(line="81.5", saved_claimed_ev=.3),
                claim(line="82.5", saved_claimed_ev=.2))
        self.assertEqual(a["top_claims_count"], 3)
        self.assertEqual(a["top_distinct_events"], 1)
        self.assertTrue(all(x["correlated_claims_in_same_event_top_n"] == 3 for x in a["top_claims"]))

    def test_same_line_other_team_not_duplicate(self):
        r = run(claim(team_id="HOME", historical_grade="W"),
                claim(team_id="AWAY", historical_grade="W"))
        self.assertFalse(any("DUPLICATE_CLAIM_IDENTITY_ALL_COPIES_HELD" in x["flags"]
                             for x in r["top_claims"]))

    def test_duplicate_canonical_identity_blocks_all_regardless_of_book(self):
        r = run(claim(book="A"), claim(book="B", price_american=110))
        self.assertTrue(all("DUPLICATE_CLAIM_IDENTITY_ALL_COPIES_HELD" in x["flags"]
                             for x in r["top_claims"]))

    def test_missing_record_preserved_not_deleted(self):
        r = run(claim(saved_claimed_ev=None), claim(event_id="OTHER", saved_claimed_ev=.4))
        self.assertEqual(r["rankable_pregame_ev_claims"], 1)
        self.assertEqual(r["missing_saved_ev_rows"], 1)
        self.assertEqual(len(r["all_original_claims_retained"]), 2)

    def test_stale_quote_at_decision_not_old_relative_to_kickoff(self):
        clean = run(claim(quote_captured_utc="2026-11-17T01:51:00Z"))["top_claims"][0]
        self.assertNotIn("QUOTE_STALE_AT_DECISION", clean["flags"])
        stale = run(claim(quote_captured_utc="2026-11-17T01:49:00Z"))["top_claims"][0]
        self.assertIn("QUOTE_STALE_AT_DECISION", stale["flags"])

    def test_late_quote_source_cannot_become_pregame(self):
        r = run(claim(quote_published_utc="2026-11-17T01:52:00Z",
                      quote_captured_utc="2026-11-17T01:51:00Z"))["top_claims"][0]
        self.assertIn("BOOK_QUOTE_PUBLICATION_AFTER_CAPTURE", r["flags"])

    def test_late_model_or_feature_releases_cannot_be_backfilled(self):
        r = run(claim(model_frozen_utc="2026-11-17T01:56:00Z",
                      model_features_available_utc="2026-11-17T01:58:00Z",
                      model_features_published_utc="2026-11-17T01:57:00Z"))["top_claims"][0]
        for bad in ("MODEL_FROZEN_AFTER_PICK", "FEATURE_PUBLISHED_AFTER_FORECAST_FREEZE",
                    "FEATURE_AVAILABLE_AFTER_FORECAST_FREEZE"):
            self.assertIn(bad, r["flags"])

    def test_fit_must_be_pre_forecast(self):
        r = run(claim(fitted_until_utc="2026-11-17T00:00:00Z"))["top_claims"][0]
        self.assertIn("MODEL_FIT_NOT_BEFORE_FREEZE", r["flags"])

    def test_pairing_captured_model_market_margin_uses_home_sign(self):
        too_far = run(claim(model_home_margin=3.0, book_home_main_spread=-11.0))["top_claims"][0]
        self.assertIn("SAVED_MODEL_MARKET_6PT_DISAGREEMENT:MARGIN", too_far["flags"])
        close = run(claim(model_home_margin=10.0, book_home_main_spread=-11.0))["top_claims"][0]
        self.assertNotIn("SAVED_MODEL_MARKET_6PT_DISAGREEMENT:MARGIN", close["flags"])

    def test_tt_and_total_disagreements(self):
        r = run(claim(model_game_total=140.5, book_game_main_total=149.0,
                      model_team_total=72.0, book_team_main_total=80.5))["top_claims"][0]
        self.assertIn("SAVED_MODEL_MARKET_6PT_DISAGREEMENT:GAME_TOTAL", r["flags"])
        self.assertIn("SAVED_MODEL_MARKET_6PT_DISAGREEMENT:TEAM_TOTAL", r["flags"])

    def test_first_half_moneyline_push_is_not_binary_ev_mismatch(self):
        r = run(claim(market="ML", period="1H", side="HOME", line="",
                      p_model=.6, price_american=200, saved_claimed_ev=.5))["top_claims"][0]
        self.assertIn("PUSH_AWARE_ORIGINAL_WIN_LOSS_MASSES_MISSING", r["flags"])
        self.assertNotIn("CLAIMED_EV_BINARY_ARITHMETIC_MISMATCH", r["flags"])

    def test_first_half_win_loss_masses_match_unconditional_ev(self):
        r = run(claim(market="ML", period="1H", side="HOME", line="",
                      p_model=.6, price_american=200, saved_claimed_ev=.5,
                      p_win_unconditional=.55, p_loss_unconditional=.6))["top_claims"][0]
        self.assertIn("PUSH_AWARE_ORIGINAL_WIN_LOSS_MASSES_MISSING", r["flags"])
        good = run(claim(market="ML", period="1H", side="HOME", line="",
                         p_model=.6, price_american=200, saved_claimed_ev=.5,
                         p_win_unconditional=.5, p_loss_unconditional=.5))["top_claims"][0]
        self.assertNotIn("PUSH_AWARE_CLAIMED_EV_MISMATCH", good["flags"])

    def test_integer_score_line_push_not_assumed_zero(self):
        r = run(claim(market="TOTAL", side="OVER", team_id="",
                      line="145", p_model=.6, saved_claimed_ev=.2))["top_claims"][0]
        self.assertIn("PUSH_AWARE_ORIGINAL_WIN_LOSS_MASSES_MISSING", r["flags"])

    def test_wrong_final_team_mapping_is_unresolved(self):
        r = run(claim(), finals=[final(home_team_id="OTHER")])["top_claims"][0]
        self.assertIsNone(r["corrected_grade"])
        self.assertIn("UNVERIFIED_TEAM_FINAL_BINDING", r["flags"])

    def test_duplicate_final_never_chooses_favorable_copy(self):
        r = run(claim(), finals=[final(home_score=80),final(home_score=90)])["top_claims"][0]
        self.assertIsNone(r["corrected_grade"])
        self.assertIn("DUPLICATE_FINALS_NOT_CANONICAL", r["flags"])

    def test_game_total_correct_score_and_moneyline(self):
        total = run(claim(market="TOTAL", team_id="", side="UNDER", line="145.5",
                          historical_grade="W"))["top_claims"][0]
        self.assertEqual(total["corrected_grade"], "W")
        ml = run(claim(market="ML", team_id="", side="AWAY", line="",
                       historical_grade="L"))["top_claims"][0]
        self.assertEqual(ml["corrected_grade"], "L")

    def test_spread_signed_relative_to_selected_side(self):
        home = run(claim(market="SPREAD", side="HOME", team_id="",
                         line="-22.5"))["top_claims"][0]
        away = run(claim(market="SPREAD", side="AWAY", team_id="",
                         line="+22.5"))["top_claims"][0]
        self.assertEqual(home["corrected_grade"], "L")
        self.assertEqual(away["corrected_grade"], "W")

    def test_provider_attestation_never_inferred_from_sha(self):
        r = run(claim())["top_claims"][0]
        self.assertIn("ORIGINAL_PROVIDER_BOOK_ATTESTATION_UNVERIFIED",r["flags"])
        self.assertEqual(r["approved_stake_u"],0)
        self.assertFalse(run(claim())["source_bookmaker_authentication_verified"])

    def test_missing_prop_mapping_not_upgraded(self):
        r = run(claim(market="PLAYER_PROP:PASS_YARDS",player_id=""))["top_claims"][0]
        self.assertIn("UNSUPPORTED_PROP_OR_PLAYER_MAPPING",r["flags"])
        self.assertIsNone(r["corrected_grade"])

    def test_bad_timestamps_visible_on_all_rows(self):
        r = run(claim(model_frozen_utc="2026-11-17T00:00:00",
                      quote_captured_utc="2026-11-17T02:00:00Z",
                      selected_utc="2026-11-17T02:01:00Z"))["top_claims"][0]
        self.assertIn("MISSING_OR_INVALID_UTC:model_frozen_utc",r["flags"])
        self.assertIn("QUOTE_CAPTURE_NOT_PREGAME",r["flags"])
        self.assertIn("PICK_SELECTED_AFTER_START",r["flags"])

    def test_readonly_private_create_only_and_sha_evidence(self):
        with TemporaryDirectory() as td:
            folder = Path(td); folder.chmod(0o700)
            inp, fin, out = [folder/x for x in ("claims.json","finals.json","audit.json")]
            original = raw_claim([claim()]); result = raw_finals([final()])
            inp.write_bytes(original); fin.write_bytes(result)
            inp.chmod(0o600); fin.chmod(0o600)
            report = audit_files(inp, fin, out)
            self.assertEqual(inp.read_bytes(),original)
            self.assertEqual(fin.read_bytes(),result)
            self.assertEqual(out.stat().st_mode & 0o077,0)
            self.assertEqual(report["claim_source_sha256"],sha256(original).hexdigest())
            with self.assertRaises(FileExistsError):
                audit_files(inp, fin, out)

    def test_symlink_and_world_readable_private_input_denied(self):
        with TemporaryDirectory() as td:
            folder=Path(td); folder.chmod(0o700)
            inp,fin,out = [folder/x for x in ("claims.json","finals.json","audit.json")]
            inp.write_bytes(raw_claim([claim()])); fin.write_bytes(raw_finals([]))
            inp.chmod(0o644); fin.chmod(0o600)
            with self.assertRaisesRegex(EvidenceError,"PRIVATE_ORIGINAL_FILE_0600_REQUIRED"):
                audit_files(inp,fin,out)
            inp.chmod(0o600)
            alias=folder/"alias.json";alias.symlink_to(inp)
            with self.assertRaisesRegex(EvidenceError,"SYMLINK_AUDIT_PATH_FORBIDDEN"):
                audit_files(alias,fin,out)
            folder.chmod(0o755)
            with self.assertRaisesRegex(EvidenceError,"PRIVATE_PARENT_DIRECTORY_0700_REQUIRED"):
                audit_files(inp,fin,out)

    def test_duplicate_json_and_exponent_overflow_refused(self):
        a = b'{"schema":"sportsedge-original-claim-census-v1","rows":[],"rows":[]}'
        with self.assertRaisesRegex(EvidenceError,"DUPLICATE_JSON_KEY"):
            _parse(a,CLAIM_SCHEMA)
        a = b'{"schema":"sportsedge-original-claim-census-v1","rows":[{"x":1e999}]}'
        with self.assertRaisesRegex(EvidenceError,"NONFINITE_JSON_NUMBER"):
            _parse(a,CLAIM_SCHEMA)

    def test_invalid_malformed_row_kept(self):
        a = audit(raw_claim([None,claim(event_id="VALID")]),raw_finals([final()]))
        self.assertEqual(a["claimed_rows_total"],2)
        self.assertEqual(len(a["all_original_claims_retained"]),2)
        self.assertIn("INVALID_CLAIM_TYPE",a["all_original_claims_retained"][0]["flags"])


if __name__ == "__main__":
    unittest.main()