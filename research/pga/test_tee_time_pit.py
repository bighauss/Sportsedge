import hashlib
import json
import unittest
from research.pga.tee_time_pit import audit

FROZEN = "2026-11-15T18:00:00Z"
FIELD = [{"player_id":"p1","tee_time_utc":"2026-11-16T14:00:00Z","status":"ENTERED"},
         {"player_id":"p2","tee_time_utc":"2026-11-16T14:10:00Z","status":"WITHDRAWN"}]

def fixture(rows=None):
    raw = json.dumps(FIELD if rows is None else rows).encode()
    man = {"sha256":hashlib.sha256(raw).hexdigest(),"source":"permitted_export",
           "source_receipt_id":"fixture","observed_utc":"2026-11-15T17:55:00Z",
           "captured_utc":"2026-11-15T17:56:00Z","frozen_utc":FROZEN}
    return raw, man

class TeeTimeContract(unittest.TestCase):
    def test_complete_original_field_paper_only(self):
        raw, man = fixture()
        result = audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])
        self.assertEqual(result["approved_stake_u"],0)
        self.assertEqual(result["withdrawn_rows"],1)
    def test_modified_original_rejected(self):
        raw,man=fixture()
        with self.assertRaisesRegex(ValueError,"ORIGINAL_SHA_MISMATCH"):
            audit(raw+b" ",man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])
    def test_suppressed_withdrawal_rejected(self):
        raw,man=fixture(FIELD[:1])
        with self.assertRaisesRegex(ValueError,"FIELD_DENOMINATOR_MISMATCH"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])
    def test_duplicate_player_rejected(self):
        raw,man=fixture([FIELD[0],FIELD[0]])
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PLAYER"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])
    def test_late_source_rejected(self):
        raw,man=fixture()
        man["captured_utc"]="2026-11-15T18:01:00Z"
        with self.assertRaisesRegex(ValueError,"SOURCE_CLOCK_INVALID"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])
    def test_tee_time_already_started_rejected(self):
        rows=[dict(FIELD[0],tee_time_utc=FROZEN),FIELD[1]]
        raw,man=fixture(rows)
        with self.assertRaisesRegex(ValueError,"TEE_TIME_NOT_FUTURE"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])
    def test_missing_provider_claim_rejected(self):
        raw,man=fixture()
        man["source"]=""
        with self.assertRaisesRegex(ValueError,"SOURCE_PROVENANCE_MISSING"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])

if __name__ == "__main__":
    unittest.main()
