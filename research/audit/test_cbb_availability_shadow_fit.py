"""Offline tests: no real data, odds, external requests, or model deployment."""
import copy
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cbb_availability_shadow_fit import admit, evaluate, parse_event, predict, Blocked

H = 'a'*64
T = 'b'*64
F = 'c'*64

def utc(t):
    return t.strftime('%Y-%m-%dT%H:%M:%SZ')

def sample(i=0):
    start=datetime(2026,10,1,12,tzinfo=timezone.utc)+timedelta(days=i)
    tip=start+timedelta(hours=4)
    final=tip+timedelta(hours=3)
    home=float((i%3)*12)
    away=float((i%4)*8)
    poss=68.0
    hp=77.0
    ap=70.0
    x=home/200.0
    y=away/200.0
    return {
        'event_id':f'G{i}', 'season':2027,
        'home_id':f'HOME{i}', 'away_id':f'AWAY{i}', 'conference_id':'SYNTH',
        'forecast_utc':utc(start),'tip_utc':utc(tip),
        'torvik_pub_utc':utc(start-timedelta(minutes=45)),
        'torvik_cap_utc':utc(start-timedelta(minutes=40)),
        'availability_pub_utc':utc(start-timedelta(minutes=35)),
        'availability_cap_utc':utc(start-timedelta(minutes=30)),
        'final_pub_utc':utc(final),'final_cap_utc':utc(final+timedelta(minutes=1)),
        'torvik_sha256':T,'availability_sha256':H,'final_sha256':F,
        'venue':'NEUTRAL' if i%5==0 else 'TRUE_HOME',
        'venue_verified':True,'availability_census_complete':True,
        'home_p':hp,'away_p':ap,'poss':poss,
        'home_final':hp+poss/100*(-12*x+6*y),
        'away_final':ap+poss/100*(-12*y+6*x),
        'players':[
            {'player_id':f'HP{i}','team_id':f'HOME{i}','status':'OUT',
             'planned_minutes':home,'published_utc':utc(start-timedelta(minutes=35)),
             'captured_utc':utc(start-timedelta(minutes=30)),'source_sha256':H},
            {'player_id':f'AP{i}','team_id':f'AWAY{i}','status':'OUT',
             'planned_minutes':away,'published_utc':utc(start-timedelta(minutes=35)),
             'captured_utc':utc(start-timedelta(minutes=30)),'source_sha256':H},
        ]}

class PITAvailabilityTest(unittest.TestCase):
    def test_fit_only_prior_finals_and_score_unseen(self):
        rows=[sample(i) for i in range(34)]
        frozen=copy.deepcopy(rows)
        report=evaluate(rows,['SYNTH'],cutoff_utc='2026-10-24T00:00:00Z',
                        min_train=10,min_holdout=5)
        self.assertEqual(report['status'],'SHADOW_COEFFICIENTS_FITTED_NO_PROMOTION')
        self.assertGreater(report['train_n'],10)
        self.assertGreater(report['holdout_n'],5)
        self.assertLess(report['heldout_candidate']['points_mae'],
                        report['historical_baseline']['points_mae'])
        self.assertLess(report['coeff_eff_own_absent'],0)
        self.assertGreater(report['coeff_eff_opponent_absent'],0)
        self.assertEqual(rows,frozen)
        self.assertEqual(report['stake_u'],0)
        self.assertFalse(report['source_authenticated'])
        self.assertFalse(report['market_close_compared'])

    def test_unknown_status_never_guess_probability(self):
        e=sample();e['players'][0]['status']='QUESTIONABLE'
        with self.assertRaisesRegex(Blocked,'UNFITTED_PARTICIPATION_STATUS'):
            parse_event(e,{'SYNTH'})

    def test_future_report_and_future_player_source_refused(self):
        e=sample();e['availability_pub_utc']=e['tip_utc']
        with self.assertRaisesRegex(Blocked,'AVAILABILITY_LOOKAHEAD'):
            parse_event(e,{'SYNTH'})
        e=sample();e['players'][0]['captured_utc']=e['tip_utc']
        with self.assertRaisesRegex(Blocked,'PLAYER_STATUS_FUTURE_SOURCE'):
            parse_event(e,{'SYNTH'})

    def test_odds_never_enter_projection_features(self):
        e=sample();e['dk_price_american']=-110
        with self.assertRaisesRegex(Blocked,'EXACT_EVENT_SCHEMA'):
            parse_event(e,{'SYNTH'})

    def test_duplicate_event_quarantines_both(self):
        row=sample()
        clean,rejected=admit([row,copy.deepcopy(row)],['SYNTH'])
        self.assertEqual(len(clean),0)
        self.assertEqual(len(rejected),2)
        self.assertTrue(all('DUPLICATE_EVENT' in x['reason'] for x in rejected))

    def test_unknown_venue_and_unapproved_conference(self):
        e=sample();e['venue_verified']=False
        with self.assertRaisesRegex(Blocked,'VENUE_NOT_VERIFIED'):
            parse_event(e,{'SYNTH'})
        with self.assertRaisesRegex(Blocked,'UNAPPROVED_CONFERENCE'):
            parse_event(sample(),{'OTHER'})

    def test_no_historical_training_data_cannot_fit(self):
        z=evaluate([sample(25)],['SYNTH'],cutoff_utc='2026-10-24T00:00:00Z',
                   min_train=2,min_holdout=1)
        self.assertEqual(z['status'],'RESEARCH_ONLY_NOT_ADMITTED')
        self.assertEqual(z['reason'],'INSUFFICIENT_PIT_TRAIN_OR_UNTOUCHED_HOLDOUT')

    def test_no_absence_means_no_projection_adjustment(self):
        e=sample(0)
        p=parse_event(e,{'SYNTH'})
        self.assertEqual(p['x'],(0.0,0.0))
        self.assertEqual(predict(p,(-35.0,21.0)),p['base'])

    def test_source_hash_and_duplicate_player_binding(self):
        e=sample();e['players'][0]['source_sha256']=T
        with self.assertRaisesRegex(Blocked,'PLAYER_SOURCE_HASH_MISMATCH'):
            parse_event(e,{'SYNTH'})
        e=sample();e['players'].append(copy.deepcopy(e['players'][0]))
        with self.assertRaisesRegex(Blocked,'PLAYER_TEAM_OR_DUPLICATE_ID'):
            parse_event(e,{'SYNTH'})

if __name__ == '__main__':
    unittest.main()
