"""Round-2 (2026-11-28) owner-approved MLB/NBA identities: fail-closed regressions."""
import copy
import json
import unittest
from pathlib import Path

from verify_code_freezes import FreezeViolation
from verify_versioned_transition import (
    LEGACY, TRANSITION, TRANSITION_2, TRANSITIONS, TRANSITIONS_2,
    apply_approved_transitions, checked_manifest, checked_round2, run,
)


class Round2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = LEGACY.read_bytes()
        cls.legacy = json.loads(cls.raw)
        cls.round1 = checked_manifest(cls.legacy, json.loads(TRANSITION.read_text()), cls.raw)
        cls.t2 = json.loads(TRANSITION_2.read_text())

    def test_chains_on_round1_and_leaves_everything_else(self):
        out = checked_round2(self.round1, self.t2)
        for sport, path, old, new, *_ in TRANSITIONS_2:
            self.assertEqual(self.round1["sports"][sport]["sources"][path], old)
            self.assertEqual(out["sports"][sport]["sources"][path], new)
        self.assertEqual(out["frozen_engine"], self.legacy["frozen_engine"])
        self.assertEqual(out["risk_contract"], self.legacy["risk_contract"])
        self.assertEqual(out["sports"]["CBB"], self.round1["sports"]["CBB"])

    def test_cannot_skip_round1(self):
        with self.assertRaisesRegex(FreezeViolation, "ROUND1_CANDIDATE_PIN_INVALID"):
            checked_round2(self.legacy, self.t2)

    def test_rejects_tampered_round2_record(self):
        for field, value in (("approved_stake_u", 1), ("official_counted", 1),
                             ("owner_decision", "PRODUCTION"), ("frozen_engine_v5_unchanged", False),
                             ("owner_decision_record", ""), ("prior_transition", "other.json")):
            with self.subTest(field=field):
                t = copy.deepcopy(self.t2); t[field] = value
                with self.assertRaises(FreezeViolation):
                    checked_round2(self.round1, t)

    def test_rejects_extra_or_altered_candidate(self):
        t = copy.deepcopy(self.t2)
        t["candidates"][0]["approved_candidate_git_blob_sha1"] = "0" * 40
        with self.assertRaises(FreezeViolation):
            checked_round2(self.round1, t)
        t = copy.deepcopy(self.t2)
        t["candidates"].append(dict(t["candidates"][0], sport="NFL"))
        with self.assertRaises(FreezeViolation):
            checked_round2(self.round1, t)

    def test_report_view_never_rewrites_unexpected_pins(self):
        f = copy.deepcopy(self.legacy)
        f["sports"]["MLB"]["sources"]["models/mlb/sportsedge_mlb_model.py"] = "1" * 40
        out = apply_approved_transitions(f)
        self.assertEqual(out["sports"]["MLB"]["sources"]["models/mlb/sportsedge_mlb_model.py"], "1" * 40)
        self.assertEqual(json.loads(self.raw), self.legacy)

    def test_full_run_on_repo(self):
        try:
            r = run()
        except FreezeViolation as e:
            if str(e).startswith("UNVERIFIABLE_GIT_PROVENANCE"):
                self.skipTest("shallow clone: provenance needs full history (CI uses fetch-depth 0)")
            raise
        self.assertEqual(r["status"], "VERSIONED_CODE_IDENTITY_ONLY_PAPER_0U")
        self.assertEqual(len(r["candidate_changes"]), len(TRANSITIONS) + len(TRANSITIONS_2))


if __name__ == "__main__":
    unittest.main()
