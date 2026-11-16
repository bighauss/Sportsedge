"""Synthetic end-to-end Open-Meteo source-to-RUN IT event overlay regressions."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sportsedge.data.open_meteo_pit import parse_hourly
from sportsedge.data.test_open_meteo_pit import sample, provider
from sportsedge.markets.weather_slate_overlay import (
    WeatherSlateError, attach_weather_references, load_triplets,
)
from sportsedge.markets.slate_orchestrator import run_slate, main
from sportsedge.markets.test_slate_orchestrator import fixture


def _z(t):
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _weather_for_event(start, *, event_id="NFL-E2", captured=None, roof="OPEN"):
    begin = datetime.fromisoformat(start.replace("Z", "+00:00"))
    hour = begin.replace(minute=0, second=0, microsecond=0)
    captured = captured or datetime.now(timezone.utc) - timedelta(minutes=1)
    request = sample(
        event_id=event_id,
        event_start_utc=_z(begin),
        roof_status=roof,
    )
    raw_req = json.dumps(request, ensure_ascii=False).encode()
    response = json.loads(provider())
    response["hourly"]["time"] = [
        (hour + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
        for i in (-1, 0, 1)
    ]
    raw_provider = json.dumps(response, ensure_ascii=False).encode()
    receipt = parse_hourly(raw_provider, request, now=captured)
    receipt["request_sha256"] = "sha256:" + sha256(raw_req).hexdigest()
    filename = "synthetic.openmeteo.original.json"
    receipt["original_file_basename"] = filename
    raw_report = json.dumps(receipt, sort_keys=True, allow_nan=False).encode()
    return {
        "request_bytes": raw_req,
        "original_bytes": raw_provider,
        "report_bytes": raw_report,
        "original_filename": filename,
    }


def _setup(*, captured=None, roof="OPEN"):
    f = fixture()
    start = next(row["start_utc"] for row in f["expected_events"]
                 if row["event_id"] == "NFL-E2")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    raw = _weather_for_event(start, captured=captured or
                             (now-timedelta(minutes=1)), roof=roof)
    return f, raw, now


class OpenMeteoSlateTests(unittest.TestCase):
    def test_one_exact_event_attached_with_all_market_inventory_intact(self):
        f, item, now = _setup()
        basic = run_slate(f, now=now)
        out = attach_weather_references(basic, [item], now_utc=now)
        self.assertNotIn("open_meteo_weather_reference", basic)
        nfl = next(x for x in out["events"] if x["event_id"] == "NFL-E2")
        cbb = next(x for x in out["events"] if x["sport"] == "CBB")
        self.assertEqual(nfl["open_meteo_weather_reference"]["state"],
                         "PAPER_OUTDOOR_FORECAST_REFERENCE_UNVERIFIED")
        self.assertIn("PLAYER_PROP", nfl["families"])
        self.assertEqual(nfl["families"], next(e for e in basic["events"]
                         if e["event_id"] == "NFL-E2")["families"])
        self.assertEqual(cbb["open_meteo_weather_reference"]["state"],
                         "WEATHER_SOURCE_NOT_REQUESTED_FOR_THIS_SPORT")
        self.assertFalse(out["source_authentication_verified"])
        self.assertEqual(out["approved_stake_u"], 0)
        self.assertIsNone(out["card"])
        self.assertFalse(out["open_meteo_weather_reference"]["model_run_issue_time_verified"])

    def test_original_market_prices_and_guards_never_change(self):
        f, item, now = _setup()
        plain = run_slate(f, now=now)
        with_weather = run_slate(f, now=now, weather_triplets=[item])
        self.assertEqual(plain["counts"], with_weather["counts"])
        for p, q in zip(plain["events"], with_weather["events"]):
            for field in ("status", "research_candidates", "research_priced",
                          "research_blocked", "approved_stake_u", "official_counted",
                          "families"):
                self.assertEqual(p[field], q[field])
            self.assertEqual(len(p.get("research_rows", [])),
                             len(q.get("research_rows", [])))
            for row_a, row_b in zip(p.get("research_rows", []),
                                    q.get("research_rows", [])):
                for field in ("market", "research_state", "research_reasons",
                              "raw_ev_unverified", "blended_ev_unverified",
                              "guard_state", "guard_reasons"):
                    self.assertEqual(row_a[field], row_b[field])

    def test_original_provider_weather_and_request_sha_exactly_bound(self):
        f, item, now = _setup()
        original = json.loads(item["report_bytes"])
        result = attach_weather_references(run_slate(f, now=now), [item],
                                           now_utc=now)
        weather = next(x for x in result["events"] if x["sport"] == "NFL")[
            "open_meteo_weather_reference"]
        self.assertEqual(weather["source_original_sha256"], original["source_raw_sha256"])
        self.assertEqual(weather["source_request_sha256"], original["request_sha256"])
        self.assertEqual(weather["event_hour_weather_forecast"],
                         original["event_hour_forecast"])
        self.assertEqual(weather["attribution"], "Weather data by Open-Meteo.com")

    def test_source_data_and_wager_status_never_promoted(self):
        f, item, now = _setup()
        out = run_slate(f, now=now, weather_triplets=[item])
        weather = next(x for x in out["events"] if x["sport"] == "NFL")[
            "open_meteo_weather_reference"]
        self.assertFalse(weather["provider_original_issue_clock_authenticated"])
        self.assertFalse(weather["weather_used_for_odds_or_bets"])
        self.assertFalse(weather["weather_model_weight_validated"])
        self.assertFalse(out["issue10_release_certified"])
        self.assertEqual(weather["official_counted"], 0)

    def test_stale_capture_is_visible_and_not_represented_as_fresh(self):
        f, _, now = _setup()
        start = next(x["start_utc"] for x in f["expected_events"]
                     if x["event_id"] == "NFL-E2")
        item = _weather_for_event(start, captured=now-timedelta(hours=7))
        out = run_slate(f, now=now, weather_triplets=[item])
        status = next(e for e in out["events"] if e["sport"] == "NFL")[
            "open_meteo_weather_reference"]["state"]
        self.assertEqual(status, "BLOCK_WEATHER_CAPTURE_STALE_OVER_6H")

    def test_closed_roof_never_claims_outdoor_effect(self):
        f, item, now = _setup(roof="CLOSED")
        out = run_slate(f, now=now, weather_triplets=[item])
        status = next(e for e in out["events"] if e["sport"] == "NFL")[
            "open_meteo_weather_reference"]["state"]
        self.assertEqual(status, "RESEARCH_WEATHER_EXPOSURE_NOT_CONFIRMED")

    def test_future_collection_claim_is_refused(self):
        f, _, now = _setup()
        start = next(x["start_utc"] for x in f["expected_events"]
                     if x["event_id"] == "NFL-E2")
        item = _weather_for_event(start, captured=now+timedelta(minutes=15))
        with self.assertRaisesRegex(WeatherSlateError,
                                    "WEATHER_CAPTURE_AFTER_RUN_IT_DECISION"):
            run_slate(f, now=now, weather_triplets=[item])

    def test_game_started_blocks_existing_weather_capture(self):
        f, item, _ = _setup()
        start = datetime.fromisoformat(next(x["start_utc"]
                      for x in f["expected_events"] if x["event_id"] == "NFL-E2"))
        later = start + timedelta(minutes=2)
        out = run_slate(f, now=later, weather_triplets=[item])
        state = next(e for e in out["events"] if e["sport"] == "NFL")[
            "open_meteo_weather_reference"]["state"]
        self.assertEqual(state, "BLOCK_WEATHER_LIVE_OR_AFTER_EVENT_START")

    def test_response_mutation_makes_receipt_fail_source_replay(self):
        f, item, now = _setup()
        bad = deepcopy(item)
        doc = json.loads(bad["original_bytes"])
        doc["hourly"]["wind_speed_10m"][1] += 18
        bad["original_bytes"] = json.dumps(doc).encode()
        with self.assertRaisesRegex(WeatherSlateError,
                                    "WEATHER_SOURCE_REPORT_ORIGINAL_MISMATCH"):
            run_slate(f, now=now, weather_triplets=[bad])

    def test_receipt_tamper_and_forged_provider_issuance_denied(self):
        f, item, now = _setup()
        for key, val in (("provider_model_run_issuance_verified", True),
                         ("approved_stake_u", 4),
                         ("weather_used_in_model_or_ev", True)):
            bad = deepcopy(item)
            doc = json.loads(bad["report_bytes"])
            doc[key] = val
            bad["report_bytes"] = json.dumps(doc).encode()
            with self.assertRaisesRegex(WeatherSlateError,
                                        "WEATHER_SOURCE_REPORT_ORIGINAL_MISMATCH"):
                run_slate(f, now=now, weather_triplets=[bad])

    def test_request_mutation_and_source_sha_mismatch_denied(self):
        f, item, now = _setup()
        bad = deepcopy(item)
        req = json.loads(bad["request_bytes"])
        req["latitude"] += 0.5
        bad["request_bytes"] = json.dumps(req).encode()
        with self.assertRaises(WeatherSlateError):
            run_slate(f, now=now, weather_triplets=[bad])

    def test_duplicate_original_for_same_game_refused(self):
        f, item, now = _setup()
        with self.assertRaisesRegex(WeatherSlateError,
                                    "DUPLICATE_WEATHER_ORIGINAL_EVENT"):
            run_slate(f, now=now, weather_triplets=[item, deepcopy(item)])

    def test_cross_event_or_wrong_start_denied(self):
        f, item, now = _setup()
        wrong = deepcopy(item)
        req = json.loads(wrong["request_bytes"])
        req["event_id"] = "MISSING_EVENT"
        wrong["request_bytes"] = json.dumps(req).encode()
        with self.assertRaises(WeatherSlateError):
            run_slate(f, now=now, weather_triplets=[wrong])
        out = run_slate(f, now=now)
        nfl = next(x for x in out["events"] if x["sport"] == "NFL")
        nfl["start_utc"] = (datetime.fromisoformat(nfl["start_utc"]) +
                            timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(WeatherSlateError,"WEATHER_EVENT_START_MISMATCH"):
            attach_weather_references(out,[item],now_utc=now)

    def test_report_filename_mismatch_refused(self):
        f, item, now = _setup()
        bad = deepcopy(item)
        bad["original_filename"] = "other_json_file.json"
        with self.assertRaisesRegex(WeatherSlateError,
                                    "WEATHER_SOURCE_REPORT_ORIGINAL_MISMATCH"):
            run_slate(f, now=now, weather_triplets=[bad])

    def test_no_weather_input_does_not_affect_existing_cli(self):
        f, _, now = _setup()
        out = run_slate(f, now=now)
        self.assertNotIn("open_meteo_weather_reference", out)
        self.assertEqual(out["approved_stake_u"], 0)

    def test_private_triplet_cli_end_to_end_no_extra_sources(self):
        f, item, now = _setup()
        with TemporaryDirectory() as td:
            root = Path(td)
            root.chmod(0o700)
            slate = root / "slate.json"
            req = root / "weather_request.json"
            raw = root / item["original_filename"]
            receipt = root / "weather_report.json"
            result = root / "result.json"
            for p, contents in (
                (slate, json.dumps(f).encode()),
                (req, item["request_bytes"]),
                (raw, item["original_bytes"]),
                (receipt, item["report_bytes"]),
            ):
                p.write_bytes(contents)
                p.chmod(0o600)
            argv = [str(slate),str(result),"--weather-triplet",
                    str(req),str(raw),str(receipt)]
            self.assertEqual(main(argv),0)
            out=json.loads(result.read_text())
            self.assertEqual(out["open_meteo_weather_reference"][
                "counts"]["original_triplets_validated"],1)
            self.assertEqual(result.stat().st_mode&0o077,0)
            self.assertEqual(out["approved_stake_u"],0)
            with self.assertRaises(FileExistsError):
                main(argv)

    def test_private_triplet_rejects_world_readable_original_file(self):
        f, item, _ = _setup()
        with TemporaryDirectory() as td:
            root=Path(td)
            root.chmod(0o700)
            paths=[root / ("file"+str(i)) for i in range(3)]
            for p, bytes_ in zip(paths,(item["request_bytes"],item["original_bytes"],
                                      item["report_bytes"])):
                p.write_bytes(bytes_)
                p.chmod(0o600)
            paths[1].chmod(0o644)
            with self.assertRaisesRegex(Exception,"PRIVATE_INPUT_0600_REQUIRED"):
                load_triplets([paths])
            self.assertEqual(len(list(root.glob("*.openmeteo.report.json"))),0)

    def test_private_triplet_no_file_aliases(self):
        f, item, _ = _setup()
        with TemporaryDirectory() as td:
            root=Path(td)
            root.chmod(0o700)
            p=root/"data.json"
            p.write_bytes(item["original_bytes"])
            p.chmod(0o600)
            with self.assertRaisesRegex(WeatherSlateError,
                                        "WEATHER_TRIPLET_PATHS_MUST_BE_DISTINCT"):
                load_triplets([(p,p,p)])

    def test_no_unknown_weather_sport_or_overcounted_registry(self):
        f, item, now = _setup()
        out = run_slate(f, now=now, weather_triplets=[item])
        self.assertEqual(out["open_meteo_weather_reference"]["counts"]["scheduled_events"],
                         len(out["events"]))
        self.assertEqual(out["open_meteo_weather_reference"]["counts"]["fresh_outdoor_research"],1)
        self.assertFalse(out["open_meteo_weather_reference"]["commercial_reuse_permitted_by_free_tier"])


if __name__ == "__main__":
    unittest.main()
