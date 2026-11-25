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

class GovernanceRecordStrictnessAndPreimportTests(unittest.TestCase):
    """Owner review of #535: strict types for release claims, records bound to the
    introducing commit, and the freeze helper verified before it is imported."""

    REL = 'docs/governance/changes/pr-446.json'
    MODEL = 'models/mlb/sportsedge_mlb_model.py'
    COMMIT = 'b73874a2ecf8d558780bacf6b636b70e409f2cb4'

    def _check(self, mutate=None, committed=None):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        import verify_versioned_transition as v
        original = (v.ROOT / self.REL).read_bytes()
        doc = json.loads(original)
        if mutate:
            mutate(doc)
        raw = json.dumps(doc, indent=2).encode() + b'\n' if mutate else original
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td) / self.REL
            rec.parent.mkdir(parents=True)
            rec.write_bytes(raw)
            # The introducing commit "holds" the same bytes unless told otherwise, so
            # these cases isolate the type/content checks from the binding check.
            with patch('verify_versioned_transition._git',
                       return_value=raw if committed is None else committed):
                v.check_governance_record(Path(td), self.REL, 446, self.MODEL, self.COMMIT)

    def test_real_records_pass_and_are_bound_to_introducing_commits(self):
        import verify_versioned_transition as v
        for sport, path, old, new, commit, pr in v.TRANSITIONS:
            v.check_governance_record(v.ROOT, 'docs/governance/changes/pr-%d.json' % pr, pr, path, commit)
        for hop in v.EXPECTED_ADDITIONAL_CANDIDATES:
            v.check_governance_record(v.ROOT, hop['governance_record'], hop['change_pr'],
                                      hop['path'], hop['first_introducing_commit'])

    def test_malformed_types_and_false_release_claims_rejected(self):
        from verify_code_freezes import FreezeViolation
        def claim(k, val):
            return lambda d: d['release_claims'].__setitem__(k, val)
        cases = {
            'official_counted_false_not_int': claim('official_counted', False),
            'approved_stake_float': claim('approved_stake_u', 0.0),
            'approved_stake_string': claim('approved_stake_u', '0'),
            'production_ready_true': claim('production_ready', True),
            'model_release_certified_zero': claim('model_release_certified', 0),
            'source_authenticated_string': claim('source_authenticated', 'false'),
            'owner_approval_true': claim('external_owner_approval_verified', True),
            'policy_changed': claim('policy_id', 'LAX'),
            'extra_claim': claim('extra', 0),
            'missing_claim': lambda d: d['release_claims'].pop('production_ready'),
            'claims_not_dict': lambda d: d.__setitem__('release_claims', []),
            'pr_number_string': lambda d: d.__setitem__('pr_number', '446'),
            'pr_number_bool': lambda d: d.__setitem__('pr_number', True),
            'protected_paths_string': lambda d: d.__setitem__('protected_paths', self.MODEL),
            'schema_changed': lambda d: d.__setitem__('schema', 'other'),
        }
        for name, mutate in cases.items():
            with self.subTest(name), self.assertRaisesRegex(FreezeViolation, 'GOVERNANCE_RECORD_INVALID'):
                self._check(mutate)

    def test_record_rewritten_after_introducing_commit_rejected(self):
        from verify_code_freezes import FreezeViolation
        with self.assertRaisesRegex(FreezeViolation, 'GOVERNANCE_RECORD_NOT_BOUND_TO_INTRODUCING_COMMIT'):
            self._check(committed=b'{"different": "bytes"}\n')

    def test_record_path_must_match_change_pr(self):
        from pathlib import Path
        from verify_code_freezes import FreezeViolation
        import verify_versioned_transition as v
        with self.assertRaisesRegex(FreezeViolation, 'GOVERNANCE_RECORD_INVALID_PATH'):
            v.check_governance_record(v.ROOT, 'docs/governance/changes/pr-293.json', 446,
                                      self.MODEL, self.COMMIT)

    def test_tampered_freeze_helper_is_refused_before_import(self):
        import subprocess, sys, tempfile
        from pathlib import Path
        here = Path(__file__).resolve().parent
        src = here / 'verify_code_freezes.py'
        bak = src.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            sentinel = Path(td) / 'HELPER_EXECUTED'
            try:
                src.write_bytes(bak + ('\nopen(%r, "w").write("x")\n' % str(sentinel)).encode())
                r = subprocess.run([sys.executable, str(here / 'verify_versioned_transition.py')],
                                   capture_output=True, text=True)
                imp = subprocess.run([sys.executable, '-c', 'import verify_versioned_transition'],
                                     cwd=str(here), capture_output=True, text=True)
            finally:
                src.write_bytes(bak)
            self.assertFalse(sentinel.exists(), 'tampered helper code must never run')
        self.assertEqual(r.returncode, 1)
        self.assertIn('CODE_FREEZE_VERIFIER_TAMPERED_PREIMPORT', r.stdout)
        self.assertNotEqual(imp.returncode, 0)
        self.assertIn('CODE_FREEZE_VERIFIER_TAMPERED_PREIMPORT', imp.stderr)


