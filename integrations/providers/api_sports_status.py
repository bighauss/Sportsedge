"""Read-only API-SPORTS football account status probe.

This endpoint is ACCOUNT METADATA ONLY: never original DraftKings or
independent-book odds, and never point-in-time player features. No request on
import, no automatic retries, no raw response persisted or printed. Caller
must confirm provider rights/quota before invocation.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen

STATUS_URL = "https://v3.football.api-sports.io/status"


class ProviderStatusError(RuntimeError):
    """Sanitized error without provider payload or credentials."""


def probe_status(*, key: str | None = None, opener=urlopen, now=None) -> dict:
    """Single bounded GET; return redacted audit metadata, never private bytes."""
    key = key if key is not None else os.environ.get("API_SPORTS_KEY", "")
    if not isinstance(key, str) or not key.strip() or "\n" in key or "\r" in key:
        raise ProviderStatusError("API_SPORTS_KEY_NOT_CONFIGURED")
    request = Request(
        STATUS_URL,
        headers={"x-apisports-key": key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(request, timeout=10) as response:
            if getattr(response, "status", None) != 200:
                raise ProviderStatusError("PROVIDER_STATUS_HTTP_NOT_200")
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ProviderStatusError("PROVIDER_STATUS_OVERSIZE")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ProviderStatusError("PROVIDER_STATUS_NOT_OBJECT")
            if data.get("errors") not in (None, [], {}):
                raise ProviderStatusError("PROVIDER_STATUS_ERRORS_PRESENT")
            if not isinstance(data.get("response"), dict):
                raise ProviderStatusError("PROVIDER_STATUS_RESPONSE_MISSING")
            captured = (now or (lambda: datetime.now(timezone.utc)))()
            if captured.tzinfo is None or captured.utcoffset() != timezone.utc.utcoffset(captured):
                raise ProviderStatusError("CAPTURE_CLOCK_NOT_UTC")
            return {
                "provider": "API-SPORTS",
                "product": "football",
                "endpoint": "/status",
                "captured_utc": captured.isoformat().replace("+00:00", "Z"),
                "original_bytes_sha256": hashlib.sha256(raw).hexdigest(),
                "original_bytes_archived": False,
                "provider_published_utc": None,
                "authenticated_original_bookmaker_odds": False,
                "source_status": "ACCOUNT_STATUS_ONLY_NOT_PIT_OR_ODDS",
            }
    except ProviderStatusError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise ProviderStatusError("PROVIDER_STATUS_READ_OR_PARSE_FAILED") from None
