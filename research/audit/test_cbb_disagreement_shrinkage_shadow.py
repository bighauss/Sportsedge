"""Synthetic forward disagreement shrinkage trial; no sportsbook prices or real outcomes."""
import copy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cbb_disagreement_shrinkage_shadow import admit,evaluate,adjusted,_fit,Rejected

B=datetime(2026,1,1,12,tzinfo=timezone.utc)
H='a'*64
T='b'*64

def t(dt):return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

def row(i=0):
    frozen=B+timedelta(days=i)
    p_model=.85 if i%2==0 else .15
    p_prior=.6 if i%2==0 else .4
    q=.55 if i%2==0 else .45
    return {
      'event_id':f'G{i}','market_family':'ML','period':'FG',
      'selection_side':'HOME','settlement':'INCLUDES_OT','line':'',
      'venue':'NEUTRAL' if i%5==0 else 'TRUE_HOME',
      'forecast_utc':t(frozen),'tipoff_utc':t(frozen+timedelta(hours=4)),
      'model_features_published_utc':t(frozen-timedelta(hours=2)),
      'model_features_captured_utc':t(frozen-timedelta(hours=1)),
      'model_fitted_until_utc':t(frozen-timedelta(days=7)),
      'decision_quote_published_utc':t(frozen-timedelta(minutes=10)),
      'decision_quote_captured_utc':t(frozen-timedelta(minutes=5)),
      'close_quote_published_utc':t(frozen+timedelta(hours=2)),
      'close_quote_captured_utc':t(frozen+timedelta(hours=3)),
      'final_published_utc':t(frozen+timedelta(hours=7)),
      'final_captured_utc':t(frozen+timedelta(hours=8)),
      'model_sha256':H,'prior_sha256':H,'decision_quote_sha256':T,
      'close_quote_sha256':T,'final_sha256':H,
      'p_model':p_model,'p_prior':p_prior,
      'p_market_decision':q,'p_market_close':.52 if i%2==0 else .48,
      'outcome':int(i%4 in (0,1))
    }

CUTOFF='2026-07-20T00:00:00Z'

