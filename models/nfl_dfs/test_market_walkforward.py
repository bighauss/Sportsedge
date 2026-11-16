import unittest
from market_walkforward import parse,report
H="a"*64
def row(i=1,**v):
    d=dict(event_id=str(i),market="NFL:passing_yards",selection="over",
           snapshot_utc="2026-11-15T16:00:00Z",baseline_utc="2026-11-15T15:00:00Z",
           kickoff_utc="2026-11-15T20:00:00Z",settled_utc="2026-11-15T23:00:00Z",
           model_p=".60",baseline_p=".50",outcome="1",model_sha256=H,
           baseline_sha256=H,baseline_books="SHARP_A;SHARP_B")
    d.update(v);return d

class Tests(unittest.TestCase):
    def test_no_prior_settled_means_baseline(self):
        a=report([row(i) for i in range(3)],min_prior=1)
        self.assertEqual(a["accepted"],3)
        self.assertTrue(all(v["anchor_weight"]==0 for v in a["predictions"]["NFL:passing_yards"]))
    def test_asof_weights_only_previous_finals(self):
        a=report([row(1),row(2,snapshot_utc="2026-11-16T16:00:00Z",baseline_utc="2026-11-16T15:00:00Z",
                              kickoff_utc="2026-11-16T20:00:00Z",settled_utc="2026-11-16T23:00:00Z")],min_prior=1)
        p=a["predictions"]["NFL:passing_yards"]
        self.assertEqual([x["prior_settled"] for x in p],[0,1])
        self.assertEqual(p[1]["anchor_weight"],1.)
    def test_duplicate_selection_even_new_snapshot_blocked(self):
        a=report([row(),row(snapshot_utc="2026-11-15T17:00:00Z")])
        self.assertEqual(a["accepted"],1)
        self.assertEqual(a["blocked"][0]["reason"],"DUPLICATE_SELECTION")
    def test_one_book_not_independent(self):
        a=report([row(baseline_books="DRAFTKINGS")])
        self.assertEqual(a["accepted"],0)
    def test_hash_lookahead_and_push(self):
        a=report([row(model_sha256="bad"),row(2,baseline_utc="2026-11-15T19:00:00Z"),
                  row(3,outcome="push")])
        self.assertEqual(a["accepted"],0)
    def test_market_separate(self):
        a=report([row(),row(2,market="NFL:rushing_yards")])
        self.assertEqual(len(a["markets"]),2)
        self.assertEqual(a["status"],"RESEARCH_ONLY_PAPER_0U_NO_PROMOTION")
if __name__=="__main__":unittest.main()
