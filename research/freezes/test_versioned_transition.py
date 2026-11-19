"""Synthetic fail-closed regressions for three versioned research code identities."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from verify_code_freezes import FreezeViolation
from verify_versioned_transition import (
    checked_manifest, check_provenance, LEGACY, TRANSITION, TRANSITIONS,
)

class TransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = LEGACY.read_bytes()
        cls.legacy = json.loads(cls.raw)
        cls.transition = json.loads(TRANSITION.read_text())

    def test_preserves_original_freeze_and_all_unrelated_pins(self):
        original = copy.deepcopy(self.legacy)
        candidate = checked_manifest(self.legacy, self.transition, self.raw)
        self.assertEqual(self.legacy, original)
        for sport, path, old, new, commit, pr in TRANSITIONS:
            self.assertEqual(self.legacy['sports'][sport]['sources'][path], old)
            self.assertEqual(candidate['sports'][sport]['sources'][path], new)
        for sport, values in original['sports'].items():
            for path, blob in values['sources'].items():
                if (sport, path) not in [(x[0], x[1]) for x in TRANSITIONS]:
                    self.assertEqual(candidate['sports'][sport]['sources'][path], blob)
        self.assertEqual(candidate['frozen_engine'], original['frozen_engine'])
        self.assertEqual(candidate['risk_contract'], original['risk_contract'])

    def test_rejects_mutated_historical_manifest(self):
        with self.assertRaisesRegex(FreezeViolation, 'ORIGINAL_FREEZE_MANIFEST_MODIFIED'):
            checked_manifest(self.legacy, self.transition, self.raw + b' ')

    def test_rejects_unapproved_candidate_and_stakes(self):
        for field, value in [('approved_stake_u', 1),
                             ('owner_decision', 'PRODUCTION')]:
            t = copy.deepcopy(self.transition); t[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(FreezeViolation, 'UNAUTHORIZED'):
                checked_manifest(self.legacy, t, self.raw)
        for i in range(len(TRANSITIONS)):
            t = copy.deepcopy(self.transition)
            t['candidates'][i]['approved_candidate_git_blob_sha1'] = '0'*40
            with self.subTest(sport=TRANSITIONS[i][0]), self.assertRaisesRegex(FreezeViolation, 'UNAUTHORIZED'):
                checked_manifest(self.legacy, t, self.raw)

    def test_missing_git_history_refused(self):
        with patch('verify_versioned_transition._git',
                   side_effect=FreezeViolation('UNVERIFIABLE_GIT_PROVENANCE')):
            with self.assertRaisesRegex(FreezeViolation, 'UNVERIFIABLE_GIT_PROVENANCE'):
                check_provenance(Path('.'))

    def test_wrong_original_bytes_refused(self):
        with patch('verify_versioned_transition._git', return_value=b'wrong'):
            with self.assertRaisesRegex(FreezeViolation, 'HISTORICAL_BASELINE_BYTES_MISMATCH'):
                check_provenance(Path('.'))


    def test_first_introducing_commit_requires_original_in_every_parent(self):
        """Adversarial proof: a later descendant and ambiguous merge fail."""
        from verify_versioned_transition import BASELINE_COMMIT
        sport, path, old, new, commit, pr = TRANSITIONS[0]
        with patch('verify_versioned_transition.TRANSITIONS',
                   ((sport, path, old, new, commit, pr),)):
            def fake_hash(data):
                return {b'old': old, b'new': new}.get(data, 'unrecognized')
            def fixture(parent_contents):
                parents = tuple(parent_contents)
                def fake_git(repo, *args):
                    if args[:2] == ('rev-list', '--parents'):
                        return (commit + ' ' + ' '.join(parents)).encode('ascii')
                    if args[0] == 'show':
                        ref = args[1].split(':', 1)[0]
                        if ref == BASELINE_COMMIT:
                            return b'old'
                        if ref == commit:
                            return b'new'
                        return parent_contents[ref]
                    if args[:2] == ('merge-base', '--is-ancestor'):
                        return b''
                    raise AssertionError('unexpected git operation: ' + str(args))
                return fake_git
            with patch('verify_versioned_transition.git_blob_digest', side_effect=fake_hash):
                with patch('verify_versioned_transition._git', side_effect=fixture({'parent1':b'old'})):
                    check_provenance(Path('.'))
                with patch('verify_versioned_transition._git', side_effect=fixture({'parent1':b'old','parent2':b'old'})):
                    check_provenance(Path('.'))
                with patch('verify_versioned_transition._git', side_effect=fixture({'parent1':b'new'})):
                    with self.assertRaisesRegex(FreezeViolation, 'NOT_FIRST_INTRODUCING_COMMIT'):
                        check_provenance(Path('.'))
                with patch('verify_versioned_transition._git', side_effect=fixture({'parent1':b'old','parent2':b'new'})):
                    with self.assertRaisesRegex(FreezeViolation, 'NOT_FIRST_INTRODUCING_COMMIT'):
                        check_provenance(Path('.'))
                with patch('verify_versioned_transition._git', side_effect=fixture({})):
                    with self.assertRaisesRegex(FreezeViolation, 'PARENTS_UNVERIFIABLE'):
                        check_provenance(Path('.'))

if __name__ == '__main__':
    unittest.main()
