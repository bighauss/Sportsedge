"""Adversarial tests for the independent, base-pinned freeze integrity gate.

Synthetic git repositories model a trusted BASE commit and an untrusted PR HEAD.
The gate under test plays the role of the BASE code run by pull_request_target.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import integrity_gate as G  # noqa: E402

REPO_ROOT = HERE.parents[1]
REQUIRED_PINNED = {
    'research/freezes/frozen_baselines_20261115.json',
    'research/freezes/code_identity_transitions_20261118.json',
    'research/freezes/code_identity_transitions_20261125.json',
    'research/freezes/verify_code_freezes.py',
    'research/freezes/verify_versioned_transition.py',
    'research/freezes/integrity_gate.py',
    '.github/workflows/freeze-integrity-trusted.yml',
    '.github/workflows/risk-lock-research.yml',
}
VERIFIER = 'research/freezes/verify_versioned_transition.py'
HOPS = 'research/freezes/code_identity_transitions_20261125.json'
FREEZE = 'research/freezes/frozen_baselines_20261115.json'
NOV18 = 'research/freezes/code_identity_transitions_20261118.json'
GATE = 'research/freezes/integrity_gate.py'
PR = 535


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout.decode().strip()


def blob(data: bytes) -> str:
    return G.git_blob_sha1(data)


class SyntheticRepo:
    """Base commit whose verifier self-hash lives in a PR-editable manifest (the flaw)."""

    def __init__(self, root: Path):
        self.root = root
        git(root, 'init', '-q', '-b', 'main')
        git(root, 'config', 'user.email', 't@example.invalid')
        git(root, 'config', 'user.name', 'test')
        git(root, 'config', 'commit.gpgsign', 'false')
        verifier = b"# trusted verifier\nSTRICT = True\n"
        files = {
            FREEZE: b'{"frozen": "nov15"}\n',
            NOV18: b'{"hop": "nov18"}\n',
            'research/freezes/verify_code_freezes.py': b'# helper\n',
            VERIFIER: verifier,
            HOPS: self.hops_doc(blob(verifier)),
            GATE: (HERE / 'integrity_gate.py').read_bytes(),
            '.github/workflows/freeze-integrity-trusted.yml': b'name: gate\n',
            '.github/workflows/risk-lock-research.yml': b'name: risk\n',
            'README.md': b'readme\n',
        }
        for path, data in files.items():
            self.write(path, data)
        self.write(G.PINS_PATH, self.pins_doc({p: blob(d) for p, d in files.items()
                                               if p in REQUIRED_PINNED}))
        self.base = self.commit('base')

    @staticmethod
    def hops_doc(self_hash: str) -> bytes:
        return json.dumps({'verify_versioned_transition_git_blob_sha1': self_hash},
                          sort_keys=True).encode() + b'\n'

    @staticmethod
    def pins_doc(pins: dict) -> bytes:
        return json.dumps({'schema': G.PINS_SCHEMA, 'description': 'synthetic',
                           'recording_act': 'OWNER_MERGE', 'pins': pins},
                          indent=2, sort_keys=True).encode() + b'\n'

    def write(self, path: str, data: bytes):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def read(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def commit(self, msg: str) -> str:
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-q', '--allow-empty', '-m', msg)
        return git(self.root, 'rev-parse', 'HEAD')

    def branch(self, name='pr'):
        git(self.root, 'checkout', '-q', '-b', name, self.base)

    def evaluate(self, head: str) -> dict:
        return G.evaluate(self.root, base_commit=self.base, head_commit=head, pr_number=PR)

    def tamper_verifier_and_self_hash(self) -> bytes:
        """Coordinated edit: verifier weakened AND its stored self-hash rewritten."""
        weak = b"# trusted verifier\nSTRICT = False  # bypass\n"
        self.write(VERIFIER, weak)
        self.write(HOPS, self.hops_doc(blob(weak)))
        return weak

    def declare(self, changes, base=None, reason='owner-requested verifier change'):
        doc = {'schema': G.DECLARATION_SCHEMA, 'pr_number': PR, 'base_commit': base or self.base,
               'recording_act': 'OWNER_MERGE', 'reason': reason, 'changes': changes}
        self.write(f'docs/governance/integrity/pr-{PR}.json',
                   json.dumps(doc, indent=2).encode() + b'\n')


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.r = SyntheticRepo(Path(self._tmp.name))
        self.r.branch()

    def tearDown(self):
        self._tmp.cleanup()

    def assertBlocked(self, result, reason):
        self.assertEqual(result['state'], 'BLOCK')
        self.assertEqual(result['reason_code'], reason)
        self.assertEqual(result['official_counted'], 0)
        self.assertEqual(result['approved_stake_u'], 0)


class IndependentIntegrityTests(GateTestCase):
    def test_unrelated_change_passes(self):
        self.r.write('README.md', b'changed docs\n')
        res = self.r.evaluate(self.r.commit('docs'))
        self.assertEqual(res['state'], 'PASS_INTEGRITY_PINS_UNCHANGED')
        self.assertEqual(res['changes'], [])

    def test_edit_of_verifier_and_its_pinned_self_hash_fails(self):
        """Owner finding: the PR-controlled self-hash check passes, the independent gate fails."""
        weak = self.r.tamper_verifier_and_self_hash()
        head = self.r.commit('coordinated tamper')
        stored = json.loads(self.r.read(HOPS))['verify_versioned_transition_git_blob_sha1']
        self.assertEqual(stored, blob(weak), 'same-boundary self-hash is satisfied by the tamper')
        res = self.r.evaluate(head)
        self.assertBlocked(res, 'INTEGRITY_PIN_CHANGE_UNDECLARED')
        self.assertEqual({c['path'] for c in res['changes']}, {VERIFIER, HOPS})

    def test_edit_of_verifier_self_hash_and_head_pins_file_fails(self):
        """Even rewriting integrity_pins.json on the head does not move the base pins."""
        weak = self.r.tamper_verifier_and_self_hash()
        pins = json.loads(self.r.read(G.PINS_PATH))['pins']
        pins[VERIFIER] = blob(weak)
        pins[HOPS] = blob(self.r.read(HOPS))
        self.r.write(G.PINS_PATH, SyntheticRepo.pins_doc(pins))
        res = self.r.evaluate(self.r.commit('tamper including pins'))
        self.assertBlocked(res, 'INTEGRITY_PIN_CHANGE_UNDECLARED')
        self.assertEqual({c['path'] for c in res['changes']}, {VERIFIER, HOPS, G.PINS_PATH})

    def test_exactly_declared_change_still_fails_until_owner_merge(self):
        self.r.tamper_verifier_and_self_hash()
        probe = self.r.commit('tamper')
        changes = self.r.evaluate(probe)['changes']
        self.r.declare(changes)
        res = self.r.evaluate(self.r.commit('declare'))
        self.assertBlocked(res, 'INTEGRITY_PIN_CHANGE_DECLARED_REQUIRES_OWNER_MERGE')

    def test_inexact_declaration_is_undeclared(self):
        self.r.tamper_verifier_and_self_hash()
        changes = self.r.evaluate(self.r.commit('tamper'))['changes']
        bad = [dict(c, head_git_blob_sha1='0' * 40) for c in changes]
        self.r.declare(bad)
        self.assertBlocked(self.r.evaluate(self.r.commit('bad decl')),
                           'INTEGRITY_PIN_CHANGE_UNDECLARED')
        self.r.declare(changes[:1])
        self.assertBlocked(self.r.evaluate(self.r.commit('partial decl')),
                           'INTEGRITY_PIN_CHANGE_UNDECLARED')
        self.r.declare(changes, base='1' * 40)
        self.assertBlocked(self.r.evaluate(self.r.commit('wrong base decl')),
                           'INTEGRITY_PIN_CHANGE_UNDECLARED')

    def test_nov15_freeze_or_nov18_manifest_edit_fails(self):
        for path in (FREEZE, NOV18):
            with self.subTest(path=path):
                self.r.write(path, self.r.read(path) + b' ')
                res = self.r.evaluate(self.r.commit('edit ' + path))
                self.assertBlocked(res, 'INTEGRITY_PIN_CHANGE_UNDECLARED')
                self.assertIn(path, {c['path'] for c in res['changes']})
                git(self.r.root, 'checkout', '-q', self.r.base, '--', path)

    def test_deleting_a_pinned_file_fails(self):
        (self.r.root / VERIFIER).unlink()
        res = self.r.evaluate(self.r.commit('delete verifier'))
        self.assertBlocked(res, 'INTEGRITY_PIN_CHANGE_UNDECLARED')
        self.assertIsNone(res['changes'][0]['head_git_blob_sha1'])

    def test_head_rewrite_of_the_gate_itself_fails(self):
        self.r.write(GATE, b"def evaluate(*a, **k):\n    return {'state': 'PASS'}\n")
        self.r.write(G.PINS_PATH, b'{}\n')
        res = self.r.evaluate(self.r.commit('neuter gate'))
        self.assertBlocked(res, 'INTEGRITY_PIN_CHANGE_UNDECLARED')
        self.assertEqual({c['path'] for c in res['changes']}, {GATE, G.PINS_PATH})

    def test_symlink_at_pinned_path_fails_closed(self):
        (self.r.root / VERIFIER).unlink()
        os.symlink('../../README.md', self.r.root / VERIFIER)
        head = self.r.commit('symlink')
        with self.assertRaises(G.IntegrityError) as cm:
            self.r.evaluate(head)
        self.assertIn('PINNED_PATH_NOT_REGULAR_FILE', str(cm.exception))

    def test_head_code_is_never_executed(self):
        sentinel = self.r.root / 'EXECUTED'
        payload = f"open({str(sentinel)!r}, 'w').write('x')\n".encode()
        self.r.write(VERIFIER, payload)
        self.r.write(GATE, payload)
        self.r.evaluate(self.r.commit('payload'))
        self.assertFalse(sentinel.exists())

    def test_main_exits_nonzero_for_coordinated_tamper(self):
        self.r.tamper_verifier_and_self_hash()
        head = self.r.commit('tamper')
        proc = subprocess.run([sys.executable, str(HERE / 'integrity_gate.py'), '--repo',
                               str(self.r.root), '--base-sha', self.r.base, '--head-sha', head,
                               '--pr-number', str(PR)], stdout=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)['reason_code'], 'INTEGRITY_PIN_CHANGE_UNDECLARED')

    def test_owner_merge_moves_base_pins_then_unrelated_followup_passes(self):
        weak = self.r.tamper_verifier_and_self_hash()
        pins = json.loads(self.r.read(G.PINS_PATH))['pins']
        pins[VERIFIER] = blob(weak)
        pins[HOPS] = blob(self.r.read(HOPS))
        self.r.write(G.PINS_PATH, SyntheticRepo.pins_doc(pins))
        merged = self.r.commit('owner-merged reviewed change')
        self.assertEqual(G.self_check(self.r.root, merged)['state'], 'PASS_TREE_MATCHES_OWN_PINS')
        self.r.base = merged
        self.r.write('README.md', b'follow-up\n')
        self.assertEqual(self.r.evaluate(self.r.commit('follow-up'))['state'],
                         'PASS_INTEGRITY_PINS_UNCHANGED')


class BaseFailClosedTests(GateTestCase):
    def _rebase_with(self, path, data):
        git(self.r.root, 'checkout', '-q', 'main')
        self.r.write(path, data)
        self.r.base = self.r.commit('base drift')
        self.r.branch('pr2')
        self.r.write('README.md', b'x\n')
        return self.r.commit('head')

    def test_base_tree_inconsistent_with_base_pins_fails(self):
        head = self._rebase_with(VERIFIER, b'# drifted on base\n')
        with self.assertRaisesRegex(G.IntegrityError, 'INTEGRITY_BASE_PINS_INCONSISTENT'):
            self.r.evaluate(head)

    def test_missing_or_malformed_base_pins_fail(self):
        cases = {
            b'{"schema": "x", "schema": "y"}': 'DUPLICATE_JSON_KEY',
            b'not json': 'MALFORMED_JSON',
            b'{"schema": "sportsedge-freeze-integrity-pins-v1"}': 'INTEGRITY_PINS_MALFORMED',
            SyntheticRepo.pins_doc({G.PINS_PATH: '0' * 40}): 'INTEGRITY_PINS_SELF_ENTRY_FORBIDDEN',
            SyntheticRepo.pins_doc({'../etc/passwd': '0' * 40}): 'INVALID_PINNED_PATH',
            SyntheticRepo.pins_doc({VERIFIER: 'NaN'}): 'INVALID_GIT_SHA',
        }
        for raw, reason in cases.items():
            with self.subTest(reason=reason):
                self.assertRaisesRegex(G.IntegrityError, reason, G.parse_pins, raw)
        git(self.r.root, 'checkout', '-q', 'main')
        (self.r.root / G.PINS_PATH).unlink()
        self.r.base = self.r.commit('drop pins')
        self.r.branch('pr3')
        head = self.r.commit('head')
        with self.assertRaisesRegex(G.IntegrityError, 'INTEGRITY_PINS_MISSING_ON_BASE'):
            self.r.evaluate(head)

    def test_bad_arguments_refused(self):
        with self.assertRaisesRegex(G.IntegrityError, 'PR_HEAD_EQUALS_BASE'):
            G.evaluate(self.r.root, base_commit=self.r.base, head_commit=self.r.base, pr_number=PR)
        with self.assertRaisesRegex(G.IntegrityError, 'INVALID_GIT_SHA'):
            G.evaluate(self.r.root, base_commit='main', head_commit=self.r.base, pr_number=PR)
        with self.assertRaisesRegex(G.IntegrityError, 'INVALID_PR_NUMBER'):
            G.evaluate(self.r.root, base_commit=self.r.base, head_commit='a' * 40, pr_number=True)


class RepositoryPinsTests(unittest.TestCase):
    """The committed pins must cover the trust-critical files and match this tree."""

    def test_pins_cover_required_paths_and_match_working_tree(self):
        pins = G.parse_pins((REPO_ROOT / G.PINS_PATH).read_bytes())
        self.assertEqual(set(pins), REQUIRED_PINNED)
        for path, want in pins.items():
            with self.subTest(path=path):
                self.assertEqual(blob((REPO_ROOT / path).read_bytes()), want)

    def test_nov15_and_nov18_pins_are_the_immutable_values(self):
        pins = G.parse_pins((REPO_ROOT / G.PINS_PATH).read_bytes())
        self.assertEqual(pins[FREEZE], 'fd90e7d493739584bf59bd9d81a69f4174f119e8')
        self.assertEqual(pins[NOV18], '399a4df65036eb236f9f56699bc4090507786a3c')
        self.assertEqual(pins['research/freezes/verify_code_freezes.py'],
                         '27d2b51d27d4b7da6f22dad31d55257541af8f67')

    def test_trusted_workflow_runs_base_code_only(self):
        wf = (REPO_ROOT / '.github/workflows/freeze-integrity-trusted.yml').read_text()
        self.assertIn('pull_request_target:', wf)
        self.assertIn('ref: ${{ github.event.pull_request.base.sha }}', wf)
        self.assertIn('persist-credentials: false', wf)
        self.assertIn('python research/freezes/integrity_gate.py', wf)
        self.assertNotIn('head.ref', wf)
        self.assertNotIn('${{ secrets', wf)


if __name__ == '__main__':
    unittest.main()
