import hashlib
import json
import unittest
from research.observability.run_manifest_contract import verify, Hold

RAW = {"schedule": b"original scheduled game", "roster": b"original pregame roster"}
def fixture():
    m = {"schema": "SPORTSEDGE_OBSERVABILITY_PIT_V1", "official": False, "stake_u": 0,
         "seed": 7, "model_sha256": "a"*64, "freeze_utc": "2026-11-15T18:00:00Z",
         "kickoff_utc": "2026-11-15T19:00:00Z",
         "sources": [{"id": k, "sha256": hashlib.sha256(v).hexdigest(),
                      "provider": "test_fixture", "published_utc": "2026-11-15T17:00:00Z",
                      "observed_utc": "2026-11-15T17:30:00Z",
                      "captured_utc": "2026-11-15T17:40:00Z"} for k,v in RAW.items()]}
    return m
def run(m, raw=None):
    return verify(json.dumps(m).encode(), RAW if raw is None else raw)

class ManifestContractTests(unittest.TestCase):
    def test_good_is_never_official(self):
        r=run(fixture()); self.assertFalse(r["official"]); self.assertEqual(r["source_count"],2)
    def test_tampered_original(self):
        with self.assertRaisesRegex(Hold,"SOURCE_SHA_MISMATCH"):
            run(fixture(), dict(RAW, roster=b"changed"))
    def test_missing_original(self):
        with self.assertRaisesRegex(Hold,"SOURCE_BYTES_MISSING"):
            run(fixture(), {"schedule":RAW["schedule"]})
    def test_unlisted_original(self):
        with self.assertRaisesRegex(Hold,"SOURCE_DENOMINATOR_MISMATCH"):
            run(fixture(), dict(RAW, extra=b"unlisted"))
    def test_duplicate_source_id(self):
        m=fixture();m["sources"][1]["id"]="schedule"
        with self.assertRaises(Hold): run(m)
    def test_postfreeze_capture(self):
        m=fixture();m["sources"][0]["captured_utc"]="2026-11-15T18:01:00Z"
        with self.assertRaisesRegex(Hold,"SOURCE_CLOCK_INVALID"):run(m)
    def test_postkickoff_freeze(self):
        m=fixture();m["freeze_utc"]=m["kickoff_utc"]
        with self.assertRaisesRegex(Hold,"FREEZE_NOT_PREGAME"):run(m)
    def test_official_rejected(self):
        m=fixture();m["official"]=True
        with self.assertRaisesRegex(Hold,"PAPER_ONLY"):run(m)
    def test_boolean_seed_rejected(self):
        m=fixture();m["seed"]=True
        with self.assertRaisesRegex(Hold,"SEED_REQUIRED"):run(m)
    def test_duplicate_json_keys_rejected(self):
        b=json.dumps(fixture()).encode().replace(b'"seed": 7',b'"seed": 7, "seed": 8')
        with self.assertRaisesRegex(Hold,"DUPLICATE_JSON_KEY"):verify(b,RAW)
    def test_nonfinite_json_rejected(self):
        b=json.dumps(fixture()).encode().replace(b'"seed": 7',b'"seed": NaN')
        with self.assertRaises(Hold):verify(b,RAW)
    def test_missing_provider(self):
        m=fixture();m["sources"][0]["provider"]=""
        with self.assertRaisesRegex(Hold,"SOURCE_PROVIDER_MISSING"):run(m)
if __name__=="__main__":unittest.main()
