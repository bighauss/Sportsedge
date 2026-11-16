import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from datagolf_receipt_store import save_capture

RAW=b'[{"dg_id":42}]'
def receipt(**kwargs):
    d={"endpoint":"players","captured_utc":"2026-11-15T12:00:00Z",
       "raw_bytes":RAW,"source_sha256":hashlib.sha256(RAW).hexdigest(),
       "params":{"key":"do-not-save"}}
    d.update(kwargs)
    return d
class ReceiptStoreTests(unittest.TestCase):
    def test_round_trip_and_sanitization(self):
        with tempfile.TemporaryDirectory() as d:
            out=save_capture(receipt(),d)
            self.assertEqual(Path(out["raw_path"]).read_bytes(),RAW)
            meta=Path(out["receipt_path"]).read_text()
            self.assertNotIn("do-not-save",meta)
            self.assertNotIn("do-not-save",str(out))
            self.assertEqual(json.loads(meta)["source_sha256"],hashlib.sha256(RAW).hexdigest())
    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(save_capture(receipt(),d),save_capture(receipt(),d))
    def test_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"SOURCE_HASH_MISMATCH"):
                save_capture(receipt(source_sha256="a"*64),d)
    def test_invalid_endpoint(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"INVALID_ENDPOINT"):
                save_capture(receipt(endpoint="../escape"),d)
    def test_invalid_clock(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"INVALID_CAPTURE_TIME"):
                save_capture(receipt(captured_utc="today"),d)
    def test_no_raw(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"RAW_BYTES_REQUIRED"):
                save_capture(receipt(raw_bytes="string"),d)
if __name__=="__main__": unittest.main()
