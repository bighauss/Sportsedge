"""Adversarial, isolated governance contract tests; no model or original odds data."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.agent_change_governance import (
    GOLDEN_CASES, GOLDEN_SHA256, GovernanceError, classify_candidate,
    golden_regression, inspect_pr, is_protected, parse, validate_manifest,
)

BASE = "a" * 40
HEAD = "b" * 40
PROTECTED = ["RISK_POLICY.md", "models/cbb/torvik_point_in_time_baseline.py"]
GOLDEN_PATH = Path(__file__).resolve().parents[1] / (
    "research/ai_governance/golden_agent_safety_v1.json"
)


def base_manifest(paths=None):
    return {
        "schema": "sportsedge-high-risk-agent-change-v1",
        "pr_number": 45, "base_commit": BASE,
        "protected_paths": sorted(PROTECTED if paths is None else paths),
        "ticket_url": "https://github.com/bighauss/Sportsedge/issues/57",
        "change_summary": "Synthetic surgical model fix with known regression tests.",
        "assumptions": ["No actual provider receipt or production rights are asserted."],
        "agent_identity": "synthetic-coding-agent",
        "permissions": {
            "role": "CODING_AGENT", "repo_write": "BRANCH_ONLY",
            "secrets_read": False, "production_deploy": False,
            "market_release": False, "merge_rights": "REPO_RULES_ONLY",
        },
        "baseline": {
            "metric": "forward_brier", "before": None,
            "unit": "score", "source_state": "UNKNOWN",
        },
        "golden": {
            "sha256": GOLDEN_SHA256, "cases": GOLDEN_CASES,
            "suite": "SYNTHETIC_AGENT_SAFETY",
        },
        "evaluation": {
            "method": "DETERMINISTIC_REGRESSION",
            "test_command": "python -m unittest tools.test_agent_change_governance -v",
            "external_review_state": "NOT_VERIFIED",
            "unseen_data_verified": False,
        },
        "rollback": {
            "target_base_sha": BASE, "strategy": "REVIEWED_REVERT_PR",
            "verification_command": "python -m unittest tools.test_agent_change_governance -v",
        },
        "cost": {
            "currency": "USD", "measurement": "UNKNOWN",
            "usd": None, "receipt_sha256": None,
            "outcome_per_dollar": None,
        },
        "release_claims": {
            "policy_id": "SPORTSEDGE_STRICT_V21_V22_20261115_R1",
            "production_ready": False,
            "external_owner_approval_verified": False,
            "source_authenticated": False,
            "model_release_certified": False,
            "official_counted": 0,
            "approved_stake_u": 0,
        },
    }


def to_raw(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


class GovernanceTests(unittest.TestCase):
    def evaluate(self, doc=None, paths=None):
        if paths is None:
            paths = PROTECTED + ["docs/README.md"]
        return validate_manifest(
            None if doc is None else to_raw(doc),
            pr_number=45, base_commit=BASE, changed_paths=paths)

    def test_frozen_golden_safety_suite_is_pinned_and_regression_clean(self):
        report = golden_regression(GOLDEN_PATH.read_bytes())
        self.assertEqual(report["cases"], 9)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["dataset_sha256"], GOLDEN_SHA256)
        self.assertEqual(report["approved_stake_u"], 0)

    def test_original_golden_byte_mutation_rejected(self):
        raw = GOLDEN_PATH.read_bytes()
        with self.assertRaisesRegex(GovernanceError, "GOLDEN_DATASET_HASH_DRIFT"):
            golden_regression(raw + b" ")

    def test_golden_safety_candidate_is_exact_and_fail_closed(self):
        safe = dict(state="PAPER_0U", official=False,
                    stake_u=0, source_authenticated=False)
        self.assertEqual(classify_candidate(safe), "ALLOW_RESEARCH")
        for modification in (
            {"official": True}, {"stake_u": 1},
            {"source_authenticated": True}, {"state": "CERTIFIED"},
            {"stake_u": False}, {"stake_u": "0"},
            {"source_authenticated": 0}, {"official": 0},
            {"approved_stake_u": 0},
        ):
            with self.subTest(modification=modification):
                self.assertEqual(classify_candidate({**safe, **modification}),
                                 "BLOCK")
        safe.pop("source_authenticated")
        self.assertEqual(classify_candidate(safe), "BLOCK")

    def test_low_risk_doc_change_needs_no_manifest_but_no_promotion(self):
        result = self.evaluate(paths=["docs/README.md", "README.md"])
        self.assertEqual(result["state"], "PASS_NO_PROTECTED_DIFF")
        self.assertFalse(result["external_owner_approval_verified"])
        self.assertFalse(result["model_release_certified"])
        self.assertEqual(result["approved_stake_u"], 0)

    def test_sensitive_paths_require_manifest(self):
        for p in (
            "RISK_POLICY.md", "models/nfl/run_it_model.py",
            "research/freezes/code_pins.json", "research/risk/strict_v21_v22.py",
            "sportsedge/odds/card_gate.py", ".github/workflows/release.yml",
            "sportsedge_v5.py", "engine/sportsedge_v5.py",
            "sportsedge/markets/allmarkets_research.py",
            "sportsedge/markets/projection_distribution.py",
            "sportsedge/validation/forward_acceptance.py",
            "research/edge/forward_holdout_contract.py",
            "AGENTS.md", "CLAUDE.md",
            "tools/agent_change_governance.py",
            "research/ai_governance/golden_agent_safety_v1.json",
        ):
            with self.subTest(path=p):
                self.assertTrue(is_protected(p))
                with self.assertRaisesRegex(GovernanceError, "MANIFEST_REQUIRED"):
                    self.evaluate(paths=[p])

    def test_trusted_manifest_accepts_a_declared_review_not_certification(self):
        report = self.evaluate(base_manifest())
        self.assertEqual(report["state"], "PASS_DECLARED_REVIEW_ONLY")
        self.assertEqual(report["protected_paths"], PROTECTED)
        self.assertFalse(report["external_owner_approval_verified"])
        self.assertFalse(report["model_release_certified"])
        self.assertEqual(report["official_counted"], 0)
        self.assertEqual(report["approved_stake_u"], 0)

    def test_pr_or_base_mismatch_refused(self):
        for change in ({"pr_number":46}, {"base_commit":HEAD}):
            d = base_manifest()
            d.update(change)
            with self.assertRaisesRegex(GovernanceError, "PR_OR_BASE_MISMATCH"):
                self.evaluate(d)

    def test_changed_path_census_must_be_exact(self):
        for paths in ([], ["RISK_POLICY.md"], ["RISK_POLICY.md"] * 2,
                      ["models/cbb/torvik_point_in_time_baseline.py",
                       "RISK_POLICY.md", "extra"]):
            d = base_manifest(paths)
            with self.assertRaisesRegex(GovernanceError, "PATH_CENSUS_MISMATCH"):
                self.evaluate(d)

    def test_incoming_paths_reject_duplicate_absolute_traversal_or_newline(self):
        for changed in (
            ["RISK_POLICY.md", "RISK_POLICY.md"],
            ["/absolute/risk.py"],
            ["models/../RISK_POLICY.md"],
            ["models/cbb/x\\nreadme.py".replace("\\n", "\n")],
            ["models\\\\nfl.py"],
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(GovernanceError):
                    self.evaluate(base_manifest(), paths=changed)

    def test_permissions_cannot_self_grant_merge_secrets_or_release(self):
        changes = [
            {"role":"OWNER"}, {"repo_write":"MAIN"},
            {"secrets_read":True}, {"production_deploy":True},
            {"market_release":True}, {"merge_rights":"SELF_APPROVE"},
        ]
        for change in changes:
            with self.subTest(change=change):
                d = base_manifest()
                d["permissions"].update(change)
                with self.assertRaisesRegex(GovernanceError, "LEAST_PRIVILEGE"):
                    self.evaluate(d)

    def test_exact_types_for_boolean_permission_and_numeric_golden_fields(self):
        for key in ("secrets_read", "production_deploy", "market_release"):
            d = base_manifest()
            d["permissions"][key] = 0
            with self.assertRaisesRegex(GovernanceError, "LEAST_PRIVILEGE"):
                self.evaluate(d)
        d = base_manifest()
        d["golden"]["cases"] = 9.0
        with self.assertRaisesRegex(GovernanceError, "GOLDEN_PIN"):
            self.evaluate(d)
        d = base_manifest()
        d["release_claims"]["official_counted"] = False
        with self.assertRaisesRegex(GovernanceError, "PROMOTION_CLAIM"):
            self.evaluate(d)

    def test_owner_approval_or_external_eval_cannot_be_asserted(self):
        for field, value in (
            ("external_review_state", "APPROVED"),
            ("unseen_data_verified", True),
        ):
            d = base_manifest()
            d["evaluation"][field] = value
            with self.assertRaisesRegex(GovernanceError, "SELF_CERTIFICATION"):
                self.evaluate(d)
        d = base_manifest()
        d["release_claims"]["external_owner_approval_verified"] = True
        with self.assertRaisesRegex(GovernanceError, "PROMOTION_CLAIM"):
            self.evaluate(d)

    def test_fake_profit_stake_pit_certification_claims_rejected(self):
        for name, value in (
            ("production_ready", True), ("source_authenticated", True),
            ("model_release_certified", True), ("official_counted", 1),
            ("approved_stake_u", 1), ("approved_stake_u", False),
        ):
            d = base_manifest()
            d["release_claims"][name] = value
            with self.assertRaisesRegex(GovernanceError, "PROMOTION_CLAIM"):
                self.evaluate(d)

    def test_golden_hash_and_case_count_must_match_frozen_fixture(self):
        for name, value in (
            ("sha256", "sha256:" + "0"*64), ("cases", 8),
            ("suite", "HISTORICAL_REAL_ODDS"),
        ):
            d = base_manifest()
            d["golden"][name] = value
            with self.assertRaisesRegex(GovernanceError, "GOLDEN_PIN_INVALID"):
                self.evaluate(d)

    def test_baseline_unknown_is_not_silent_zero(self):
        d = base_manifest()
        d["baseline"]["before"] = "0"
        with self.assertRaisesRegex(GovernanceError, "UNKNOWN_BASELINE"):
            self.evaluate(d)
        d = base_manifest()
        d["baseline"]["source_state"] = "SELF_REPORTED"
        d["baseline"]["before"] = "0.25"
        self.assertEqual(self.evaluate(d)["state"], "PASS_DECLARED_REVIEW_ONLY")

    def test_cost_unknown_is_not_free_and_measured_requires_receipt(self):
        d = base_manifest()
        d["cost"]["usd"] = "0"
        with self.assertRaisesRegex(GovernanceError, "UNKNOWN_COST"):
            self.evaluate(d)
        d = base_manifest()
        d["cost"]["measurement"] = "SELF_REPORTED"
        d["cost"]["usd"] = "1.25"
        d["cost"]["receipt_sha256"] = "sha256:" + "c"*64
        self.assertEqual(self.evaluate(d)["state"], "PASS_DECLARED_REVIEW_ONLY")
        for bad in ("-1", "NaN", "1e100", "0.00001", "", 0, True):
            with self.subTest(bad=bad):
                d["cost"]["usd"] = bad
                with self.assertRaises(GovernanceError):
                    self.evaluate(d)
        d = base_manifest()
        d["cost"]["outcome_per_dollar"] = 999
        with self.assertRaisesRegex(GovernanceError, "UNSUPPORTED_COST"):
            self.evaluate(d)

    def test_rollback_must_be_linked_to_exact_base_and_have_unit_test(self):
        d = base_manifest()
        d["rollback"]["target_base_sha"] = HEAD
        with self.assertRaisesRegex(GovernanceError, "ROLLBACK_BASE"):
            self.evaluate(d)
        d = base_manifest()
        d["rollback"]["verification_command"] = "echo done"
        with self.assertRaisesRegex(GovernanceError, "ROLLBACK_VERIFICATION"):
            self.evaluate(d)

    def test_spec_and_assumptions_required(self):
        for field,value in (
            ("assumptions", []), ("change_summary", ""),
            ("ticket_url", "https://fake.example/issues/5"),
            ("agent_identity", ""),
        ):
            d = base_manifest()
            d[field] = value
            with self.assertRaises(GovernanceError):
                self.evaluate(d)

    def test_duplicate_json_fields_and_nonfinite_numbers_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.assertRaises(GovernanceError):
                parse(raw)

    def test_stray_manifest_field_rejected(self):
        d = base_manifest()
        d["agent_may_approve_bets"] = True
        with self.assertRaisesRegex(GovernanceError, "FIELDS_MISMATCH"):
            self.evaluate(d)

    def test_git_diff_does_not_execute_head_and_requires_manifest(self):
        calls = []
        def fake_git(repo, args):
            calls.append(args)
            if args[0] == "diff":
                return b"RISK_POLICY.md\x00"
            if args[0] == "show":
                return to_raw(base_manifest(paths=["RISK_POLICY.md"]))
            raise AssertionError(args)
        with patch("tools.agent_change_governance._git", side_effect=fake_git):
            out=inspect_pr(Path("/tmp"), base_commit=BASE, head_commit=HEAD, pr_number=45)
        self.assertEqual(out["state"], "PASS_DECLARED_REVIEW_ONLY")
        self.assertEqual(calls[0], [
            "diff", "--no-renames", "--name-only", "-z", BASE, HEAD
        ])
        self.assertEqual(calls[1], [
            "show", f"{HEAD}:docs/governance/changes/pr-45.json"
        ])

    def test_unprotected_diff_never_reads_manifest(self):
        calls=[]
        def fake_git(repo,args):
            calls.append(args)
            return b"docs/research/notes.md\x00"
        with patch("tools.agent_change_governance._git", side_effect=fake_git):
            out=inspect_pr(Path("/tmp"),base_commit=BASE,head_commit=HEAD,pr_number=45)
        self.assertEqual(out["state"], "PASS_NO_PROTECTED_DIFF")
        self.assertEqual(len(calls),1)

    def test_first_governed_pr_manifest_self_check(self):
        manifest_path = GOLDEN_PATH.parents[2] / (
            "docs/governance/changes/pr-268.json"
        )
        d = parse(manifest_path.read_bytes())
        changed = [
            ".github/workflows/agent-high-risk-governance.yml",
            "research/ai_governance/golden_agent_safety_v1.json",
            "tools/agent_change_governance.py",
            "tools/test_agent_change_governance.py",
            "docs/governance/changes/pr-268.json",
            "docs/governance/TRUSTED_AGENT_CHANGE_GATE.md",
        ]
        out = validate_manifest(
            to_raw(d), pr_number=268,
            base_commit=d["base_commit"], changed_paths=changed)
        self.assertEqual(out["state"], "PASS_DECLARED_REVIEW_ONLY")
        self.assertEqual(out["protected_paths"], d["protected_paths"])
        self.assertEqual(out["official_counted"], 0)

    def test_missing_head_manifest_fails_closed(self):
        def fake_git(repo,args):
            if args[0] == "diff":
                return b"models/nfl/weights.py\x00"
            raise GovernanceError("GIT_READ_OR_REVISION_FAILED")
        with patch("tools.agent_change_governance._git",side_effect=fake_git):
            with self.assertRaisesRegex(GovernanceError, "MANIFEST_REQUIRED"):
                inspect_pr(Path("/tmp"),base_commit=BASE,head_commit=HEAD,pr_number=45)

    def test_head_same_as_base_refused(self):
        with self.assertRaisesRegex(GovernanceError, "HEAD_EQUALS_BASE"):
            inspect_pr(Path("/tmp"),base_commit=BASE,head_commit=BASE,pr_number=45)


if __name__ == "__main__":
    unittest.main()
