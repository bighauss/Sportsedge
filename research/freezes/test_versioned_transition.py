"""Synthetic fail-closed regressions for versioned CBB identity freeze."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from verify_code_freezes import FreezeViolation
from verify_versioned_transition import (
    checked_manifest, check_provenance, BASELINE_BLOB, CANDIDATE_BLOB,
    LEGACY, TRANSITION, FROZEN_PATH,
)

class TransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = LEGACY.read_bytes()
        cls.legacy = json.loads(cls.raw)
        cls.transition = json.loads(TRANSITION.read_text())

    def test_preserves_original_freeze_and_engine(self):
        original = copy.deepcopy(self.legacy)
        candidate = checked_manifest(self.legacy, self.transition, self.raw)
        self.assertEqual(self.legacy, original)
        self.assertEqual(self.legacy['sports']['CBB']['sources'][FROZEN_PATH], BASELINE_BLOB)
        self.assertEqual(candidate['sports']['CBB']['sources'][FROZEN_PATH], CANDIDATE_BLOB)
        self.assertEqual(candidate['frozen_engine'], original['frozen_engine'])

    def test_rejects_mutated_historical_manifest(self):
        altered = self.raw + b' '
        with self.assertRaisesRegex(FreezeViolation, 'ORIGINAL_FREEZE_MANIFEST_MODIFIED'):
            checked_manifest(self.legacy, self.transition, altered)

    def test_rejects_unapproved_transition_or_stakes(self):
        for field, value in [('approved_candidate_git_blob_sha1', '0'*40),
                             ('approved_stake_u', 1),
                             ('owner_decision', 'PRODUCTION'),
                             ('change_pr', 999)]:
            t = dict(self.transition); t[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(FreezeViolation, 'UNAUTHORIZED'):
                checked_manifest(self.legacy, t, self.raw)

    def test_no_git_history_refused(self):
        with patch('verify_versioned_transition._git',
                   side_effect=FreezeViolation('UNVERIFIABLE_GIT_PROVENANCE')):
            with self.assertRaisesRegex(FreezeViolation, 'UNVERIFIABLE_GIT_PROVENANCE'):
                check_provenance(Path('.'))

    def test_wrong_original_bytes_refused(self):
        with patch('verify_versioned_transition._git', return_value=b'wrong'):
            with self.assertRaisesRegex(FreezeViolation, 'HISTORICAL_BASELINE_BYTES_MISMATCH'):
                check_provenance(Path('.'))

if __name__ == '__main__':
    unittest.main()
