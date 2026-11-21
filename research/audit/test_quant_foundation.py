import unittest
import csv
import io
from quant_foundation import (american, devig_two_way, ev_per_dollar,
                              probabilities_from_samples, player_prop_baseline,
                              audit_rows, paper_ledger, parse_source_csv)
H='a'*64
BASE=dict(sport='NFL',event_id='E1',period='FG',market='TOTAL',side='over',
          line='44.5',price_american='-110',p_model='0.54',
          model_asof_utc='2026-11-15T17:00:00-06:00',
          captured_utc='2026-11-15T17:30:00-06:00',
          game_start_utc='2026-11-15T19:20:00-06:00',quote_sha256=H,
          model_sha256=H,feature_available_utc='2026-11-15T16:00:00-06:00',
          source_published_utc='2026-11-15T16:00:00-06:00',
          book='DK',qualified='1',selection_id='S1',qualification_rule_sha256=H,
          outcome='W',result_source='finals:sha256:example',
          fitted_until_utc='2026-11-14T12:00:00Z',
          settled_utc='2026-11-16T02:00:00Z')
class TestFoundation(unittest.TestCase):
    def test_odds(self):
        self.assertAlmostEqual(american(-110)[0],1.90909090909)
        self.assertAlmostEqual(american('+150')[0],2.5)
        self.assertAlmostEqual(devig_two_way(-110,-110)['no_vig_a'],.5)
    def test_ev_push(self):
        self.assertAlmostEqual(ev_per_dollar(.5,.1,+100),.1)
        self.assertAlmostEqual(ev_per_dollar(.5,0,+100),0)
        with self.assertRaises(ValueError): ev_per_dollar(.9,.2,-110)
    def test_samples(self):
        d=probabilities_from_samples([3,4,4,5],4,'over')
        self.assertEqual((d['p_win'],d['p_push'],d['p_loss']),(.25,.5,.25))
    def test_no_future_logs(self):
        logs=[dict(player_id='x',game_start_utc=f'2026-11-0{i}T17:00:00Z',
                   data_available_utc=f'2026-11-0{i}T23:00:00Z',
                   played_minutes='30',opportunities='10',actual_stat=str(i)) for i in range(1,4)]
        logs.append(dict(player_id='x',game_start_utc='2026-11-02T17:00:00Z',
                         data_available_utc='2026-11-17T00:00:00Z',
                         played_minutes='30',opportunities='10',actual_stat='9999'))
        p=player_prop_baseline(logs,player_id='x',asof_utc='2026-11-15T00:00:00Z',
                               projected_minutes=30,line=2,side='over')
        self.assertEqual(p['n_past_games'],3)
        self.assertAlmostEqual(p['baseline_mean'],2)
    def test_audit_no_deletions_and_leakage(self):
        future=dict(BASE,feature_available_utc='2026-11-16T00:00:00Z')
        r=audit_rows([dict(BASE),future,dict(BASE)])
        self.assertEqual(r['retained_rows'],3)
        codes=[x['code'] for x in r['issues']]
        self.assertIn('FUTURE_INPUT_LEAK',codes)
        self.assertIn('DUPLICATE_QUOTE_IDENTITY',codes)
    def test_do_not_count_both_sides(self):
        rs=[dict(BASE),dict(BASE,selection_id='S2',side='under',outcome='L'),
            dict(BASE,selection_id='S3',qualified='0',outcome='L')]
        r=paper_ledger(rs)
        self.assertEqual(r['qualified_graded_n'],0)
        self.assertEqual(r['net_units'],0)
        self.assertIsNone(r['roi_flat_1u'])
        self.assertEqual(r['mirror_quarantined_rows'],2)
        self.assertEqual(r['unqualified_n'],1)

    def test_legacy_paper_ledger_duplicate_snapshots_quarantined(self):
        a=dict(BASE)
        b=dict(BASE,selection_id='S2',captured_utc='2026-11-15T17:45:00-06:00',
               price_american='+130')
        r=paper_ledger([a,b])
        self.assertEqual(r['qualified_graded_n'],0)
        self.assertEqual(r['total_quarantined_rows'],2)

    def test_strict_ledger_requires_training_and_settlement_clocks(self):
        r=paper_ledger([dict(BASE,fitted_until_utc='')])
        self.assertEqual(r['qualified_graded_n'],0)
        self.assertTrue(any('fitted_until_utc' in x['code'] for x in r['unverifiable']))

    def test_ledger_retains_one_unambiguous_win(self):
        r=paper_ledger([dict(BASE)])
        self.assertEqual(r['qualified_graded_n'],1)
        self.assertEqual(r['wins'],1)
        self.assertEqual(r['losses'],0)
        self.assertAlmostEqual(r['net_units'],100/110,places=6)
        self.assertAlmostEqual(r['roi_flat_1u'],100/110,places=6)
    def test_odd_type_and_missing_line_never_crash(self):
        r=audit_rows([dict(BASE,price_american=-110,line='')])
        self.assertEqual(r['retained_rows'],1)
        self.assertTrue(any(x['code']=='MISSING_LINE' for x in r['issues']))
    def test_unverified_results_excluded(self):
        r=paper_ledger([dict(BASE, result_source='')])
        self.assertEqual(r['qualified_graded_n'],0)
        self.assertEqual(len(r['unverifiable']),1)

