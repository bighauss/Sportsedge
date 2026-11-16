import hashlib
import unittest
from research.odds.offered_universe_contract import census, UniverseHold
RAW=b"synthetic original not a real book response"
def manifest():
    return {"official":False,"stake_u":0,"original_sha256":hashlib.sha256(RAW).hexdigest(),
            "original_offer_count":2,"provider":"synthetic",
            "provider_observed_utc":"2026-11-16T01:00:00Z",
            "local_captured_utc":"2026-11-16T01:00:10Z",
            "event_start_utc":"2026-11-16T02:00:00Z"}
def rows():
    base=dict(sport="NFL",event_id="e",market="total",period="FG",
              participant_id="game",line=47.5,settlement_rule="standard")
    return [dict(base,side="over",status="OFFERED"),
            dict(base,side="under",status="EXCLUDED",exclusion_reason="suspended")]
def run(m=None,r=None,raw=RAW):
    return census(raw,manifest() if m is None else m,rows() if r is None else r)
class Tests(unittest.TestCase):
    def test_valid_census_paper_only(self):
        x=run();self.assertEqual((x["offered"],x["excluded"]),(1,1));self.assertFalse(x["official"])
    def test_missing_row(self):
        with self.assertRaisesRegex(UniverseHold,"DENOMINATOR"):run(r=rows()[:1])
    def test_duplicate_row(self):
        r=rows();r[1]=dict(r[0])
        with self.assertRaisesRegex(UniverseHold,"DUPLICATE"):run(r=r)
    def test_exclusion_without_reason(self):
        r=rows();r[1].pop("exclusion_reason")
        with self.assertRaisesRegex(UniverseHold,"EXCLUSION_REASON"):run(r=r)
    def test_unclassified(self):
        r=rows();r[1]["status"]="UNKNOWN"
        with self.assertRaisesRegex(UniverseHold,"UNCLASSIFIED"):run(r=r)
    def test_hash_mismatch(self):
        with self.assertRaisesRegex(UniverseHold,"HASH_MISMATCH"):run(raw=RAW+b"changed")
    def test_post_event_capture(self):
        m=manifest();m["local_captured_utc"]=m["event_start_utc"]
        with self.assertRaisesRegex(UniverseHold,"CHRONOLOGY"):run(m=m)
    def test_future_observation(self):
        m=manifest();m["provider_observed_utc"]="2026-11-16T01:01:00Z"
        with self.assertRaisesRegex(UniverseHold,"CHRONOLOGY"):run(m=m)
    def test_boolean_denominator(self):
        m=manifest();m["original_offer_count"]=True
        with self.assertRaisesRegex(UniverseHold,"DENOMINATOR"):run(m=m)
    def test_no_official(self):
        m=manifest();m["official"]=True
        with self.assertRaisesRegex(UniverseHold,"PAPER_ONLY"):run(m=m)
    def test_nan_line(self):
        r=rows();r[0]["line"]=float("nan")
        with self.assertRaisesRegex(UniverseHold,"IDENTITY"):run(r=r)
    def test_unsupported_sport(self):
        r=rows();r[0]["sport"]="XYZ"
        with self.assertRaisesRegex(UniverseHold,"SPORT_UNSUPPORTED"):run(r=r)
    def test_contradictory_offered_reason(self):
        r=rows();r[0]["exclusion_reason"]="not really"
        with self.assertRaisesRegex(UniverseHold,"CONTRADICTORY"):run(r=r)
if __name__=="__main__":unittest.main()
