import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from tools.media.private_asset_cli import evaluate, private_file
from tools.media.asset_intake_contract import MediaHold

PNG=bytes.fromhex("89504e470d0a1a0a")+b"synthetic"
def receipt():
    return {"asset_id":"private-fixture","media_type":"image/png",
            "sha256":hashlib.sha256(PNG).hexdigest(),"permission":"OWNER_AUTHORIZED",
            "publish_approved":False,"contains_private_odds":False,"contains_secrets":False,
            "license":"owner-created","captured_utc":"2026-11-15T18:00:00Z"}

class PrivateAssetCliTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.asset=Path(self.t.name)/"asset.png"
        self.meta=Path(self.t.name)/"receipt.json"
        self.asset.write_bytes(PNG);self.meta.write_text(json.dumps(receipt()))
        self.asset.chmod(0o600);self.meta.chmod(0o600)
    def check(self):
        return evaluate(self.asset,self.meta,"2026-11-15T19:00:00Z")
    def test_pass_unpublished(self):
        self.assertFalse(self.check()["publish_approved"])
    def test_world_readable_asset_blocked(self):
        self.asset.chmod(0o644)
        with self.assertRaisesRegex(MediaHold,"PRIVATE_FILE_MODE_REQUIRED"):self.check()
    def test_world_readable_receipt_blocked(self):
        self.meta.chmod(0o644)
        with self.assertRaisesRegex(MediaHold,"PRIVATE_FILE_MODE_REQUIRED"):self.check()
    def test_symlink_blocked(self):
        link=Path(self.t.name)/"link"
        link.symlink_to(self.asset)
        with self.assertRaisesRegex(MediaHold,"SYMLINK_REJECTED"):private_file(link)
    def test_tampered_asset_blocked(self):
        self.asset.write_bytes(PNG+b"tampered")
        with self.assertRaisesRegex(MediaHold,"MEDIA_SHA_MISMATCH"):self.check()
    def test_permission_missing_blocked(self):
        r=receipt();r["permission"]="UNKNOWN"
        self.meta.write_text(json.dumps(r))
        with self.assertRaisesRegex(MediaHold,"PERMISSION_OR_PUBLISH_GATE"):self.check()
    def test_future_capture_blocked(self):
        r=receipt();r["captured_utc"]="2026-11-15T20:00:00Z"
        self.meta.write_text(json.dumps(r))
        with self.assertRaisesRegex(MediaHold,"FUTURE_CAPTURE"):self.check()
    def test_receipt_directory_blocked(self):
        with self.assertRaisesRegex(MediaHold,"REGULAR_FILE_REQUIRED"):
            private_file(self.t.name)
if __name__=="__main__":unittest.main()
