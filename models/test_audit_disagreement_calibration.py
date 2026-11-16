import unittest
from audit_disagreement_calibration import audit
H="a"*64
def row(**changes):
 r=dict(event_id="e",market="moneyline",selection="home",model_p=".6",market_p=".5",outcome="1",snapshot_utc="2026-11-15T20:00:00Z",kickoff_utc="2026-11-15T21:00:00Z",final_utc="2026-11-16T00:00:00Z",model_sha256=H,source_sha256=H)
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
if __name__=="__main__":unittest.main()