if __name__ == '__main__':
    unittest.main()


class AdditionalHopAndIntegrityTests(unittest.TestCase):
    """Unified multi-hop gate: both MLB and NBA hops, plus fail-closed integrity."""

    def test_run_accepts_mlb_and_nba_hops_and_all_seven_pins(self):
        from verify_versioned_transition import run
        report = run()
        self.assertEqual(report['status'], 'VERSIONED_CODE_IDENTITY_ONLY_PAPER_0U')
        self.assertEqual(sorted(report['sports']), ['CBB', 'CFB', 'MLB', 'NBA', 'NFL', 'NHL', 'PGA'])
        self.assertTrue(report['legacy_manifest_unchanged'])
        self.assertTrue(report['nov18_transition_manifest_unchanged'])
        self.assertTrue(report['code_freeze_verifier_unmodified'])
        sports = {h['sport']: h for h in report['additional_hops']}
        self.assertEqual(sports['MLB']['candidate_git_blob_sha1'],
                         '30c6cb3355ac5f6b6cbb018729c4fdc41255e057')
        self.assertEqual(sports['NBA']['candidate_git_blob_sha1'],
                         'b353de86445188288cab4050f6cae13eee76bff6')
        self.assertEqual(sports['NBA']['introducing_commit'],
                         '8537ae481a34fa6972a67389a6ac75172ee1f59c')

    def test_main_exits_zero_on_clean_tree(self):
        from verify_versioned_transition import main
        self.assertEqual(main([]), 0)


