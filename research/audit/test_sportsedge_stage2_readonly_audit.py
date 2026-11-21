import tempfile
import unittest
from pathlib import Path
from sportsedge_stage2_readonly_audit import strict_csv, audit_ledger, audit_models, audit_other

class Stage2Checks(unittest.TestCase):
    def parse(self, body):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'source.csv'
            path.write_bytes(body)
            before=path.read_bytes()
            got=strict_csv(path)
            self.assertEqual(before,path.read_bytes())
            return got

    def test_normal_csv_and_provenance(self):
        r=self.parse(b'A,B\n1,2\n')
        self.assertEqual(r['status'],'PARSED')
        self.assertEqual(r['row_count'],1)
        self.assertEqual(len(r['sha256']),64)

    def test_duplicate_header_refused(self):
        r=self.parse(b'Player, player \nA,B\n')
        self.assertEqual(r['reason'],'DUPLICATE_NORMALIZED_HEADER')

    def test_ragged_extra_refused(self):
        self.assertIn('RAGGED_RECORD',self.parse(b'A,B\n1,2,3\n')['reason'])

    def test_ragged_short_refused(self):
        self.assertIn('RAGGED_RECORD',self.parse(b'A,B\n1\n')['reason'])

    def test_blank_record_refused(self):
        self.assertEqual(self.parse(b'A,B\n1,2\n\n')['reason'],'BLANK_LOGICAL_RECORD')

    def test_quoted_multiline_is_preserved(self):
        r=self.parse(b'A,B\n1,"line one\nline two"\n')
        self.assertEqual(r['status'],'PARSED')
        with tempfile.TemporaryDirectory() as d:
            # A separate reader check ensures CSV newline semantics survive.
            p=Path(d)/'x.csv'; p.write_bytes(b'A,B\n1,"line one\nline two"\n')
            import csv
            with p.open('r', newline='') as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(rows[0]['B'],'line one\nline two')

    def test_non_utf8_refused(self):
        self.assertEqual(self.parse(b'A,B\n1,\xff\n')['status'],'AMBIGUOUS_CSV')

    def test_ledger_realistic_money_arithmetic(self):
        rows=[
            {'BetID':'a','Result':'WIN','Stake':'10','Profit':'6.62','Bet Price':'-151'},
            {'BetID':'b','Result':'LOSS','Stake':'7.32','Profit':'-7.32','Bet Price':'+803'},
            {'BetID':'c','Result':'LOSS','Stake':'10','Profit':'-10','Bet Price':'+395 boosted'},
        ]
        z=audit_ledger(rows)
        self.assertEqual(z['noncanonical_american_odds'],1)
        self.assertEqual(len(z['arithmetic_issues']),0)
        self.assertEqual(z['recorded_profit'],'-10.70')
        self.assertEqual(z['duplicate_bet_id_groups'],0)

    def test_dup_bet_id_flagged(self):
        rows=[{'BetID':'a','Result':'LOSS','Stake':'1','Profit':'-1','Bet Price':'-110'}]*2
        self.assertEqual(audit_ledger(rows)['duplicate_bet_id_groups'],1)

    def test_gated_placeholders_not_forecasts(self):
        rows=[{'Pulled_CT':'#N/A','GameID':'','Market':'','Grade':'GATED','Stake_u':'0'} for _ in range(5)]
        z=audit_models(rows)
        self.assertEqual(z['complete_price_and_probability'],0)
        self.assertEqual(z['zero_stake_rows'],5)

    def test_derived_rows_never_called_bets(self):
        d=audit_other('PICKS_DERIVED', [{'game':'a','pick':'Home -5.5'},{'game':'a','pick':'Away +5.5'}])
        self.assertEqual(d['classification'],'DERIVED_TWO_SIDED_PRICE_ROWS_NOT_INDEPENDENT_BETS')

if __name__=='__main__':unittest.main(verbosity=2)