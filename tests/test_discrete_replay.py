import csv,hashlib,io,json,tempfile,unittest
from pathlib import Path
from research.market_implied.discrete_replay import discrete_bins,integer_outcomes,reference_two_way,replay
from research.market_implied import devig

class DiscreteReplayTests(unittest.TestCase):
    def test_missing_rungs_remain_one_bin(self):
        bins,gaps=discrete_bins([(-1.5,.7),(1.5,.6)])
        self.assertEqual(bins[1][:2],[-1,1]);self.assertAlmostEqual(bins[1][2],.1)
        self.assertEqual(gaps,[[-1.5,1.5,.6,.7]])
    def test_open_tails_preserved(self):
        bins,_=discrete_bins([(1.5,.8),(2.5,.6)])
        self.assertIsNone(bins[0][0]);self.assertIsNone(bins[-1][1]);self.assertAlmostEqual(sum(x[2] for x in bins),1)
    def test_tail_mass_not_renormalized(self):
        bins,_=discrete_bins([(1.5,.8),(2.5,.6)]);self.assertAlmostEqual(bins[1][2],.2);self.assertAlmostEqual(bins[-1][2],.6)
    def test_increasing_survival_rejected(self):
        with self.assertRaises(ValueError):discrete_bins([(1.5,.4),(2.5,.6)])
    def test_duplicate_threshold_rejected(self):
        with self.assertRaises(ValueError):discrete_bins([(1.5,.4),(1.5,.3)])
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):discrete_bins([(1.5,float('nan')),(2.5,.3)])
    def test_invalid_probability_rejected(self):
        with self.assertRaises(ValueError):discrete_bins([(1.5,1.1),(2.5,.3)])
    def test_integer_anchor_not_treated_as_no_push(self):
        with self.assertRaisesRegex(ValueError,'pushes'):discrete_bins([(1,.8),(2,.6)])
    def test_quarter_line_rejected(self):
        with self.assertRaises(ValueError):discrete_bins([(1.25,.8),(2.5,.6)])
    def test_integer_push_mass(self):
        result=integer_outcomes(2,[(1.5,.8),(2.5,.6)])
        self.assertAlmostEqual(result['push'],.2);self.assertAlmostEqual(result['win'],.6);self.assertAlmostEqual(result['loss'],.2)
    def test_missing_push_neighbors_rejected(self):
        with self.assertRaisesRegex(ValueError,'unidentified'):integer_outcomes(2,[(.5,.8),(2.5,.6)])
    def test_zero_push_only_when_implied(self):
        self.assertEqual(integer_outcomes(2,[(1.5,.6),(2.5,.6)])['push'],0)
    def test_binary_shin_reference_is_additive(self):
        self.assertEqual(reference_two_way([-200,170],'shin'),reference_two_way([-200,170],'additive'))
    def synthetic_replay(self,rows):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);text=io.StringIO();w=csv.writer(text);w.writerow(['market','subject','line','price_a','price_b','market_role']);w.writerows(rows);raw=text.getvalue().encode();(p/'q.csv').write_bytes(raw)
            code=Path(devig.__file__).read_bytes();blob=hashlib.sha1(b'blob '+str(len(code)).encode()+b'\0'+code).hexdigest()
            meta=dict(csv_sha256=hashlib.sha256(raw).hexdigest(),engine_git_blob=blob,paired_quotes=len(rows),away='A',home='B',event_id='synthetic',source_url='synthetic',input_origin='synthetic test',eligible_for_pricing=False,settlement_rules_verified=False,external_consensus_eligible=False,approved_stake_u=0)
            (p/'r.json').write_text(json.dumps(meta));return replay(p/'q.csv',p/'r.json')
    def test_inconsistent_priced_ladder_rejected(self):
        with self.assertRaisesRegex(ValueError,'survival'):self.synthetic_replay([['TOTAL','GAME',1.5,150,-170,'ALTERNATE'],['TOTAL','GAME',2.5,-150,130,'ALTERNATE']])
    def test_conflicting_prices_at_same_rung_rejected(self):
        with self.assertRaisesRegex(ValueError,'conflicting'):self.synthetic_replay([['TOTAL','GAME',1.5,-110,-110,'ALTERNATE'],['TOTAL','GAME',1.5,-120,100,'ALTERNATE']])
    def test_valid_replay_keeps_guards_false(self):
        _,_,audit=self.synthetic_replay([['TOTAL','GAME',1.5,-150,130,'ALTERNATE'],['TOTAL','GAME',2.5,150,-170,'ALTERNATE']])
        self.assertEqual(audit['evaluations'],8);self.assertIs(audit['eligible_for_pricing'],False);self.assertIs(audit['external_consensus_eligible'],False)
