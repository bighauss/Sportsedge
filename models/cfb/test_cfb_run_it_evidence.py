"""CFB RUN IT P0 regressions: original weather/line bytes and sealed final public state.

Provider-free only. The workflow's actual embedded export Python is executed
against synthetic originals, rather than reimplementing the archive logic.
"""
from __future__ import annotations
import contextlib
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import cfb_run_it as R
import test_cfb_run_it as F

WORKFLOW = REPO / '.github' / 'workflows' / 'cfb-run-it.yml'


def _section(step):
    source = WORKFLOW.read_text()
    head = '      - name: ' + step + '\n'
    if source.count(head) != 1:
        raise AssertionError('Missing/duplicated workflow step: ' + step)
    return source.split(head, 1)[1].split('      - name: ', 1)[0].split('      - uses: ', 1)[0]


def _python(step):
    section = _section(step)
    if section.count("          python - <<'PY'\n") != 1:
        raise AssertionError('Missing Python heredoc in ' + step)
    code = section.split("          python - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
    code = textwrap.dedent(code)
    compile(code, step, 'exec')
    return code


def _weather_blob():
    today = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = [(today + dt.timedelta(hours=i)).strftime('%Y-%m-%dT%H:00') for i in range(24)]
    return json.dumps({'hourly': {'time': hours, 'wind_speed_10m': [6.5] * len(hours),
                                   'precipitation': [0.0] * len(hours),
                                   'snowfall': [0.0] * len(hours)}}).encode()


class LiveCaptureIsOriginal(unittest.TestCase):
    def test_real_runner_adapts_mocked_source_bytes_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            intake_bytes = json.dumps(F.INTAKE, separators=(',', ':')).encode()
            path = root / 'intake.json'; path.write_bytes(intake_bytes)
            cap = F.fixture()
            now = dt.datetime.now(dt.timezone.utc)
            for i, g in enumerate(cap['games'][:2]):
                g['startDate'] = (now + dt.timedelta(hours=4+i)).isoformat()
            weather_bytes = _weather_blob()
            games_bytes = json.dumps(cap['games']).encode()
            receipt = {'source': 'games', 'provider': 'collegefootballdata.com',
                       'bytes': len(games_bytes), 'sha256': R.sha256(games_bytes),
                       'observed_utc': now.isoformat()}
            with mock.patch.object(R, 'capture_cfbd', return_value=(cap, {'games': games_bytes}, [receipt])), \
                 mock.patch.object(R, 'http_bytes', return_value=weather_bytes) as fetch, \
                 mock.patch.dict(os.environ, {'CFBD_API_KEY': 'SYNTHETIC_TEST_ONLY'}):
                result = R.main([str(path), '--season', '2026', '--out', str(root/'out'),
                                 '--private-dir', str(root/'private'), '--allow-no-injury-feed'])
            self.assertEqual(result, 0)
            private = root/'private'
            self.assertEqual((private/'games.json').read_bytes(), games_bytes)
            self.assertEqual((private/'operator_lines.json').read_bytes(), intake_bytes)
            self.assertEqual(fetch.call_count, 2)
            doc = json.loads((root/'out'/'cfb_run_it.json').read_bytes())
            receipts = doc['card']['receipts']
            self.assertEqual(len(receipts), 4)
            for source in ('games', 'operator_lines', 'weather_game_1', 'weather_game_2'):
                entry = next(r for r in receipts if r['source'] == source)
                original = (private/(source+'.json')).read_bytes()
                self.assertEqual(entry['sha256'], hashlib.sha256(original).hexdigest())
                self.assertEqual(entry['bytes'], len(original))
            self.assertEqual(doc['card']['eligibility']['state'], 'RESEARCH_ONLY')
            self.assertEqual(doc['card']['eligibility']['approved_stake_u'], 0)

    def test_manual_injury_original_is_receipted_and_protected(self):
        """A provided review file is archived by exact bytes, not just transformed rows."""
        import cfb_injury_intake as INJ
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            intake_file = root / 'intake.json'
            intake_file.write_bytes(json.dumps(F.INTAKE).encode())
            manual = {'schema': INJ.SCHEMA,
                      'reviewed_utc': '2026-11-21T15:00:00Z',
                      'teams_reviewed': ['Michigan', 'UCLA'], 'injuries': []}
            manual_bytes = json.dumps(manual, separators=(',', ':')).encode()
            manual_file = root / 'injuries.json'
            manual_file.write_bytes(manual_bytes)
            cap = F.fixture()
            now = dt.datetime.now(dt.timezone.utc)
            for i, g in enumerate(cap['games'][:2]):
                g['startDate'] = (now + dt.timedelta(hours=4+i)).isoformat()
            weather_bytes = _weather_blob()
            games_bytes = json.dumps(cap['games']).encode()
            receipt = {'source': 'games', 'provider': 'collegefootballdata.com',
                       'bytes': len(games_bytes), 'sha256': R.sha256(games_bytes),
                       'observed_utc': now.isoformat()}
            with mock.patch.object(R, 'capture_cfbd', return_value=(cap, {'games': games_bytes}, [receipt])), \
                 mock.patch.object(R, 'http_bytes', return_value=weather_bytes), \
                 mock.patch.dict(os.environ, {'CFBD_API_KEY': 'SYNTHETIC_TEST_ONLY'}):
                code = R.main([str(intake_file), '--season', '2026', '--out', str(root/'out'),
                               '--private-dir', str(root/'private'), '--injuries', str(manual_file)])
            self.assertEqual(code, 0)
            archived = root / 'private' / 'manual_injuries.json'
            self.assertEqual(archived.read_bytes(), manual_bytes)
            doc = json.loads((root/'out'/'cfb_run_it.json').read_bytes())
            receipt_rows = [x for x in doc['card']['receipts'] if x['source'] == 'manual_injuries']
            self.assertEqual(len(receipt_rows), 1)
            self.assertEqual(receipt_rows[0]['bytes'], len(manual_bytes))
            self.assertEqual(receipt_rows[0]['sha256'], R.sha256(manual_bytes))
            self.assertEqual(doc['card']['eligibility']['state'], 'RESEARCH_ONLY')
            self.assertEqual(doc['card']['eligibility']['approved_stake_u'], 0)

    def test_duplicate_completed_provider_id_quarantines_team_denominator(self):
        cap = F.fixture()
        duplicate = dict(cap['games'][2])  # completed UCLA game, duplicated by provider
        cap['games'].append(duplicate)
        now = dt.datetime.fromisoformat('2026-11-21T15:00:00+00:00')
        self.assertNotIn('UCLA', R.games_played(cap['games'], now))
        self.assertEqual(R.games_played(F.fixture()['games'], now)['UCLA'], 10)
        _, projections, withheld, _ = R.run(F.INTAKE, cap, now, lambda *_: cap['_weather'])
        self.assertNotIn('UCLA', [p['away'] for p in projections])
        self.assertTrue(any('UCLA: games played unknown' in reason for _, reason in withheld))

    def test_missing_completed_provider_id_is_not_counted(self):
        cap = F.fixture()
        del cap['games'][2]['id']
        now = dt.datetime.fromisoformat('2026-11-21T15:00:00+00:00')
        self.assertNotIn('UCLA', R.games_played(cap['games'], now))

    def test_future_and_malformed_injury_review_are_explicit(self):
        now = dt.datetime.fromisoformat('2026-11-21T15:00:00+00:00')
        future = R.eligibility({'injuries': [], 'injuries_reviewed_utc': '2026-11-21T16:00:00Z'}, now)
        invalid = R.eligibility({'injuries': [], 'injuries_reviewed_utc': 'not-a-timestamp'}, now)
        self.assertIn('INJURY_REVIEW_FUTURE', future['reasons'])
        self.assertIn('INJURY_REVIEW_TIME_INVALID', invalid['reasons'])


class ExactWorkflowEvidence(unittest.TestCase):
    def _case(self, temp, *, stray=False, dup=False, post_kickoff=False):
        root = Path(temp)
        src = root/'private'; src.mkdir()
        (root/'out').mkdir()
        raw = {'games': b'{"games":[]}', 'operator_lines': b'{"lines":[]}',
               'weather_game_3': b'{"hourly":{}}'}
        receipts = [{'source': name, 'sha256': hashlib.sha256(data).hexdigest(),
                     'bytes': len(data)} for name, data in raw.items()]
        if dup:
            receipts.append(dict(receipts[0]))
        for name, data in raw.items():
            (src/(name+'.json')).write_bytes(data)
        if stray:
            (src/'unreceipted.json').write_text('SENSITIVE_UNRECEIPTED')
        (src/'stdout.log').write_text('private stdout')
        (src/'stderr.log').write_text('private stderr')
        doc = {'card': {'schema': 'sportsedge-cfb-run-it-card-v1',
                        'eligibility': {'state': 'RESEARCH_ONLY', 'approved_stake_u': 0},
                        'rechecked_utc': '2026-11-21T16:00:00+00:00',
                        'receipts': receipts,
                        'rows': [{'kickoff_utc': '2026-11-21T15:00:00+00:00' if post_kickoff else
                                  '2026-11-21T20:30:00+00:00'}]}}
        (root/'out'/'receipts.json').write_text(json.dumps(receipts))
        (root/'out'/'cfb_run_it.json').write_text(json.dumps(doc))
        (root/'out'/'cfb_card.md').write_text('RESEARCH ONLY - TEST')
        from models.cfb import cfb_ledger as LG
        card_sha = hashlib.sha256(json.dumps(doc['card'], sort_keys=True, separators=(',', ':'),
                                             allow_nan=False, default=str).encode()).hexdigest()
        LG.append(root/'ledger'/'ledger.jsonl', {'type': 'CARD_FROZEN', 'game_ids': ['3'],
                                                 'card_sha256': card_sha, 'rows': []})
        return raw

    def _execute(self, step, root, key):
        env = {**os.environ, 'RUNNER_TEMP': str(root), 'SPORTSEDGE_ARCHIVE_FERNET_KEY': key,
               'PYTHONPATH': str(REPO) + os.pathsep + os.environ.get('PYTHONPATH', '')}
        return subprocess.run([sys.executable, '-c', _python(step)], cwd=root, env=env,
                              text=True, capture_output=True)

    def test_embedded_export_seals_final_card_and_logs(self):
        from cryptography.fernet import Fernet
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); original = self._case(d)
            key = Fernet.generate_key().decode()
            a = self._execute('Encrypt private capture and verify against public receipts', root, key)
            self.assertEqual(a.returncode, 0, a.stderr)
            b = self._execute('Seal the final rechecked card and private logs', root, key)
            self.assertEqual(b.returncode, 0, b.stderr)
            encrypted = root/'private-enc'
            self.assertEqual({p.name for p in encrypted.iterdir()},
                             {name+'.json.fernet' for name in original} |
                             {'cfb_card.md.fernet', 'cfb_run_it.json.fernet', 'receipts.json.fernet',
                              'stdout.log.fernet', 'stderr.log.fernet', 'ledger.jsonl.fernet'})
            cipher = Fernet(key.encode())
            for name, value in original.items():
                self.assertEqual(cipher.decrypt((encrypted/(name+'.json.fernet')).read_bytes()), value)
            self.assertEqual(cipher.decrypt((encrypted/'cfb_card.md.fernet').read_bytes()),
                             b'RESEARCH ONLY - TEST')
            self.assertEqual(cipher.decrypt((encrypted/'stdout.log.fernet').read_bytes()), b'private stdout')
            from models.cfb import cfb_ledger as LG
            self.assertEqual(cipher.decrypt((encrypted/'ledger.jsonl.fernet').read_bytes()),
                             (root/'ledger'/'ledger.jsonl').read_bytes())
            self.assertEqual(len(LG.verify(root/'ledger'/'ledger.jsonl')), 1)

    def test_unlisted_original_and_duplicate_receipt_block_encryption(self):
        from cryptography.fernet import Fernet
        for kwargs in ({'stray': True}, {'dup': True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as d:
                self._case(d, **kwargs)
                a = self._execute('Encrypt private capture and verify against public receipts',
                                  Path(d), Fernet.generate_key().decode())
                self.assertNotEqual(a.returncode, 0)

    def test_post_kickoff_row_blocks_final_seal(self):
        from cryptography.fernet import Fernet
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self._case(d, post_kickoff=True)
            key = Fernet.generate_key().decode()
            a = self._execute('Encrypt private capture and verify against public receipts', root, key)
            self.assertEqual(a.returncode, 0, a.stderr)
            b = self._execute('Seal the final rechecked card and private logs', root, key)
            self.assertNotEqual(b.returncode, 0)
            self.assertIn('BLOCK_POST_KICKOFF_ROW', b.stderr)

    def test_card_change_after_ledger_freeze_blocks_seal(self):
        from cryptography.fernet import Fernet
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self._case(d)
            key = Fernet.generate_key().decode()
            a = self._execute('Encrypt private capture and verify against public receipts', root, key)
            self.assertEqual(a.returncode, 0, a.stderr)
            doc_path = root/'out'/'cfb_run_it.json'
            doc = json.loads(doc_path.read_text())
            doc['card']['rows'][0]['kickoff_utc'] = '2026-11-21T21:00:00+00:00'
            doc_path.write_text(json.dumps(doc))
            b = self._execute('Seal the final rechecked card and private logs', root, key)
            self.assertNotEqual(b.returncode, 0)
            self.assertIn('BLOCK_CARD_LEDGER_HASH_MISMATCH', b.stderr)

    def test_last_publication_cutoff_blocks_started_rows(self):
        from cryptography.fernet import Fernet
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self._case(d)
            doc_path = root/'out'/'cfb_run_it.json'
            doc = json.loads(doc_path.read_text())
            doc['card']['rows'][0]['kickoff_utc'] = '2099-11-21T20:30:00+00:00'
            doc_path.write_text(json.dumps(doc))
            key = Fernet.generate_key().decode()
            good = self._execute('Final kickoff admission immediately before publication', root, key)
            self.assertEqual(good.returncode, 0, good.stderr)
            doc['card']['rows'][0]['kickoff_utc'] = '2001-11-21T20:30:00+00:00'
            doc_path.write_text(json.dumps(doc))
            bad = self._execute('Final kickoff admission immediately before publication', root, key)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('BLOCK_KICKOFF_AT_PUBLICATION', bad.stderr)

    def test_workflow_never_publishes_without_encrypted_upload(self):
        workflow = WORKFLOW.read_text()
        assert 'if-no-files-found: error' in _section('Retain encrypted source evidence')
        self.assertIn("steps.seal.outcome == 'success'", _section('Retain encrypted source evidence'))
        self.assertIn("steps.evidence.outcome == 'success'", _section('Publish card after verified evidence retention'))
        self.assertIn("steps.ledger_evidence.outcome == 'success'", _section('Publish card after verified evidence retention'))
        self.assertNotIn('cfb-run-it-card-${{', workflow)
        self.assertLess(workflow.index('Encryption preflight'), workflow.index('Live run'))
        self.assertLess(workflow.index('Freeze recheck'), workflow.index('Seal the final'))
        self.assertLess(workflow.index('Retain encrypted source evidence'), workflow.index('Publish card'))


if __name__ == '__main__':
    unittest.main()
