"""Regression: matrix dates must be canonical YYYY-MM-DD, not Python basic ISO."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.whole_repo_release_audit import audit


class MatrixDateCanonicalTest(unittest.TestCase):
    def test_basic_iso_date_is_rejected_not_treated_as_valid_history(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("tools.whole_repo_release_audit.inspect_matrix",
                       return_value={"status": "PAPER_0U_SAFE_MATRIX", "issues": []}), \
                 patch("tools.whole_repo_release_audit.verify_freezes",
                       return_value={"status": "OK", "sports": [], "files": 0}):
                report = audit(Path(directory),
                               matrix={"policy": "historical",
                                       "asof_date_ct": "20261115",
                                       "markets": []},
                               freeze={}, asof_date_ct="2026-11-16")
        self.assertIn("MATRIX_ASOF_INVALID", report["blockers"])
        self.assertNotIn("MATRIX_ASOF_NOT_CURRENT", report["blockers"])

    def test_calendar_iso_date_is_accepted_as_historical(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("tools.whole_repo_release_audit.inspect_matrix",
                       return_value={"status": "PAPER_0U_SAFE_MATRIX", "issues": []}), \
                 patch("tools.whole_repo_release_audit.verify_freezes",
                       return_value={"status": "OK", "sports": [], "files": 0}):
                report = audit(Path(directory),
                               matrix={"policy": "historical",
                                       "asof_date_ct": "2026-11-15",
                                       "markets": []},
                               freeze={}, asof_date_ct="2026-11-16")
        self.assertIn("MATRIX_ASOF_NOT_CURRENT", report["blockers"])
        self.assertNotIn("MATRIX_ASOF_INVALID", report["blockers"])


if __name__ == "__main__":
    unittest.main()
