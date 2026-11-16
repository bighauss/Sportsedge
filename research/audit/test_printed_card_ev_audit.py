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
    def test_california_ml_inconsistent(self):
        s=fixture('1H California ML | +200 | 38.6% | +159 | +0.0% | +15.1%')
        a=audit(s)
        self.assertEqual(len(a['anomalies']),1)
        self.assertEqual(a['anomalies'][0]['computed_binary_ev_pct_from_display'],'15.800')
        self.assertEqual(a['anomalies'][0]['rounding_tolerance_pp'],'0.200')
    def test_utsa_ml_inconsistent(self):
        a=audit(fixture('1H UTSA ML | +470 | 21.1% | +374 | +0.0% | +19.7%'))
        self.assertEqual(a['anomalies'][0]['computed_binary_ev_pct_from_display'],'20.270')
        self.assertEqual(a['anomalies'][0]['rounding_tolerance_pp'],'0.335')
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


if __name__=='__main__':unittest.main()
