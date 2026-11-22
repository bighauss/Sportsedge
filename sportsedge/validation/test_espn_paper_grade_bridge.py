import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timezone

from sportsedge.validation import espn_paper_grade_bridge as bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.now = datetime(2026, 11, 23, tzinfo=timezone.utc)
        tip = '2026-11-22T18:00:00Z'
        pick = self.source('pick.json', dict(
            pick_id='synthetic', home_id='22', away_id='23', kickoff_utc=tip,
            decision_at_utc='2026-11-22T17:00:00Z', market=dict(
                sport='NFL', event_id='123', kind='TOTAL', period='1H',
                selection='OVER', line='20', settlement='REGULATION')), '17:10')
        def side(name, ident, values):
            return dict(homeAway=name, team={'id': ident}, score=sum(values),
                        linescores=[{'value': x} for x in values])
        raw = {'header': {'id': '123', 'competitions': [dict(
            date=tip, status={'type': {'completed': True, 'name': 'STATUS_FINAL'}},
            competitors=[side('home', '22', [7, 7, 0, 3]), side('away', '23', [3, 3, 0, 7])])]}}
        self.row = dict(kickoff_utc=tip, pick=pick, espn_ids_reviewed=True,
                        espn_original=self.source('original.json', raw, '21:10'))

    def source(self, name, doc, clock):
        raw = json.dumps(doc).encode()
        p = self.root / name
        p.write_bytes(raw)
        p.chmod(0o600)
        return dict(path=name, sha256=hashlib.sha256(raw).hexdigest(),
                    captured_at_utc='2026-11-22T' + clock + ':00Z')

    def run_rows(self, *rows):
        self.source('bridge.json', dict(schema=bridge.SCHEMA, entries=rows), '22:00')
        report = bridge.dry_run(self.root / 'bridge.json', now=self.now)
        self.assertFalse(list(self.root.glob('.paper-bridge-*')))
        self.assertFalse(list(self.root.glob('*.sqlite*')))
        return report

    def test_exact_original_reaches_existing_dry_run_grader(self):
        report = self.run_rows(self.row)
        self.assertEqual(report['espn_intake'], {'FINAL_STAGED': 1})
        self.assertEqual(report['results'], {'PAPER_RESULT_GRADED': 1})
        self.assertEqual(report['ledger'], {'DRY_RUN': 1})

    def test_unreviewed_mapping_stays_pending(self):
        report = self.run_rows(dict(self.row, espn_ids_reviewed=False))
        self.assertEqual(report['espn_intake'], {'FINAL_INPUT_BLOCKED': 1})
        self.assertEqual(report['results'], {'PENDING_FINAL': 1})

    def test_tampered_raw_does_not_grade(self):
        (self.root / 'original.json').write_text('{}')
        self.assertEqual(self.run_rows(self.row)['espn_intake'], {'FINAL_INPUT_BLOCKED': 1})

    def test_duplicates_and_bad_rows_stay_in_denominator(self):
        report = self.run_rows(self.row, self.row, {'invalid': True})
        self.assertEqual(report['manifest_entries'], 3)
        self.assertEqual(report['picks'], {'DUPLICATE_PICK_OR_MARKET_BLOCKED': 2, 'PICK_EVIDENCE_BLOCKED': 1})


if __name__ == '__main__':
    unittest.main()
