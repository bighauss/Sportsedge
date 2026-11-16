import unittest
from quant_walkforward_baseline import run_walkforward_baseline

H='a'*64
BASE=dict(sport='NBA',event_id='A',market='TOTAL',period='FG',side='over',line='220.5',
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
        self.assertEqual(len(r['invalid_rows']),1)
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

if __name__=='__main__':unittest.main()
