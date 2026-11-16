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
    def test_conflicting_duplicate_json_key_rejected(self):
        raw, man = fixture()
        raw = raw.replace(b'"player_id": "p1"', b'"player_id": "p1", "player_id": "p2"', 1)
        man["sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, "ORIGINAL_JSON_INVALID"):
            audit(raw, man, frozen_utc=FROZEN, expected_player_ids=["p1", "p2"])

    def test_nonstring_source_claim_rejected(self):
        raw, man = fixture()
        man["source_receipt_id"] = {"unverified": True}
        with self.assertRaisesRegex(ValueError, "SOURCE_PROVENANCE_MISSING"):
            audit(raw, man, frozen_utc=FROZEN, expected_player_ids=["p1", "p2"])

    def test_json_exponent_overflow_in_unused_provider_field_blocked(self):
        raw,man=fixture()
        original=json.loads(raw)
        # A nested nonfinite numeric remains invalid even if not used by the
        # displayed field identity and all hashes locally agree.
        candidate=json.dumps(original).replace(
            '"status": "ENTERED"', '"status": "ENTERED", "provider_rating": 1e999', 1)
        raw=candidate.encode()
        man["sha256"]=hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,"ORIGINAL_JSON_INVALID"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])

    def test_withdrawn_without_tee_slot_kept_in_original_denominator(self):
        rows=[FIELD[0],{"player_id":"p2","status":"WITHDRAWN"}]
        raw,man=fixture(rows)
        result=audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])
        self.assertEqual(result["field_rows"],2)
        self.assertEqual(result["withdrawn_rows"],1)
        self.assertEqual(result["unassigned_tee_time_rows"],1)
        self.assertFalse(result["expected_field_independently_authenticated"])
        self.assertFalse(result["provider_authentication_attested"])
        self.assertEqual(result["approved_stake_u"],0)

    def test_entered_without_tee_slot_refused_not_auto_filled(self):
        rows=[{"player_id":"p1","status":"ENTERED"},FIELD[1]]
        raw,man=fixture(rows)
        with self.assertRaisesRegex(ValueError,"TEE_TIME_REQUIRED_FOR_ENTERED"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])

    def test_withdrawn_stale_provided_tee_slot_refused(self):
        rows=[FIELD[0],dict(FIELD[1],tee_time_utc=FROZEN)]
        raw,man=fixture(rows)
        with self.assertRaisesRegex(ValueError,"TEE_TIME_NOT_FUTURE"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])

    def test_unknown_without_tee_slot_retained_as_unauthenticated(self):
        rows=[FIELD[0],{"player_id":"p2","status":"UNKNOWN","tee_time_utc":None}]
        raw,man=fixture(rows)
        report=audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])
        self.assertEqual(report["unassigned_tee_time_rows"],1)
        self.assertEqual(report["state"],"PAPER_0U_SOURCE_CLAIMS_UNAUTHENTICATED")

    def test_missing_provider_claim_rejected(self):
        raw,man=fixture()
        man["source"]=""
        with self.assertRaisesRegex(ValueError,"SOURCE_PROVENANCE_MISSING"):
            audit(raw,man,frozen_utc=FROZEN,expected_player_ids=["p1","p2"])

if __name__ == "__main__":
    unittest.main()
