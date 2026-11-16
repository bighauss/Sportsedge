import json
import tempfile
import unittest
from pathlib import Path

from printed_card_ev_audit import audit, main


def fixture(card, doubted=''):
    lines=['LATE CBB CARD — synthetic PAPER/0u','Card rows: 1','Format: # | game | pick | price | model% | fair | edge | EV | score | stars','',
          f'1 | CBB USC @ California | {card} | 68 | *****']
    if doubted:
        lines += ['', 'MODEL-DOUBTED (1) — EV >= +40%:',
                  f'1 | CBB Cal Poly @ Grand Canyon | {doubted} | 71 | *****']
    return '\n'.join(lines)+'\n'

class PrintedCardTests(unittest.TestCase):
    def test_california_1h_ml_push_aware_not_false_anomaly(self):
        s=fixture('1H California ML | +200 | 38.6% | +159 | +0.0% | +15.1%')
        a=audit(s)
        self.assertEqual(len(a['anomalies']),0)
        self.assertEqual(len(a['push_aware_unresolved']),1)
        r=a['push_aware_unresolved'][0]
        self.assertEqual(r['computed_binary_ev_pct_from_display'],'15.800')
        self.assertEqual(r['rounding_tolerance_pp'],'0.200')
        self.assertIsNone(r['ev_math_inconsistent_beyond_rounding'])
        implied=r['approx_display_implied_push_share_range']
        self.assertLess(float(implied['min']),0.0444)
        self.assertGreater(float(implied['max']),0.0442)
    def test_utsa_1h_ml_push_aware_not_false_anomaly(self):
        a=audit(fixture('1H UTSA ML | +470 | 21.1% | +374 | +0.0% | +19.7%'))
        self.assertEqual(len(a['anomalies']),0)
        r=a['push_aware_unresolved'][0]
        self.assertEqual(r['computed_binary_ev_pct_from_display'],'20.270')
        self.assertEqual(r['rounding_tolerance_pp'],'0.335')
        implied=r['approx_display_implied_push_share_range']
        self.assertLess(float(implied['min']),0.0282)
        self.assertGreater(float(implied['max']),0.0281)
    def test_not_anomaly_within_rounding(self):
        a=audit(fixture('Over 138.5 | -108 | 71.3% | -248 | +21.7% | +37.2%'))
        self.assertEqual(len(a['anomalies']),0)
    def test_doubted_not_card(self):
        a=audit(fixture('Over 138.5 | -108 | 71.3% | -248 | +21.7% | +37.2%',
                         'Under 181.5 | -108 | 85.7% | -601 | +36.2% | +65.1%'))
        self.assertEqual(a['card_count'],1)
        self.assertEqual(a['model_doubted_count'],1)
        self.assertEqual(a['table_rows_total'],2)
    def test_bad_price_preserved_as_problem(self):
        a=audit(fixture('ML | +0 | 45.0% | +100 | +1% | +2%'))
        self.assertEqual(a['parse_or_count_problems'][0]['reason'],'INVALID_AMERICAN_PRICE')
        self.assertEqual(a['card_count'],0)
    def test_wrong_header_count_flagged(self):
        a=audit(fixture('ML | +200 | 40.0% | +150 | +10% | +20%').replace('Card rows: 1','Card rows: 65'))
        self.assertTrue(any(p['reason']=='CARD_COUNT_MISMATCH' for p in a['parse_or_count_problems']))
    def test_create_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            src=root/'card.txt';out=root/'audit.json'
            src.write_text(fixture('ML | +200 | 40.0% | +150 | +10% | +20%'))
            self.assertEqual(main([str(src),'--report',str(out)]),0)
            self.assertEqual(json.loads(out.read_text())['card_count'],1)
            with self.assertRaises(FileExistsError):
                main([str(src),'--report',str(out)])





class SettlementSafetyTests(unittest.TestCase):
    def test_integer_team_total_is_push_sensitive(self):
        r=audit(fixture('1H UTSA Over 44 | -110 | 58.0% | -138 | +0.0% | +8.0%'))
        self.assertEqual(len(r['anomalies']),0)
        self.assertEqual(r['push_aware_unresolved'][0]['settlement_review_category'],'PUSH_AWARE_INTEGER_LINE')
        self.assertIsNone(r['push_aware_unresolved'][0]['ev_math_inconsistent_beyond_rounding'])

    def test_integer_spread_is_push_sensitive(self):
        r=audit(fixture('California +8.0 | -110 | 58.0% | -138 | +0.0% | +8.0%'))
        self.assertEqual(len(r['push_aware_unresolved']),1)
        self.assertFalse(r['anomalies'])

    def test_non_half_or_integer_line_is_nonbinary_settlement(self):
        r=audit(fixture('Over 151.25 | -110 | 58.0% | -138 | +0.0% | +8.0%'))
        self.assertEqual(len(r['nonbinary_settlement_unresolved']),1)
        self.assertIsNone(r['nonbinary_settlement_unresolved'][0]['ev_math_inconsistent_beyond_rounding'])

    def test_half_point_binary_discrepancy_still_flagged(self):
        r=audit(fixture('Over 151.5 | -110 | 58.0% | -138 | +0.0% | +8.0%'))
        self.assertEqual(len(r['anomalies']),1)
        self.assertEqual(r['anomalies'][0]['reason'],'EV_UNEXPLAINED_BY_DISPLAY_ROUNDING')
        self.assertFalse(r['push_aware_unresolved'])

    def test_binary_no_push_exact_rounding_passes(self):
        r=audit(fixture('Over 151.5 | -110 | 58.0% | -138 | +0.0% | +10.7%'))
        self.assertEqual(len(r['anomalies']),0)
        self.assertEqual(r['rows'][0]['settlement_review_category'],
                         'BINARY_NO_EXACT_PUSH_FOR_DISCRETE_CBB_SCORE')

    def test_private_file_mode_and_duplicate_creation(self):
        import os,stat
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            src=root/'card.txt';out=root/'audit.json'
            src.write_text(fixture('1H California ML | +200 | 38.6% | +159 | +0.0% | +15.1%'))
            before=src.read_bytes()
            self.assertEqual(main([str(src),'--report',str(out)]),0)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o600)
            self.assertEqual(src.read_bytes(),before)
            with self.assertRaises(FileExistsError):
                main([str(src),'--report',str(out)])

    def test_public_original_and_symlink_alias_refused(self):
        from printed_card_ev_audit import _private_path,REPO_ROOT
        with self.assertRaisesRegex(ValueError,'PUBLIC_CHECKOUT'):
            _private_path(REPO_ROOT/'card.csv')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'alias').symlink_to(REPO_ROOT,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'PUBLIC_CHECKOUT'):
                _private_path(root/'alias'/'card.csv')

    def test_push_share_interval_unavailable_when_binary_ev_zero(self):
        r=audit(fixture('1H California ML | +200 | 33.3% | +200 | +0.0% | +0.0%'))
        self.assertEqual(len(r['push_aware_unresolved']),1)
        self.assertIsNone(r['rows'][0]['approx_display_implied_push_share_range'])


if __name__ == '__main__':
    unittest.main()
