import hashlib
import unittest
from snapshot_gate import validate_snapshot

RAW=b"synthetic provider bytes"
def field():
    return [{"player_id":x,"identity_verified":True,"sg_ott":0.1,"sg_app":0.2,
             "sg_arg":0.0,"sg_putt":0.1,"round_sd":2.8} for x in ("a","b")]
def snap(**kwargs):
    x=dict(provider="SYNTHETIC",event_id="synthetic-tournament",
           captured_utc="2026-11-15T12:00:00Z",event_start_utc="2026-11-16T12:00:00Z",
           source_sha256=hashlib.sha256(RAW).hexdigest(),players=field())
    x.update(kwargs)
    return x

class TestSnapshot(unittest.TestCase):
    def test_valid_evidence_not_model_validation(self):
        r=validate_snapshot(snap(),RAW,provider_verified=True)
        self.assertEqual(r["status"],"PREGAME_EVIDENCE_ONLY_UNCALIBRATED")
        self.assertEqual(r["betting_status"],"PAPER_0U")
    def test_default_blocks_provider(self):
        self.assertIn("PROVIDER_NOT_VERIFIED",validate_snapshot(snap(),RAW)["reasons"])
    def test_hash_mismatch(self):
        self.assertIn("SOURCE_HASH_MISMATCH",validate_snapshot(snap(),b"tampered",provider_verified=True)["reasons"])
    def test_post_start(self):
        self.assertIn("POST_START_CAPTURE",validate_snapshot(snap(captured_utc="2026-11-17T12:00:00Z"),RAW,provider_verified=True)["reasons"])
    def test_duplicate_ids(self):
        p=field();p[1]["player_id"]="a"
        self.assertIn("DUPLICATE_PLAYER",validate_snapshot(snap(players=p),RAW,provider_verified=True)["reasons"])
    def test_unverified_ids(self):
        p=field();p[1]["identity_verified"]=False
        self.assertIn("PLAYER_ID_NOT_VERIFIED",validate_snapshot(snap(players=p),RAW,provider_verified=True)["reasons"])
    def test_nonfinite_sg(self):
        p=field();p[0]["sg_ott"]=float("nan")
        self.assertIn("INVALID_SG_OTT",validate_snapshot(snap(players=p),RAW,provider_verified=True)["reasons"])
    def test_missing_source_bytes(self):
        self.assertIn("SOURCE_BYTES_REQUIRED",validate_snapshot(snap(),None,provider_verified=True)["reasons"])

if __name__=="__main__":
    unittest.main()
