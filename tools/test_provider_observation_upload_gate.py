"""Fail-closed provider-artifact upload branch regression.

A failed/invalid metadata manifest must not publish a success-named artifact.
This is a workflow-structure test, not a live GitHub Actions attempt and
NOT upstream bookmaker source authentication.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/provider-observation.yml"


class ProviderObservationGate(unittest.TestCase):
    def test_metadata_artifact_requires_successful_validation(self):
        contents = WORKFLOW.read_text(encoding="utf-8")
        validation = contents.index("- name: Validate manifest before archival")
        upload = contents.index("- name: Upload sanitized manifest")
        self.assertLess(validation, upload)
        self.assertIn(
            "- name: Validate manifest before archival\n"
            "        if: success()\n"
            "        run: python tools/validate_provider_observation.py "
            "provider_observation/manifest.json", contents)
        self.assertIn(
            "- name: Upload sanitized manifest\n"
            "        if: success()\n"
            "        uses: actions/upload-artifact@v4", contents)
        self.assertNotIn("if: always()", contents)

    def test_only_sanitized_metadata_is_uploaded(self):
        contents = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("path: provider_observation/manifest.json", contents)
        self.assertIn("if-no-files-found: error", contents)
        self.assertIn("not_a_point_in_time_quote_receipt", contents)
        self.assertIn('"gate_a":"OPEN"', contents)
        self.assertIn('"market_state":"PAPER/0u"', contents)
        self.assertNotIn("upload-artifact@v3", contents)


if __name__ == "__main__":
    unittest.main()
