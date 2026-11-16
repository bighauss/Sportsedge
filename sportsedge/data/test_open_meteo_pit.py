"""All-synthetic PIT and legal/source safety tests; never call live Open-Meteo."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit

from sportsedge.data.open_meteo_pit import (
    SOURCE, ForecastSourceError, _private, build_url,
    capture, fetch_forecast, parse_hourly, read_request, validate_request,
)

NOW = datetime(2026, 11, 15, 23, tzinfo=timezone.utc)
START = "2026-11-16T19:20:00Z"


def sample(**updated):
    request = dict(
        schema="sportsedge-open-meteo-pregame-request-v1",
        sport="NFL", event_id="SYNTH_NFL_GAME_A", event_start_utc=START,
        venue_id="SYNTH_STADIUM", latitude=41.13, longitude=-87.54,
        coordinate_source="OPERATOR_SUPPLIED", roof_status="OPEN",
        purpose="PERSONAL_NONCOMMERCIAL_RESEARCH",
    )
    request.update(updated)
    return request


def provider(**updated):
    r = {
        "latitude": 41.125, "longitude": -87.56, "utc_offset_seconds": 0,
        "timezone": "GMT",
        "generationtime_ms": 0.6,
        "hourly_units": {
            "time": "iso8601", "temperature_2m": "°F",
            "wind_speed_10m": "mp/h", "wind_gusts_10m": "mp/h",
            "precipitation_probability": "%", "cloud_cover": "%",
        },
        "hourly": {
            "time": ["2026-11-16T18:00", "2026-11-16T19:00", "2026-11-16T20:00"],
            "temperature_2m": [39.1, 38.0, 37.5],
            "wind_speed_10m": [11.0, 15.0, 19.0],
            "wind_gusts_10m": [16.0, 22.5, 26.0],
            "precipitation_probability": [10, 22, 42],
            "cloud_cover": [45, 62, 80],
        },
    }
    r.update(updated)
    return json.dumps(r, ensure_ascii=False).encode("utf-8")


class FakeResult:
    def __init__(self, requested, content, *, url=None, status=200, content_type="application/json"):
        self._requested, self._url, self._content = requested, url or requested, content
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self._url

    def read(self, amount):
        return self._content[:amount]


class FakeOpener:
    def __init__(self, content=None, *, changed_url=False, content_type="application/json"):
        self.calls = []
        self.content = provider() if content is None else content
        self.changed_url = changed_url
        self.content_type = content_type

    def open(self, req, timeout=None):
        self.calls.append((req.full_url, dict(req.header_items()), timeout))
        return FakeResult(req.full_url, self.content,
                          url="https://third.example/secret" if self.changed_url else None,
                          content_type=self.content_type)


class WeatherProspectiveTests(unittest.TestCase):
    def test_allowlisted_documented_no_key_get_and_fixed_units(self):
        url = build_url(sample(), now=NOW)
        self.assertEqual(urlsplit(url).scheme, "https")
        self.assertEqual(urlsplit(url).netloc, "api.open-meteo.com")
        self.assertEqual(urlsplit(url).path, "/v1/forecast")
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q["timezone"], ["GMT"])
        self.assertEqual(q["wind_speed_unit"], ["mph"])
        self.assertEqual(q["temperature_unit"], ["fahrenheit"])
        self.assertEqual(q["past_days"], ["0"])
        self.assertEqual(q["forecast_days"], ["16"])
        self.assertNotIn("apikey", q)
        self.assertNotIn("username", q)

    def test_no_request_without_terms_review_and_noncommercial_personal_purpose(self):
        fake = FakeOpener()
        with self.assertRaisesRegex(ForecastSourceError, "NONCOMMERCIAL_TERMS_REVIEW_REQUIRED"):
            fetch_forecast(sample(), now=NOW, opener=fake)
        with self.assertRaisesRegex(ForecastSourceError, "FREE_API_COMMERCIAL_USE_FORBIDDEN"):
            fetch_forecast(sample(purpose="COMMERCIAL_BETTING_FEED"), now=NOW,
                           terms_reviewed=True, opener=fake)
        self.assertEqual(fake.calls, [])

    def test_one_request_no_cookie_and_no_token(self):
        fake = FakeOpener()
        raw = fetch_forecast(sample(), now=NOW, terms_reviewed=True, opener=fake)
        self.assertEqual(raw, provider())
        self.assertEqual(len(fake.calls), 1)
        url, headers, timeout = fake.calls[0]
        self.assertEqual(urlsplit(url).hostname, "api.open-meteo.com")
        self.assertEqual(timeout, 12)
        self.assertFalse(any(x.lower() in ("cookie", "authorization") for x in headers))

    def test_redirect_or_wrong_media_type_refused(self):
        with self.assertRaisesRegex(ForecastSourceError, "UNEXPECTED_HTTP_RESPONSE_OR_REDIRECT"):
            fetch_forecast(sample(), now=NOW, terms_reviewed=True,
                           opener=FakeOpener(changed_url=True))
        with self.assertRaisesRegex(ForecastSourceError, "UNEXPECTED_HTTP_RESPONSE_OR_REDIRECT"):
            fetch_forecast(sample(), now=NOW, terms_reviewed=True,
                           opener=FakeOpener(content_type="text/html"))

    def test_event_hour_weather_and_original_digest_no_promotion(self):
        raw = provider()
        result = parse_hourly(raw, sample(), now=NOW)
        self.assertEqual(result["forecast_valid_hour_utc"], "2026-11-16T19:00:00Z")
        self.assertEqual(result["event_hour_forecast"]["wind_speed_10m"], 15.0)
        self.assertEqual(result["event_hour_forecast"]["wind_gusts_10m"], 22.5)
        self.assertEqual(result["roof_status_owner_claim"], "OPEN")
        self.assertIsNone(result["provider_forecast_issue_time_utc"])
        self.assertFalse(result["historical_pregame_publication_certified"])
        self.assertFalse(result["weather_used_in_model_or_ev"])
        self.assertFalse(result["gate_a_closed"])
        self.assertEqual(result["approved_stake_u"], 0)

    def test_late_event_snapshot_rejected(self):
        with self.assertRaisesRegex(ForecastSourceError, "AFTER_EVENT_START_NO_PREGAME_CAPTURE"):
            validate_request(sample(event_start_utc=NOW.isoformat().replace("+00:00", "Z")), now=NOW)
        with self.assertRaisesRegex(ForecastSourceError, "AFTER_EVENT_START_NO_PREGAME_CAPTURE"):
            parse_hourly(provider(), sample(), now=NOW+timedelta(days=1))

    def test_future_beyond_forecast_horizon_refused(self):
        later = (NOW+timedelta(days=16)).isoformat().replace("+00:00", "Z")
        with self.assertRaisesRegex(ForecastSourceError, "OUTSIDE_16_DAY_FORECAST_HORIZON"):
            validate_request(sample(event_start_utc=later), now=NOW)

    def test_no_guessed_or_unverified_venue_identity(self):
        with self.assertRaisesRegex(ForecastSourceError, "INVALID_VENUE_ID"):
            validate_request(sample(venue_id="../something"), now=NOW)
        with self.assertRaisesRegex(ForecastSourceError, "INVALID_LATITUDE"):
            validate_request(sample(latitude=999), now=NOW)
        with self.assertRaisesRegex(ForecastSourceError, "INVALID_LONGITUDE"):
            validate_request(sample(longitude=float("nan")), now=NOW)

    def test_closed_roof_weather_not_implied_in_play(self):
        x = sample(roof_status="CLOSED")
        result = parse_hourly(provider(), x, now=NOW)
        self.assertIn("NOT_CONFIRMED_APPLICABLE", result["exposure_status"])
        self.assertFalse(result["weather_used_in_model_or_ev"])

    def test_utc_timezone_and_wrong_units_fail_closed(self):
        bad = json.loads(provider())
        bad["timezone"] = "America/Chicago"
        with self.assertRaisesRegex(ForecastSourceError, "PROVIDER_RESPONSE_MUST_USE_GMT"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)
        bad = json.loads(provider())
        bad["hourly_units"]["wind_speed_10m"] = "km/h"
        with self.assertRaisesRegex(ForecastSourceError, "INVALID_FORECAST_UNIT"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)

    def test_time_duplicates_and_missing_event_hour(self):
        bad = json.loads(provider())
        bad["hourly"]["time"][2] = bad["hourly"]["time"][1]
        with self.assertRaisesRegex(ForecastSourceError, "DUPLICATE_OR_UNSORTED"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)
        bad = json.loads(provider())
        bad["hourly"]["time"][1] = "2026-11-16T19:30"
        with self.assertRaisesRegex(ForecastSourceError, "INVALID_HOURLY_UTC_TIME"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)
        bad = json.loads(provider())
        bad["hourly"]["time"][1] = "2026-11-16T18:30"
        with self.assertRaisesRegex(ForecastSourceError, "INVALID_HOURLY_UTC_TIME"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)

    def test_missing_field_or_nan_forecast_rejected(self):
        bad = json.loads(provider())
        bad["hourly"]["wind_speed_10m"].pop()
        with self.assertRaisesRegex(ForecastSourceError, "FORECAST_HOURLY_COLUMN_LENGTH"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)
        bad = json.loads(provider())
        bad["hourly"]["wind_speed_10m"][1] = float("nan")
        with self.assertRaisesRegex(ForecastSourceError, "NONFINITE_JSON_LITERAL"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)

    def test_bad_ranges_and_grid_mismatch(self):
        bad = json.loads(provider())
        bad["hourly"]["precipitation_probability"][1] = 121
        with self.assertRaisesRegex(ForecastSourceError, "FORECAST_PERCENT_OUT_OF_RANGE"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)
        bad = json.loads(provider())
        bad["latitude"] = 44
        with self.assertRaisesRegex(ForecastSourceError, "VENUE_RESPONSE_GRID_TOO_FAR"):
            parse_hourly(json.dumps(bad).encode(), sample(), now=NOW)

    def test_duplicate_provider_keys_rejected(self):
        raw = provider().replace(b'"timezone": "GMT"',
                                 b'"timezone": "GMT", "timezone": "Europe/Paris"')
        with self.assertRaisesRegex(ForecastSourceError, "DUPLICATE_ORIGINAL_JSON_KEY"):
            parse_hourly(raw, sample(), now=NOW)

    def test_exponent_overflow_nested_json_rejected(self):
        # Python's standard JSON parser may convert 1e999 to float infinity.
        # A nonselected provider metadata field may not bypass that guard.
        bad = provider().replace(b'"generationtime_ms": 0.6',
                                 b'"generationtime_ms": 1e999')
        with self.assertRaisesRegex(ForecastSourceError, "NONFINITE_JSON_EXPONENT"):
            parse_hourly(bad, sample(), now=NOW)

    def test_original_byte_changes_digest(self):
        good = parse_hourly(provider(), sample(), now=NOW)
        other = json.loads(provider())
        other["hourly"]["wind_gusts_10m"][0] = 999
        changed = parse_hourly(json.dumps(other).encode(), sample(), now=NOW)
        self.assertNotEqual(good["source_raw_sha256"], changed["source_raw_sha256"])

    def test_private_capture_creates_original_once_and_receipt(self):
        with TemporaryDirectory() as td:
            folder = Path(td)
            folder.chmod(0o700)
            req = folder / "request.json"
            raw_request = json.dumps(sample()).encode("utf-8")
            req.write_bytes(raw_request)
            req.chmod(0o600)
            original = capture(req, folder, terms_reviewed=True, now=NOW,
                               opener=FakeOpener())
            self.assertEqual(original["approved_stake_u"], 0)
            sources = list(folder.glob("*.original.json"))
            reports = list(folder.glob("*.report.json"))
            self.assertEqual((len(sources), len(reports)), (1,1))
            self.assertEqual(sources[0].read_bytes(), provider())
            self.assertEqual(sources[0].stat().st_mode & 0o077, 0)
            self.assertEqual(reports[0].stat().st_mode & 0o077, 0)
            self.assertEqual(req.read_bytes(), raw_request)
            with self.assertRaises(FileExistsError):
                capture(req, folder, terms_reviewed=True, now=NOW,
                        opener=FakeOpener())

    def test_invalid_forecast_still_archives_original_and_no_valid_report(self):
        with TemporaryDirectory() as td:
            folder = Path(td)
            folder.chmod(0o700)
            req = folder / "request.json"
            req.write_text(json.dumps(sample()))
            req.chmod(0o600)
            with self.assertRaisesRegex(ForecastSourceError, "INVALID_JSON"):
                capture(req, folder, terms_reviewed=True, now=NOW,
                        opener=FakeOpener(content=b"{corrupt"))
            self.assertEqual(len(list(folder.glob("*.original.json"))), 1)
            self.assertEqual(len(list(folder.glob("*.report.json"))), 0)

    def test_source_private_and_public_repository_denied(self):
        with TemporaryDirectory() as td:
            folder = Path(td)
            folder.chmod(0o700)
            req = folder / "request.json"
            req.write_bytes(json.dumps(sample()).encode())
            req.chmod(0o644)
            with self.assertRaisesRegex(ForecastSourceError, "PRIVATE_INPUT_0600_REQUIRED"):
                read_request(req)
            req.chmod(0o600)
            alias = folder / "aliased.json"
            alias.symlink_to(req)
            with self.assertRaisesRegex(ForecastSourceError, "SYMLINK"):
                read_request(alias)
            folder.chmod(0o755)
            with self.assertRaisesRegex(ForecastSourceError, "PRIVATE_PARENT_0700_REQUIRED"):
                read_request(req)
        with self.assertRaisesRegex(ForecastSourceError, "PUBLIC_REPOSITORY_PATH_FORBIDDEN"):
            _private(Path(__file__).resolve().parents[2] / "secrets.json")

    def test_non_nfl_research_sports_contract(self):
        for sport in ("CFB", "MLB", "PGA"):
            x = sample(sport=sport)
            self.assertEqual(parse_hourly(provider(), x, now=NOW)["sport"], sport)
        with self.assertRaisesRegex(ForecastSourceError, "UNSUPPORTED_WEATHER_SPORT_OR_SCHEMA"):
            validate_request(sample(sport="NBA"), now=NOW)


if __name__ == "__main__":
    unittest.main()
