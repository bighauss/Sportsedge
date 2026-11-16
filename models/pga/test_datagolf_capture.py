import hashlib
import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs
from datagolf_capture import capture

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
class Response:
    def __init__(self, raw): self.raw = raw
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size): return self.raw
def mock(req, timeout):
    args = parse_qs(urlsplit(req.full_url).query)
    assert args["key"] == ["fake-secret"]
    assert args["file_format"] == ["json"]
    return Response(b'[{"dg_id":1,"player_name":"Synthetic Golfer"}]')
def run(endpoint="players", **kwargs):
    return capture(endpoint, api_key="fake-secret", opener=mock, clock=lambda: NOW, **kwargs)
class DataGolfCaptureTests(unittest.TestCase):
    def test_authenticated_mock_receipt(self):
        r = run()
        self.assertEqual(r["source_sha256"], hashlib.sha256(r["raw_bytes"]).hexdigest())
        self.assertEqual(r["status"], "UNVERIFIED_RESEARCH_PAPER_0U")
        self.assertNotIn("fake-secret", repr(r))
    def test_odds_market_allowlist(self):
        r = run("outrights", params={"tour":"pga", "market":"win"})
        self.assertEqual(r["endpoint"], "outrights")
    def test_unknown_endpoint(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_ENDPOINT"): run("secret")
    def test_key_required(self):
        with self.assertRaisesRegex(ValueError, "DATAGOLF_API_KEY_REQUIRED"):
            capture("players", api_key="", opener=mock)
    def test_market_required(self):
        with self.assertRaisesRegex(ValueError, "REQUIRED_PARAMS_MISSING"): run("outrights")
    def test_bad_market(self):
        with self.assertRaisesRegex(ValueError, "INVALID_PARAM_CHOICE"): run("outrights",params={"market":"any"})
    def test_bad_param(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_PARAMS"): run(params={"key":"steal"})
    def test_historical_requires_identifiers(self):
        with self.assertRaisesRegex(ValueError, "REQUIRED_PARAMS_MISSING"): run("historical_rounds",params={"tour":"pga"})
    def test_provider_error(self):
        with self.assertRaisesRegex(ValueError, "PROVIDER_ERROR_RESPONSE"):
            capture("players",api_key="fake-secret",opener=lambda req,timeout:Response(b'{"error":"invalid key"}'),clock=lambda:NOW)
    def test_invalid_timeout(self):
        with self.assertRaisesRegex(ValueError, "INVALID_TIMEOUT"): run(timeout=True)
if __name__ == "__main__": unittest.main()
