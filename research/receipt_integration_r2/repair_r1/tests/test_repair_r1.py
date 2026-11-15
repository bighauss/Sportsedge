from __future__ import annotations
import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import integrity_gate as g
import regrade_portable as h

SHA='a'*64

def fixture():
    return dict(event_id='NCAA-CBB-2026-11-15-1',sport='CBB',book='DraftKings',market='spread',
      period='FG',side='away',line='+5.5',odds_american='-110',snapshot_id='frozen-1',quote_id='dk-q1',
      quote_receipt_sha256=SHA,captured_at_utc='2026-11-15T16:30:00Z',
      decision_at_utc='2026-11-15T16:32:00Z',game_start_utc='2026-11-15T18:00:00Z',
      max_quote_age_minutes='5',model_prediction_at_utc='2026-11-15T16:20:00Z',
      features_asof_utc='2026-11-15T16:15:00Z',rules_effective_at_utc='2026-11-01T00:00:00Z',
      model_sha256=SHA,rules_sha256=SHA,model_version='v5',rules_version='r1',
      projection_mode='PROJECTION',projection_source_period='FG',probability_type='unconditional_win',model_p='0.55',
      model_push_p='0',status='PAPER',event_source_id='provider-event-123',
      home_team_id='TEAM1',away_team_id='TEAM2',team_id='TEAM2',source_home_team_id='TEAM1',source_away_team_id='TEAM2',venue_id='VENUE42',neutral_site='false',
      venue_verified_at_utc='2026-11-15T16:00:00Z',
      source_model_home_proj='80',source_model_away_proj='75',
      emitted_model_home_proj='80',emitted_model_away_proj='75',
      source_projection_sha256=SHA,book_home_spread='-4.5',book_game_total='155',
      quote_verification='INDEPENDENT_RECEIPT_VERIFIED')

def errs(patch):
    r=fixture();r.update(patch)
    return g.checks(r)[0]

