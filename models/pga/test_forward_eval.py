import unittest
from forward_eval import evaluate

def row(**kw):
    x=dict(event_id="pga-event-1",market="make_cut",player_id="golfer-1",
           asof_utc="2026-11-14T12:00:00Z",event_start_utc="2026-11-15T12:00:00Z",
           probability=0.6,outcome=1,source_sha256="a"*64,model_sha256="b"*64)
    x.update(kw)
    return x

class ForwardEvalTests(unittest.TestCase):
    def test_brier_and_log_loss(self):
        r=evaluate([row()])
        self.assertAlmostEqual(r["metrics"]["make_cut"]["brier"],0.16)
        self.assertEqual(r["unit_status"],"PAPER_0U")
        self.assertTrue(r["metrics"]["make_cut"]["small_sample"])
    def test_collision_both_blocked(self):
        r=evaluate([row(probability=0.1),row(probability=0.9)])
        self.assertEqual(r["accepted"],0)
        self.assertEqual(len(r["blocked"]),2)
    def test_different_snapshots_distinct(self):
        r=evaluate([row(),row(asof_utc="2026-11-14T13:00:00Z")])
        self.assertEqual(r["accepted"],2)
    def test_post_start_blocked(self):
        self.assertIn("NOT_PREGAME",evaluate([row(asof_utc="2026-11-16T12:00:00Z")])["blocked"][0]["reasons"])
    def test_nonfinite_blocked(self):
        self.assertIn("INVALID_PROBABILITY",evaluate([row(probability=float("nan"))])["blocked"][0]["reasons"])
    def test_bad_outcome_blocked(self):
        self.assertIn("INVALID_OUTCOME",evaluate([row(outcome=True)])["blocked"][0]["reasons"])
    def test_invalid_hash_blocked(self):
        self.assertIn("INVALID_SOURCE_SHA256",evaluate([row(source_sha256="bad")])["blocked"][0]["reasons"])
    def test_bad_row_retained(self):
        self.assertEqual(len(evaluate([None,{}])["blocked"]),2)

if __name__=="__main__":
    unittest.main()
