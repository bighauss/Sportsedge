"""Whole-repository certification audit: research-only truthfulness contracts.

All fixtures are local code/release-matrix metadata, never original odds,
real-time sportsbook responses, settled wagers, or independent signatures.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from tools.whole_repo_release_audit import (
    REPO, audit, parse_unique_json, MATRIX_PATH, FREEZE_PATH, PolicyError,
)
from research.risk.strict_v21_v22 import POLICY_VERSION


class WholeRepoCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = parse_unique_json((REPO / MATRIX_PATH).read_bytes())
        cls.freeze = parse_unique_json((REPO / FREEZE_PATH).read_bytes())

    def test_actual_matrix_stays_uncertified_and_surfaces_policy_drift(self):
        report = audit(REPO, matrix=self.original, freeze=self.freeze,
                       asof_date_ct="2026-11-16")
        self.assertEqual(report["release_verdict"], "NOT_CERTIFIED")
        self.assertFalse(report["production_certified"])
        self.assertEqual(report["approved_stake_u"], 0)
        self.assertEqual(report["official_market_count"], 0)
        self.assertEqual(report["declared_market_families"], 49)
        self.assertEqual(report["declared_closed_gate_claims"], 0)
        self.assertEqual(report["unverified_gate_requirements"], 245)
        self.assertIn("MATRIX_POLICY_MISMATCH", report["blockers"])
        self.assertIn("MATRIX_ASOF_NOT_CURRENT", report["blockers"])
        self.assertEqual(report["code_freeze"]["status"],
                         "CODE_IDENTITY_MATCH_ONLY_PAPER_0U")
        self.assertFalse(report["source_authenticated"])
        self.assertFalse(report["independent_review_verified"])

    def test_correcting_self_declared_policy_does_not_issue_certificate(self):
        matrix = deepcopy(self.original)
        matrix["policy"] = POLICY_VERSION
        matrix["asof_date_ct"] = "2026-11-16"
        report = audit(REPO, matrix=matrix, freeze=self.freeze,
                       asof_date_ct="2026-11-16")
        self.assertNotIn("MATRIX_POLICY_MISMATCH", report["blockers"])
        self.assertNotIn("MATRIX_ASOF_NOT_CURRENT", report["blockers"])
        self.assertFalse(report["production_certified"])
        self.assertIn("ORIGINAL_BOOKMAKER_AND_PIT_PROOF_MISSING", report["blockers"])
        self.assertIn("FORWARD_CALIBRATION_AND_CLV_PROOF_MISSING", report["blockers"])

    def test_forged_a_to_e_pass_flags_refused_not_certified(self):
        matrix = deepcopy(self.original)
        matrix["policy"] = POLICY_VERSION
        for row in matrix["markets"]:
            row["gates"] = dict.fromkeys("ABCDE", True)
        x = audit(REPO, matrix=matrix, freeze=self.freeze,
                  asof_date_ct="2026-11-16")
        self.assertIn("UNVERIFIED_SELF_REPORTED_GATE_PASSES", x["blockers"])
        self.assertEqual(x["declared_closed_gate_claims"], 245)
        self.assertFalse(x["production_certified"])

    def test_tampered_official_release_cannot_pass(self):
        matrix = deepcopy(self.original)
        matrix["markets"][0]["release_state"] = "OFFICIAL"
        matrix["markets"][0]["approved_stake_u"] = 2
        x = audit(REPO, matrix=matrix, freeze=self.freeze,
                  asof_date_ct="2026-11-16")
        self.assertIn("RELEASE_MATRIX_UNSAFE_OR_INCOMPLETE", x["blockers"])
        self.assertEqual(x["official_market_count"], 0)
        self.assertEqual(x["approved_stake_u"], 0)

    def test_missing_sport_and_duplicate_market_block(self):
        m = deepcopy(self.original)
        m["markets"] = m["markets"][1:]
        x = audit(REPO, matrix=m, freeze=self.freeze,
                  asof_date_ct="2026-11-16")
        self.assertIn("RELEASE_MATRIX_UNSAFE_OR_INCOMPLETE", x["blockers"])

    def test_malformed_unhashable_market_identity_does_not_crash_audit(self):
        # The standalone daily sweep can encounter list/dict where a valid
        # sport/family should be; still return a reason-coded BLOCK verdict.
        for name, value in (("sport", []), ("market_family", {})):
            with self.subTest(name=name):
                matrix = deepcopy(self.original)
                matrix["markets"][0][name] = value
                x = audit(REPO, matrix=matrix, freeze=self.freeze,
                          asof_date_ct="2026-11-16")
                self.assertIn("RELEASE_MATRIX_UNSAFE_OR_INCOMPLETE", x["blockers"])
                self.assertEqual(x["market_safety_audit_status"], "BLOCK")
                self.assertFalse(x["production_certified"])

    def test_modified_code_baseline_reported_as_code_integrity_fail(self):
        f = deepcopy(self.freeze)
        f["frozen_engine"]["git_blob_sha1"] = "0"*40
        x = audit(REPO, matrix=self.original, freeze=f,
                  asof_date_ct="2026-11-16")
        self.assertEqual(x["code_freeze"]["status"], "CODE_IDENTITY_CHECK_FAILED")
        self.assertIn("FROZEN_CODE_IDENTITY_INVALID", x["blockers"])
        self.assertFalse(x["production_certified"])

    def test_malformed_policy_is_rejected_before_report(self):
        with self.assertRaises(PolicyError):
            audit(REPO, matrix=self.original, freeze=self.freeze,
                  asof_date_ct="not-a-date")

    def test_duplicate_json_keys_cannot_inject_fake_evidence(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            parse_unique_json(b'{"policy":"GOOD","policy":"BAD"}')
        with self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
            parse_unique_json(b'{"gain":NaN}')

    def test_overflowing_json_number_cannot_enter_audit(self):
        # Python's json.loads accepts syntactically valid 1e999 as infinity
        # unless parse_float is guarded, even with parse_constant blocked.
        for payload in (b'{"stake":1e999}', b'{"stake":-1e999}',
                        b'{"stake":1e-999}', b'{"stake":1e9999}'):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "NONFINITE_JSON|UNDERFLOW_JSON"):
                    parse_unique_json(payload)

    def test_policy_date_asof_never_retroactively_updates_file(self):
        before=(REPO / MATRIX_PATH).read_bytes()
        audit(REPO, matrix=self.original, freeze=self.freeze,
              asof_date_ct="2026-11-16")
        self.assertEqual(before, (REPO / MATRIX_PATH).read_bytes())


if __name__ == "__main__":
    unittest.main()
