"""Provider-free regression of CBB RUN IT's actual ledger-restore shell step.

No GitHub API call or model input is fetched: a fake gh executable supplies
controlled responses, and the workflow's own script is executed unchanged.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'cbb-run-it.yml'
STEP = 'Restore and verify encrypted paper ledger from the previous run'


def restore_shell():
    src = WORKFLOW.read_text()
    anchor = '      - name: ' + STEP + '\n'
    if src.count(anchor) != 1:
        raise AssertionError('ledger restore step missing or duplicated')
    body = src.split(anchor, 1)[1].split('\n      - name: ', 1)[0]
    assert '        run: |\n' in body
    return textwrap.dedent(body.split('        run: |\n', 1)[1])


FAKE_GH = '''#!/usr/bin/env python3
import os, pathlib, sys
args = sys.argv[1:]
if args[:1] != ['api']:
    sys.exit(64)
url = args[1] if len(args) > 1 else ''
with open(os.environ['FAKE_GH_CALLS'], 'a') as f:
    f.write(url+'\\n')
if os.getenv('FAKE_GH_ERROR') == '1':
    sys.exit(70)
if '/actions/artifacts?name=cbb-run-it-ledger' in url:
    print(os.getenv('FAKE_GH_ARTIFACT', 'NONE'))
elif '/actions/workflows/cbb-run-it.yml/runs?' in url:
    # Simulate GitHub filtering: fixture-only PR successes must not count.
    if 'event=workflow_dispatch' not in url or 'branch=main' not in url:
        print('99')
    else:
        print(os.getenv('FAKE_GH_PRIOR_SUCCESS', '0'))
elif '/actions/artifacts/123/zip' in url:
    sys.stdout.buffer.write(pathlib.Path(os.environ['FAKE_GH_ZIP']).read_bytes())
else:
    sys.exit(65)
'''


class Continuity(unittest.TestCase):
    def run_restore(self, *, artifact='NONE', prior='0', api_error=False,
                    zip_content=None, parser_accept=True):
        from cryptography.fernet import Fernet
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bindir = root / 'bin'; bindir.mkdir()
            fake = bindir / 'gh'; fake.write_text(FAKE_GH); fake.chmod(0o755)
            lib = root / 'lib'; lib.mkdir()
            (lib / 'cbbd_paper_ledger.py').write_text(
                "def parse_ledger(raw):\n"
                "    if raw != b'VALID-SYNTHETIC-CHAIN' : raise ValueError('broken ledger')\n"
                if parser_accept else
                "def parse_ledger(raw): raise ValueError('broken ledger')\n"
            )
            key = Fernet.generate_key().decode()
            archive = root / 'prior.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('ledger.jsonl.fernet', Fernet(key.encode()).encrypt(
                    zip_content if zip_content is not None else b'VALID-SYNTHETIC-CHAIN'))
            calls = root/'calls'
            env = {**os.environ, 'PATH': str(bindir)+os.pathsep+os.environ.get('PATH', ''),
                   'RUNNER_TEMP': str(root), 'GITHUB_REPOSITORY': 'test/Sportsedge',
                   'SPORTSEDGE_ARCHIVE_FERNET_KEY': key,
                   'PYTHONPATH': str(lib), 'FAKE_GH_CALLS': str(calls),
                   'FAKE_GH_ARTIFACT': artifact, 'FAKE_GH_PRIOR_SUCCESS': prior,
                   'FAKE_GH_ZIP': str(archive), 'FAKE_GH_ERROR': '1' if api_error else '0'}
            result = subprocess.run(['bash', '-euo', 'pipefail', '-c', restore_shell()],
                                    cwd=root, env=env, capture_output=True, text=True)
            ledger = root/'ledger'/'ledger.jsonl'
            return result.returncode, result.stdout + result.stderr, calls.read_text() if calls.exists() else '', (
                ledger.read_bytes() if ledger.exists() else None)

    def test_no_successful_run_allows_first_chain_only(self):
        code, msg, calls, raw = self.run_restore()
        self.assertEqual(code, 0, msg)
        self.assertIn('initialize PAPER chain', msg)
        self.assertIsNone(raw)
        self.assertIn('/actions/workflows/cbb-run-it.yml/runs?event=workflow_dispatch&branch=main&status=success', calls)

    def test_missing_artifact_after_prior_success_refused(self):
        code, msg, calls, raw = self.run_restore(prior='1')
        self.assertNotEqual(code, 0)
        self.assertIn('CBB_LEDGER_MISSING_AFTER_PRIOR_SUCCESS', msg)
        self.assertIsNone(raw)
        self.assertNotIn('/zip', calls)

    def test_missing_artifact_with_unverified_history_refused(self):
        for value in ('', 'UNKNOWN', '-1'):
            with self.subTest(value=value):
                code, msg, _, raw = self.run_restore(prior=value)
                self.assertNotEqual(code, 0)
                self.assertIn('CBB_LEDGER_HISTORY_UNVERIFIED', msg)
                self.assertIsNone(raw)

    def test_expired_or_malformed_artifact_refused(self):
        for artifact in ('123 true', '123 maybe', 'invalid false', '0 true'):
            with self.subTest(artifact=artifact):
                code, msg, calls, raw = self.run_restore(artifact=artifact)
                self.assertNotEqual(code, 0)
                self.assertIn('CBB_LEDGER_ARTIFACT_', msg)
                self.assertIsNone(raw)
                self.assertNotIn('/zip', calls)

    def test_history_api_failure_does_not_bootstrap(self):
        code, msg, calls, raw = self.run_restore(api_error=True)
        self.assertNotEqual(code, 0)
        self.assertIsNone(raw)
        self.assertNotIn('/zip', calls)

    def test_existing_encrypted_ledger_restored_and_parsed(self):
        code, msg, calls, raw = self.run_restore(artifact='123 false', prior='12')
        self.assertEqual(code, 0, msg)
        self.assertEqual(raw, b'VALID-SYNTHETIC-CHAIN')
        self.assertIn('/actions/artifacts/123/zip', calls)
        self.assertNotIn('/actions/workflows/cbb-run-it.yml/runs?', calls)

    def test_corrupt_existing_ledger_refused(self):
        code, msg, _, raw = self.run_restore(artifact='123 false', zip_content=b'TAMPERED')
        self.assertNotEqual(code, 0)
        self.assertIsNone(raw)  # parser rejects before any restored ledger is written


if __name__ == '__main__':
    unittest.main()
