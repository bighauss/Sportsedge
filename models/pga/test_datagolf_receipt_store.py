import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os
from datagolf_receipt_store import save_capture, REPO_ROOT

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
    def test_checkout_root_is_refused_before_original_bytes_are_written(self):
        with self.assertRaisesRegex(ValueError, "PRIVATE_PGA_CAPTURE_OUTSIDE_PUBLIC_REPO_REQUIRED"):
            save_capture(receipt(), REPO_ROOT / "models" / "pga" / "private-dont-create")
        self.assertFalse((REPO_ROOT / "models" / "pga" / "private-dont-create").exists())

    def test_broad_permissions_are_rejected(self):
        if os.name != "posix":
            self.skipTest("POSIX modes required")
        with tempfile.TemporaryDirectory() as d:
            public = Path(d) / "world-readable"
            public.mkdir(mode=0o755)
            with self.assertRaisesRegex(ValueError, "PRIVATE_DIRECTORY_PERMISSIONS_TOO_BROAD"):
                save_capture(receipt(), public)
            self.assertFalse(list(public.iterdir()))

    def test_manifest_publication_failure_rolls_back_both_files(self):
        import datagolf_receipt_store as module
        real_link = module.os.link
        with tempfile.TemporaryDirectory() as d:
            def fail_manifest(src, dest, *args, **kwargs):
                if str(dest).endswith(".receipt.json"):
                    raise OSError("simulated manifest publication failure")
                return real_link(src, dest, *args, **kwargs)
            with patch.object(module.os, "link", side_effect=fail_manifest):
                with self.assertRaisesRegex(OSError, "simulated manifest publication failure"):
                    save_capture(receipt(), d)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_existing_capture_is_never_overwritten_on_race(self):
        import datagolf_receipt_store as module
        real_link = module.os.link
        with tempfile.TemporaryDirectory() as d:
            def race(src, dest, *args, **kwargs):
                if str(dest).endswith(".receipt.json"):
                    Path(dest).write_text("other-writer-owned", encoding="utf-8")
                return real_link(src, dest, *args, **kwargs)
            with patch.object(module.os, "link", side_effect=race):
                with self.assertRaises(FileExistsError):
                    save_capture(receipt(), d)
            all_files = list(Path(d).iterdir())
            self.assertEqual(len(all_files), 1)
            self.assertEqual(all_files[0].read_text(), "other-writer-owned")

    def test_partial_preexisting_pair_refused(self):
        with tempfile.TemporaryDirectory() as d:
            saved = save_capture(receipt(), d)
            Path(saved["receipt_path"]).unlink()
            with self.assertRaisesRegex(ValueError, "PARTIAL_CAPTURE_PAIR_REFUSED"):
                save_capture(receipt(), d)
            self.assertEqual(Path(saved["raw_path"]).read_bytes(), RAW)

    def test_invalid_calendar_date_not_only_string_shape(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "INVALID_CAPTURE_TIME"):
                save_capture(receipt(captured_utc="2026-02-31T12:00:00Z"), d)

    def test_no_raw(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"RAW_BYTES_REQUIRED"):
                save_capture(receipt(raw_bytes="string"),d)
if __name__=="__main__": unittest.main()
