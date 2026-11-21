"""Provider-free tests executing the actual CBB workflow export script."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/cbb-run-it.yml'

class WorkflowEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'evidence'
        self.source.mkdir(mode=0o700)
        self.target = self.root / 'cbb-evidence.tar.fernet'
        self.key = Fernet.generate_key()
        self.document = yaml.safe_load(WORKFLOW.read_text())
        self.steps = self.document['jobs']['run-it']['steps']
        self.by_id = {s['id']: s for s in self.steps if 'id' in s}
        run = self.by_id['encrypt']['run']
        self.script = run.split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        for target in ('socket.create_connection', 'socket.socket.connect', 'socket.socket.connect_ex'):
            guard = patch(target, side_effect=AssertionError('NETWORK_FORBIDDEN'))
            guard.start()
            self.addCleanup(guard.stop)

    def seed(self):
        (self.source / 'card').mkdir()
        (self.source / 'capture').mkdir()
        original = b'{"synthetic_source":true}'
        files = {
            'card/cbb_card.json': json.dumps({'sport': 'CBB', 'rows': []}).encode(),
            'card/cbb_card.md': b'PAPER / 0u',
            'card/receipts.json': json.dumps([{'source': 'fixture', 'sha256': hashlib.sha256(original).hexdigest()}]).encode(),
            'capture/source.json': original,
            'capture/ledger.jsonl': b'{"synthetic":true}\n',
            'board.csv': b'synthetic board',
            'stdout.log': b'PRIVATE SYNTHETIC LOG',
            'stderr.log': b'',
        }
        for name, data in files.items():
            (self.source / name).write_bytes(data)

    def execute_export(self, outcome='success'):
        env = {'RUNNER_TEMP': str(self.root), 'SPORTSEDGE_ARCHIVE_FERNET_KEY': self.key.decode(), 'MODEL_OUTCOME': outcome}
        with patch.dict(os.environ, env):
            exec(compile(self.script, str(WORKFLOW), 'exec'), {})

    def test_roundtrip_preserves_private_logs(self):
        self.seed()
        self.execute_export()
        with tarfile.open(fileobj=io.BytesIO(Fernet(self.key).decrypt(self.target.read_bytes()))) as archive:
            self.assertEqual(archive.extractfile('stdout.log').read(), b'PRIVATE SYNTHETIC LOG')
            index = json.load(archive.extractfile('bundle-index.json'))
            self.assertFalse(index['wager_eligible'])
            self.assertEqual(index['status'], 'DIAGNOSTIC_ONLY')

    def test_empty_directories_refused(self):
        (self.source / 'card').mkdir()
        (self.source / 'capture').mkdir()
        with self.assertRaises(SystemExit):
            self.execute_export()
        self.assertFalse(self.target.exists())

    def test_missing_card_refused(self):
        self.seed()
        (self.source / 'card/cbb_card.json').unlink()
        with self.assertRaises(SystemExit):
            self.execute_export()
        self.assertFalse(self.target.exists())

    def test_hash_mismatch_refused(self):
        self.seed()
        (self.source / 'capture/source.json').write_bytes(b'tampered')
        with self.assertRaises(SystemExit):
            self.execute_export()
        self.assertFalse(self.target.exists())

    def test_failed_run_keeps_encrypted_diagnostics(self):
        (self.source / 'stderr.log').write_bytes(b'SYNTHETIC FAILURE')
        self.execute_export('failure')
        with tarfile.open(fileobj=io.BytesIO(Fernet(self.key).decrypt(self.target.read_bytes()))) as archive:
            self.assertEqual(json.load(archive.extractfile('bundle-index.json'))['status'], 'FAILED_RUN')

    def test_write_failure_never_publishes_partial_bundle(self):
        self.seed()
        with patch('os.fsync', side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError):
                self.execute_export()
        self.assertFalse(self.target.exists())

    def test_publication_boundary(self):
        self.assertEqual(self.document['permissions'], {'contents': 'read', 'actions': 'read'})  # read-only: restore ledger artifact
        self.assertEqual(self.by_id['evidence']['with']['if-no-files-found'], 'error')
        self.assertEqual(self.by_id['evidence']['with']['path'], '${{ runner.temp }}/cbb-evidence.tar.fernet')
        summary = next(s for s in self.steps if s.get('name') == 'Sanitized diagnostic summary')
        self.assertIn("steps.evidence.outcome == 'success'", summary['if'])
        self.assertNotIn('gh issue comment', WORKFLOW.read_text())
        self.assertIn('2> "$RUNNER_TEMP/evidence/stderr.log"', self.by_id['model']['run'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
