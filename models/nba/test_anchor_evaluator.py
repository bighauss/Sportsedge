import unittest
from anchor_evaluator import run
H="b"*64
def row(i=1,**kw):
    r=dict(event_id=str(i),market="NBA:PTS",selection="OVER",model_p=".7",market_p=".5",
           snapshot_utc="2026-11-15T12:00:00Z",baseline_utc="2026-11-15T11:00:00Z",
           tipoff_utc="2026-11-16T01:00:00Z",final_utc="2026-11-16T04:00:00Z",
           result="1",model_sha256=H,baseline_sha256=H,baseline_books="A;B")
    r.update(kw);return r
class Tests(unittest.TestCase):
    def test_no_same_night_leakage(self):
        r=run([row(1),row(2)],1)
        self.assertEqual([x["chosen_weight"] for x in r["walkforward"]["NBA:PTS"]],[0,0])
    def test_earlier_final_can_inform_later(self):
        r=run([row(),row(2,snapshot_utc="2026-11-17T12:00:00Z",baseline_utc="2026-11-17T11:00:00Z",
                 tipoff_utc="2026-11-18T01:00:00Z",final_utc="2026-11-18T04:00:00Z")],1)
        self.assertEqual(r["walkforward"]["NBA:PTS"][1]["chosen_weight"],1)
    def test_invalid_baseline_and_future(self):
        r=run([row(baseline_books="DK"),row(2,baseline_utc="2026-11-16T03:00:00Z")])
        self.assertEqual(r["accepted"],0)
    def test_per_market(self):
        r=run([row(),row(2,market="NBA:REB")])
        self.assertEqual(len(r["markets"]),2)
        self.assertTrue(all(x["insufficient_n30"] for x in r["markets"]))
if __name__=="__main__":unittest.main()
