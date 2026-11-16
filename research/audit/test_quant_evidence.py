import copy
import unittest

from quant_evidence import replay, bias_analysis, paired_ablation, market_census

H='a'*64
BASE=dict(sport='CBB',event_id='E1',period='FG',market='spread',side='home',
    line='-3.5',book='DK',price_american='-110',p_model='0.60',
    model_asof_utc='2026-11-15T12:00:00Z',captured_utc='2026-11-15T12:02:00Z',
    game_start_utc='2026-11-15T20:00:00Z',
    feature_available_utc='2026-11-15T11:00:00Z',source_published_utc='2026-11-15T11:00:00Z',
    model_sha256=H,quote_sha256=H,qualification_rule_sha256=H,qualified='1',
    selection_id='B1',outcome='W',result_source='official_final:receipt')


class QuantEvidenceTests(unittest.TestCase):
    def test_replay_roi_and_baseline(self):
        r1=dict(BASE,market_p_no_vig='.52',paired_quote_sha256=H,
                paired_captured_utc='2026-11-15T12:05:00Z')
        r2=dict(BASE,event_id='E2',selection_id='B2',outcome='L',price_american='+150')
        r3=dict(BASE,event_id='E3',selection_id='B3',outcome='P')
        out=replay([r1,r2,r3])
        self.assertEqual(out['eligible'],3)
        self.assertEqual(out['overall']['market_baseline_matched_n'],1)
        self.assertAlmostEqual(out['overall']['net_units'],-.0909090909,places=6)
        self.assertAlmostEqual(out['overall']['roi'],-.030303,places=5)
        self.assertEqual(out['max_drawdown_units'],1.0)
        self.assertIn('60-65%', [x['prob_bucket'] for x in out['calibration_5pp']])
    def test_missing_provenance_fails_closed(self):
        row=dict(BASE,source_published_utc='2026-11-15T12:01:00Z')
        out=replay([row])
        self.assertEqual(out['eligible'],0)
        self.assertEqual(out['rejected_qualified_or_invalid'][0]['reason'],'PIT_FEATURE_NOT_RELEASED')
    def test_duplicate_id_cannot_double_count(self):
        out=replay([dict(BASE),dict(BASE,event_id='E2')])
        self.assertEqual(out['eligible'],1)
        self.assertEqual(len(out['rejected_qualified_or_invalid']),1)
    def test_pushes_not_in_calibration(self):
        out=replay([dict(BASE,outcome='P')])
        self.assertEqual(out['eligible'],1)
        self.assertEqual(out['overall']['decided_n'],0)
        self.assertIsNone(out['overall']['brier'])
    def test_unqualified_retained_census(self):
        out=replay([dict(BASE,qualified='0',outcome='L')])
        self.assertEqual(out['unqualified'],1)
        self.assertEqual(out['eligible'],0)
    def test_future_training_fails(self):
        out=replay([dict(BASE,fitted_until_utc=BASE['model_asof_utc'])])
        self.assertEqual(out['eligible'],0)
    def test_market_baseline_needs_second_quote(self):
        out=replay([dict(BASE,market_p_no_vig='.55')])
        self.assertEqual(out['eligible'],0)
        self.assertEqual(out['rejected_qualified_or_invalid'][0]['reason'],'MARKET_BASELINE_PAIR_NOT_ATTESTED')
    def test_bias(self):
        row=dict(BASE,actual_value='95',projected_mean='100',player_id='ID')
        out=bias_analysis([row])
        self.assertEqual(out['accepted'],1)
        self.assertEqual([x for x in out['groups'] if x['dimension']=='sport'][0]['mean_error_actual_minus_model'],-5)
    def test_bias_future_excluded(self):
        row=dict(BASE,actual_value='95',projected_mean='100',feature_available_utc='2026-11-16T00:00:00Z')
        out=bias_analysis([row])
        self.assertEqual(out['accepted'],0)
    def test_ablation(self):
        row=dict(event_id='E1',market='TOTAL',selection='over',outcome='1',
                 feature_available_utc='2026-11-15T10:00:00Z',forecast_asof_utc='2026-11-15T12:00:00Z',
                 game_start_utc='2026-11-15T20:00:00Z',baseline_model_sha256=H,candidate_model_sha256=H,
                 baseline_probability='.5',candidate_probability='.7')
        out=paired_ablation([row])
        self.assertEqual(out['n'],1)
        self.assertGreater(out['delta_brier_positive_is_candidate_better'],0)
    def test_no_invented_census(self):
        rows=[dict(sport='NHL',event_id='X',period='FG',market='GOALS',offered='1',captured='0'),
              dict(sport='NBA',event_id='Y',period='FG',market='POINTS',offered='0')]
        out=market_census(rows)
        self.assertEqual(out['provided_inventory_n'],2)
        self.assertEqual(out['status_counts'],{'NOT_CAPTURED':1,'NOT_OFFERED':1})

if __name__=='__main__':unittest.main()
