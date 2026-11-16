import unittest
from research.evidence.source_lineage_gate import inspect_pair,Refused
def fixture():
    common=dict(event_id="E",market_id="M",selection_id="OVER",opposite_selection_id="UNDER",line="49.5",price="-110",opposite_price="-110",observed_utc="2026-11-15T18:00:00Z",captured_utc="2026-11-15T18:00:01Z",decision_utc="2026-11-15T18:00:02Z",kickoff_utc="2026-11-15T19:00:00Z",raw_sha256="a"*64,status="OPEN")
    return [{**common,"source_id":"A","upstream_operator_id":"DK","aggregator_id":"direct-dk","book_id":"DK","receipt_id":"R1"},{**common,"source_id":"B","upstream_operator_id":"FD","aggregator_id":"direct-fd","book_id":"FD","receipt_id":"R2"}]
class TestLineage(unittest.TestCase):
    def test_paper_only(self):
        self.assertFalse(inspect_pair(fixture())["authenticated"])
    def test_same_aggregator(self):
        r=fixture();r[1]["aggregator_id"]=r[0]["aggregator_id"]
        with self.assertRaisesRegex(Refused,"NOT_INDEPENDENT"):inspect_pair(r)
    def test_same_upstream(self):
        r=fixture();r[1]["upstream_operator_id"]="dk"
        with self.assertRaisesRegex(Refused,"NOT_INDEPENDENT"):inspect_pair(r)
    def test_stale(self):
        r=fixture();r[0]["observed_utc"]="2026-11-15T17:00:00Z"
        with self.assertRaisesRegex(Refused,"STALE"):inspect_pair(r)
    def test_live(self):
        r=fixture();r[0]["decision_utc"]=r[0]["kickoff_utc"]
        with self.assertRaisesRegex(Refused,"LOOKAHEAD"):inspect_pair(r)
    def test_market_mismatch(self):
        r=fixture();r[1]["line"]="50.5"
        with self.assertRaisesRegex(Refused,"MISMATCH"):inspect_pair(r)
    def test_missing_field(self):
        r=fixture();del r[0]["book_id"]
        with self.assertRaisesRegex(Refused,"SCHEMA"):inspect_pair(r)
    def test_nan(self):
        r=fixture();r[0]["line"]="NaN"
        with self.assertRaisesRegex(Refused,"INVALID_NUMBER"):inspect_pair(r)
    def test_suspended(self):
        r=fixture();r[0]["status"]="SUSPENDED"
        with self.assertRaisesRegex(Refused,"NOT_OPEN"):inspect_pair(r)
    def test_bool_policy(self):
        with self.assertRaisesRegex(Refused,"AGE_POLICY"):inspect_pair(fixture(),True)
if __name__=="__main__":unittest.main()
