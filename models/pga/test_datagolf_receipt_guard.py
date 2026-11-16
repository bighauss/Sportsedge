import hashlib
import unittest
from datagolf_receipt_guard import validate_receipt

def receipt(**kw):
    raw=b'{"players":[]}'
    r={"raw_bytes":raw,"source_sha256":hashlib.sha256(raw).hexdigest(),
       "status":"UNVERIFIED_RESEARCH_PAPER_0U","endpoint":"field",
       "captured_utc":"2026-11-15T19:00:00Z",
       "provider_observed_utc":"2026-11-15T18:59:00Z"}
    r.update(kw)
    return r
def check(r,**kw):
    return validate_receipt(r,decision_utc="2026-11-15T19:01:00Z",
                            event_start_utc="2026-11-15T19:20:00Z",**kw)
class TestReceipt(unittest.TestCase):
    def test_integrity_is_not_authentication(self):
        self.assertEqual(check(receipt())["status"],"PAPER_0U_UNAUTHENTICATED")
    def test_tampered(self):
        with self.assertRaisesRegex(ValueError,"ALTERED_BYTES"):
            check(receipt(raw_bytes=b'changed'))
    def test_missing_raw(self):
        with self.assertRaisesRegex(ValueError,"RAW_BYTES_REQUIRED"):
            check(receipt(raw_bytes=b""))
    def test_bad_hash(self):
        with self.assertRaisesRegex(ValueError,"INVALID_SHA256"):
            check(receipt(source_sha256="x"))
    def test_no_observation(self):
        with self.assertRaisesRegex(ValueError,"PROVIDER_OBSERVATION_MISSING"):
            check(receipt(provider_observed_utc=None))
    def test_unobserved_research_only(self):
        self.assertEqual(check(receipt(provider_observed_utc=None),require_observed=False)["status"],"PAPER_0U_NO_OBSERVATION")
    def test_future_observation(self):
        with self.assertRaisesRegex(ValueError,"OBSERVED_AFTER_CAPTURE"):
            check(receipt(provider_observed_utc="2026-11-15T19:00:01Z"))
    def test_capture_after_decision(self):
        with self.assertRaisesRegex(ValueError,"CAPTURE_AFTER_DECISION"):
            check(receipt(captured_utc="2026-11-15T19:02:00Z"))
    def test_stale(self):
        with self.assertRaisesRegex(ValueError,"STALE_SOURCE"):
            check(receipt(provider_observed_utc="2026-11-15T18:50:00Z"))
    def test_decision_after_start(self):
        with self.assertRaisesRegex(ValueError,"DECISION_NOT_PREGAME"):
            validate_receipt(receipt(),decision_utc="2026-11-15T19:20:00Z",event_start_utc="2026-11-15T19:20:00Z")
    def test_research_status_required(self):
        with self.assertRaisesRegex(ValueError,"RESEARCH_STATUS_REQUIRED"):
            check(receipt(status="OFFICIAL"))
    def test_utc_only(self):
        with self.assertRaisesRegex(ValueError,"UTC_Z_REQUIRED"):
            check(receipt(captured_utc="2026-11-15T19:00:00-06:00"))
    def test_unknown_endpoint(self):
        with self.assertRaisesRegex(ValueError,"UNKNOWN_ENDPOINT"):
            check(receipt(endpoint="private"))
if __name__=="__main__":unittest.main()
