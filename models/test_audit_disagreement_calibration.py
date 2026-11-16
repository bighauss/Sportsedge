import unittest
from audit_disagreement_calibration import audit
H="a"*64
def row(**changes):
 r=dict(event_id="e",market="moneyline",selection="home",model_p=".6",market_p=".5",outcome="1",snapshot_utc="2026-11-15T20:00:00Z",kickoff_utc="2026-11-15T21:00:00Z",final_utc="2026-11-16T00:00:00Z",model_sha256=H,source_sha256=H,odds="-110")
 r.update(changes);return r
class Tests(unittest.TestCase):
 def test_good(self):
  a=audit([row()]);self.assertEqual(a["accepted"],1);self.assertEqual(a["overall"]["brier"],.16)
 def test_lookahead(self):
  a=audit([row(snapshot_utc="2026-11-15T22:00:00Z")]);self.assertEqual(a["accepted"],0)
 def test_missing_hash(self):
  a=audit([row(source_sha256="bad")]);self.assertEqual(a["accepted"],0)
 def test_duplicate(self):
  a=audit([row(),row()]);self.assertEqual(a["accepted"],1);self.assertEqual(len(a["blocked"]),1)
 def test_push(self):self.assertEqual(audit([row(outcome="push")])["accepted"],0)
 def test_naive(self):self.assertEqual(audit([row(snapshot_utc="2026-11-15T20:00:00")])["accepted"],0)
 def test_invalid_probability(self):self.assertEqual(audit([row(model_p="1.2")])["accepted"],0)
 def test_market_split(self):
  a=audit([row(),row(event_id="e2",market_p=".7",outcome="0")])
  self.assertEqual(a["accepted"],2);self.assertEqual(len(a["disagreement"]),2)
 def test_deciles(self):
  a=audit([row(),row(event_id="e2",model_p=".21",outcome="0")])
  self.assertEqual([x["decile"] for x in a["calibration"]],[2,6])
 def test_exact_ten_pp(self):
  from audit_disagreement_calibration import bucket
  self.assertEqual(bucket(.6-.5),"10-20pp")
 def test_roi_and_ci(self):
  a=audit([row()])
  self.assertAlmostEqual(a["overall"]["roi"],100/110)
  self.assertTrue(a["overall"]["insufficient_n30"])
  self.assertEqual(len(a["overall"]["observed_wilson_95"]),2)
 def test_stats_after_odds_tuple_expansion(self):
  a=audit([row(),row(event_id="second",model_p=".4",market_p=".3",outcome="0",odds="+250")])
  self.assertEqual(a["accepted"],2)
  self.assertEqual(a["overall"]["market_brier"],.17)
  self.assertAlmostEqual(a["overall"]["roi"],(100/110-1)/2,places=5)
  self.assertTrue(all(k in a["overall"] for k in ("market_log_loss","bias","observed","predicted")))
 def test_n30_and_wilson_bounds(self):
  a=audit([row(event_id=str(i),outcome="1" if i<15 else "0") for i in range(30)])
  self.assertFalse(a["overall"]["insufficient_n30"])
  self.assertLess(a["overall"]["observed_wilson_95"][0],.5)
  self.assertGreater(a["overall"]["observed_wilson_95"][1],.5)
 def test_invalid_odds(self):
  self.assertEqual(audit([row(odds="0")])["accepted"],0)
if __name__=="__main__":unittest.main()
