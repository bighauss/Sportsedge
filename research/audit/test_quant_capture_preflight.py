import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from quant_capture_preflight import manifest_for_capture, write_create_only, quota_decision, main, REPO_ROOT

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
    def test_nonfinite_quota_age_and_noninteger_policy_fail_closed(self):
        for bad in (float('nan'), float('inf'), float('-inf'), True, -1, '200'):
            with self.subTest(age=bad), self.assertRaisesRegex(ValueError,'INVALID_CACHE_AGE'):
                quota_decision('2026-11-15T18:00:00Z',[],max_hour=2,max_day=4,
                               cache_age_seconds=bad)
        for changes in ({'max_hour':True}, {'max_day':1.5},
                        {'min_cache_seconds':float('inf')}):
            cfg=dict(max_hour=2,max_day=4,cache_age_seconds=None,min_cache_seconds=300)
            cfg.update(changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError,'INVALID_QUOTA_POLICY'):
                quota_decision('2026-11-15T18:00:00Z',[],**cfg)

    def test_future_call_log_cannot_hide_behind_cached_response(self):
        with self.assertRaisesRegex(ValueError,'FUTURE_REQUEST_LOG'):
            quota_decision('2026-11-15T18:00:00Z',
                           ['2026-11-15T18:01:00Z'],max_hour=2,max_day=4,
                           cache_age_seconds=5)

    def test_duplicate_csv_headers_block_entire_snapshot(self):
        raw=capture()
        altered=raw.replace(b'market,offered',b'market,market,offered')
        self.assertNotEqual(raw,altered)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_CAPTURE_CSV_HEADERS'):
            manifest_for_capture(altered,asof_utc='2026-11-15T18:00:00Z',
                                 provider='DK')

    def test_overlong_csv_source_row_cannot_be_silently_truncated(self):
        raw=capture()
        altered=raw.rstrip(b'\r\n')+b',FORGED\r\n'
        with self.assertRaisesRegex(ValueError,'CAPTURE_CSV_EXTRA_FIELDS'):
            manifest_for_capture(altered,asof_utc='2026-11-15T18:00:00Z',
                                 provider='DK')

    def test_nonbytes_input_not_silently_parsed(self):
        with self.assertRaisesRegex(ValueError,'INVALID_SOURCE_BYTES'):
            manifest_for_capture('bad',asof_utc='2026-11-15T18:00:00Z',provider='DK')

    def test_public_repo_paths_refused_without_creating_a_file(self):
        bad=REPO_ROOT/'research'/'audit'/'no_private_capture_here.json'
        with self.assertRaisesRegex(ValueError,'PRIVATE_CAPTURE_PATH_INSIDE_PUBLIC_REPO'):
            write_create_only(bad,{'status':'PAPER'})
        with self.assertRaisesRegex(ValueError,'PRIVATE_CAPTURE_PATH_INSIDE_PUBLIC_REPO'):
            main([str(REPO_ROOT/'research'/'audit'/'fake_private.csv'),
                  '--asof-utc','2026-11-15T18:00:00Z',
                  '--provider','DK','--manifest','/tmp/not_a_real_capture_manifest.json'])
        self.assertFalse(bad.exists())

    def test_optional_original_source_clocks_never_look_ahead(self):
        cases = [
            (dict(source_published_utc='2026-11-15T18:01:00Z'),
             'SOURCE_PUBLISHED_AFTER_LOCAL_CAPTURE'),
            (dict(source_published_utc='2026-11-15T16:00:00Z',
                  source_captured_utc='2026-11-15T18:01:00Z'),
             'SOURCE_CAPTURED_AFTER_LOCAL_CAPTURE'),
            (dict(source_published_utc='2026-11-15T16:01:00Z',
                  source_captured_utc='2026-11-15T16:00:00Z'),
             'SOURCE_CAPTURE_PRECEDES_PUBLICATION'),
        ]
        for changes, expected in cases:
            with self.subTest(reason=expected):
                result=manifest_for_capture(capture(**changes),
                    asof_utc='2026-11-15T18:00:00Z',provider='DK')
                self.assertEqual(result['row_count'],1)
                self.assertIn(expected,[x['reason'] for x in result['rejected_rows']])
                self.assertFalse(result['admission_allowed'])

    def test_optional_model_feature_and_fit_clocks_reject_future(self):
        cases = [
            (dict(model_asof_utc='2026-11-15T21:00:00Z'),
             'MODEL_FORECAST_NOT_PREGAME'),
            (dict(model_asof_utc='2026-11-15T16:00:00Z',
                  feature_available_utc='2026-11-15T16:01:00Z'),
             'FEATURE_AVAILABLE_AFTER_MODEL_FORECAST'),
            (dict(model_asof_utc='2026-11-15T16:00:00Z',
                  fitted_until_utc='2026-11-15T16:00:00Z'),
             'MODEL_FITTED_USING_FUTURE_INFORMATION'),
        ]
        for changes, expected in cases:
            with self.subTest(reason=expected):
                result=manifest_for_capture(capture(**changes),
                    asof_utc='2026-11-15T18:00:00Z',provider='DK')
                self.assertEqual(result['rejected_rows'][0]['reason'],expected)
                self.assertEqual(result['row_count'],1)

    def test_duplicate_original_offer_quarantines_all_copies_in_any_order(self):
        rows=[
            dict(sport='NFL',event_id='G1',book='DK',period='FG',
                 market='total',side='over',line='44.50',price_american='-110',
                 quote_sha256=H,captured_utc='2026-11-15T17:00:00Z',
                 game_start_utc='2026-11-15T21:00:00Z',offered='1',
                 captured='1',modeled='0',provenance='0'),
            dict(sport='NFL',event_id='G1',book='DK',period='FG',
                 market='total',side='over',line='44.5',price_american='-105',
                 quote_sha256=H,captured_utc='2026-11-15T17:00:00Z',
                 game_start_utc='2026-11-15T21:00:00Z',offered='1',
                 captured='1',modeled='0',provenance='0'),
        ]
        for order in (rows,rows[::-1]):
            file=io.StringIO()
            writer=csv.DictWriter(file,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(order)
            result=manifest_for_capture(file.getvalue().encode(),
                asof_utc='2026-11-15T18:00:00Z',provider='DK')
            self.assertEqual(result['row_count'],2)
            self.assertEqual(
                [r['row'] for r in result['rejected_rows']
                 if r['reason']=='DUPLICATE_OR_CONFLICTING_OFFER_IDENTITY'],
                [2,3])
            self.assertFalse(result['source_authenticated'])
        rows[1]['side']='under'
        file=io.StringIO()
        writer=csv.DictWriter(file,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        result=manifest_for_capture(file.getvalue().encode(),
            asof_utc='2026-11-15T18:00:00Z',provider='DK')
        self.assertFalse(any(x['reason']=='DUPLICATE_OR_CONFLICTING_OFFER_IDENTITY'
                             for x in result['rejected_rows']))

    def test_invalid_numeric_line_in_quote_identity_visible_without_deletion(self):
        result=manifest_for_capture(capture(book='DK',side='over',
                                            line='not-a-number'),
             asof_utc='2026-11-15T18:00:00Z',provider='DK')
        self.assertEqual(result['row_count'],1)
        self.assertIn('INVALID_OFFER_LINE',
                      [x['reason'] for x in result['rejected_rows']])

    def test_future_api_call_denied(self):
        with self.assertRaises(ValueError):quota_decision('2026-11-15T18:00:00Z',
             ['2026-11-15T19:00:00Z'],max_hour=2,max_day=4,cache_age_seconds=None)

if __name__=='__main__':unittest.main()
