import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import closing_pair_guard as c
from test_repair_r1 import SHA

def example():
 return dict(event_id='SPORT-2026-11-16-GAME-1',sport='CBB',book='DK',home_team_id='HOME',away_team_id='AWAY',
  market='SPREAD',price_a='-110',price_b='-110',line='-18.5',
  captured_at_utc='2026-11-16T17:00:00Z',game_start_utc='2026-11-16T20:00:00Z',
  quote_id_a='q1',quote_id_b='q2',receipt_sha_a=SHA,receipt_sha_b=SHA)

class ClosePairTests(unittest.TestCase):
 def test_spread_two_sides(self):
  a,b=c.convert_two_sided(example());self.assertEqual((a['side'],a['line'],b['side'],b['line']),('home','-18.5','away','18.5'))
 def test_total_two_sides(self):
  r=example();r.update(market='TOTAL',line='153.5');a,b=c.convert_two_sided(r);self.assertEqual((a['side'],b['side']),('over','under'))
 def test_moneyline_blanks(self):
  r=example();r.update(market='ML',line='');a,b=c.convert_two_sided(r);self.assertEqual(a['line'],'0')
 def test_half_period(self):
  r=example();r.update(market='1H_TOTAL',line='75.5');a,b=c.convert_two_sided(r);self.assertEqual(a['period'],'1H')
 def test_period_conflict(self):
  r=example();r.update(market='1H_TOTAL',line='75.5',period='FG');
  with self.assertRaisesRegex(ValueError,'PERIOD_CONFLICT'):c.convert_two_sided(r)
 def test_missing_event_id(self):
  r=example();r.pop('event_id')
  with self.assertRaisesRegex(ValueError,'MISSING:event_id'):c.convert_two_sided(r)
 def test_after_kickoff(self):
  r=example();r['captured_at_utc']='2026-11-16T20:00:00Z'
  with self.assertRaisesRegex(ValueError,'AFTER_KICKOFF'):c.convert_two_sided(r)
 def test_invalid_receipt(self):
  r=example();r['receipt_sha_a']='x'
  with self.assertRaisesRegex(ValueError,'MISSING_RECEIPT_HASH'):c.convert_two_sided(r)
 def test_normalized_ml_empty_zero_same(self):
  a={'event_id':'g1','sport':'NBA','market':'ML','period':'FG','side':'Home','line':'','team_id':'home','book':'DK'}
  b={**a,'market':'ml','side':'home','line':'0','book':'dk'}
  self.assertEqual(c.selection_key(a),c.selection_key(b))
 def test_separate_game_not_duplicate(self):
  a={'event_id':'g1','sport':'NBA','market':'ML','period':'FG','side':'Home','line':'','team_id':'home','book':'DK'}
  self.assertNotEqual(c.selection_key(a),c.selection_key({**a,'event_id':'g2'}))
 def test_two_snapshots_one_bet(self):
  a,b=c.convert_two_sided(example())
  newer={**a,'quote_id':'q3','odds_american':'-105','captured_at_utc':'2026-11-16T18:00:00+00:00'}
  result=c.match_closes([a],[a,newer]);self.assertEqual(len(result['matched']),1)
  self.assertEqual(result['matched'][0]['closing_price'],'-105')
 def test_double_count_rejected(self):
  a,b=c.convert_two_sided(example());result=c.match_closes([a,a],[a]);self.assertIn('DUPLICATE_ENTRY_BET',str(result['issues']))
 def test_closer_after_game_rejected(self):
  a,b=c.convert_two_sided(example());late={**a,'captured_at_utc':'2026-11-16T21:00:00Z'}
  self.assertIn('POST_KICKOFF_CLOSE',str(c.match_closes([a],[late])['issues']))
 def test_missing_matching_line(self):
  a,b=c.convert_two_sided(example());b['side']='home'
  self.assertIn('NO_MATCHED_CLOSE',str(c.match_closes([a],[b])['issues']))

if __name__=='__main__':unittest.main()
