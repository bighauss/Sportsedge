import unittest
from quant_foundation import (american, devig_two_way, ev_per_dollar,
                              probabilities_from_samples, player_prop_baseline,
                              audit_rows, paper_ledger)
H='a'*64
BASE=dict(sport='NFL',event_id='E1',period='FG',market='TOTAL',side='over',
          line='44.5',price_american='-110',p_model='0.54',
          model_asof_utc='2026-11-15T17:00:00-06:00',
          captured_utc='2026-11-15T17:30:00-06:00',
          game_start_utc='2026-11-15T19:20:00-06:00',quote_sha256=H,
          model_sha256=H,feature_available_utc='2026-11-15T16:00:00-06:00',
          source_published_utc='2026-11-15T16:00:00-06:00',
          book='DK',qualified='1',selection_id='S1',qualification_rule_sha256=H,
          outcome='W',result_source='finals:sha256:example')
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
        self.assertEqual(r['qualified_graded_n'],2)
        self.assertAlmostEqual(r['net_units'],-.0909090909)
        self.assertEqual(r['losses'],1)
    def test_odd_type_and_missing_line_never_crash(self):
        r=audit_rows([dict(BASE,price_american=-110,line='')])
        self.assertEqual(r['retained_rows'],1)
        self.assertTrue(any(x['code']=='MISSING_LINE' for x in r['issues']))
    def test_unverified_results_excluded(self):
        r=paper_ledger([dict(BASE, result_source='')])
        self.assertEqual(r['qualified_graded_n'],0)
        self.assertEqual(len(r['unverifiable']),1)
if __name__=='__main__':unittest.main()