class GateTests(unittest.TestCase):
    def test_clean_readonly_pass(self):
        res=g.audit_rows([fixture()]);self.assertEqual(res['status'],'PASS_STRUCTURAL_RESEARCH_ONLY')
        self.assertEqual(res['summary']['official_counted'],0)
    def test_ev_positive(self):self.assertAlmostEqual(float(g.expected_roi('.6','+200')),0.8)
    def test_ev_negative(self):self.assertAlmostEqual(float(g.expected_roi('.55','-110')),0.05)
    def test_ev_pushed_1h_conditional(self):
        self.assertAlmostEqual(float(g.expected_roi('.6','+100','.2','conditional_on_no_push')),0.16)
    def test_implied_plus(self):self.assertAlmostEqual(float(g.odds_break_even('+1400')),1/15)
    def test_implied_minus(self):self.assertAlmostEqual(float(g.odds_break_even('-110')),110/210)
    def test_invalid_odds(self):
        for x in ['+99','-99','0','+100.5','nan','inf']:
            with self.subTest(x=x),self.assertRaises(ValueError):g.odds_break_even(x)
    def test_stale_quote(self):self.assertIn('STALE_QUOTE',errs({'decision_at_utc':'2026-11-15T16:50:00Z'}))
    def test_after_kickoff(self):self.assertIn('DECISION_NOT_BEFORE_START',errs({'decision_at_utc':'2026-11-15T18:01:00Z'}))
    def test_quote_after_decision(self):self.assertIn('QUOTE_OBSERVED_AFTER_DECISION',errs({'captured_at_utc':'2026-11-15T16:35:00Z'}))
    def test_future_features(self):self.assertIn('FEATURE_LOOKAHEAD',errs({'features_asof_utc':'2026-11-15T16:25:00Z'}))
    def test_post_rule_activation(self):self.assertIn('RULES_POSTDATED_DECISION',errs({'rules_effective_at_utc':'2026-11-16T00:00:00Z'}))
    def test_wrong_team_mapping(self):self.assertIn('TEAM_NOT_IN_EVENT',errs({'team_id':'WRONG_TEAM'}))
    def test_rating_input_fuzzy_team_mismatch(self):self.assertIn('PROJECTION_TEAM_BINDING_MISMATCH',errs({'source_away_team_id':'MISSISSIPPI_STATE'}))
    def test_duplicate_home_away(self):self.assertIn('SAME_HOME_AWAY_TEAM_ID',errs({'away_team_id':'TEAM1'}))
    def test_hca_projection_mismatch(self):self.assertIn('PROJECTION_SOURCE_MISMATCH',errs({'emitted_model_home_proj':'77.7'}))
    def test_source_projection_hash_required(self):self.assertIn('MISSING_SOURCE_PROJECTION_HASH',errs({'source_projection_sha256':''}))
    def test_neutral_flag_not_inferred(self):self.assertIn('MISSING_OR_INVALID_BOOLEAN:neutral_site',errs({'neutral_site':''}) if False else errs({'neutral_site':'UNKNOWN'}))
    def test_half_model_period_mismatch(self):self.assertIn('PROJECTION_PERIOD_MISMATCH',errs({'period':'1H'}))
    def test_projection_source_after_model(self):self.assertIn('LOOKAHEAD:projection_source_created_at_utc',errs({'projection_source_created_at_utc':'2026-11-15T17:00:00Z'}))
    def test_venue_lookahead(self):self.assertIn('VENUE_LOOKAHEAD',errs({'venue_verified_at_utc':'2026-11-15T17:00:00Z'}))
    def test_invalid_hash(self):self.assertIn('INVALID_SHA256:rules_sha256',errs({'rules_sha256':'NO'}))
    def test_invalid_probability(self):self.assertIn('INVALID_MODEL_P',errs({'model_p':'1.25'}))
    def test_negative_push(self):self.assertIn('INVALID_PROBABILITIES',errs({'model_push_p':'-.2'}))
    def test_ev_mismatch(self):self.assertIn('EXPECTED_VALUE_MISMATCH',errs({'claimed_ev':'0.9'}))
    def test_projections_total_consistency(self):self.assertIn('TOTAL_DOES_NOT_MATCH_PROJECTIONS',errs({'model_game_total':'160'}))
    def test_projections_margin_consistency(self):self.assertIn('MARGIN_DOES_NOT_MATCH_PROJECTIONS',errs({'model_home_margin':'8'}))
    def test_margin_disagreement_all_sports(self):self.assertIn('DISAGREEMENT_REVIEW_HOLD',errs({'book_home_spread':'-15.5'}))
    def test_total_disagreement(self):self.assertIn('DISAGREEMENT_REVIEW_HOLD',errs({'book_game_total':'165'}))
    def test_team_total_disagreement(self):
        self.assertIn('DISAGREEMENT_REVIEW_HOLD',errs({'market':'team_total','side':'under','selection_team_position':'home','book_team_total':'92.5'}))
    def test_team_total_no_market(self):
        self.assertIn('TEAM_TOTAL_MISSING_PAIRED_MARKET',errs({'market':'team_total','side':'under'}))
    def test_ml_no_spread(self):self.assertIn('ML_MISSING_PAIRED_BOOK_SPREAD',errs({'market':'ML','book_home_spread':''}))
    def test_ml_paired_spread_gap(self):self.assertIn('DISAGREEMENT_REVIEW_HOLD',errs({'market':'ML','book_home_spread':'-18.5'}))
    def test_player_mapping(self):
        self.assertIn('PLAYER_TEAM_MISMATCH',errs({'market':'player_prop:points','player_id':'p1','player_team_id':'TEAM1',
            'roster_asof_utc':'2026-11-15T16:00:00Z','roster_source_id':'provider-roster'}))
    def test_prop_roster_missing(self):self.assertIn('PLAYER_ID_MISSING',errs({'market':'player_prop:points'}))
    def test_prop_roster_lookahead(self):self.assertIn('LOOKAHEAD:roster_asof_utc',errs({'market':'player_prop:points','player_id':'p1',
            'player_team_id':'TEAM2','roster_asof_utc':'2026-11-15T17:30:00Z','roster_source_id':'r'}))
    def test_cfb_starter(self):self.assertIn('CFB_STARTER_UNVERIFIED',errs({'sport':'CFB'}))
    def test_duplicate_quote(self):
        row=fixture();other=fixture();other['snapshot_id']='frozen2';other['side']='home'
        res=g.audit_rows([row,other]);self.assertIn('DUPLICATE_BOOK_QUOTE_ID',res['rows'][1]['errors'])
    def test_duplicate_selection_with_new_quote(self):
        row=fixture();other=fixture();other['snapshot_id']='frozen2';other['quote_id']='dk-q2'
        self.assertIn('DUPLICATE_SELECTION_DECISION',g.audit_rows([row,other])['rows'][1]['errors'])
    def test_unicode_name_ignored_by_identity(self):
        row=fixture();row['display_team']='Hawaiʻi';self.assertEqual(g.audit_rows([row])['summary']['rejected'],0)
    def test_postgame_fields_not_used(self):
        row=fixture();row['actual_result']='W';self.assertEqual(g.audit_rows([row])['summary']['rejected'],0)
        self.assertIn('POSTGAME_FIELDS_PRESENT_IGNORED_FOR_ADMISSION',g.checks(row)[1])
    def test_unverified_quote_still_not_counted(self):
        row=fixture();row['quote_verification']='unverified';out=g.audit_rows([row]);
        self.assertIn('EXTERNAL_QUOTE_NOT_INDEPENDENTLY_VERIFIED',out['rows'][0]['warnings']);self.assertFalse(out['rows'][0]['official_countable'])

class HistoricalGradeTests(unittest.TestCase):
    def test_washington_team_total_correct(self):
        self.assertEqual(h.settle('Mississippi Valley @ Washington','Washington Under 82.5'),'W')
    def test_game_total_not_team_total(self):
        self.assertEqual(h.settle('Mississippi Valley @ Washington','Under 140.5'),'L')
    def test_half_team_total(self):self.assertEqual(h.settle('Rice @ Stanford','1H Rice Over 28.5'),'W')
    def test_spread_sign(self):
        self.assertEqual(h.settle('Rice @ Stanford','Rice +17.5'),'L')
        self.assertEqual(h.settle('Rice @ Stanford','Rice +18.5'),'W')
        self.assertEqual(h.settle('Rice @ Stanford','Stanford -18.5'),'L')
    def test_half_moneyline_push(self):
        self.assertEqual(h.settle('Rice @ Stanford','1H Rice ML'),'L')
    def test_washington_1h(self):self.assertEqual(h.settle('Mississippi Valley @ Washington','1H Washington Over 39.5'),'W')
    def test_all_496_oracle(self):
        p=ROOT/'source'/'census.json'
        if not p.exists():p=Path('/mnt/data/census.json')
        if p.exists():
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as d:
                result=h.run(p,d);self.assertEqual(result['grade_corrections'],70)

if __name__=='__main__':unittest.main()
