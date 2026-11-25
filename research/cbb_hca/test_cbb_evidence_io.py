import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from research.cbb_hca.evidence_io import atomic_publish

class AtomicEvidence(unittest.TestCase):
    def test_exact_complete_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"record.json";r=atomic_publish(p,b'{"complete":true}\n')
            self.assertEqual(p.read_bytes(),b'{"complete":true}\n');self.assertEqual(r["bytes"],18)
    def test_private_file_mode(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"record";atomic_publish(p,b"x");self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_existing_bytes_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"record";atomic_publish(p,b"original")
            with self.assertRaises(FileExistsError):atomic_publish(p,b"replacement")
            self.assertEqual(p.read_bytes(),b"original")
    def test_prepublication_failure_leaves_no_final_or_temp(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"record"
            def fail():raise ValueError("TIP_PASSED")
            with self.assertRaisesRegex(ValueError,"TIP_PASSED"):atomic_publish(p,b"complete",before_publish=fail)
            self.assertEqual(list(Path(d).iterdir()),[])
    def test_staging_fsync_failure_leaves_no_partial(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("os.fsync",side_effect=OSError("DISK_FAILURE")):
                with self.assertRaises(OSError):atomic_publish(Path(d)/"record",b"complete")
            self.assertEqual(list(Path(d).iterdir()),[])
    def test_symlink_target_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            original=Path(d)/"original";original.write_bytes(b"keep")
            p=Path(d)/"record";p.symlink_to(original)
            with self.assertRaises(FileExistsError):atomic_publish(p,b"replacement")
            self.assertEqual(original.read_bytes(),b"keep")
    def test_broad_directory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            os.chmod(d,0o755)
            with self.assertRaisesRegex(ValueError,"PRIVATE_DIRECTORY"):atomic_publish(Path(d)/"record",b"x")
    def test_empty_payload_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):atomic_publish(Path(d)/"record",b"")

if __name__=="__main__":unittest.main()
