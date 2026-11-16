import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from quant_capture_preflight import manifest_for_capture, write_create_only, quota_decision

H='a'*64


def capture(**overrides):
    row=dict(sport='NFL',event_id='G1',period='FG',market='TOTAL',offered='1',captured='1',
             modeled='0',provenance='0',player_id='',quote_sha256=H,
             captured_utc='2026-11-15T17:00:00Z',game_start_utc='2026-11-15T21:00:00Z')
    row.update(overrides)
    file=io.StringIO()
    w=csv.DictWriter(file,fieldnames=list(row));w.writeheader();w.writerow(row)
    return file.getvalue().encode()

class CapturePreflightTests(unittest.TestCase):
    def test_before_kickoff_still_paper(self):
        x=manifest_for_capture(capture(),asof_utc='2026-11-15T18:00:00Z',provider='DK')
        self.assertEqual(x['row_count'],1)
        self.assertEqual(x['market_inventory_counts'],{'NO_MODEL':1})
        self.assertFalse(x['admission_allowed'])
    def test_future_capture_excluded_not_deleted(self):
        x=manifest_for_capture(capture(captured_utc='2026-11-15T22:00:00Z'),
                               asof_utc='2026-11-15T23:00:00Z',provider='DK')
        self.assertEqual(x['row_count'],1)
        self.assertEqual(len(x['rejected_rows']),1)
    def test_claim_authentication_denied(self):
        with self.assertRaises(ValueError):
            manifest_for_capture(capture(),asof_utc='2026-11-15T18:00:00Z',
                                 provider='DK',claim_source_authenticated=True)
    def test_create_only(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'receipt.json'
            write_create_only(out,{'status':'PAPER'})
            self.assertEqual(json.loads(out.read_text())['status'],'PAPER')
            with self.assertRaises(FileExistsError):write_create_only(out,{'status':'OTHER'})
            self.assertEqual(json.loads(out.read_text())['status'],'PAPER')
    def test_quota_and_cache(self):
        self.assertEqual(quota_decision('2026-11-15T18:00:00Z',[],max_hour=2,max_day=4,
                                        cache_age_seconds=20)['code'],'USE_CACHE')
        self.assertEqual(quota_decision('2026-11-15T18:00:00Z',
                                        ['2026-11-15T17:50:00Z']*2,
                                        max_hour=2,max_day=4,cache_age_seconds=None)['code'],
                         'HOUR_QUOTA_EXHAUSTED')
    def test_future_api_call_denied(self):
        with self.assertRaises(ValueError):quota_decision('2026-11-15T18:00:00Z',
             ['2026-11-15T19:00:00Z'],max_hour=2,max_day=4,cache_age_seconds=None)

if __name__=='__main__':unittest.main()
