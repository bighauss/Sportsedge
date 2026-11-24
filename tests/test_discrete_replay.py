import csv,hashlib,io,json,tempfile,unittest
from pathlib import Path
from research.market_implied.discrete_replay import discrete_bins,integer_outcomes,reference_two_way,replay,research_ev_bounds,write_evidence
from research.market_implied import devig

class DiscreteReplayTests(unittest.TestCase):
    def test_missing_rungs_remain_one_bin(self):
        bins,gaps=discrete_bins([(-1.5,.7),(1.5,.6)])
        self.assertEqual(bins[1][:2],[-1,1]);self.assertAlmostEqual(bins[1][2],.1);self.assertEqual(gaps,[[-1.5,1.5,.6,.7]])
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
    def synthetic_replay(self,rows=None,*,changes=None,pin_changes=None,pin_override=None,tamper_receipt=False):
        if rows is None:rows=[['TOTAL','GAME',1.5,-150,130,'MAIN'],['TOTAL','GAME',2.5,150,-170,'ALTERNATE']]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);text=io.StringIO();w=csv.writer(text);w.writerow(['market','subject','line','price_a','price_b','market_role']);w.writerows(rows);raw=text.getvalue().encode();(p/'q.csv').write_bytes(raw)
            code=Path(devig.__file__).read_bytes();blob=hashlib.sha1(b'blob '+str(len(code)).encode()+b'\0'+code).hexdigest()
            meta=dict(csv_sha256=hashlib.sha256(raw).hexdigest(),engine_git_blob=blob,paired_quotes=len(rows),away='A',home='B',event_id='synthetic',source_url='synthetic',input_origin='synthetic test',capture_start_ct='2026-11-24T05:49:00-06:00',capture_end_ct='2026-11-24T05:58:00-06:00',tipoff_ct='2026-11-24T10:00:00-06:00',eligible_for_pricing=False,settlement_rules_verified=False,external_consensus_eligible=False,approved_stake_u=0)
            meta.update(changes or {});receipt=json.dumps(meta).encode();(p/'r.json').write_bytes(receipt)
            pin=dict(version=1,receipt_sha256=hashlib.sha256(receipt).hexdigest(),fixture_sha256=hashlib.sha256(raw).hexdigest(),engine_git_blob=blob,event_id='synthetic',expected_ladders=[['TOTAL','GAME']]);pin.update(pin_changes or {})
            manifest=json.dumps(pin).encode();(p/'m.json').write_bytes(manifest)
            if tamper_receipt:(p/'r.json').write_bytes(receipt+b' ')
            return replay(p/'q.csv',p/'r.json',manifest=p/'m.json',manifest_sha256=pin_override or hashlib.sha256(manifest).hexdigest())
    def test_inconsistent_priced_ladder_rejected(self):
        with self.assertRaisesRegex(ValueError,'survival'):self.synthetic_replay([['TOTAL','GAME',1.5,150,-170,'MAIN'],['TOTAL','GAME',2.5,-150,130,'ALTERNATE']])
    def test_conflicting_prices_at_same_rung_rejected(self):
        with self.assertRaisesRegex(ValueError,'conflicting'):self.synthetic_replay([['TOTAL','GAME',1.5,-110,-110,'MAIN'],['TOTAL','GAME',1.5,-120,100,'ALTERNATE']])
    def test_valid_replay_keeps_guards_false(self):
        _,_,audit=self.synthetic_replay();self.assertEqual(audit['evaluations'],8);self.assertIs(audit['eligible_for_pricing'],False);self.assertIs(audit['external_consensus_eligible'],False)
    def test_wrong_manifest_pin_rejected(self):
        with self.assertRaisesRegex(ValueError,'manifest digest'):self.synthetic_replay(pin_override='0'*64)
    def test_receipt_tampering_rejected(self):
        with self.assertRaisesRegex(ValueError,'receipt binding'):self.synthetic_replay(tamper_receipt=True)
    def test_fixture_manifest_binding(self):
        with self.assertRaisesRegex(ValueError,'fixture digest'):self.synthetic_replay(pin_changes={'fixture_sha256':'0'*64})
    def test_event_binding(self):
        with self.assertRaisesRegex(ValueError,'event binding'):self.synthetic_replay(pin_changes={'event_id':'other'})
    def test_capture_after_tipoff_rejected(self):
        with self.assertRaisesRegex(ValueError,'before tipoff'):self.synthetic_replay(changes={'capture_end_ct':'2026-11-24T10:01:00-06:00'})
    def test_capture_at_tipoff_rejected(self):
        with self.assertRaisesRegex(ValueError,'before tipoff'):self.synthetic_replay(changes={'capture_end_ct':'2026-11-24T10:00:00-06:00'})
    def test_reversed_capture_rejected(self):
        with self.assertRaisesRegex(ValueError,'before tipoff'):self.synthetic_replay(changes={'capture_start_ct':'2026-11-24T06:00:00-06:00'})
    def test_naive_capture_rejected(self):
        with self.assertRaisesRegex(ValueError,'chronology'):self.synthetic_replay(changes={'capture_start_ct':'2026-11-24T05:49:00'})
    def test_missing_main_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError,'main anchor'):self.synthetic_replay([['TOTAL','GAME',1.5,-150,130,'ALTERNATE'],['TOTAL','GAME',2.5,150,-170,'ALTERNATE']])
    def test_multiple_main_anchors_rejected(self):
        with self.assertRaisesRegex(ValueError,'main anchor'):self.synthetic_replay([['TOTAL','GAME',1.5,-150,130,'MAIN'],['TOTAL','GAME',2.5,150,-170,'MAIN']])
    def test_missing_expected_ladder_rejected(self):
        with self.assertRaisesRegex(ValueError,'main anchor'):self.synthetic_replay(pin_changes={'expected_ladders':[['TOTAL','GAME'],['TEAM_TOTAL','A']]})
    def test_evidence_create_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'evidence';audit={'manifest_sha256':'0'*64};write_evidence(p,{}, {},audit);before={f.name:f.read_bytes() for f in p.iterdir()}
            with self.assertRaises(FileExistsError):write_evidence(p,{}, {},audit)
            self.assertEqual(before,{f.name:f.read_bytes() for f in p.iterdir()})
    def test_evidence_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'evidence';complete=write_evidence(p,{}, {},{'manifest_sha256':'0'*64})
            self.assertEqual(complete,json.loads((p/'COMPLETE.json').read_text()))
            for name,digest in complete['output_sha256'].items():self.assertEqual(digest,hashlib.sha256((p/name).read_bytes()).hexdigest())
    def test_incomplete_evidence_has_no_complete_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'evidence'
            with self.assertRaises(ValueError):write_evidence(p,{'bad':float('nan')},{},{'manifest_sha256':'0'*64})
            self.assertFalse((p/'COMPLETE.json').exists())
    def test_ev_bounds_propagate_probability_range(self):
        bounds=research_ev_bounds(100,(.4,.6),p_push=0);self.assertAlmostEqual(bounds['lower'],-.2);self.assertAlmostEqual(bounds['upper'],.2);self.assertIs(bounds['eligible_for_pricing'],False)
    def test_ev_requires_explicit_push(self):
        with self.assertRaises(TypeError):research_ev_bounds(100,(.4,.6))
    def test_ev_rejects_impossible_push(self):
        with self.assertRaises(ValueError):research_ev_bounds(100,(.4,.8),p_push=.3)
    def test_ev_preserves_explicit_push(self):
        bounds=research_ev_bounds(100,(.4,.6),p_push=.2);self.assertAlmostEqual(bounds['lower'],0);self.assertAlmostEqual(bounds['upper'],.4)