class StrictSourceCsvTests(unittest.TestCase):
    @staticmethod
    def valid_csv():
        stream=io.StringIO()
        writer=csv.DictWriter(stream, fieldnames=list(BASE))
        writer.writeheader()
        writer.writerow(BASE)
        return stream.getvalue().encode()

    def test_valid_csv_retained_without_row_loss(self):
        rows=parse_source_csv(self.valid_csv())
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['selection_id'],'S1')

    def test_duplicated_header_must_not_replace_first_value(self):
        original=self.valid_csv()
        duplicate=original.replace(b'p_model,',b'p_model,p_model,',1)
        with self.assertRaisesRegex(ValueError,'CSV_DUPLICATE_NORMALIZED_HEADER'):
            parse_source_csv(duplicate)
        spaced=original.replace(b'p_model,',b'p_model,p_model ,',1)
        with self.assertRaisesRegex(ValueError,'CSV_DUPLICATE_NORMALIZED_HEADER'):
            parse_source_csv(spaced)

    def test_overlong_record_is_not_silently_trimmed(self):
        original=self.valid_csv()
        long=original.rstrip(b'\r\n')+b',EXTRA\r\n'
        with self.assertRaisesRegex(ValueError,'CSV_EXTRA_FIELD_NOT_IN_HEADER'):
            parse_source_csv(long)

    def test_short_record_and_blank_record_refused(self):
        header,payload=self.valid_csv().splitlines()
        short=header+b'\n'+payload.rsplit(b',',1)[0]+b'\n'
        with self.assertRaisesRegex(ValueError,'CSV_MISSING_FIELD_IN_RECORD'):
            parse_source_csv(short)
        blank=header+b'\n\n'+payload+b'\n'
        with self.assertRaisesRegex(ValueError,'BLANK_CSV_RECORD'):
            parse_source_csv(blank)

    def test_non_utf8_capture_refused_before_cleaned_report(self):
        with self.assertRaisesRegex(ValueError,'INVALID_UTF8_CSV'):
            parse_source_csv(b'\xff\xfe')


class OddsFormatsAndQuality(unittest.TestCase):
    def test_decimal_fractional(self):
        from quant_foundation import odds_in_format
        self.assertAlmostEqual(odds_in_format('2.5','decimal')[1],.4)
        self.assertAlmostEqual(odds_in_format('3/2','fractional')[0],2.5)
        self.assertAlmostEqual(ev_per_dollar(.45,.05,'3/2',odds_format='fractional'),.175)
        self.assertAlmostEqual(devig_two_way('1.91','1.91',format_a='decimal',format_b='decimal')['no_vig_a'],.5)
    def test_format_invalid(self):
        from quant_foundation import odds_in_format
        with self.assertRaises(ValueError):odds_in_format('1.0','decimal')
        with self.assertRaises(ValueError):odds_in_format('0/1','fractional')
        with self.assertRaises(ValueError):odds_in_format('+100','auto')
    def test_half_win_half_loss_settlement(self):
        from quant_foundation import settlement_ev
        self.assertAlmostEqual(settlement_ev({'HW':.5,'HL':.5},+150),.125)
        with self.assertRaises(ValueError):settlement_ev({'W':.8,'L':.1},-110)
    def test_quarter_line_splits(self):
        from quant_foundation import quarter_line_probabilities,settlement_ev
        p=quarter_line_probabilities([2,3,4],2.25,'over')
        self.assertEqual(p,{'W':2/3,'L':0,'P':0,'HW':0,'HL':1/3})
        self.assertAlmostEqual(settlement_ev(p,+100),.5)
        with self.assertRaises(ValueError):quarter_line_probabilities([2],2.5,'over')
    def test_quarter_continuous_sample_refused(self):
        from quant_foundation import quarter_line_probabilities
        with self.assertRaisesRegex(ValueError,'INTEGER_OUTCOMES'):
            quarter_line_probabilities([2.3],2.25,'over')
    def test_game_id_conflicts_retained(self):
        r=audit_rows([dict(BASE),dict(BASE,game_start_utc='2026-11-16T19:20:00-06:00')])
        self.assertEqual(r['retained_rows'],2)
        self.assertTrue(any('EVENT_ID_KICKOFF_CONFLICT' in x['code'] for x in r['issues']))
    def test_outlier_review_retains_every_row(self):
        records=[dict(BASE,event_id=f'E{i}',actual_stat=str(i%3+10)) for i in range(25)]
        records[-1]['actual_stat']='100000'
        r=audit_rows(records)
        self.assertEqual(r['retained_rows'],25)
        self.assertTrue(any(x['code']=='ROBUST_STAT_OUTLIER_REVIEW' for x in r['issues']))

if __name__=='__main__':unittest.main()