class AdversarialNonzeroExitTests(unittest.TestCase):
    """Each integrity failure must be a non-zero process exit, not a reported flag."""

    @classmethod
    def setUpClass(cls):
        import sys
        from pathlib import Path
        from verify_versioned_transition import ROOT, HOPS, LEGACY
        cls.ROOT, cls.HOPS, cls.LEGACY = ROOT, HOPS, LEGACY
        cls.exe = sys.executable
        cls.script = str(Path(__file__).with_name('verify_versioned_transition.py'))

    def _run(self, args=(), cwd=None):
        import subprocess
        return subprocess.run([self.exe, self.script, *args], cwd=cwd or self.ROOT,
                              capture_output=True, text=True)

    def test_edited_nov15_freeze_exits_nonzero(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'frozen_baselines_20261115.json'
            p.write_bytes(self.LEGACY.read_bytes() + b' ')
            r = self._run(['--legacy', str(p)])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('ORIGINAL_FREEZE_MANIFEST_MODIFIED', r.stdout + r.stderr)

    def test_unknown_extra_hop_exits_nonzero(self):
        import copy, json, tempfile
        from pathlib import Path
        hops = json.loads(self.HOPS.read_text())
        extra = copy.deepcopy(hops['candidates'][0])
        extra['sport'] = 'CFB'
        extra['path'] = 'models/cfb/sportsedge_cfb_model.py'
        hops['candidates'].append(extra)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'hops.json'
            p.write_text(json.dumps(hops, indent=2) + '\n')
            r = self._run(['--hops', str(p)])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('UNAUTHORIZED_OR_UNVERSIONED_CODE_TRANSITION', r.stdout + r.stderr)

    def test_edited_verifier_exits_nonzero(self):
        import subprocess
        from pathlib import Path
        tmp = Path(self.script).with_name('_tmp_tampered_verify_versioned_transition.py')
        try:
            tmp.write_bytes(Path(self.script).read_bytes() + b'\n# tamper\n')
            r = subprocess.run([self.exe, str(tmp)], cwd=str(self.ROOT),
                               capture_output=True, text=True)
        finally:
            tmp.unlink(missing_ok=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('VERSIONED_TRANSITION_VERIFIER_TAMPERED', r.stdout + r.stderr)

    def test_edited_code_freezes_verifier_exits_nonzero(self):
        """The owner's finding: a hash mismatch must fail the process, not just be reported."""
        import subprocess, tempfile
        from pathlib import Path
        from verify_code_freezes import git_blob_digest
        src = Path(self.script).with_name('verify_code_freezes.py')
        bak = src.read_bytes()
        self.assertEqual(git_blob_digest(bak),
                         '27d2b51d27d4b7da6f22dad31d55257541af8f67')
        try:
            src.write_bytes(bak + b'\n# tamper\n')
            r = subprocess.run([self.exe, self.script], cwd=str(self.ROOT),
                               capture_output=True, text=True)
        finally:
            src.write_bytes(bak)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('CODE_FREEZE_VERIFIER_TAMPERED', r.stdout + r.stderr)
        self.assertEqual(git_blob_digest(src.read_bytes()),
                         '27d2b51d27d4b7da6f22dad31d55257541af8f67')

    def test_tampered_blob_exits_nonzero(self):
        import subprocess, tempfile
        from pathlib import Path
        td = tempfile.mkdtemp(prefix='wt-tamper-blob-')
        try:
            subprocess.check_call(['git', '-C', str(self.ROOT), 'worktree', 'add', '--detach',
                                   '-q', td, 'HEAD'])
            # The worktree is at HEAD which may not yet include this working tree change;
            # copy the current verifier + hops into the worktree so we test pin matching
            # against the unified hops, then tamper the live MLB model.
            import shutil
            for rel in ('research/freezes/verify_versioned_transition.py',
                        'research/freezes/code_identity_transitions_20261125.json'):
                shutil.copy2(self.ROOT / rel, Path(td) / rel)
            model = Path(td) / 'models/mlb/sportsedge_mlb_model.py'
            model.write_bytes(model.read_bytes() + b'\n# tamper\n')
            # After copying the verifier, its self-hash no longer matches the hops file
            # unless we also re-hash. Recompute hops self-hash so the only failure is the blob.
            import hashlib, json
            body = (Path(td) / 'research/freezes/verify_versioned_transition.py').read_bytes()
            digest = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            hops_p = Path(td) / 'research/freezes/code_identity_transitions_20261125.json'
            hops = json.loads(hops_p.read_text())
            hops['verify_versioned_transition_git_blob_sha1'] = digest
            hops_p.write_text(json.dumps(hops, indent=2) + '\n')
            # EXPECTED in the copied verifier still exact-matches except the self-hash, which
            # is filled from __file__. Good.
            r = subprocess.run([self.exe, str(Path(td) / 'research/freezes/verify_versioned_transition.py')],
                               cwd=td, capture_output=True, text=True)
        finally:
            subprocess.call(['git', '-C', str(self.ROOT), 'worktree', 'remove', '--force', td],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('CODE_CHANGED_SINCE_FREEZE:models/mlb/sportsedge_mlb_model.py',
                      r.stdout + r.stderr)

    def test_missing_governance_record_exits_nonzero(self):
        import subprocess, tempfile, shutil, hashlib, json
        from pathlib import Path
        td = tempfile.mkdtemp(prefix='wt-missing-gov-')
        try:
            subprocess.check_call(['git', '-C', str(self.ROOT), 'worktree', 'add', '--detach',
                                   '-q', td, 'HEAD'])
            for rel in ('research/freezes/verify_versioned_transition.py',
                        'research/freezes/code_identity_transitions_20261125.json'):
                shutil.copy2(self.ROOT / rel, Path(td) / rel)
            body = (Path(td) / 'research/freezes/verify_versioned_transition.py').read_bytes()
            digest = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            hops_p = Path(td) / 'research/freezes/code_identity_transitions_20261125.json'
            hops = json.loads(hops_p.read_text())
            hops['verify_versioned_transition_git_blob_sha1'] = digest
            hops_p.write_text(json.dumps(hops, indent=2) + '\n')
            (Path(td) / 'docs/governance/changes/pr-446.json').unlink()
            r = subprocess.run([self.exe, str(Path(td) / 'research/freezes/verify_versioned_transition.py')],
                               cwd=td, capture_output=True, text=True)
        finally:
            subprocess.call(['git', '-C', str(self.ROOT), 'worktree', 'remove', '--force', td],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('GOVERNANCE_RECORD_MISSING', r.stdout + r.stderr)

    def test_wrong_ancestry_exits_nonzero(self):
        import subprocess
        code = r'''
import sys
from pathlib import Path
from unittest.mock import patch
from verify_code_freezes import FreezeViolation
import verify_versioned_transition as v
hop = v.EXPECTED_ADDITIONAL_CANDIDATES[0]
prior, new = hop["prior_approved_candidate_git_blob_sha1"], hop["approved_candidate_git_blob_sha1"]
commit = hop["first_introducing_commit"]
# Commit has the new blob; prior introducing commit has the prior blob;
# the sole parent holds the NEW blob — so this is not the first introducing commit.
prior_commit = hop["prior_first_introducing_commit"]
def fake_git(repo, *args):
    if args[:2] == ("rev-list", "--parents"):
        return (commit + " parent1").encode()
    if args[0] == "show":
        ref = args[1].split(":", 1)[0]
        if ref == commit:
            return b"new"
        if ref == prior_commit:
            return b"prior"
        return b"new"  # parent also new
    if args[:2] == ("merge-base", "--is-ancestor"):
        return b""
    raise AssertionError(args)
def fake_hash(data):
    return {b"new": new, b"prior": prior}.get(data, "unrecognized")
try:
    with patch("verify_versioned_transition.git_blob_digest", side_effect=fake_hash), \
         patch("verify_versioned_transition._git", side_effect=fake_git):
        v.check_hop_provenance(Path("."), hop)
except FreezeViolation as e:
    print(str(e))
    sys.exit(1)
print("UNEXPECTED_PASS")
sys.exit(0)
'''
        r = subprocess.run([self.exe, '-c', code], cwd=str(self.ROOT / 'research/freezes'),
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('NOT_FIRST_INTRODUCING_COMMIT', r.stdout + r.stderr)
