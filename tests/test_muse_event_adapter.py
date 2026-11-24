import csv,hashlib,importlib.util,io,json,tempfile,unittest
from pathlib import Path
from research.market_implied.muse_event_adapter import load_verified_events

class EventAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=Path(self.tmp.name)
        self.event=dict(dk_event_id='123',home='A',away='B',tipoff_ct='2026-11-24T09:00:00-06:00')
        self.contracts=[]
        for i,(market,line) in enumerate([('SPREAD',-1.5),('TOTAL',146.5),('ML','')],1):
            self.contracts.append(dict(self.event,board_row=i,sport='CBB',market=market,line=line,price_a=-110,price_b=-110,period='FULL_GAME',source_comment_id=1,capture_start_ct='2026-11-24T05:46:00-06:00',capture_end_ct='2026-11-24T05:47:59.999999-06:00',eligible_for_pricing=False,settlement_rules_verified=False))
        self.events=[dict(self.event,cbbd_game_id=None,neutral=None)]
        self.manifest=dict(source_kind='GITHUB_RELAY_NOT_BOOK_RECEIPT',primary_totals_gate_changed=False,forecast_execution_complete=False,approved_stake_u=0,source_url='https://github.com/bighauss/Sportsedge/issues/57#issuecomment-1',github_author_id=7,games=1,paired_markets=3,offered_sides=6,capture_start_ct=self.contracts[0]['capture_start_ct'],capture_end_ct=self.contracts[0]['capture_end_ct'])
        (self.d/'comment.raw.json').write_text(json.dumps(dict(id=1,html_url=self.manifest['source_url'],user=dict(id=7))))
        self.write()
    def seal(self):
        self.manifest['output_sha256']={name:hashlib.sha256((self.d/name).read_bytes()).hexdigest() for name in ['board.csv','contracts.json','events.json','comment.raw.json']}
        (self.d/'COMPLETE.json').write_text(json.dumps(self.manifest))
        self.pin=hashlib.sha256((self.d/'COMPLETE.json').read_bytes()).hexdigest()
    def write(self):
        columns=['sport','away','home','market','line','price_a','price_b']
        stream=io.StringIO();w=csv.DictWriter(stream,columns);w.writeheader()
        w.writerows([{k:c[k] for k in columns} for c in self.contracts])
        (self.d/'board.csv').write_text(stream.getvalue())
        (self.d/'contracts.json').write_text(json.dumps(self.contracts));(self.d/'events.json').write_text(json.dumps(self.events));self.seal()
    def load(self):return load_verified_events(self.d,manifest_sha256=self.pin,expected_game_count=1)
    def test_three_markets_one_event(self):
        result=self.load();self.assertEqual(result['events'],[self.event]);self.assertEqual(len(result['contracts']),3)
        self.assertIs(result['pricing_authorized'],False)
    def test_conflicting_teams(self):
        self.contracts[1]['home']='C';self.write()
        with self.assertRaises(ValueError):self.load()
    def test_conflicting_tip(self):
        self.contracts[1]['tipoff_ct']='2026-11-24T10:00:00-06:00';self.write()
        with self.assertRaises(ValueError):self.load()
    def test_csv_value_mismatch_even_when_rehashed(self):
        path=self.d/'board.csv';path.write_text(path.read_text().replace('-110','-115',1));self.seal()
        with self.assertRaises(ValueError):self.load()
    def test_duplicate_event_sidecar(self):
        self.events*=2;self.write()
        with self.assertRaises(ValueError):self.load()
    def test_bad_row_ordinal(self):
        self.contracts[1]['board_row']=1;self.write()
        with self.assertRaises(ValueError):self.load()
    def test_pricing_flag_cannot_be_promoted(self):
        self.contracts[0]['eligible_for_pricing']=True;self.write()
        with self.assertRaises(ValueError):self.load()
    def test_manifest_pin_and_file_digest(self):
        good=self.pin;self.pin='0'*64
        with self.assertRaises(ValueError):self.load()
        self.pin=good;(self.d/'events.json').write_text('[]')
        with self.assertRaises(ValueError):self.load()
    def test_missing_output_digest(self):
        del self.manifest['output_sha256']['board.csv'];(self.d/'COMPLETE.json').write_text(json.dumps(self.manifest));self.pin=hashlib.sha256((self.d/'COMPLETE.json').read_bytes()).hexdigest()
        with self.assertRaises(ValueError):self.load()
    def test_capture_conflict(self):
        self.contracts[2]['capture_start_ct']='2026-11-24T06:00:00-06:00';self.write()
        with self.assertRaises(ValueError):self.load()
    def test_denominator_and_duplicate_market(self):
        self.manifest['offered_sides']=8;self.seal()
        with self.assertRaises(ValueError):self.load()
        self.manifest['offered_sides']=6;self.contracts[1].update(market='SPREAD',line=-1.5);self.write()
        with self.assertRaises(ValueError):self.load()
    @unittest.skipUnless(importlib.util.find_spec('research.cbb_event_binding') is not None,'requires ChatGPT runtime reconciliation module')
    def test_runtime_reconciliation_without_weakening_duplicate_guard(self):
        from research.cbb_event_binding import reconcile
        slate=[dict(game_id='456',_home='A',_away='B',tipoff_utc='2026-11-24T15:00:00Z')]
        self.assertEqual([r['status'] for r in reconcile(self.contracts,slate)],['BLOCKED']*3)
        result=reconcile(self.load()['events'],slate)
        self.assertEqual(result,[dict(dk_event_id='123',status='MATCHED',cbbd_game_id='456')])
