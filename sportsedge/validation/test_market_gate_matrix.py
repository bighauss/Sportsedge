"""Synthetic-only tests: a green structural count never certifies a market."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from sportsedge.validation.market_gate_matrix import (
    POLICY, SCHEMA, SPORTS, assess, report_file
)


def blank():
    return {
        "schema": SCHEMA,
        "rules_version": POLICY,
        "markets": [
            {"sport": sport, "market_family": "ML", "period": "FG",
             "market_key": "standard", "evidence_manifest": None}
            for sport in sorted(SPORTS)
        ],
    }


def evidence_one(card_id="c1"):
    return {
        "schema": "sportsedge-issue10-structural-v1",
        "cards": [{
            "card_id": card_id, "generated_utc": "2026-11-11T18:00:00Z",
            "price_rows": 1, "missing_price_rows": 0,
            "stale_quote_rows": 0, "unauthenticated_quote_rows": 0,
            "guard_bypasses": 0, "pit_total": 1, "pit_complete": 1
        }],
        "clv_triples": [], "calibration_cycles": [],
    }


def entirely_self_reported_passing_evidence():
    evidence = evidence_one()
    evidence["cards"] = []
    for day in range(10, 15):
        for offset in range(20):
            card = copy.deepcopy(evidence_one()["cards"][0])
            card["card_id"] = f"card-{day}-{offset}"
            card["generated_utc"] = f"2026-11-{day}T18:{offset:02}Z"
            evidence["cards"].append(card)
    for i in range(200):
        evidence["clv_triples"].append({
            "bet_id": f"bet-{i}",
            "event_start_utc": "2026-11-11T23:00:00Z",
            "open_observed_utc": "2026-11-11T14:00:00Z",
            "taken_observed_utc": "2026-11-11T15:00:00Z",
            "close_observed_utc": "2026-11-11T22:00:00Z",
            "settled_at_utc": "2026-11-12T02:00:00Z",
            "settlement": "WIN" if i % 2 == 0 else "LOSS",
            "market_identity_matched": True,
            "upstream_book_matched": True,
        })
    for i in range(3):
        evidence["calibration_cycles"].append({
            "cycle_id": f"cycle-{i}",
            "registered_utc": f"2026-10-0{i + 1}T00:00:00Z",
            "window_start_utc": f"2026-10-0{i + 2}T00:00:00Z",
            "window_end_utc": f"2026-10-0{i + 3}T00:00:00Z",
            "leakage_findings": 0, "report_sha256": "sha256:" + "a" * 64,
        })
    return evidence


class MarketGateMatrixTests(unittest.TestCase):
    def test_all_seven_sports_required_and_no_evidence_is_never_certified(self):
        result = assess(blank())
        self.assertEqual(set(result["declared_market_count_by_sport"]), SPORTS)
        self.assertEqual(result["official_market_count"], 0)
        self.assertEqual(result["approved_stake_u"], 0)
        self.assertFalse(result["release_certified"])
        self.assertTrue(all(x["reason"] == "NO_SUBMITTED_EVIDENCE"
                            for x in result["markets"]))

    def test_one_market_does_not_greenlight_seven(self):
        manifest = blank()
        manifest["markets"][0]["evidence_manifest"] = evidence_one()
        r = assess(manifest)
        self.assertFalse(r["markets"][0]["reported_all_structural_thresholds_met"])
        self.assertEqual(r["markets"][1]["reported_structural_thresholds"], {})
        self.assertEqual(r["official_market_count"], 0)

    def test_all_structural_thresholds_still_0u(self):
        manifest = blank()
        manifest["markets"][0]["evidence_manifest"] = entirely_self_reported_passing_evidence()
        r = assess(manifest)
        first = r["markets"][0]
        self.assertTrue(first["reported_all_structural_thresholds_met"])
        self.assertFalse(first["externally_certified"])
        self.assertEqual(first["approved_stake_u"], 0)
        self.assertFalse(r["release_certified"])
        self.assertEqual(r["official_market_count"], 0)

    def test_reused_evidence_id_across_markets_fails_closed(self):
        manifest = blank()
        manifest["markets"][0]["evidence_manifest"] = evidence_one()
        manifest["markets"][1]["evidence_manifest"] = evidence_one()
        with self.assertRaisesRegex(ValueError, "CROSS_MARKET_EVIDENCE_REUSE"):
            assess(manifest)

    def test_missing_sport_refused_not_silently_dropped(self):
        manifest = blank()
        manifest["markets"] = manifest["markets"][:-1]
        with self.assertRaisesRegex(ValueError, "INVALID_MARKET_ENTRY_COUNT|MISSING_SPORT_COVERAGE"):
            assess(manifest)
        manifest["markets"].append(copy.deepcopy(manifest["markets"][0]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_MARKET_IDENTITY"):
            assess(manifest)

    def test_unknown_sport_market_period_and_key(self):
        for field, value in (("sport", "WNBA"), ("market_family", "UNKNOWN"),
                             ("period", "bad space"), ("market_key", "unsafe|join")):
            with self.subTest(field=field):
                manifest = blank()
                manifest["markets"][0][field] = value
                with self.assertRaises(ValueError):
                    assess(manifest)

    def test_v22_not_silently_adopted(self):
        manifest = blank()
        manifest["rules_version"] = "RUN_IT_V2_2"
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_RISK_POLICY_VERSION"):
            assess(manifest)

    def test_nested_bad_evidence_rejected(self):
        manifest = blank()
        manifest["markets"][0]["evidence_manifest"] = {"cards": [], "clv_triples": [],
                                                     "calibration_cycles": []}
        with self.assertRaisesRegex(ValueError, "INVALID_FIELDS"):
            assess(manifest)

    def test_strict_report_is_private_create_only(self):
        manifest = blank()
        with tempfile.TemporaryDirectory() as work:
            src = Path(work) / "input.json"
            dst = Path(work) / "output.json"
            src.write_text(json.dumps(manifest), encoding="utf-8")
            report = report_file(src, dst)
            self.assertEqual(json.loads(dst.read_text())["input_sha256"],
                             report["input_sha256"])
            self.assertFalse(report["release_certified"])
            if os.name == "posix":
                self.assertEqual(dst.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                report_file(src, dst)

    def test_duplicate_json_key_and_nan_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            src = Path(work) / "in.json"
            dst = Path(work) / "out.json"
            src.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
                report_file(src, dst)
            self.assertFalse(dst.exists())
            src.write_text('{"schema":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
                report_file(src, dst)
            self.assertFalse(dst.exists())

    def test_extra_keys_and_wrong_type_are_not_accepted(self):
        manifest = blank()
        manifest["allow_official"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_FIELDS"):
            assess(manifest)
        manifest = blank()
        manifest["markets"][0]["evidence_manifest"] = 7
        with self.assertRaisesRegex(ValueError, "INVALID_EVIDENCE_MANIFEST"):
            assess(manifest)


if __name__ == "__main__":
    unittest.main()
