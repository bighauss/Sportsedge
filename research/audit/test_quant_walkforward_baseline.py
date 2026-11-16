import unittest
from quant_walkforward_baseline import run_walkforward_baseline

H='a'*64
BASE=dict(sport='NBA',event_id='A',market='TOTAL',period='FG',side='over',line='220.5',book='DraftKings',settlement='FULL_GAME_INC_OT',
          game_start_utc='2026-11-11T20:00:00Z',forecast_asof_utc='2026-11-11T17:00:00Z',
          features_published_utc='2026-11-11T16:00:00Z',fitted_until_utc='2026-11-10T00:00:00Z',
          final_published_utc='2026-11-11T23:00:00Z',model_sha256=H,
          result_source='final_receipt',outcome='W',p_model='.6')

class ChronoBaselineTests(unittest.TestCase):
    def test_uses_only_prior_published_result(self):
        a=dict(BASE)
        b=dict(BASE,event_id='B',game_start_utc='2026-11-12T20:00:00Z',
               forecast_asof_utc='2026-11-12T17:00:00Z',final_published_utc='2026-11-12T23:00:00Z',outcome='L')
        r=run_walkforward_baseline([b,a],min_prior=1)
        self.assertEqual(r['evaluated_n'],1)
        self.assertAlmostEqual(r['baseline_brier'], (2/3)**2, places=6)
        self.assertEqual(r['by_market_line'][0]['frozen_model_matched_n'],1)
    def test_future_released_outcome_does_not_train(self):
        a=dict(BASE,final_published_utc='2026-11-14T10:00:00Z')
        b=dict(BASE,event_id='B',game_start_utc='2026-11-12T20:00:00Z',
               forecast_asof_utc='2026-11-12T17:00:00Z',final_published_utc='2026-11-12T23:00:00Z',outcome='L')
        c=dict(BASE,event_id='C',game_start_utc='2026-11-13T20:00:00Z',
               forecast_asof_utc='2026-11-13T17:00:00Z',final_published_utc='2026-11-13T23:00:00Z',outcome='W')
        r=run_walkforward_baseline([a,b,c],min_prior=1)
        self.assertEqual(r['evaluated_n'],1)
        self.assertAlmostEqual(r['baseline_brier'], (1/3-1)**2, places=6)
    def test_same_game_cannot_replicate(self):
        r=run_walkforward_baseline([dict(BASE),dict(BASE)],min_prior=1)
        self.assertEqual(len(r['invalid_rows']),2)
        self.assertEqual(r['duplicate_rows_quarantined'],2)
    def test_push_not_silently_scheduled_as_loss(self):
        r=run_walkforward_baseline([dict(BASE,outcome='P')],min_prior=1)
        self.assertEqual(r['push_rows_excluded_from_binary_scoring'],1)
        self.assertEqual(r['evaluated_n'],0)
    def test_future_feature_is_refused(self):
        r=run_walkforward_baseline([dict(BASE,features_published_utc='2026-11-12T00:00:00Z')],min_prior=1)
        self.assertEqual(len(r['invalid_rows']),1)
    def test_distinct_line_not_pooled(self):
        b=dict(BASE,event_id='B',game_start_utc='2026-11-12T20:00:00Z',
               forecast_asof_utc='2026-11-12T17:00:00Z',final_published_utc='2026-11-12T23:00:00Z',line='225.5')
        r=run_walkforward_baseline([dict(BASE),b],min_prior=1)
        self.assertEqual(r['evaluated_n'],0)

