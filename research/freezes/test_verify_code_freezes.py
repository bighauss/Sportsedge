"""Offline freeze manifest regression probes, no provider network or wagers."""
import tempfile
import unittest
from pathlib import Path

from verify_code_freezes import FreezeViolation, git_blob_digest, verified_file


class PinnedCodeTest(unittest.TestCase):
    def test_git_blob_known_example(self):
        self.assertEqual(git_blob_digest(b"test\n"), "9daeafb9864cf43055ae93beb0afd6c7d144bfa4")

    def test_reject_changed_code(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_bytes(b"a")
            original = git_blob_digest(b"a")
            self.assertEqual(verified_file(root, "a.py", original)["git_blob_sha1"], original)
            (root / "a.py").write_bytes(b"b")
            with self.assertRaisesRegex(FreezeViolation, "CODE_CHANGED_SINCE_FREEZE"):
                verified_file(root, "a.py", original)

    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(FreezeViolation, "INVALID_RELATIVE_PATH"):
                verified_file(Path(td), "../outside.py", "a" * 40)

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_bytes(b"a")
            (root / "link.py").symlink_to(root / "a.py")
            with self.assertRaisesRegex(FreezeViolation, "UNSAFE_OR_MISSING_CODE"):
                verified_file(root, "link.py", git_blob_digest(b"a"))


if __name__ == "__main__":
    unittest.main()
