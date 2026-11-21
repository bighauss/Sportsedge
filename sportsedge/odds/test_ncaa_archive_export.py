"""Exercise the actual export and the workflow's failure routing with offline artifacts."""
import io
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
import yaml

from sportsedge.odds import daily_pilot_artifact_gate as gate
from sportsedge.odds.ncaa_archive_export import export


class ExportTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.runner = Path(directory.name)
        self.root = self.runner / "private"
        self.root.mkdir()
        self.target = self.runner / "ncaa-evidence.tar.fernet"
        self.cipher = Fernet(Fernet.generate_key())
        self.payload = b'{"reason":"arbitrary private detail"}'
        (self.root / "hold.json").write_bytes(self.payload)
        workflow = Path(__file__).resolve().parents[2] / ".github/workflows/ncaa-daily-odds.yml"
        steps = yaml.safe_load(workflow.read_text())["jobs"]["capture"]["steps"]
        self.steps = {step.get("id", step.get("name")): step for step in steps}

    def test_complete_bundle_round_trip_and_no_replacement(self):
        export(self.root, self.target, self.cipher)
        original = self.target.read_bytes()
        with tarfile.open(fileobj=io.BytesIO(self.cipher.decrypt(original))) as archive:
            self.assertEqual(archive.getnames(), ["hold.json"])
            self.assertEqual(archive.extractfile("hold.json").read(), self.payload)
        with self.assertRaises(FileExistsError):
            export(self.root, self.target, self.cipher)
        self.assertEqual(self.target.read_bytes(), original)

    def test_failed_staging_leaves_no_uploadable_bundle(self):
        with patch("os.fsync", side_effect=OSError("simulated partial export")):
            with self.assertRaises(OSError):
                export(self.root, self.target, self.cipher)
        self.assertEqual(list(self.runner.iterdir()), [self.root])
        upload = self.steps["export"]
        self.assertEqual(upload["if"], "always() && steps.encrypt.outcome == 'success'")
        self.assertEqual(upload["with"]["path"], "${{ runner.temp }}/ncaa-evidence.tar.fernet")
        self.assertEqual(upload["with"]["if-no-files-found"], "error")

    def test_marker_remains_available_on_failure_and_has_only_fixed_bytes(self):
        marker = self.steps["hold"]
        self.assertEqual(marker["if"], "always() && steps.capture.outcome != 'skipped' && "
                         "(steps.capture.outcome != 'success' || steps.export.outcome != 'success')")
        subprocess.run(["bash", "-eu", "-c", marker["run"]], check=True,
                       env={**os.environ, "RUNNER_TEMP": str(self.runner)})
        self.assertEqual((self.runner / "ncaa-hold.txt").read_bytes(), b"HOLD\n")
        publish = self.steps["Persist shared stop signal"]
        self.assertFalse(publish.get("continue-on-error", False))
        self.assertEqual(publish["with"]["if-no-files-found"], "error")
        self.assertEqual(publish["with"]["path"], "${{ runner.temp }}/ncaa-hold.txt")
        self.assertEqual(publish["with"]["name"], gate.NCAA_HOLD_ARTIFACT_NAME)

    def test_fresh_runner_blocks_every_slot_on_remote_hold_and_same_slot_on_claim(self):
        for pilot in gate.NCAA_PILOTS:
            for prior, reason in ((gate.NCAA_HOLD_ARTIFACT_NAME, "QUOTA_HOLD"), (pilot, "ALREADY_ATTEMPTED")):
                def lookup(repo, token, name):
                    present = name == prior or name.startswith(prior + "-daily-odds-attempt-")
                    return {"total_count": int(present), "artifacts": [{"name": name}] if present else []}
                with self.subTest(pilot=pilot, prior=prior), self.assertRaisesRegex(gate.Blocked, reason):
                    gate.reserve(self.runner, repository="bighauss/Sportsedge", run_id="9",
                                 token="fake", pilot=pilot, lookup=lookup)
