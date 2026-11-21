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
    rules_effective_utc='2026-11-15T11:00:00Z',selected_utc='2026-11-15T12:06:00Z',
    selection_id='B1',outcome='W',result_source='official_final:receipt',
    fitted_until_utc='2026-11-14T22:00:00Z',settled_utc='2026-11-15T23:00:00Z')


class QuantEvidenceTests(unittest.TestCase):
    def test_qualified_replay_requires_both_prospective_decision_clocks(self):
        for omitted in ('rules_effective_utc', 'selected_utc'):
            with self.subTest(omitted=omitted):
                row = dict(BASE, **{omitted: ''})
                result = replay([row])
                self.assertEqual(result['eligible'], 0)
                self.assertIn(omitted, result['rejected_qualified_or_invalid'][0]['reason'])

    def test_retroactive_qualification_rule_is_rejected(self):
        result = replay([dict(BASE, rules_effective_utc='2026-11-15T12:06:01Z')])
        self.assertEqual(result['eligible'], 0)
        self.assertEqual(result['rejected_qualified_or_invalid'][0]['reason'],
                         'QUALIFICATION_RULE_RETROACTIVE')

    def test_price_captured_after_selection_is_rejected(self):
        result = replay([dict(BASE, selected_utc='2026-11-15T12:01:59Z')])
        self.assertEqual(result['eligible'], 0)
        self.assertEqual(result['rejected_qualified_or_invalid'][0]['reason'],
                         'SELECTION_NOT_PROSPECTIVE')

    def test_selection_after_kickoff_is_rejected(self):
        result = replay([dict(BASE, selected_utc='2026-11-15T20:00:01Z')])
        self.assertEqual(result['eligible'], 0)
        self.assertEqual(result['rejected_qualified_or_invalid'][0]['reason'],
                         'SELECTION_NOT_PROSPECTIVE')

    def test_original_quote_older_than_five_minutes_at_decision_is_rejected(self):
        result = replay([dict(BASE, selected_utc='2026-11-15T12:07:01Z')])
        self.assertEqual(result['eligible'], 0)
        self.assertEqual(result['rejected_qualified_or_invalid'][0]['reason'],
                         'STALE_QUOTE_AT_SELECTION')

    def test_opposing_quote_captured_after_selection_is_not_market_baseline(self):
        pair = dict(BASE, market_p_no_vig='.5', paired_quote_sha256=H,
                    paired_price_american='-110',
                    paired_captured_utc='2026-11-15T12:07:00Z',
                    paired_event_id='E1', paired_book='DK', paired_period='FG',
                    paired_market='spread', paired_side='away', paired_line='3.5')
        result = replay([pair])
        self.assertEqual(result['eligible'], 0)
        self.assertEqual(result['rejected_qualified_or_invalid'][0]['reason'],
                         'OPPOSING_QUOTE_AFTER_SELECTION')

    def test_nonqualified_unselected_row_stays_in_denominator(self):
        row = dict(BASE, qualified='0', rules_effective_utc='', selected_utc='')
        result = replay([row])
        self.assertEqual(result['unqualified'], 1)
        self.assertEqual(result['eligible'], 0)
        self.assertEqual(result['rejected_qualified_or_invalid'], [])

    def test_rules_effective_between_forecast_and_selection_allowed(self):
        row = dict(BASE, rules_effective_utc='2026-11-15T12:05:00Z')
        result = replay([row])
        self.assertEqual(result['eligible'], 1)

    def test_quote_and_selection_same_instant_allowed(self):
        result = replay([dict(BASE, selected_utc=BASE['captured_utc'])])
        self.assertEqual(result['eligible'], 1)

    def test_replay_roi_and_baseline(self):
        r1=dict(BASE,market_p_no_vig='.5',paired_quote_sha256=H,paired_price_american='-110',
                paired_captured_utc='2026-11-15T12:05:00Z',paired_event_id='E1',
                paired_book='DK',paired_period='FG',paired_market='spread',
                paired_side='away',paired_line='3.5')
        r2=dict(BASE,event_id='E2',selection_id='B2',outcome='L',price_american='+150')
        r3=dict(BASE,event_id='E3',selection_id='B3',outcome='P')
        out=replay([r1,r2,r3])
        self.assertEqual(out['eligible'],3)
        self.assertEqual(out['overall']['market_baseline_matched_n'],1)
        self.assertAlmostEqual(out['overall']['net_units'],-.0909090909,places=6)
        self.assertAlmostEqual(out['overall']['roi'],-.030303,places=5)
        self.assertEqual(out['max_drawdown_units'],1.0)
        self.assertIn('60-65%', [x['prob_bucket'] for x in out['calibration_5pp']])
    def test_model_vs_market_brier_uses_identical_matched_decisions(self):
        paired=dict(market_p_no_vig='.5',paired_quote_sha256=H,
                    paired_price_american='-110',
                    paired_captured_utc='2026-11-15T12:05:00Z',
                    paired_book='DK',paired_period='FG',
                    paired_market='spread',paired_side='away',
                    paired_line='3.5')
        first=dict(BASE,**paired,paired_event_id='E1',p_model='.9',
                   selection_id='B1',outcome='W')
        second=dict(BASE,**paired,paired_event_id='E2',event_id='E2',
                    selection_id='B2',p_model='.1',outcome='L')
        # Deliberately terrible model forecast has NO authenticated same-line
        # market pair and must not contaminate the paired comparison.
        third=dict(BASE,event_id='E3',selection_id='B3',
                   p_model='.01',outcome='W')
        overall=replay([first,second,third])['overall']
        self.assertEqual(overall['n'],3)
        self.assertEqual(overall['market_baseline_matched_n'],2)
        self.assertAlmostEqual(overall['model_brier_on_market_matched_rows'],.01)
        self.assertAlmostEqual(overall['market_brier'],.25)
        self.assertAlmostEqual(overall['paired_brier_delta_model_minus_market'],-.24)
        self.assertGreater(overall['brier'],.33)
        self.assertAlmostEqual(overall['paired_brier_event_cluster95'][0],-.24)
        self.assertAlmostEqual(overall['paired_brier_event_cluster95'][1],-.24)

    def test_no_matched_quote_means_no_paired_brier_claim(self):
        overall=replay([dict(BASE)])['overall']
        self.assertIsNone(overall['model_brier_on_market_matched_rows'])
        self.assertIsNone(overall['market_brier'])
        self.assertIsNone(overall['paired_brier_delta_model_minus_market'])
        self.assertIsNone(overall['paired_brier_event_cluster95'])
        self.assertEqual(overall['market_baseline_matched_n'],0)

    def test_missing_provenance_fails_closed(self):
        row=dict(BASE,source_published_utc='2026-11-15T12:01:00Z')
        out=replay([row])
        self.assertEqual(out['eligible'],0)
        self.assertEqual(out['rejected_qualified_or_invalid'][0]['reason'],'PIT_FEATURE_NOT_RELEASED')
    def test_duplicate_id_cannot_double_count(self):
        out=replay([dict(BASE),dict(BASE,event_id='E2')])
        self.assertEqual(out['eligible'],0)
        self.assertEqual({x['row'] for x in out['rejected_qualified_or_invalid']}, {2,3})
        self.assertEqual(out['total_quarantined_rows'], 2)
    def test_canonical_duplicate_under_different_id_denied(self):
        same=dict(BASE,selection_id='B2',market='Spreads',side='HOME',line='-3.50')
        out=replay([dict(BASE),same])
        self.assertEqual(out['eligible'],0)
        self.assertEqual({x['row'] for x in out['rejected_qualified_or_invalid']}, {2,3})
        self.assertEqual(out['total_quarantined_rows'],2)
    def test_opposite_spread_sides_quarantined_not_in_roi(self):
        home = dict(BASE)
        away = dict(BASE, selection_id='B2', side='away', line='+3.5',
                    outcome='L', price_american='+150')
        report = replay([home, away])
        self.assertEqual(report['eligible'], 0)
        self.assertEqual(report['overall']['n'], 0)
        self.assertIsNone(report['overall']['roi'])
        self.assertEqual(report['mirror_quarantined_rows'], 2)
        self.assertEqual(report['possible_opposite_side_selection_groups'], 1)
        self.assertEqual({x['reason'] for x in report['rejected_qualified_or_invalid']},
                         {'MIRRORED_QUALIFIED_PAIR_QUARANTINED'})
        self.assertEqual({x['row'] for x in report['rejected_qualified_or_invalid']}, {2, 3})

    def test_mirrored_alias_book_names_still_quarantine(self):
        home = dict(BASE)
        away = dict(BASE, selection_id='B2', book='DraftKings', side='away',
                    line='3.5', outcome='L')
        report = replay([home, away])
        self.assertEqual(report['mirror_quarantined_rows'], 2)
        self.assertEqual(report['eligible'], 0)

    def test_different_capture_times_not_forced_into_same_pair(self):
        home = dict(BASE)
        away = dict(BASE, selection_id='B2', side='away', line='3.5',
                    captured_utc='2026-11-15T12:03:00Z', outcome='L')
        report = replay([home, away])
        self.assertEqual(report['eligible'], 2)
        self.assertEqual(report['mirror_quarantined_rows'], 0)

    def test_independent_team_totals_do_not_false_pair(self):
        home = dict(BASE, market='TEAM_TOTAL', side='over', line='79.5',
                    team_id='H001')
        away = dict(BASE, market='team_total', side='under', line='79.5',
                    team_id='A002', selection_id='B2', outcome='L')
        report = replay([home, away])
        self.assertEqual(report['eligible'], 2)
        self.assertEqual(report['mirror_quarantined_rows'], 0)

    def test_same_team_total_opposite_sides_quarantined(self):
        over = dict(BASE, market='team_total', side='over', line='79.5',
                    team_id='H001')
        under = dict(BASE, market='TEAM_TOTAL', side='under', line='79.50',
                     team_id='H001', selection_id='B2', outcome='L')
        report = replay([over, under])
        self.assertEqual(report['eligible'], 0)
        self.assertEqual(report['mirror_quarantined_rows'], 2)

    def test_different_team_total_same_side_not_duplicate(self):
        team_a = dict(BASE, market='TEAM_TOTAL', side='over', line='79.5',
                      team_id='H001')
        team_b = dict(BASE, market='TEAM_TOTAL', side='over', line='79.5',
                      team_id='A002', selection_id='B2', outcome='L')
        report = replay([team_a, team_b])
        self.assertEqual(report['eligible'], 2)
        self.assertEqual(report['mirror_quarantined_rows'], 0)

    def test_moneyline_blank_and_zero_are_mirrors(self):
        home = dict(BASE, market='ml', side='home', line='', outcome='W')
        away = dict(BASE, market='moneyline', side='away', line='0.0',
                    selection_id='B2', outcome='L')
        report = replay([home, away])
        self.assertEqual(report['eligible'], 0)
        self.assertEqual(report['mirror_quarantined_rows'], 2)

    def test_invalid_nonfinite_line_is_rejected(self):
        report = replay([dict(BASE,line='NaN')])
        self.assertEqual(report['eligible'], 0)
        self.assertEqual(report['rejected_qualified_or_invalid'][0]['reason'],
                         'INVALID_MARKET_LINE')

    def test_duplicate_book_alias_same_side_still_refused(self):
        original = dict(BASE)
        duplicate = dict(BASE, selection_id='B2', book='DraftKings',
                         line='-3.50')
        report = replay([original, duplicate])
        self.assertEqual(report['eligible'], 0)
        self.assertEqual(report['total_quarantined_rows'],2)

    def test_pair_line_or_side_mismatch_denied(self):
        pair=dict(BASE,market_p_no_vig='.5',paired_quote_sha256=H,paired_price_american='-110',
            paired_captured_utc=BASE['captured_utc'],paired_event_id='E1',paired_book='DK',
            paired_period='FG',paired_market='spread',paired_side='away',paired_line='-3.5')
        out=replay([pair])
        self.assertEqual(out['eligible'],0)
        self.assertEqual(out['rejected_qualified_or_invalid'][0]['reason'],'MISMATCHED_SPREAD_LINE')
    def test_market_baseline_math_mismatch(self):
        row=dict(BASE,market_p_no_vig='.90',paired_quote_sha256=H,
                 paired_captured_utc=BASE['captured_utc'],paired_price_american='-110',
                 paired_event_id='E1',paired_book='DK',paired_period='FG',
                 paired_market='spread',paired_side='away',paired_line='3.5')
        out=replay([row])
        self.assertEqual(out['eligible'],0)
        self.assertEqual(out['rejected_qualified_or_invalid'][0]['reason'], 'NO_VIG_BASELINE_MATH_MISMATCH')
    def test_missing_fitted_until_denied(self):
        out=replay([dict(BASE,fitted_until_utc='')])
        self.assertEqual(out['eligible'],0)
        self.assertIn('fitted_until_utc',out['rejected_qualified_or_invalid'][0]['reason'])
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


    def test_same_decision_different_capture_and_price_quarantines_both(self):
        earliest=dict(BASE)
        later=dict(BASE,selection_id='B2',captured_utc='2026-11-15T12:22:00Z',
                   selected_utc='2026-11-15T12:22:30Z',price_american='+150',outcome='W')
        out=replay([earliest,later])
        self.assertEqual(out['eligible'],0)
        self.assertEqual(out['total_quarantined_rows'],2)
        self.assertIsNone(out['overall']['roi'])
        self.assertEqual(out['overall']['net_units'],0)
        self.assertEqual({x['reason'] for x in out['rejected_qualified_or_invalid']},
                         {'REPEATED_QUALIFIED_DECISION_QUARANTINED'})

    def test_same_decision_snapshot_book_alias_quarantines_both(self):
        r1=dict(BASE)
        r2=dict(BASE,selection_id='B2',book='Draft Kings',
                captured_utc='2026-11-15T12:04:00Z')
        self.assertEqual(replay([r1,r2])['eligible'],0)

    def test_different_line_legitimate_distinct_decision(self):
        r1=dict(BASE)
        r2=dict(BASE,selection_id='B2',line='-4.5',
                captured_utc='2026-11-15T12:04:00Z')
        self.assertEqual(replay([r1,r2])['eligible'],2)

    def test_different_book_is_separate_reference_but_paper(self):
        r1=dict(BASE)
        r2=dict(BASE,selection_id='B2',book='FanDuel',
                captured_utc='2026-11-15T12:04:00Z')
        report=replay([r1,r2])
        self.assertEqual(report['eligible'],2)
        self.assertEqual(report['status'],'REPLAY_PAPER_0U_NOT_EXECUTION_AUTHENTICATED')

    def test_team_total_without_exact_team_identity_denied(self):
        r=dict(BASE,market='TEAM_TOTAL',line='80.5',side='over')
        report=replay([r])
        self.assertEqual(report['eligible'],0)
        self.assertEqual(report['rejected_qualified_or_invalid'][0]['reason'],
                         'UNBOUND_TEAM_TOTAL_ID')

    def test_anytime_touchdown_without_player_id_denied(self):
        r=dict(BASE,market='ATTD',side='yes',line='')
        report=replay([r])
        self.assertEqual(report['eligible'],0)
        self.assertEqual(report['rejected_qualified_or_invalid'][0]['reason'],
                         'UNBOUND_PROP_ID')

    def test_no_vig_player_pair_rejects_different_player(self):
        r=dict(BASE,market='player_prop:passing_yards',line='250.5',side='over',
               player_id='p1',stat='passing_yards',market_p_no_vig='.5',
               paired_quote_sha256=H,paired_price_american='-110',
               paired_captured_utc=BASE['captured_utc'],paired_event_id='E1',
               paired_book='DraftKings',paired_period='FG',
               paired_market='player_prop:passing_yards',paired_side='under',
               paired_line='250.5',paired_player_id='p2',paired_stat='passing_yards')
        report=replay([r])
        self.assertEqual(report['eligible'],0)
        self.assertEqual(report['rejected_qualified_or_invalid'][0]['reason'],
                         'MISMATCHED_MARKET_PAIR_SUBJECT:player_id')

    def test_no_vig_player_pair_rejects_different_stat(self):
        r=dict(BASE,market='player_prop:passing_yards',line='250.5',side='over',
               player_id='p1',stat='passing_yards',market_p_no_vig='.5',
               paired_quote_sha256=H,paired_price_american='-110',
               paired_captured_utc=BASE['captured_utc'],paired_event_id='E1',
               paired_book='DK',paired_period='FG',
               paired_market='player_prop:passing_yards',paired_side='under',
               paired_line='250.5',paired_player_id='p1',paired_stat='rushing_yards')
        report=replay([r])
        self.assertEqual(report['eligible'],0)
        self.assertEqual(report['rejected_qualified_or_invalid'][0]['reason'],
                         'MISMATCHED_MARKET_PAIR_SUBJECT:stat')

    def test_no_vig_team_total_pair_rejects_opposing_team(self):
        r=dict(BASE,market='TEAM_TOTAL',line='80.5',side='over',team_id='H001',
               market_p_no_vig='.5',paired_quote_sha256=H,
               paired_price_american='-110',paired_captured_utc=BASE['captured_utc'],
               paired_event_id='E1',paired_book='DK',paired_period='FG',
               paired_market='team_total',paired_side='under',paired_line='80.5',
               paired_team_id='A001')
        report=replay([r])
        self.assertEqual(report['eligible'],0)
        self.assertEqual(report['rejected_qualified_or_invalid'][0]['reason'],
                         'MISMATCHED_MARKET_PAIR_SUBJECT:team_id')

    def test_valid_paired_player_same_subject_alias_book(self):
        r=dict(BASE,market='player_prop:passing_yards',line='250.5',side='over',
               player_id='p1',stat='passing_yards',market_p_no_vig='.5',
               paired_quote_sha256=H,paired_price_american='-110',
               paired_captured_utc=BASE['captured_utc'],paired_event_id='E1',
               paired_book='Draft Kings',paired_period='FG',
               paired_market='player_prop:passing_yards',paired_side='under',
               paired_line='250.5',paired_player_id='p1',paired_stat='passing_yards')
        report=replay([r])
        self.assertEqual(report['eligible'],1)
        self.assertEqual(report['overall']['market_baseline_matched_n'],1)

if __name__=='__main__':unittest.main()