class ShrinkageTests(unittest.TestCase):
    def test_chronological_fit_future_holdout_and_two_baselines(self):
        rows=[row(i) for i in range(260)]
        before=copy.deepcopy(rows)
        z=evaluate(rows,cutoff_utc=CUTOFF)
        m=z['families']['ML']
        self.assertEqual(m['status'],'SHADOW_HOLDOUT_EVALUATED_NO_ADOPTION')
        self.assertGreaterEqual(m['train_unique_events'],180)
        self.assertGreaterEqual(m['holdout_unique_events'],50)
        self.assertGreater(m['unshrunk_model']['brier'],m['candidate']['brier'])
        self.assertIn('prior_model',m)
        self.assertIn('market_close',m)
        self.assertEqual(len(m['candidate_vs_close_brier_event_cluster95']),2)
        self.assertEqual(rows,before)
        self.assertEqual(z['official_counted'],0)
        self.assertFalse(z['source_authenticated'])

    def test_close_probability_not_used_to_choose_weights(self):
        original=[row(i) for i in range(260)]
        changed=copy.deepcopy(original)
        for e in changed:
            e['p_market_close']=.91 if e['outcome']==1 else .09
        a=evaluate(original,cutoff_utc=CUTOFF)['families']['ML']
        b=evaluate(changed,cutoff_utc=CUTOFF)['families']['ML']
        self.assertEqual((a['fit_a'],a['fit_b']),(b['fit_a'],b['fit_b']))
        self.assertEqual(a['candidate'],b['candidate'])
        self.assertNotEqual(a['market_close'],b['market_close'])

    def test_no_data_does_not_claim_fit(self):
        z=evaluate([row(245)],cutoff_utc=CUTOFF)
        self.assertEqual(z['families']['ML']['status'],
                         'INSUFFICIENT_CHRONOLOGICAL_MATCHED_EVENTS')

    def test_future_decision_quote_rejected(self):
        e=row();e['decision_quote_published_utc']=e['tipoff_utc']
        self.assertEqual(admit([e])[1][0]['reason'],'LOOKAHEAD_OR_INVALID_BOOK_OR_RESULT_CLOCKS')

    def test_closing_price_after_tip_rejected(self):
        e=row();e['close_quote_captured_utc']=e['final_captured_utc']
        self.assertEqual(admit([e])[1][0]['reason'],'LOOKAHEAD_OR_INVALID_BOOK_OR_RESULT_CLOCKS')

    def test_duplicate_event_versions_block_all_copies(self):
        e=row()
        clean,blocks=admit([e,copy.deepcopy(e)])
        self.assertEqual(len(clean),0)
        self.assertEqual(len(blocks),2)
        self.assertTrue(all(x['reason']=='DUPLICATE_DECISION_ALL_COPIES_BLOCKED' for x in blocks))

    def test_no_odds_or_postgame_features_in_schema(self):
        e=row();e['postgame_features']={'points':99}
        self.assertIn('EXACT_FROZEN_DECISION_SCHEMA_REQUIRED',admit([e])[1][0]['reason'])

    def test_half_point_and_no_push_enforced(self):
        e=row();e['market_family']='TOTAL';e['line']='150';e['selection_side']='UNDER'
        self.assertEqual(admit([e])[1][0]['reason'],'ONLY_NO_PUSH_HALF_POINT_LINE_SUPPORTED')
        e['line']='150.5'
        self.assertEqual(len(admit([e])[0]),1)

    def test_shrinkage_formula_monotone_toward_market(self):
        p,q=.8,.5
        self.assertEqual(adjusted(p,q,0,0),p)
        self.assertLess(abs(adjusted(p,q,.5,10)-q),abs(p-q))
        self.assertGreater(adjusted(p,q,.5,10),q)


    def test_inner_selection_is_validation_not_training_outcomes(self):
        train,_=admit([row(i) for i in range(20)])
        validation,_=admit([row(i) for i in range(30,46,2)])
        for x in validation:
            x['outcome']=1
        winning=_fit(train,validation)
        self.assertEqual(winning,(0.0,0.0))
        inverted=copy.deepcopy(train)
        for x in inverted:
            x['outcome']=1-x['outcome']
        self.assertEqual(winning,_fit(inverted,validation))
        for x in validation:
            x['outcome']=0
        self.assertNotEqual(winning,_fit(train,validation))

    def test_reject_weak_preregistered_sample_override(self):
        with self.assertRaisesRegex(Rejected,'MINIMUM_FOLD_SIZE_WEAK'):
            evaluate([row(i) for i in range(260)],cutoff_utc=CUTOFF,
                     min_train=20,min_holdout=10)


    def test_first_half_ml_tie_contract_is_not_binary(self):
        e=row();e['period']='1H';e['settlement']='TWO_WAY_TIE_PUSH'
        self.assertEqual(admit([e])[1][0]['reason'],
            'UNMODELED_FIRST_HALF_MONEYLINE_DRAW_SETTLEMENT')
        e['settlement']='THREE_WAY_DRAW_LOSES'
        self.assertEqual(admit([e])[1][0]['reason'],
            'UNMODELED_FIRST_HALF_MONEYLINE_DRAW_SETTLEMENT')

    def test_period_settlement_must_be_explicit_and_match(self):
        e=row();e['settlement']='UNKNOWN'
        self.assertEqual(admit([e])[1][0]['reason'],
            'MARKET_PERIOD_SETTLEMENT_CONTRACT_INVALID')
        e=row();e['market_family']='TOTAL';e['selection_side']='UNDER'
        e['line']='150.5';e['period']='1H';e['settlement']='INCLUDES_OT'
        self.assertEqual(admit([e])[1][0]['reason'],
            'MARKET_PERIOD_SETTLEMENT_CONTRACT_INVALID')
        e['settlement']='FIRST_HALF_REGULATION'
        self.assertEqual(len(admit([e])[0]),1)


    def test_fg_1h_report_separate_and_not_period_admission(self):
        rows=[row(i) for i in range(260)]
        for i,x in enumerate(rows):
            if i%2:
                x['period']='1H'
        z=evaluate(rows,cutoff_utc=CUTOFF)
        p=z['families']['ML']['period_slices']
        self.assertEqual(p['FG']['n']+p['1H']['n'],
                         z['families']['ML']['holdout_n'])
        self.assertGreater(p['FG']['unique_events'],0)
        self.assertGreater(p['1H']['unique_events'],0)
        self.assertEqual(p['FG']['status'],
                         'INSUFFICIENT_UNIQUE_PERIOD_HOLDOUT_GAMES')
        self.assertEqual(p['1H']['status'],
                         'INSUFFICIENT_UNIQUE_PERIOD_HOLDOUT_GAMES')
        self.assertIsNotNone(p['FG']['candidate']['brier'])
        self.assertIsNotNone(p['1H']['market_close']['log_loss'])
        self.assertEqual(z['approved_stake_u'],0)

    def test_single_period_does_not_create_empty_period_scores(self):
        rows=[row(i) for i in range(260)]
        z=evaluate(rows,cutoff_utc=CUTOFF)
        periods=z['families']['ML']['period_slices']
        self.assertEqual(periods['1H']['unique_events'],0)
        self.assertIsNone(periods['1H']['candidate']['brier'])
        self.assertEqual(periods['1H']['status'],
                         'INSUFFICIENT_UNIQUE_PERIOD_HOLDOUT_GAMES')

if __name__=="__main__":unittest.main()
