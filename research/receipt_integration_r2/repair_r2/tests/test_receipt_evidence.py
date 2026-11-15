import csv,hashlib,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'repair_r1'/'tests'))
sys.path.insert(0,str(ROOT/'repair_r2'))
from test_repair_r1 import fixture
from test_close_pair import example
import receipt_evidence_gate as gate
import run_guarded_v5_r2 as runner

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.receipts=self.root/'receipts';self.receipts.mkdir()
        self.board=example();self.board.update(home_proj='80',away_proj='75',home='Test Home',away='Test Away',
          player='',team='',proj='',sgp='',side='',home_score='',away_score='',remaining='')
        a=fixture();a.update(event_id=self.board['event_id'],sport='CBB',book='DK',market='SPREAD',period='FG',
           home_team_id='HOME',away_team_id='AWAY',source_home_team_id='HOME',source_away_team_id='AWAY',
           team_id='HOME',side='home',line='-18.5',odds_american='-110',quote_id='q1',
           captured_at_utc='2026-11-16T17:00:00Z',game_start_utc='2026-11-16T20:00:00Z',
           decision_at_utc='2026-11-16T17:02:00Z',model_prediction_at_utc='2026-11-16T16:40:00Z',
           features_asof_utc='2026-11-16T16:35:00Z',venue_verified_at_utc='2026-11-16T15:00:00Z',
           status='PAPER',model_sha256=runner.r1_run.__globals__['V5_SHA'],book_home_spread='-4.5',
           max_quote_age_minutes='5',event_source_id='provider-event-123')
        b={**a,'team_id':'AWAY','side':'away','line':'18.5','quote_id':'q2','snapshot_id':'frozen-2'}
        self.snap=[a,b];self.freeze()
    def freeze(self):
        for i,r in enumerate(self.snap):
            q={k:r.get(k,'') for k in ('event_id','quote_id','book','sport','market','period','side','line','team_id','player_id','odds_american','game_start_utc')}
            q.update(provider='DraftKings',source_url='https://example.org/test-only',
               provider_event_id=r['event_source_id'],observed_at_utc='2026-11-16T16:59:00Z',
               ingested_at_utc='2026-11-16T17:00:00Z')
            b=(json.dumps(q,sort_keys=True)+'\n').encode();h=hashlib.sha256(b).hexdigest()
            (self.receipts/(h+'.json')).write_bytes(b)
            r['quote_receipt_sha256']=h
            self.board['receipt_sha_a' if i==0 else 'receipt_sha_b']=h
        self.snap_path=self.root/'snap.csv';self.board_path=self.root/'board.csv'
        for p,rows in ((self.snap_path,self.snap),(self.board_path,[self.board])):
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    def test_byte_and_row_linkage(self):
        x=gate.audit_evidence(self.snap_path,self.receipts)
        self.assertEqual((x['n_rows'],x['linked_rows'],x['failed_rows']),(2,2,0))
        self.assertFalse(x['externally_authenticated'])
    def test_missing_receipt_fails(self):
        (self.receipts/(self.snap[0]['quote_receipt_sha256']+'.json')).unlink()
        self.assertIn('RAW_QUOTE_RECEIPT_MISSING',str(gate.audit_evidence(self.snap_path,self.receipts)))
    def test_hash_tamper_fails(self):
        p=self.receipts/(self.snap[0]['quote_receipt_sha256']+'.json');p.write_text(p.read_text()+' ')
        self.assertIn('RECEIPT_BYTES_HASH_MISMATCH',str(gate.audit_evidence(self.snap_path,self.receipts)))
    def test_quote_change_without_new_hash_fails(self):
        self.snap[1]['odds_american']='-115'
        with self.snap_path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(self.snap[0]));w.writeheader();w.writerows(self.snap)
        self.assertIn('RECEIPT_ROW_MISMATCH:odds_american',str(gate.audit_evidence(self.snap_path,self.receipts)))
    def test_line_change_fails(self):
        self.snap[0]['line']='-17.5'
        with self.snap_path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(self.snap[0]));w.writeheader();w.writerows(self.snap)
        self.assertIn('RECEIPT_ROW_MISMATCH:line',str(gate.audit_evidence(self.snap_path,self.receipts)))
    def test_start_time_change_without_raw_change_fails(self):
        self.snap[1]['game_start_utc']='2026-11-16T21:00:00Z'
        with self.snap_path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(self.snap[0]));w.writeheader();w.writerows(self.snap)
        self.assertIn('START_TIME_MISMATCH',str(gate.audit_evidence(self.snap_path,self.receipts)))
    def test_wrapper_preflight_reaches_r1(self):
        engine=ROOT.parents[1]/'engine'/'sportsedge_v5.py'
        rep=runner.run(self.board_path,self.snap_path,self.receipts,engine,self.root/'out')
        self.assertEqual(rep['verdict'],'R2_PREFLIGHT_PASS_RESEARCH_ONLY')
        self.assertFalse(rep['engine_invoked'])
        self.assertEqual(rep['official_counted'],0)
    def test_full_synthetic_v5_research_execution(self):
        engine=ROOT.parents[1]/'engine'/'sportsedge_v5.py'
        rep=runner.run(self.board_path,self.snap_path,self.receipts,engine,self.root/'executed',execute=True)
        self.assertEqual(rep['verdict'],'RESEARCH_EXECUTED_NOT_DEPLOYED')
        self.assertTrue(rep['engine_invoked'])
        self.assertEqual(rep['official_counted'],0)
        self.assertTrue((self.root/'executed'/'r1_research'/'guarded_v5'/'picks_research.csv').exists())
    def test_no_claim_of_external_authentication(self):
        rep=gate.audit_evidence(self.snap_path,self.receipts)
        self.assertEqual(rep['verdict'],'BYTE_LINKAGE_PASS_NOT_PROVIDER_AUTHENTICATED')
        self.assertFalse(rep['externally_authenticated'])
    def test_wrapper_missing_receipt_does_not_call_r1(self):
        engine=ROOT.parents[1]/'engine'/'sportsedge_v5.py'
        (self.receipts/(self.snap[0]['quote_receipt_sha256']+'.json')).unlink()
        rep=runner.run(self.board_path,self.snap_path,self.receipts,engine,self.root/'blocked')
        self.assertEqual(rep['verdict'],'BLOCK')
        self.assertFalse((self.root/'blocked'/'r1_research').exists())
    def test_no_overwrite(self):
        engine=ROOT.parents[1]/'engine'/'sportsedge_v5.py'
        runner.run(self.board_path,self.snap_path,self.receipts,engine,self.root/'out')
        with self.assertRaises(FileExistsError):runner.run(self.board_path,self.snap_path,self.receipts,engine,self.root/'out')
    def test_old_snapshot_no_bytes(self):
        # A fabricated SHA alone cannot pass the R2 execution gate.
        self.snap[0]['quote_receipt_sha256']='a'*64
        with self.snap_path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(self.snap[0]));w.writeheader();w.writerows(self.snap)
        self.assertEqual(gate.audit_evidence(self.snap_path,self.receipts)['verdict'],'BLOCK')

    def _rewrite_snap(self):
        with self.snap_path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(self.snap[0]))
            w.writeheader()
            w.writerows(self.snap)

    def test_duplicate_header_blocked_before_receipt_read(self):
        lines = self.snap_path.read_text().splitlines()
        lines[0] += ',quote_id'
        self.snap_path.write_text(chr(10).join(lines) + chr(10))
        result = gate.audit_evidence(self.snap_path, self.receipts)
        self.assertEqual(result['verdict'], 'BLOCK')
        self.assertEqual(result['error'], 'SNAPSHOT_DUPLICATE_HEADER')
        self.assertEqual(result['official_counted'], 0)

    def test_duplicate_header_case_variant_blocked(self):
        lines = self.snap_path.read_text().splitlines()
        lines[0] += ',QUOTE_ID'
        self.snap_path.write_text(chr(10).join(lines) + chr(10))
        self.assertEqual(gate.audit_evidence(self.snap_path, self.receipts)['error'],
                         'SNAPSHOT_DUPLICATE_HEADER')

    def test_underflow_and_overflow_are_blocked(self):
        original = self.snap_path.read_text()
        records = list(csv.reader(original.splitlines()))
        for altered in (records[1][:-1], records[1]+['EXTRA']):
            with self.snap_path.open('w', newline='') as f:
                w = csv.writer(f)
                w.writerow(records[0])
                w.writerow(altered)
            result = gate.audit_evidence(self.snap_path, self.receipts)
            self.assertEqual(result['verdict'], 'BLOCK')
            self.assertEqual(result['error'], 'SNAPSHOT_RAGGED_ROW')
            self.assertEqual(result['official_counted'], 0)

    def test_quote_json_duplicate_key_rejected_before_r1(self):
        old = self.snap[0]['quote_receipt_sha256']
        raw = (self.receipts / (old+'.json')).read_bytes()
        new_raw = raw.replace(b'"quote_id": "q1"', b'"quote_id": "q1", "quote_id": "shadow"', 1)
        self.assertNotEqual(raw, new_raw)
        digest = hashlib.sha256(new_raw).hexdigest()
        (self.receipts / (digest+'.json')).write_bytes(new_raw)
        self.snap[0]['quote_receipt_sha256'] = digest
        self._rewrite_snap()
        result = gate.audit_evidence(self.snap_path, self.receipts)
        self.assertEqual(result['verdict'], 'BLOCK')
        self.assertIn('RECEIPT_DUPLICATE_JSON_KEY:quote_id', str(result))
        self.assertEqual(result['official_counted'], 0)

    def test_same_book_quote_id_distinct_receipts_rejected(self):
        old = self.snap[1]['quote_receipt_sha256']
        q = json.loads((self.receipts / (old+'.json')).read_text())
        q['quote_id'] = 'q1'
        new_raw = (json.dumps(q, sort_keys=True)+chr(10)).encode()
        digest = hashlib.sha256(new_raw).hexdigest()
        (self.receipts / (digest+'.json')).write_bytes(new_raw)
        self.snap[1]['quote_receipt_sha256'] = digest
        self.snap[1]['quote_id'] = 'q1'
        self._rewrite_snap()
        result = gate.audit_evidence(self.snap_path, self.receipts)
        self.assertEqual(result['verdict'], 'BLOCK')
        self.assertIn('DUPLICATE_BOOK_QUOTE_ID', str(result))
        self.assertEqual(result['official_counted'], 0)

    def test_bad_utf8_snapshot_returns_consistent_block_report(self):
        self.snap_path.write_bytes(bytes([0xff, 0xfe, 0xff]))
        result = gate.audit_evidence(self.snap_path, self.receipts)
        self.assertEqual(result['verdict'], 'BLOCK')
        self.assertEqual(result['error'], 'INVALID_SNAPSHOT_CSV')
        self.assertEqual((result['n_rows'], result['official_counted']), (0,0))

if __name__=='__main__':unittest.main()
