"""Additional offline failure-mode regressions for the API-SPORTS status probe."""
import unittest
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError
from integrations.providers.api_sports_status import probe_status, ProviderStatusError


class FakeResponse:
    def __init__(self, raw, status=200):
        self.raw, self.status = raw, status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        return self.raw[:n]


class AdditionalStatusTests(unittest.TestCase):
    def test_http_403_429_rejected_without_payload(self):
        for status in (403, 429):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ProviderStatusError, "HTTP_NOT_200") as caught:
                    probe_status(
                        key="secret",
                        opener=lambda *a, **k: FakeResponse(
                            b'{"response":{"secret":"private"}}', status
                        ),
                    )
                self.assertNotIn("private", str(caught.exception))

    def test_http_error_exception_sanitized(self):
        def reject(*args, **kwargs):
            raise HTTPError(
                "https://redacted", 429, "private-provider-message", None, None
            )

        with self.assertRaisesRegex(ProviderStatusError, "READ_OR_PARSE_FAILED") as caught:
            probe_status(key="secret", opener=reject)
        self.assertNotIn("private-provider-message", str(caught.exception))

    def test_oversized_body_rejected(self):
        with self.assertRaisesRegex(ProviderStatusError, "OVERSIZE"):
            probe_status(
                key="secret",
                opener=lambda *a, **k: FakeResponse(b"x" * 1_000_001),
            )

    def test_non_utc_offset_rejected(self):
        with self.assertRaisesRegex(ProviderStatusError, "CLOCK_NOT_UTC"):
            probe_status(
                key="secret",
                opener=lambda *a, **k: FakeResponse(b'{"response":{}}'),
                now=lambda: datetime(
                    2026, 11, 17, tzinfo=timezone(timedelta(hours=-6))
                ),
            )
