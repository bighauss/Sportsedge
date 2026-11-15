import unittest
from v21_risk_contract import diagnostic

def candidate(**kwargs):
    d=dict(bet_id='B1',event_id='G1',theme='signal-T',risk_date_ct='2026-11-15',
           market='ML',sport='NFL',book='DK',price_american='+120',
           p_model='.60',p_market_novig='.55',bankroll='1000',dollars_per_u='10',
           confidence='HIGH',captured_utc='2026-11-15T17:10:00Z',
           game_start_utc='2026-11-15T18:00:00Z',
           source_receipt_verified=True,independent_model_verified=True,
           quote_is_fresh=True,injury_snapshot_locked=True)
    d.update(kwargs)
    return d

def size(x,**kwargs):return diagnostic(candidate(**x),**kwargs)

class Contract(unittest.TestCase):
    def test_always_research_0u(self):
        z=size({});self.assertEqual(z['approved_stake_u'],0)
        self.assertNotEqual(z['diagnostic_u'],0)
    def test_low_halves_after_initial(self):
        self.assertAlmostEqual(float(size({'confidence':'LOW'})['diagnostic_u']),
                               float(size({})['diagnostic_u'])/2)
    def test_nonpositive_ev_zero(self):
        z=size({'p_model':'.25','p_market_novig':'.35'})
        self.assertIn('NON_POSITIVE_BLENDED_EV',z['flags'])
        self.assertEqual(z['diagnostic_u'],0)
    def test_missing_units_fail_closed(self):
        self.assertIn('MISSING:dollars_per_u',str(size({'dollars_per_u':None})['flags']))
    def test_missing_quote_evidence_fail_closed(self):
        self.assertIn('SOURCE_RECEIPT_NOT_VERIFIED',size({'source_receipt_verified':False})['flags'])
    def test_unconfirmed_goalie_stops(self):
        self.assertIn('GOALIE_UNCONFIRMED',size({'sport':'NHL','goalie_confirmed':False})['flags'])
    def test_late_change_requires_reprice(self):
        self.assertIn('MATERIAL_NEWS_REPRICE_REQUIRED',size({'material_news_changed':True})['flags'])
    def test_t90_lock_enforced(self):
        self.assertIn('T90_INJURY_LOCK_MISSING',size({'injury_snapshot_locked':False})['flags'])
    def test_prop_nfl_targets(self):
        self.assertIn('NFL_TARGET_MIN_4',size({'market':'PLAYER_PROP','stat':'RECEIVING','projected_targets':'3'})['flags'])
    def test_prop_nba_minutes(self):
        self.assertIn('NBA_MINUTES_20',size({'sport':'NBA','market':'PLAYER_PROP','projected_minutes':'19'})['flags'])
    def test_prop_nhl_toi(self):
        self.assertIn('NHL_TOI_14',size({'sport':'NHL','goalie_confirmed':True,
                                        'market':'PLAYER_PROP','projected_toi':'12'})['flags'])
    def test_prop_mlb_starter(self):
        self.assertIn('MLB_STARTER_UNCONFIRMED',size({'sport':'MLB','market':'PLAYER_PROP',
                                                       'confirmed_starting_pitcher':False})['flags'])
    def test_push_requires_probabilities(self):
        self.assertIn('UNVERIFIED_NUMERIC_OR_LEDGER:ValueError',size({'push_capable':True})['flags'])
    def test_push_kelly_valid(self):
        self.assertNotEqual(size({'push_capable':True,'p_model_push':'.03','p_market_push':'.02'})['diagnostic_u'],0)
    def test_negative_clv_recent_50_halves(self):
        closes=[{'eligible':True,'comparable':True,'clv':'-.01','sport':'NFL'} for _ in range(50)]
        self.assertAlmostEqual(float(size({},closing_observations=closes)['diagnostic_u']),
                               float(size({})['diagnostic_u'])/2)
    def test_clv_49_no_reduction(self):
        closes=[{'eligible':True,'comparable':True,'clv':'-.01','sport':'NFL'} for _ in range(49)]
        self.assertEqual(size({},closing_observations=closes)['diagnostic_u'],size({})['diagnostic_u'])
    def test_game_cap(self):
        l=[{'bet_id':'X','risk_date_ct':'2026-11-15','event_id':'G1','theme':'other','stake_u':'1.90'}]
        self.assertEqual(size({},ledger=l)['diagnostic_u'],'0.10')
    def test_day_cap(self):
        l=[{'bet_id':'X','risk_date_ct':'2026-11-15','event_id':'G2','theme':'other','stake_u':'4.90'}]
        self.assertEqual(size({},ledger=l)['diagnostic_u'],'0.10')
    def test_theme_cap(self):
        l=[{'bet_id':'X','risk_date_ct':'2026-11-14','event_id':'G2','theme':'signal-T','stake_u':'2.90'}]
        self.assertEqual(size({},ledger=l)['diagnostic_u'],'0.10')
    def test_duplicate_ledger_block(self):
        l=[{'bet_id':'B1','risk_date_ct':'2026-11-15','event_id':'G1','theme':'signal-T','stake_u':'0.4'}]
        self.assertIn('DUPLICATE_BET_ALREADY_RECORDED',size({},ledger=l)['flags'])
    def test_line_cross_kills(self):
        self.assertIn('LINE_CROSSED_PROJECTION',size({'line_crossed_projection':True})['flags'])
    def test_model_missing_reject(self):
        self.assertIn('MODEL_SOURCE_UNVERIFIED',size({'independent_model_verified':False})['flags'])
    def test_clv_other_sport_does_not_halve(self):
        closes=[{'eligible':True,'comparable':True,'clv':'-2','sport':'NBA'} for _ in range(50)]
        self.assertEqual(size({},closing_observations=closes)['diagnostic_u'],size({})['diagnostic_u'])
    def test_actual_ct_date_required(self):
        z=size({'game_start_utc':'2026-11-16T02:00:00Z',
                'captured_utc':'2026-11-16T01:25:00Z','risk_date_ct':'2026-11-16'})
        self.assertIn('CT_DATE_NEEDS_INDEPENDENT_VERIFICATION',z['flags'])
if __name__=='__main__':unittest.main()