class IntegrityAdversarialTests(unittest.TestCase):
    """Independently witnessed synthetic failures, not historical results."""
    def next_game(self, game='B', days=1, **extra):
        fields = dict(BASE)
        fields.update(event_id=game,
            game_start_utc=f'2026-11-{11+days:02d}T20:00:00Z',
            forecast_asof_utc=f'2026-11-{11+days:02d}T17:00:00Z',
            final_published_utc=f'2026-11-{11+days:02d}T23:00:00Z')
        fields.update(extra)
        return fields

    def test_opposite_input_order_never_picks_lucky_duplicate(self):
        candidate = [dict(BASE, outcome='W'),dict(BASE, outcome='L'),
                     self.next_game('B',1,outcome='L'),self.next_game('C',2,outcome='W')]
        for rows in (candidate, list(reversed(candidate))):
            result=run_walkforward_baseline(rows,min_prior=1)
            self.assertEqual(result['raw_rows'],4)
            self.assertEqual(result['valid_decided_rows'],2)
            self.assertEqual(result['evaluated_n'],1)
            self.assertEqual(result['duplicate_rows_quarantined'],2)
            self.assertEqual(result['baseline_brier'],round((1/3-1)**2,6))
            self.assertEqual(len(result['invalid_rows']),2)
            self.assertTrue(all(x['reason']=='DUPLICATE_EVENT_MARKET_ALL_COPIES_QUARANTINED'
                                for x in result['invalid_rows']))

    def test_bad_first_copy_cannot_let_good_copy_train(self):
        rows=[dict(BASE,p_model='NaN'),dict(BASE,p_model='.6'),self.next_game()]
        result=run_walkforward_baseline(rows,min_prior=1)
        self.assertEqual(result['duplicate_rows_quarantined'],2)
        self.assertEqual(result['evaluated_n'],0)
        self.assertEqual(result['insufficient_training_rows'],1)

    def test_push_and_decided_duplicate_both_refused(self):
        result=run_walkforward_baseline([dict(BASE,outcome='P'),dict(BASE,outcome='W')],min_prior=1)
        self.assertEqual(result['duplicate_rows_quarantined'],2)
        self.assertEqual(result['push_rows_excluded_from_binary_scoring'],0)
        self.assertEqual(result['valid_decided_rows'],0)

    def test_different_team_totals_are_not_one_market(self):
        a=dict(BASE,market='TEAM_TOTAL',side='Under',line='110.5',team_id='BOS')
        b=dict(a,team_id='TOR',outcome='L')
        r=run_walkforward_baseline([a,b],min_prior=1)
        self.assertEqual(r['valid_decided_rows'],2)
        self.assertEqual(r['duplicate_rows_quarantined'],0)
        self.assertEqual(r['evaluated_n'],0)  # opposite teams never train one another

    def test_player_stat_market_requires_identity(self):
        a=dict(BASE,market='player_prop',player_id='id1',stat='PASS_YDS',line='225.5')
        b=dict(a,player_id='id2')
        c=dict(a,stat='REC_YDS')
        r=run_walkforward_baseline([a,b,c],min_prior=1)
        self.assertEqual(r['valid_decided_rows'],3)
        self.assertEqual(r['duplicate_rows_quarantined'],0)
        d=dict(a,player_id='')
        self.assertIn('PLAYER_AND_STAT_ID_REQUIRED',run_walkforward_baseline([d],min_prior=1)['invalid_rows'][0]['reason'])
        e=dict(BASE,market='FIRST_TD',player_id='id1')
        self.assertIn('PLAYER_AND_STAT_ID_REQUIRED',run_walkforward_baseline([e],min_prior=1)['invalid_rows'][0]['reason'])

    def test_books_and_settlement_are_separate_cohorts(self):
        a=dict(BASE,book='DK')
        b=dict(BASE,book='DraftKings')
        c=dict(BASE,book='FanDuel',outcome='L')
        d=dict(BASE,settlement='REGULATION_ONLY',outcome='L')
        r=run_walkforward_baseline([a,b,c,d],min_prior=1)
        self.assertEqual(r['duplicate_rows_quarantined'],2)
        self.assertEqual(r['valid_decided_rows'],2)
        self.assertEqual(r['evaluated_n'],0)

    def test_same_ml_line_zero_aliases_duplicate(self):
        a=dict(BASE,market='moneyline',line='',book='DK')
        b=dict(a,market='ML',line='0',book='DraftKings')
        r=run_walkforward_baseline([a,b],min_prior=1)
        self.assertEqual(r['duplicate_rows_quarantined'],2)

    def test_different_alt_lines_can_coexist(self):
        a=dict(BASE,line='220.5')
        b=dict(BASE,line='224.5')
        r=run_walkforward_baseline([a,b],min_prior=1)
        self.assertEqual(r['duplicate_rows_quarantined'],0)
        self.assertEqual(r['valid_decided_rows'],2)

    def test_market_nan_or_missing_field_never_trains(self):
        invalid=[dict(BASE,line='NaN'),dict(BASE,book=''),dict(BASE,settlement=''),
                 dict(BASE,outcome='P',p_model='NaN'), dict(BASE,market='TEAM_TOTAL',team_id='')]
        for item in invalid:
            with self.subTest(item=item):
                r=run_walkforward_baseline([item],min_prior=1)
                self.assertEqual(r['valid_decided_rows'],0)
                self.assertEqual(len(r['invalid_rows']),1)

    def test_training_minimum_cannot_be_bool_or_float(self):
        for value in (True,1.2,0,-1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'MIN_PRIOR'):
                run_walkforward_baseline([dict(BASE)],min_prior=value)

    def test_output_rows_retained_with_never_count_picks(self):
        d=[dict(BASE,outcome='P'),self.next_game('B',1,book=''),self.next_game('C',2)]
        r=run_walkforward_baseline(d,min_prior=1)
        self.assertEqual(r['raw_rows'],3)
        self.assertEqual(r['push_rows_excluded_from_binary_scoring'],1)
        self.assertEqual(len(r['invalid_rows']),1)
        self.assertEqual(r['valid_decided_rows'],1)
        self.assertEqual(r['evaluated_n'],0)
        self.assertIn('PAPER_0U',r['status'])


