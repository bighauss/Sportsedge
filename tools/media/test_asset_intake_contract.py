import hashlib
import unittest
from tools.media.asset_intake_contract import preflight, MediaHold

PNG = bytes.fromhex("89504e470d0a1a0a") + b"synthetic fixture"
def fixture(raw=PNG):
    return {"asset_id": "fixture-1", "media_type": "image/png",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "permission": "OWNER_AUTHORIZED", "publish_approved": False,
            "contains_private_odds": False, "contains_secrets": False,
            "license": "owner-created", "captured_utc": "2026-11-15T18:00:00Z"}
def run(raw=PNG, receipt=None):
    return preflight(raw, fixture(raw) if receipt is None else receipt,
                     now_utc="2026-11-15T19:00:00Z")

class MediaContractTests(unittest.TestCase):
    def test_valid_remains_unpublished(self):
        self.assertFalse(run()["publish_approved"])
    def test_tamper_rejected(self):
        with self.assertRaisesRegex(MediaHold, "MEDIA_SHA_MISMATCH"):
            run(PNG+b"altered", fixture())
    def test_permission_missing(self):
        r=fixture();r["permission"]="UNKNOWN"
        with self.assertRaisesRegex(MediaHold,"PERMISSION_OR_PUBLISH_GATE"):run(receipt=r)
    def test_publishing_needs_review(self):
        r=fixture();r["publish_approved"]=True
        with self.assertRaisesRegex(MediaHold,"PERMISSION_OR_PUBLISH_GATE"):run(receipt=r)
    def test_private_odds_blocked(self):
        r=fixture();r["contains_private_odds"]=True
        with self.assertRaisesRegex(MediaHold,"PRIVATE_DATA_NOT_CLEARED"):run(receipt=r)
    def test_secret_unknown_blocked(self):
        r=fixture();r.pop("contains_secrets")
        with self.assertRaisesRegex(MediaHold,"PRIVATE_DATA_NOT_CLEARED"):run(receipt=r)
    def test_license_missing(self):
        r=fixture();r["license"]=""
        with self.assertRaisesRegex(MediaHold,"LICENSE_UNRESOLVED"):run(receipt=r)
    def test_future_capture(self):
        r=fixture();r["captured_utc"]="2026-11-15T20:00:00Z"
        with self.assertRaisesRegex(MediaHold,"FUTURE_CAPTURE"):run(receipt=r)
    def test_mime_spoof_rejected(self):
        raw=b"not really a png";r=fixture(raw)
        with self.assertRaisesRegex(MediaHold,"MEDIA_SIGNATURE_MISMATCH"):run(raw,r)
    def test_unsupported_type(self):
        r=fixture();r["media_type"]="application/pdf"
        with self.assertRaisesRegex(MediaHold,"MEDIA_TYPE_NOT_ALLOWED"):run(receipt=r)
if __name__=="__main__":unittest.main()
