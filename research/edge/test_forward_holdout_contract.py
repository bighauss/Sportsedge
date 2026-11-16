import unittest
from research.edge.forward_holdout_contract import evaluate, Hold
H="a"*64
F={"status":"PREREGISTERED_PAPER","official":False,"model_sha256":H,"registered_utc":"2026-11-15T16:00:00Z"}
def row():
    return {"event_id":"1","market_id":"ml","period":"FG","selection":"home","line":"0",
            "feature_available_utc":"2026-11-15T16:30:00Z","freeze_utc":"2026-11-15T17:00:00Z",
            "event_start_utc":"2026-11-15T18:00:00Z","model_sha256":H,
            "outcome":1,"model_p":.7,"book_p":.6}
class Tests(unittest.TestCase):
    def test_valid(self):
        x=evaluate(F,[row()]);self.assertEqual(x["denominator"],1);self.assertFalse(x["official"])
    def test_duplicate(self):
        with self.assertRaisesRegex(Hold,"DUPLICATE"):evaluate(F,[row(),row()])
    def test_future_feature(self):
        r=row();r["feature_available_utc"]="2026-11-15T17:01:00Z"
        with self.assertRaisesRegex(Hold,"LOOKAHEAD"):evaluate(F,[r])
    def test_post_event_freeze(self):
        r=row();r["freeze_utc"]=r["event_start_utc"]
        with self.assertRaisesRegex(Hold,"LOOKAHEAD"):evaluate(F,[r])
    def test_model_changed(self):
        r=row();r["model_sha256"]="b"*64
        with self.assertRaisesRegex(Hold,"MODEL_CHANGED"):evaluate(F,[r])
    def test_unsettled_preserved(self):
        r=row();r["outcome"]=None;x=evaluate(F,[r]);self.assertEqual((x["denominator"],x["unsettled"],x["scored"]),(1,1,0))
    def test_nan(self):
        r=row();r["model_p"]=float("nan")
        with self.assertRaisesRegex(Hold,"PROBABILITY_INVALID"):evaluate(F,[r])
    def test_boolean_probability(self):
        r=row();r["model_p"]=True
        with self.assertRaisesRegex(Hold,"PROBABILITY_INVALID"):evaluate(F,[r])
    def test_boolean_outcome(self):
        r=row();r["outcome"]=True
        with self.assertRaisesRegex(Hold,"OUTCOME_INVALID"):evaluate(F,[r])
    def test_paper_only(self):
        f=dict(F,official=True)
        with self.assertRaisesRegex(Hold,"PAPER_FREEZE"):evaluate(f,[row()])
if __name__=="__main__":unittest.main()
