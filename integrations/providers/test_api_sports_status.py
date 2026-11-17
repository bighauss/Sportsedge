"""Offline regression tests for API-SPORTS status-only read probe."""
import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from integrations.providers.api_sports_status import probe_status, ProviderStatusError, STATUS_URL

class Response:
    status = 200
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): return self.data[:size]

class StatusContractTests(unittest.TestCase):
    def test_no_key_no_network(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ProviderStatusError, "NOT_CONFIGURED"):
                probe_status(opener=lambda *args, **kw: self.fail("unexpected network"))

    def test_exact_get_redacts_credentials_and_private_account(self):
        raw = b'{"response":{"account":{"firstname":"private"}},"errors":[]}'
        def open_status(request, timeout):
            self.assertEqual(request.full_url, STATUS_URL)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("X-apisports-key"), "private-key")
            self.assertEqual(timeout, 10)
            return Response(raw)
        result = probe_status(key="private-key", opener=open_status,
                              now=lambda: datetime(2026, 11, 17, tzinfo=timezone.utc))
        self.assertEqual(result["original_bytes_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn("private-key", str(result))
        self.assertNotIn("firstname", str(result))
        self.assertFalse(result["original_bytes_archived"])
        self.assertFalse(result["authenticated_original_bookmaker_odds"])

    def test_bad_shapes_and_provider_errors_fail_closed(self):
        for raw in (b"[]", b"{}", b'{"errors":["bad"],"response":{}}',
                    b"not-json", b'{"response":null}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ProviderStatusError):
                    probe_status(key="x", opener=lambda *a, **k: Response(raw))

    def test_bad_key_and_naive_clock_fail_closed(self):
        with self.assertRaisesRegex(ProviderStatusError, "NOT_CONFIGURED"):
            probe_status(key="x\ny", opener=lambda *a, **k: self.fail("network"))
        with self.assertRaisesRegex(ProviderStatusError, "CLOCK_NOT_UTC"):
            probe_status(key="x", opener=lambda *a, **k: Response(b'{"response":{}}'),
                         now=lambda: datetime(2026, 11, 17))
