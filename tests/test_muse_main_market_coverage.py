"""Synthetic artifact tests: main-board completeness, not sportsbook authentication."""
import csv,hashlib,io,json,tempfile,unittest
from pathlib import Path
from research.market_implied.muse_event_adapter import load_verified_events

class MainMarketCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=Path(self.tmp.name)
        self.event=dict(dk_event_id='123',home='A',away='B',tipoff_ct='2026-11-24T09:00:00-06:00')
        self.contracts=[dict(self.event,sport='CBB',market=m,line=l,price_a=-110,price_b=-110,period='FULL_GAME',source_comment_id=1,capture_start_ct='2026-11-24T05:46:00-06:00',capture_end_ct='2026-11-24T05:47:59.999999-06:00',eligible_for_pricing=False,settlement_rules_verified=False) for m,l in [('SPREAD',-1.5),('TOTAL',146.5),('ML','')]]
    def load(self):
        for i,c in enumerate(self.contracts,1):c['board_row']=i
        columns=['sport','away','home','market','line','price_a','price_b']
        text=io.StringIO();w=csv.DictWriter(text,columns);w.writeheader();w.writerows([{k:c[k] for k in columns} for c in self.contracts])
        url='https://github.com/bighauss/Sportsedge/issues/57#issuecomment-1'
        files={'board.csv':text.getvalue().encode(),'contracts.json':json.dumps(self.contracts).encode(),'events.json':json.dumps([self.event]).encode(),'comment.raw.json':json.dumps(dict(id=1,html_url=url,user=dict(id=7))).encode()}
        manifest=dict(source_kind='GITHUB_RELAY_NOT_BOOK_RECEIPT',primary_totals_gate_changed=False,forecast_execution_complete=False,approved_stake_u=0,source_url=url,github_author_id=7,games=1,paired_markets=len(self.contracts),offered_sides=2*len(self.contracts),capture_start_ct=self.contracts[0]['capture_start_ct'],capture_end_ct=self.contracts[0]['capture_end_ct'],output_sha256={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
        for name,raw in files.items():(self.d/name).write_bytes(raw)
        raw=json.dumps(manifest).encode();(self.d/'COMPLETE.json').write_bytes(raw)
        return load_verified_events(self.d,manifest_sha256=hashlib.sha256(raw).hexdigest(),expected_game_count=1)
    def test_missing_spread_rejected(self):
        self.contracts=[c for c in self.contracts if c['market']!='SPREAD']
        with self.assertRaisesRegex(ValueError,'main market coverage'):self.load()
    def test_missing_total_rejected(self):
        self.contracts=[c for c in self.contracts if c['market']!='TOTAL']
        with self.assertRaisesRegex(ValueError,'main market coverage'):self.load()
    def test_second_spread_line_rejected(self):
        self.contracts.append(dict(self.contracts[0],line=-2.5))
        with self.assertRaisesRegex(ValueError,'multiple main lines'):self.load()
    def test_second_total_line_rejected(self):
        self.contracts.append(dict(self.contracts[1],line=147.5))
        with self.assertRaisesRegex(ValueError,'multiple main lines'):self.load()
    def test_missing_moneyline_allowed(self):
        self.contracts=[c for c in self.contracts if c['market']!='ML']
        result=self.load();self.assertEqual(len(result['events']),1);self.assertEqual(len(result['contracts']),2)
        self.assertIs(result['pricing_authorized'],False)
    def test_complete_main_board_allowed(self):
        result=self.load();self.assertEqual(len(result['contracts']),3)
        self.assertIs(result['settlement_rules_verified'],False)