class PrivateCliTests(unittest.TestCase):
    def test_private_csv_integrity_and_mode(self):
        import csv
        import hashlib
        import json
        import os
        import stat
        import tempfile
        from pathlib import Path
        from quant_walkforward_baseline import main
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'frozen.csv'
            fields=list(BASE)
            with src.open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=fields)
                writer.writeheader();writer.writerow(BASE)
            original=src.read_bytes()
            out=Path(directory)/'private_report.json'
            self.assertEqual(main([str(src),'--report',str(out),'--min-prior','1']),0)
            report=json.loads(out.read_text())
            self.assertEqual(report['source_sha256'],hashlib.sha256(original).hexdigest())
            self.assertEqual(report['raw_rows'],1)
            self.assertEqual(src.read_bytes(),original)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):
                main([str(src),'--report',str(out),'--min-prior','1'])

    def test_cli_duplicate_header_and_malformed_rows_fails(self):
        import tempfile
        from pathlib import Path
        from quant_walkforward_baseline import main
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'frozen.csv'
            dst=Path(directory)/'output.json'
            src.write_text('sport,sport,event_id\nNBA,NBA,x\n')
            with self.assertRaisesRegex(ValueError,'DUPLICATE_CSV_HEADERS'):
                main([str(src),'--report',str(dst)])
            self.assertFalse(dst.exists())
            src.write_text('sport,event_id\nNBA,x\n')
            with self.assertRaisesRegex(ValueError,'MISSING_CSV_COLUMNS'):
                main([str(src),'--report',str(dst)])
            self.assertFalse(dst.exists())

    def test_refuse_inside_public_checkout_and_symlink_alias(self):
        import tempfile
        from pathlib import Path
        from quant_walkforward_baseline import _private_path, REPO_ROOT
        with self.assertRaisesRegex(ValueError,'PUBLIC_CHECKOUT'):
            _private_path(REPO_ROOT/'secrets.csv')
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            (p/'alias').symlink_to(REPO_ROOT,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'PUBLIC_CHECKOUT'):
                _private_path(p/'alias'/'grade.csv')
            (p/'alias').unlink()
            (p/'alias').symlink_to(p/'private',target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'SYMLINK_PATH'):
                _private_path(p/'alias'/'grade.csv')


if __name__ == "__main__":
    unittest.main()
