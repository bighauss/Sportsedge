"""Original-byte private observability bridge synthetic/adversarial regressions.

No synthetic source here is an authenticated sportsbook, wager or forward run.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from integrations.observability.private_source_bridge import (
    SCHEMA, BridgeHold, _json, transform, private_cli,
)


def digest(raw):
    return "sha256:" + sha256(raw).hexdigest()


class PrivateBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o700)
        self.sel = {
            "sport": "CBB", "event_id": "fixture-GAME-1",
            "period": "FG", "market": "total", "side": "over",
            "line": "149.5", "tipoff_utc": "2026-11-15T19:00:00Z",
        }
        self.model = {
            "sha256": "sha256:" + "a"*64,
            "trained_until_utc": "2026-11-14T21:00:00Z",
            "freeze_utc": "2026-11-15T17:45:00Z",
            "probability": 0.58,
        }
        self.source = {
            "provider": "operator-test-source",
            "data_through_utc": "2026-11-15T16:00:00Z",
            "published_utc": "2026-11-15T16:15:00Z",
            "captured_utc": "2026-11-15T17:00:00Z",
        }
        self.take = {
            "book": "DraftKings", "captured_utc": "2026-11-15T17:30:00Z",
            "price_american": -110,
        }
        self.close = {
            **self.sel, "book": "DraftKings",
            "captured_utc": "2026-11-15T18:58:00Z",
            "price_american": -125,
        }
        self.outcome = {
            "result": "W", "settled_utc": "2026-11-16T03:00:00Z",
            "observed_utc": "2026-11-16T03:01:00Z",
            "captured_utc": "2026-11-16T03:02:00Z",
        }
        self.attempt = self.make_attempt()

    def write(self, name, raw):
        path = self.root / name
        path.write_bytes(raw)
        path.chmod(0o600)
        return {"path": str(path), "sha256": digest(raw)}

    def make_attempt(self, *, include_close=True, include_outcome=True,
                     selection=None, name="fixture"):
        selection = deepcopy(self.sel if selection is None else selection)
        model = deepcopy(self.model)
        source = deepcopy(self.source)
        take = deepcopy(self.take)
        freeze = self.write(name + "-freeze.json",
                            b'{"schema":"local-freeze-only","certified":false}')
        forecast = self.write(name + "-forecast.json", json.dumps({
            "schema": "SPORTSEDGE_OBS_FORECAST_ROW_V1",
            "selection": selection, "model_sha256": model["sha256"],
            "freeze_sha256": freeze["sha256"],
            "model_probability": model["probability"],
        }).encode())
        model["forecast_sha256"] = forecast["sha256"]
        source_file = self.write(name + "-source-original.json",
                                 b'{"pre_event_source":"synthetic"}')
        source["sha256"] = source_file["sha256"]
        take_file = self.write(name + "-take-original.json", json.dumps({
            "schema": "SPORTSEDGE_OBS_QUOTE_ROW_V1", "selection": selection,
            "book": take["book"], "captured_utc": take["captured_utc"],
            "price_american": take["price_american"],
        }).encode())
        take["sha256"] = take_file["sha256"]
        originals = {"freeze": freeze, "forecast": forecast,
                     "source": source_file, "take": take_file}
        result = {
            "schema": SCHEMA, "state": "PAPER_0U",
            "decision_id": "decision-" + name, "selection": selection,
            "model": model, "source": source, "take": take,
            "freeze_sha256": freeze["sha256"], "originals": originals,
        }
        if include_close:
            close = deepcopy(self.close)
            for k in selection:
                if k in close:
                    close[k] = selection[k]
            close_file = self.write(name + "-close-original.json", json.dumps({
                "schema": "SPORTSEDGE_OBS_QUOTE_ROW_V1", "selection": selection,
                "book": close["book"], "captured_utc": close["captured_utc"],
                "price_american": close["price_american"],
            }).encode())
            close["sha256"] = close_file["sha256"]
            result["close"] = close
            originals["close"] = close_file
        if include_outcome:
            outcome = deepcopy(self.outcome)
            outcome_file = self.write(name + "-outcome-original.json", json.dumps({
                "schema": "SPORTSEDGE_OBS_OUTCOME_ROW_V1",
                "selection": selection,
                "result": outcome["result"],
                "settled_utc": outcome["settled_utc"],
            }).encode())
            outcome["sha256"] = outcome_file["sha256"]
            result["outcome"] = outcome
            originals["outcome"] = outcome_file
        return result

    @staticmethod
    def raw(*attempts):
        return [json.dumps(a).encode() for a in attempts]

    def test_originals_all_present_locally_still_unauthenticated(self):
        downstream, report = transform(self.raw(self.attempt))
        self.assertEqual(report["state"], "PAPER_0U_LOCAL_ONLY")
        self.assertEqual(report["attempted_rows"], 1)
        self.assertEqual(report["blocked_rows"], 0)
        self.assertEqual(report["quality_gate_aggregate"]["n_clv_matched_unverified"], 1)
        self.assertFalse(report["source_original_book_authenticated"])
        self.assertFalse(report["genuine_clv_certified"])
        self.assertEqual(report["approved_stake_u"], 0)
        self.assertNotIn("decision_id", downstream[0])

    def test_original_sha_tamper_retains_blocked_denominator(self):
        Path(self.attempt["originals"]["source"]["path"]).write_text("tampered")
        _, report = transform(self.raw(self.attempt))
        self.assertEqual((report["attempted_rows"], report["blocked_rows"]), (1,1))
        self.assertIn("ORIGINAL_SHA_MISMATCH", report["rows"][0]["reason"])

    def test_original_take_content_cannot_relabel_line(self):
        original = self.attempt["originals"]["take"]
        body = json.loads(Path(original["path"]).read_text())
        body["selection"]["line"] = "150.5"
        raw = json.dumps(body).encode()
        Path(original["path"]).write_bytes(raw)
        self.attempt["take"]["sha256"] = digest(raw)
        self.attempt["originals"]["take"]["sha256"] = digest(raw)
        _, report = transform(self.raw(self.attempt))
        self.assertIn("ORIGINAL_SELECTION_OR_SCHEMA_MISMATCH", report["rows"][0]["reason"])

    def test_original_selection_boolean_cannot_equal_integer(self):
        # A JSON boolean is not the integer event identity in original bytes.
        original = self.attempt["originals"]["take"]
        body = json.loads(Path(original["path"]).read_text())
        body["selection"]["event_id"] = 1
        self.attempt["selection"]["event_id"] = True
        # Keep other original selections consistent with claimed selection so
        # this specifically probes the take-original nested equality.
        for key in ("forecast", "close", "outcome"):
            ref = self.attempt["originals"][key]
            doc = json.loads(Path(ref["path"]).read_text())
            doc["selection"]["event_id"] = True
            raw = json.dumps(doc).encode()
            Path(ref["path"]).write_bytes(raw)
            ref["sha256"] = digest(raw)
            if key == "forecast":
                self.attempt["model"]["forecast_sha256"] = digest(raw)
            elif key == "close":
                self.attempt["close"]["sha256"] = digest(raw)
            else:
                self.attempt["outcome"]["sha256"] = digest(raw)
        raw = json.dumps(body).encode()
        Path(original["path"]).write_bytes(raw)
        original["sha256"] = digest(raw)
        self.attempt["take"]["sha256"] = digest(raw)
        _, report = transform(self.raw(self.attempt))
        self.assertIn("ORIGINAL_SELECTION_OR_SCHEMA_MISMATCH",
                      report["rows"][0]["reason"])

    def test_original_selection_float_cannot_equal_integer(self):
        # Nested numeric representation must be exact even when Python == agrees.
        original = self.attempt["originals"]["take"]
        body = json.loads(Path(original["path"]).read_text())
        body["selection"]["line"] = 1
        self.attempt["selection"]["line"] = 1.0
        for key in ("forecast", "close", "outcome"):
            ref = self.attempt["originals"][key]
            doc = json.loads(Path(ref["path"]).read_text())
            doc["selection"]["line"] = 1.0
            raw = json.dumps(doc).encode()
            Path(ref["path"]).write_bytes(raw)
            ref["sha256"] = digest(raw)
            if key == "forecast":
                self.attempt["model"]["forecast_sha256"] = digest(raw)
            elif key == "close":
                self.attempt["close"]["sha256"] = digest(raw)
            else:
                self.attempt["outcome"]["sha256"] = digest(raw)
        raw = json.dumps(body).encode()
        Path(original["path"]).write_bytes(raw)
        original["sha256"] = digest(raw)
        self.attempt["take"]["sha256"] = digest(raw)
        _, report = transform(self.raw(self.attempt))
        self.assertIn("ORIGINAL_SELECTION_OR_SCHEMA_MISMATCH",
                      report["rows"][0]["reason"])

    def test_forged_quote_clock_fails_without_regenerating_original(self):
        self.attempt["take"]["captured_utc"] = "2026-11-15T17:32:00Z"
        _, report = transform(self.raw(self.attempt))
        self.assertIn("ORIGINAL_RECEIPT_CONTENT_MISMATCH", report["rows"][0]["reason"])

    def test_original_quote_boolean_cannot_equal_integer_price(self):
        # Python True == 1 must not bind a claimed numeric quote to boolean bytes.
        self.attempt["take"]["price_american"] = True
        original = self.attempt["originals"]["take"]
        body = json.loads(Path(original["path"]).read_text())
        body["price_american"] = 1
        raw = json.dumps(body).encode()
        Path(original["path"]).write_bytes(raw)
        original["sha256"] = digest(raw)
        self.attempt["take"]["sha256"] = digest(raw)
        _, report = transform(self.raw(self.attempt))
        self.assertIn("ORIGINAL_RECEIPT_CONTENT_MISMATCH:price_american",
                      report["rows"][0]["reason"])

    def test_original_quote_float_cannot_equal_integer_price(self):
        self.attempt["take"]["price_american"] = 200.0
        original = self.attempt["originals"]["take"]
        body = json.loads(Path(original["path"]).read_text())
        body["price_american"] = 200
        raw = json.dumps(body).encode()
        Path(original["path"]).write_bytes(raw)
        original["sha256"] = digest(raw)
        self.attempt["take"]["sha256"] = digest(raw)
        _, report = transform(self.raw(self.attempt))
        self.assertIn("ORIGINAL_RECEIPT_CONTENT_MISMATCH:price_american",
                      report["rows"][0]["reason"])

    def test_claimed_source_after_freeze_blocks(self):
        self.attempt["source"]["captured_utc"] = "2026-11-15T17:46:00Z"
        _, report = transform(self.raw(self.attempt))
        self.assertIn("SOURCE_LOOKAHEAD_OR_CLOCK_ORDER", report["rows"][0]["reason"])

    def test_missing_settlement_raw_preserved_as_blocked(self):
        self.attempt["originals"].pop("outcome")
        _, report = transform(self.raw(self.attempt))
        self.assertIn("ORIGINAL_RECEIPT_DENOMINATOR_MISMATCH", report["rows"][0]["reason"])

    def test_pre_event_outcome_observation_blocked(self):
        self.attempt["outcome"]["observed_utc"] = "2026-11-15T18:59:00Z"
        _, report = transform(self.raw(self.attempt))
        self.assertIn("OUTCOME_OBSERVATION_BEFORE_SETTLEMENT", report["rows"][0]["reason"])

    def test_blocked_manual_exclusion_stays_in_denominator(self):
        block = {"schema": SCHEMA, "state":"BLOCKED",
                 "decision_id":"EXCLUDED-1","selection":self.sel,
                 "block_reason":"MISSING_ORIGINAL_DK_PRICE"}
        _, report = transform(self.raw(block))
        self.assertEqual(report["blocked_rows"],1)
        self.assertIn("ORIGINAL_BLOCKED",report["rows"][0]["reason"])

    def test_no_close_not_historically_backfilled(self):
        a=self.make_attempt(include_close=False,name="no-close")
        _, report=transform(self.raw(a))
        self.assertEqual(report["blocked_rows"],0)
        self.assertEqual(report["quality_gate_aggregate"]["n_clv_matched_unverified"],0)

    def test_same_selection_different_attempt_ids_quarantine_both(self):
        a=self.make_attempt(name="one")
        b=self.make_attempt(name="two")
        _, report=transform(self.raw(a,b))
        self.assertEqual(report["blocked_rows"],2)
        self.assertTrue(all("DUPLICATE_CANONICAL_SELECTION" in r["reason"]
                            for r in report["rows"]))

    def test_duplicate_id_different_alt_lines_quarantines_both(self):
        a=self.make_attempt(name="one")
        selection=dict(self.sel,line="151.5")
        b=self.make_attempt(selection=selection,name="two")
        b["decision_id"]=a["decision_id"]
        _, report=transform(self.raw(a,b))
        self.assertEqual(report["blocked_rows"],2)
        self.assertTrue(all("DUPLICATE_DECISION_ID" in r["reason"]
                            for r in report["rows"]))

    def test_different_alt_lines_with_distinct_ids_preserved(self):
        a=self.make_attempt(name="one")
        b=self.make_attempt(selection=dict(self.sel,line="151.5"),name="two")
        _, report=transform(self.raw(a,b))
        self.assertEqual(report["locally_checked_rows"],2)

    def test_invalid_one_copy_quarantines_other_matching_selection(self):
        a=self.make_attempt(name="one")
        b=self.make_attempt(name="two")
        b["model"]["forecast_sha256"]="sha256:"+"f"*64
        _, report=transform(self.raw(a,b))
        self.assertEqual(report["blocked_rows"],2)

    def test_original_nested_duplicate_json_key_refused(self):
        raw=b'{"schema":"x","extra":{"p":1,"p":2}}'
        with self.assertRaisesRegex(BridgeHold,"ORIGINAL_JSON_DUPLICATE_KEY"):
            _json(raw)
        lines=self.raw(self.attempt) + [raw]
        _, report=transform(lines)
        self.assertEqual((report["attempted_rows"],report["blocked_rows"]),(2,1))

    def test_exponent_overflow_nonfinite_original_json_refused(self):
        with self.assertRaisesRegex(BridgeHold,"ORIGINAL_JSON_NONFINITE"):
            _json(b'{"nested":{"unexpected":1e999}}')
        _, report=transform([b'{"nested":{"unexpected":1e999}}'])
        self.assertEqual(report["blocked_rows"],1)

    def test_bogus_model_probability_stays_blocked(self):
        self.attempt["model"]["probability"]=1.2
        _, report=transform(self.raw(self.attempt))
        self.assertEqual(report["blocked_rows"],1)

    def test_private_os_error_path_never_leaks_into_report(self):
        secret_path="/private/customer-identity-secret-original.json"
        with patch("integrations.observability.private_source_bridge._read",
                   side_effect=OSError("ACCESS DENIED: " + secret_path)):
            _, report = transform(self.raw(self.attempt))
        self.assertEqual(report["blocked_rows"], 1)
        self.assertEqual(report["rows"][0]["reason"], "PRIVATE_ORIGINAL_IO_FAILURE")
        self.assertNotIn(secret_path, json.dumps(report))

    def test_excessively_nested_json_quarantines_row_not_whole_batch(self):
        malicious=b'{"nested":' + b'['*1200 + b'0' + b']'*1200 + b'}'
        _, report=transform(self.raw(self.attempt) + [malicious])
        self.assertEqual(report["attempted_rows"], 2)
        self.assertEqual(report["blocked_rows"], 1)
        self.assertIn("ORIGINAL_JSON_MALFORMED", report["rows"][1]["reason"])

    def test_private_cli_writes_two_owner_only_create_once_files(self):
        attempts=self.root/"attempts.jsonl"
        attempts.write_bytes(b"\n".join(self.raw(self.attempt))+b"\n")
        attempts.chmod(0o600)
        normalized=self.root/"quality-input.jsonl"
        report_file=self.root/"bridge-report.json"
        rc=private_cli(["--attempts",str(attempts),"--normalized",
                        str(normalized),"--report",str(report_file)])
        self.assertEqual(rc,0)
        self.assertEqual(normalized.stat().st_mode & 0o777,0o600)
        self.assertEqual(report_file.stat().st_mode & 0o777,0o600)
        self.assertEqual(len(normalized.read_text().splitlines()),1)
        saved=json.loads(report_file.read_bytes())
        self.assertFalse(saved["source_original_book_authenticated"])
        self.assertNotIn("fixture-GAME-1", report_file.read_text())
        with self.assertRaisesRegex(BridgeHold,"PRIVATE_OUTPUT_MUST_BE_NEW"):
            private_cli(["--attempts",str(attempts),"--normalized",
                         str(normalized),"--report",str(report_file)])

    def test_private_cli_public_output_refused(self):
        attempts=self.root/"attempts.jsonl"
        attempts.write_bytes(b"\n".join(self.raw(self.attempt))+b"\n")
        attempts.chmod(0o600)
        with self.assertRaisesRegex(BridgeHold,"PUBLIC_REPO_PATH_REFUSED"):
            private_cli(["--attempts",str(attempts),
                         "--normalized",str(Path(__file__).resolve().parents[2]/"leak.jsonl"),
                         "--report",str(self.root/"report.json")])


if __name__ == "__main__":
    unittest.main()
