"""Adversarial, OFFLINE tests for exact original CBB board/final receipt joining."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cbbd_frozen_final_join import reconcile, run, Hold
from point_in_time_score_walkforward import audit as walkforward_audit

H = "a" * 64
B = "b" * 64
FREEZE = "2026-11-15T18:00:00Z"
TIP = "2026-11-15T20:00:00Z"
OBS = "2026-11-15T23:30:00Z"


def prediction(id_value="10", *, home="101", away="202"):
    sources = {key: {"sha256": H, "captured_utc": "2026-11-15T17:00:00Z"}
               for key in ("home", "away", "league", "hca")}
    return {"input_index": 0, "game_id": id_value, "season": 2027,
            "status": "PAPER_NON_COUNTED_UNCALIBRATED", "official": False, "stake_u": 0,
            "home_team_id": home, "away_team_id": away,
            "freeze_utc": FREEZE, "tipoff_utc": TIP, "model_sha256": H,
            "home_points": 73.0, "away_points": 69.0, "margin_home": 4.0,
            "total": 142.0, "source_clock_consistent_not_authenticated": sources,
            "expected_value": None}


def board(*items):
    results = deepcopy(list(items or [prediction()]))
    for i, r in enumerate(results):
        r["input_index"] = i
    return {"status": "CBB_POINT_IN_TIME_RESEARCH_ONLY_UNAUTHENTICATED_PAPER_0U",
            "official": False, "stake_u": 0,
            "season": 2027, "freeze_utc": FREEZE,
            "input_rows": len(results),
            "projected_rows": sum(x["status"] == "PAPER_NON_COUNTED_UNCALIBRATED" for x in results),
            "source_sha256": {"schedule": H, "torvik": H, "crosswalk": H, "hca": H},
            "results": results}


def final_row(id_value="10", *, home="101", away="202", observed=OBS):
    return {"input_index": 0, "game_id": id_value,
            "status": "FINAL_RECEIPT_LOCAL_CAPTURE_UNAUTHENTICATED",
            "official": False, "stake_u": 0,
            "final": {"game_id": id_value, "season": 2027,
                      "home_team_id": home, "away_team_id": away,
                      "status": "FINAL", "period": "FG_INCL_OT",
                      "home_score": 75, "away_score": 70,
                      "sha256": B, "published_utc": observed, "captured_utc": observed,
                      "publication_basis": "UPPER_BOUND_LOCAL_OBSERVATION_NOT_PROVIDER_PUBLICATION"}}


def finals(*items):
    records = deepcopy(list(items or [final_row()]))
    for i, r in enumerate(records):
        r["input_index"] = i
    return {"format": "CBBD_LOCAL_FINAL_RECEIPTS_V1",
            "status": "PAPER_0U_SOURCE_NOT_INDEPENDENTLY_ATTESTED",
            "official": False, "stake_u": 0,
            "source_sha256": B, "local_observed_utc": OBS,
            "row_count": len(records), "rows": records}


class StrictCBBJoinTests(unittest.TestCase):
    def test_complete_score_join_exact_identity_and_evaluator_compatible(self):
        ledger, report = reconcile(board(), finals())
        self.assertEqual(len(ledger), 1)
        self.assertEqual(report["matched_rows"], 1)
        self.assertEqual(ledger[0]["final"]["home_score"], 75)
        self.assertEqual(ledger[0]["final"]["away_team_id"], "202")
        self.assertIsNone(ledger[0]["quote"])
        self.assertFalse(report["official"])
        self.assertEqual(report["stake_u"], 0)
        evaluated = walkforward_audit(ledger)
        self.assertEqual(evaluated["valid_decided_rows"] if "valid_decided_rows" in evaluated else
                         evaluated["row_statuses"]["VALID_SCORE_RECEIPTS_UNAUTHENTICATED"], 1)
        self.assertEqual(evaluated["walkforward_evaluated_n"], 0)

    def test_no_final_is_preserved_pending_not_omitted(self):
        report_final = finals()
        report_final["rows"] = []
        report_final["row_count"] = 0
        ledger, report = reconcile(board(), report_final)
        self.assertEqual(len(ledger), 1)
        self.assertEqual(report["join_status_counts"]["MISSING_FINAL_RECEIPT"], 1)
        self.assertIsNone(ledger[0]["final"])

    def test_blocked_original_preserved(self):
        orig = prediction()
        orig = {"input_index": 0, "game_id": "10", "status": "BLOCKED",
                "official": False, "stake_u": 0, "reason": "MISSING_HCA"}
        ledger, report = reconcile(board(orig), finals())
        self.assertEqual(report["join_status_counts"]["BLOCKED_ORIGINAL_ROW"], 1)
        self.assertEqual(ledger[0]["prediction"]["reason"], "MISSING_HCA")
        self.assertIsNone(ledger[0]["final"])

    def test_duplicate_original_all_copies_quarantined(self):
        ledger, report = reconcile(board(prediction(), prediction()), finals())
        self.assertEqual(report["matched_rows"], 0)
        self.assertEqual(report["join_status_counts"]["DUPLICATE_ORIGINAL_BOARD_ALL_COPIES"], 2)
        self.assertTrue(all(x["final"] is None for x in ledger))

    def test_duplicate_final_all_copies_quarantined_even_if_first_final(self):
        ledger, report = reconcile(board(), finals(final_row(), final_row()))
        self.assertEqual(report["join_status_counts"]["DUPLICATE_FINAL_RECEIPT_ALL_COPIES"], 1)
        self.assertIsNone(ledger[0]["final"])

    def test_wrong_team_or_season_not_joined(self):
        ledger, report = reconcile(board(), finals(final_row(home="999")))
        self.assertIsNone(ledger[0]["final"])
        self.assertEqual(report["rows"][0]["join_status"], "FINAL_IDENTITY_OR_CLOCK_BLOCKED")
        fr = final_row()
        fr["final"]["season"] = 2026
        ledger, report = reconcile(board(), finals(fr))
        self.assertIsNone(ledger[0]["final"])
        self.assertIn("FINAL_IDENTITY_MISMATCH", report["rows"][0]["reason"])

    def test_wrong_source_hash_does_not_join(self):
        fr = final_row()
        fr["final"]["sha256"] = H
        ledger, report = reconcile(board(), finals(fr))
        self.assertEqual(report["rows"][0]["reason"], "FINAL_SOURCE_DIGEST_MISMATCH")
        self.assertIsNone(ledger[0]["final"])

    def test_forged_earlier_publication_not_joined(self):
        fr = final_row()
        fr["final"]["published_utc"] = "2026-11-15T21:00:00Z"
        ledger, report = reconcile(board(), finals(fr))
        self.assertEqual(report["rows"][0]["reason"], "FINAL_LOCAL_OBSERVATION_CLOCK_MISMATCH")
        self.assertIsNone(ledger[0]["final"])

    def test_live_or_tbd_final_is_not_joined(self):
        fr = final_row()
        fr["status"] = "NOT_FINAL_OR_FUTURE_EVENT"
        fr.pop("final")
        ledger, report = reconcile(board(), finals(fr))
        self.assertIsNone(ledger[0]["final"])
        self.assertEqual(report["rows"][0]["join_status"], "UNAVAILABLE_OR_INVALID_FINAL")

    def test_invalid_original_math_blocks_join(self):
        orig = prediction()
        orig["total"] = 123.5
        ledger, report = reconcile(board(orig), finals())
        self.assertIsNone(ledger[0]["final"])
        self.assertEqual(report["rows"][0]["join_status"], "INVALID_ORIGINAL_PREDICTION")

    def test_original_source_observed_late_blocks_join(self):
        orig = prediction()
        orig["source_clock_consistent_not_authenticated"]["home"]["captured_utc"] = TIP
        ledger, report = reconcile(board(orig), finals())
        self.assertIsNone(ledger[0]["final"])
        self.assertIn("FUTURE_CAPTURE", report["rows"][0]["reason"])

    def test_board_freeze_identity_is_invariant(self):
        orig = prediction()
        orig["freeze_utc"] = "2026-11-15T18:01:00Z"
        ledger, report = reconcile(board(orig), finals())
        self.assertEqual(report["rows"][0]["join_status"], "INVALID_ORIGINAL_PREDICTION")

    def test_unmatched_final_source_census_is_reported(self):
        ledger, report = reconcile(board(), finals(final_row(), final_row("11"), final_row("12")))
        self.assertEqual(report["matched_rows"], 1)
        self.assertEqual(report["unmatched_final_source_rows"], 2)
        self.assertEqual(report["final_source_rows"], 3)
        self.assertEqual(len(ledger), 1)

    def test_invalid_source_index_or_census_fails_whole_import(self):
        fr = finals()
        fr["row_count"] = 0
        with self.assertRaisesRegex(Hold, "FINALS_ROW_CENSUS"):
            reconcile(board(), fr)
        bd = board()
        bd["results"][0]["input_index"] = 44
        with self.assertRaisesRegex(Hold, "BOARD_ROW_INDEX"):
            reconcile(bd, finals())

    def test_nonpaper_promotion_claim_blocks_import(self):
        bd = board()
        bd["official"] = True
        with self.assertRaisesRegex(Hold, "ORIGINAL_BOARD_UNRECOGNIZED"):
            reconcile(bd, finals())
        fr = finals()
        fr["stake_u"] = 1
        with self.assertRaisesRegex(Hold, "ORIGINAL_FINALS_REPORT_UNRECOGNIZED"):
            reconcile(board(), fr)

    def test_original_malformed_id_not_fuzzy_joined(self):
        bd = board(prediction("010"))
        ledger, report = reconcile(bd, finals())
        self.assertEqual(report["rows"][0]["join_status"], "INVALID_BOARD_EVENT_ID")
        self.assertIsNone(ledger[0]["final"])

    def test_nonpostgame_observation_cannot_grade(self):
        fr = final_row(observed="2026-11-15T19:00:00Z")
        f = finals(fr)
        f["local_observed_utc"] = "2026-11-15T19:00:00Z"
        ledger, report = reconcile(board(), f)
        self.assertEqual(report["rows"][0]["join_status"], "FINAL_IDENTITY_OR_CLOCK_BLOCKED")
        self.assertIsNone(ledger[0]["final"])

    def test_create_only_private_two_outputs_with_exact_hash_and_0600(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board_path, final_path = root/"orig.json", root/"final.json"
            board_path.write_text(json.dumps(board()))
            final_path.write_text(json.dumps(finals()))
            ledger_path, audit_path = root/"ledger.json", root/"ledger_audit.json"
            result = run(board_path, final_path, ledger_path=ledger_path, audit_path=audit_path)
            self.assertEqual(result["matched_rows"], 1)
            self.assertEqual(ledger_path.stat().st_mode & 0o077, 0)
            self.assertEqual(audit_path.stat().st_mode & 0o077, 0)
            report = json.loads(audit_path.read_text())
            self.assertEqual(report["original_frozen_board_file_sha256"],
                             hashlib.sha256(board_path.read_bytes()).hexdigest())
            self.assertEqual(report["ledger_sha256"], hashlib.sha256(ledger_path.read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                run(board_path, final_path, ledger_path=ledger_path, audit_path=audit_path)

    def test_invalid_json_duplicate_keys_fail_without_creating_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board_path, final_path = root/"orig.json", root/"final.json"
            board_path.write_text('{"status":1,"status":2}')
            final_path.write_text(json.dumps(finals()))
            with self.assertRaisesRegex(Hold, "INVALID_OR_DUPLICATE_JSON_SOURCE"):
                run(board_path, final_path, ledger_path=root/"ledger.json", audit_path=root/"audit.json")
            self.assertFalse((root/"ledger.json").exists())
            self.assertFalse((root/"audit.json").exists())

    def test_public_checkout_paths_not_accepted(self):
        from cbbd_frozen_final_join import __file__ as module
        with self.assertRaisesRegex(Hold, "PUBLIC_GIT_REPOSITORY"):
            run(Path(module), Path(module), ledger_path="/tmp/synth-ledger",
                audit_path="/tmp/synth-audit")

    def test_report_write_failure_rolls_back_ledger_without_touching_sources(self):
        import cbbd_frozen_final_join as module
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp, fin = root/"board.json", root/"finals.json"
            inp.write_text(json.dumps(board()))
            fin.write_text(json.dumps(finals()))
            original_hash = hashlib.sha256(inp.read_bytes()).hexdigest()
            real_create = module._private_create
            def failing_create(path, data):
                if str(path).endswith("audit.json"):
                    raise OSError("synthetic audit write failure")
                return real_create(path, data)
            with patch.object(module, "_private_create", side_effect=failing_create):
                with self.assertRaisesRegex(OSError, "synthetic audit write failure"):
                    run(inp, fin, ledger_path=root/"ledger.json", audit_path=root/"audit.json")
            self.assertFalse((root/"ledger.json").exists())
            self.assertFalse((root/"audit.json").exists())
            self.assertEqual(hashlib.sha256(inp.read_bytes()).hexdigest(), original_hash)


if __name__ == "__main__":
    unittest.main()
