import unittest,sys,csv,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import guarded_v5_receipt_runner as m
from test_repair_r1 import fixture,SHA
from test_close_pair import example

class RunnerTests(unittest.TestCase):
 def setUp(self):
  self.board=example();self.board.update(home_proj='80',away_proj='75')
  self.a=fixture();self.a.update(sport='CBB',event_id=self.board['event_id'],book='DK',team_id='HOME',
    home_team_id='HOME',away_team_id='AWAY',source_home_team_id='HOME',source_away_team_id='AWAY',
    side='home',line='-18.5',quote_id='q1',quote_receipt_sha256=SHA,
    captured_at_utc='2026-11-16T17:00:00Z',game_start_utc='2026-11-16T20:00:00Z',
    model_prediction_at_utc='2026-11-16T16:40:00Z',features_asof_utc='2026-11-16T16:35:00Z',
    decision_at_utc='2026-11-16T17:02:00Z',venue_verified_at_utc='2026-11-16T15:00:00Z',
    max_quote_age_minutes='5',book_home_spread='-4.5',status='PAPER')
  self.b={**self.a,'side':'away','team_id':'AWAY','line':'18.5','quote_id':'q2','snapshot_id':'frozen-2'}
 def test_full_research_preflight_without_running_engine(self):
  with tempfile.TemporaryDirectory() as d:
   board_path=Path(d)/'board.csv';snapshot_path=Path(d)/'snap.csv'
   for rec in (self.a,self.b):rec['model_sha256']=m.V5_SHA
   for path,rows in ((board_path,[self.board]),(snapshot_path,[self.a,self.b])):
    with open(path,'w',newline='') as f:
     w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
   engine=Path(__file__).resolve().parents[4]/'engine'/'sportsedge_v5.py'
   result=m.run(board_path,snapshot_path,engine,Path(d)/'output',run_engine=False)
   self.assertEqual(result['verdict'],'PREFLIGHT_PASS_RESEARCH_ONLY')
   self.assertEqual(result['official_counted'],0)
   self.assertFalse((Path(d)/'output'/'guarded_v5').exists())
 def test_linkage_clean(self):
  res=m.validate_linkage([self.board],[self.a,self.b],SHA)
  self.assertEqual(res['verdict'],'PASS');self.assertEqual(res['matched_endpoints'],2)
 def test_price_tamper(self):
  self.b['odds_american']='-115'
  self.assertIn('BOARD_QUOTE_PRICE_DIFFERS_FROM_RECEIPT',str(m.validate_linkage([self.board],[self.a,self.b],SHA)['issues']))
 def test_id_tamper(self):
  self.b['event_id']='different'
  self.assertIn('RECEIPT_MARKET_OR_SELECTION_MISMATCH',str(m.validate_linkage([self.board],[self.a,self.b],SHA)['issues']))
 def test_quote_tamper(self):
  self.board['quote_id_b']='different'
  self.assertIn('PRICE_ENDPOINT_HAS_NO_FROZEN_RECEIPT',str(m.validate_linkage([self.board],[self.a,self.b],SHA)['issues']))
 def test_unlinked_price_disallowed(self):
  self.assertIn('PRICE_ENDPOINT_HAS_NO_FROZEN_RECEIPT',str(m.validate_linkage([self.board],[],SHA)['issues']))
 def test_projection_tamper(self):
  self.board['home_proj']='81'
  self.assertIn('BOARD_PROJECTION_DIFFERS_FROM_FROZEN_RECEIPT',str(m.validate_linkage([self.board],[self.a,self.b],SHA)['issues']))
 def test_engine_sha_mismatch(self):
  self.assertIn('MODEL_SHA_NOT_PINNED_TO_V5',str(m.validate_linkage([self.board],[self.a,self.b],'0'*64)['issues']))
 def test_legacy_board_blocked(self):
  self.board.pop('event_id')
  self.assertIn('MISSING:event_id',str(m.validate_linkage([self.board],[self.a,self.b],SHA)['issues']))

if __name__=='__main__':unittest.main()
