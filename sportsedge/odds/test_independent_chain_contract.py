import unittest
from sportsedge.odds.independent_chain_contract import inspect, ChainHold

def pair():
    base = dict(sport="NFL",event_id="e1",market="total",period="FG",
                participant_id="game",side="over",line=47.5,settlement_rule="standard",
                source_attestation="EXTERNAL_VERIFIED",
                provider_observed_utc="2026-11-16T01:00:00Z",
                local_captured_utc="2026-11-16T01:00:20Z")
    return (dict(base,bookmaker_id="DK",upstream_chain_id="dk-direct",
                 transport_id="auth-dk",original_receipt_id="r1",original_sha256="a"*64),
            dict(base,bookmaker_id="OTHER",upstream_chain_id="other-direct",
                 transport_id="auth-other",original_receipt_id="r2",original_sha256="b"*64))
def run(a,b):
    return inspect(a,b,decision_utc="2026-11-16T01:01:00Z")

class IndependentChainTests(unittest.TestCase):
    def test_shape_only_never_promotes(self):
        a,b=pair();self.assertFalse(run(a,b)["official"])
    def test_same_aggregator_two_logos(self):
        a,b=pair();b["upstream_chain_id"]=a["upstream_chain_id"]
        with self.assertRaisesRegex(ChainHold,"SHARED_UPSTREAM_CHAIN"):run(a,b)
    def test_same_book_different_logo(self):
        a,b=pair();b["bookmaker_id"]="DK"
        with self.assertRaisesRegex(ChainHold,"SAME_BOOKMAKER"):run(a,b)
    def test_no_external_attestation(self):
        a,b=pair();a["source_attestation"]="SELF_REPORTED"
        with self.assertRaisesRegex(ChainHold,"EXTERNAL_ATTESTATION_MISSING"):run(a,b)
    def test_different_line(self):
        a,b=pair();b["line"]=48.5
        with self.assertRaisesRegex(ChainHold,"EXACT_SELECTION_MISMATCH"):run(a,b)
    def test_malformed_line(self):
        a,b=pair();a["line"]=[]
        with self.assertRaisesRegex(ChainHold,"SELECTION_IDENTITY_INVALID"):run(a,b)
    def test_nan_line(self):
        a,b=pair();a["line"]=float("nan")
        with self.assertRaisesRegex(ChainHold,"SELECTION_IDENTITY_INVALID"):run(a,b)
    def test_missing_original_hash(self):
        a,b=pair();a["original_sha256"]=""
        with self.assertRaisesRegex(ChainHold,"ORIGINAL_HASH_INVALID"):run(a,b)
    def test_same_original(self):
        a,b=pair();b["original_sha256"]=a["original_sha256"]
        with self.assertRaisesRegex(ChainHold,"DUPLICATE_ORIGINAL_RECEIPT"):run(a,b)
    def test_capture_after_decision(self):
        a,b=pair();b["local_captured_utc"]="2026-11-16T01:02:00Z"
        with self.assertRaisesRegex(ChainHold,"SOURCE_CHRONOLOGY_INVALID"):run(a,b)
    def test_stale(self):
        a,b=pair();a["local_captured_utc"]="2026-11-16T00:50:00Z";a["provider_observed_utc"]="2026-11-16T00:49:00Z"
        with self.assertRaisesRegex(ChainHold,"STALE_SOURCE"):run(a,b)
    def test_missing_transport(self):
        a,b=pair();a["transport_id"]=""
        with self.assertRaisesRegex(ChainHold,"SOURCE_IDENTITY_MISSING"):run(a,b)
if __name__=="__main__":unittest.main()
