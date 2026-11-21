"""No network/paid source. Test persistent pre-credit GitHub Actions artifact claim."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest

from sportsedge.odds.daily_pilot_artifact_gate import (
    Blocked, reserve, verify, validate_artifacts, CLAIM_FILENAME
)

REPO = "bighauss/Sportsedge"
RUN = "45789"
TOKEN = "synthetic-not-a-real-token"
AT = datetime.fromisoformat("2026-11-21T16:00:00+00:00")
NAME = "nfl-daily-odds-attempt-2026-11-21"


class GateTests(unittest.TestCase):
    def setUp(self):
        d = TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.claims = {}
        self.hold = False

    def lookup(self, repo, token, name):
        self.assertEqual(repo, REPO)
        self.assertEqual(token, TOKEN)
        if name == "nfl-daily-odds-quota-hold":
            if self.hold:
                return {"total_count": 1, "artifacts": [{
                    "name": name, "expired": False, "workflow_run": {"id": 1}}]}
            return {"total_count": 0, "artifacts": []}
        row = self.claims.get(name)
        return {"total_count": 1 if row else 0, "artifacts": [row] if row else []}

    def reserve(self, at=AT):
        return reserve(self.root, repository=REPO, run_id=RUN, token=TOKEN,
                       now=at, lookup=self.lookup)

    def verify(self, at=AT, run=RUN):
        return verify(self.root, repository=REPO, run_id=run, token=TOKEN,
                      now=at, lookup=self.lookup)

    def register(self):
        self.claims[NAME] = {"name": NAME, "expired": False,
                             "workflow_run": {"id": int(RUN)}}

    def test_safe_claim_has_metadata_not_secrets_and_mode_600(self):
        x = self.reserve()
        self.assertEqual(x["name"], NAME)
        self.assertEqual(x["date_ct"], "2026-11-21")
        raw = (self.root / CLAIM_FILENAME).read_text()
        self.assertNotIn(TOKEN, raw)
        self.assertEqual((self.root / CLAIM_FILENAME).stat().st_mode & 0o777, 0o600)

    def test_verify_requires_uploaded_marker(self):
        self.reserve()
        with self.assertRaisesRegex(Blocked, "NOT_UNIQUE_OR_NOT_VISIBLE"):
            self.verify()
        self.register()
        self.assertEqual(self.verify()["run_id"], RUN)

    def test_rerun_bypasses_no_marker_never(self):
        self.register()
        with self.assertRaisesRegex(Blocked, "ALREADY_ATTEMPTED"):
            self.reserve()
        self.assertFalse((self.root / CLAIM_FILENAME).exists())

    def test_prior_quota_hold_blocks_future_day(self):
        self.hold = True
        with self.assertRaisesRegex(Blocked, "QUOTA_HOLD"):
            self.reserve()
        self.assertFalse((self.root / CLAIM_FILENAME).exists())

    def test_missing_api_token_blocks(self):
        with self.assertRaisesRegex(Blocked, "READ_TOKEN_MISSING"):
            reserve(self.root, repository=REPO, run_id=RUN, token="",
                    now=AT, lookup=self.lookup)

    def test_expired_or_wrong_run_marker_refused(self):
        self.reserve()
        self.register()
        self.claims[NAME]["expired"] = True
        with self.assertRaisesRegex(Blocked, "WRONG_RUN_OR_EXPIRED"):
            self.verify()
        self.claims[NAME]["expired"] = False
        self.claims[NAME]["workflow_run"]["id"] = 321
        with self.assertRaisesRegex(Blocked, "WRONG_RUN_OR_EXPIRED"):
            self.verify()

    def test_day_rollover_refuses_postmidnight_capture(self):
        self.reserve()
        self.register()
        with self.assertRaisesRegex(Blocked, "IDENTITY_OR_DAY_CHANGED"):
            self.verify(datetime.fromisoformat("2026-11-22T06:00:00+00:00"))

    def test_missing_repo_or_run_number_refused(self):
        for repo, run in (("../bad", RUN), (REPO, "not-int")):
            with self.subTest(repo=repo, run=run), self.assertRaises(Blocked):
                reserve(self.root, repository=repo, run_id=run, token=TOKEN,
                        now=AT, lookup=self.lookup)

    def test_invalid_artifact_response_refuses(self):
        for malformed in ({"total_count": False, "artifacts": []},
                          {"total_count": 1, "artifacts": []},
                          {"total_count": 0, "artifacts": [{"name": NAME}]},
                          {"total_count": -1, "artifacts": []},
                          {"total_count": 1, "artifacts": [{"name": "wrong"}]}):
            with self.subTest(malformed=malformed), self.assertRaises(Blocked):
                validate_artifacts(malformed, NAME)

    def test_claim_output_only_minted_day_and_repo(self):
        self.reserve()
        self.register()
        r = self.verify()
        self.assertEqual(r["repository"], REPO)
        self.assertEqual(r["date_ct"], "2026-11-21")
        self.assertNotIn("api_key", r)
        self.assertNotIn("fernet_key", r)

    def test_no_reuse_local_claim_file(self):
        self.reserve()
        with self.assertRaisesRegex(Blocked, "ATTEMPT_CLAIM_CREATE_FAILED"):
            self.reserve()


if __name__ == "__main__":
    unittest.main(verbosity=2)
