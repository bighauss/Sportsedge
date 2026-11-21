"""Synthetic, offline tests for the CFB PAPER card pipeline. Fake teams, fake numbers.

Nothing here is real CFBD, Open-Meteo or sportsbook data, and passing these
tests is NOT predictive validation of any model.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest import mock

from models.cfb import cfb_baselines as baselines
from models.cfb import cfb_capture_store as store
from models.cfb import cfb_cfbd_capture as cfbd_capture
from models.cfb import cfb_grading as grading
from models.cfb import cfb_ledger as ledger
from models.cfb import cfb_paper_card as card_mod
from models.cfb import cfb_pregame_assembler as asm
from models.cfb import sportsedge_cfb_model as runit
from sportsedge.data import open_meteo_pit
from sportsedge.validation import daily_ratings_capture as ratings_capture

SEASON, WEEK = 2026, 13
T = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
CAPTURED = T("2026-11-27T12:00:00Z")
SP_OBSERVED = T("2026-11-27T10:00:00Z")
FROZEN = "2026-11-28T15:00:00Z"
K1, K2 = "2026-11-28T20:00:00.000Z", "2026-11-28T23:30:00.000Z"
TEAMS = {"Alpha State": 11, "Beta Tech": 12, "Delta Mines": 13, "Gamma U": 14}


def _side(ppa, plays=760, drives=125):
    return {"plays": plays, "drives": drives, "ppa": ppa, "successRate": 0.44, "explosiveness": 1.25,
            "pointsPerOpportunity": 4.2, "fieldPosition": {"averageStart": 29.0}, "havoc": {"total": 0.16},
            "rushingPlays": {"ppa": ppa - 0.03, "successRate": 0.43, "rate": 0.52},
            "passingPlays": {"ppa": ppa + 0.05, "successRate": 0.45, "rate": 0.48}}


def games_doc(over=None):
    over = over or {}
    g1 = {"id": 401, "season": SEASON, "week": WEEK, "seasonType": "regular", "startDate": K1,
          "startTimeTBD": False, "completed": False, "neutralSite": False, "venue": "Alpha Field",
          "homeId": 11, "homeTeam": "Alpha State", "homePoints": None,
          "awayId": 12, "awayTeam": "Beta Tech", "awayPoints": None}
    g2 = {**g1, "id": 402, "startDate": K2, "venue": "Mines Bowl", "homeId": 13, "homeTeam": "Delta Mines",
          "awayId": 14, "awayTeam": "Gamma U"}
    g1.update(over.get(401, {}))
    g2.update(over.get(402, {}))
    return [g1, g2]


def advanced_doc(season=SEASON):
    vals = {"Alpha State": (0.30, 0.05), "Beta Tech": (0.12, 0.15), "Delta Mines": (0.20, 0.10),
            "Gamma U": (0.18, 0.12), "Filler A": (0.10, 0.10), "Filler B": (0.05, 0.20)}
    return [{"season": season, "team": t, "conference": "X", "offense": _side(o), "defense": _side(d)}
            for t, (o, d) in vals.items()]


def talent_doc(season=SEASON):
    return [{"year": season, "team": t, "talent": 700 + 10 * i} for i, t in enumerate(TEAMS)]


def returning_doc(season=SEASON):
    return [{"season": season, "team": t, "percentPPA": 0.55} for t in TEAMS]


def sp_doc(season=SEASON):
    rows = [{"year": season, "team": t, "rating": r, "offense": {"rating": o}, "defense": {"rating": d},
             "specialTeams": {"rating": 0.5}}
            for t, (r, o, d) in {"Alpha State": (20.0, 38.0, 18.0), "Beta Tech": (2.0, 30.0, 28.0),
                                 "Delta Mines": (8.0, 33.0, 25.0), "Gamma U": (6.0, 31.0, 25.0)}.items()]
    rows += [{"year": season, "team": f"Filler {i:03d}", "rating": 0.0, "offense": {"rating": 29.0},
              "defense": {"rating": 29.0}, "specialTeams": {"rating": 0.0}} for i in range(126)]
    return rows


def qb_doc(rows=None, season=SEASON):
    if rows is None:
        rows = [{"cfbd_game_id": 401, "team_id": 11, "team": "Alpha State", "qb_id": "qb-a", "starter_status": "CONFIRMED"},
                {"cfbd_game_id": 401, "team_id": 12, "team": "Beta Tech", "qb_id": "qb-b", "starter_status": "CONFIRMED"},
                {"cfbd_game_id": 402, "team_id": 13, "team": "Delta Mines", "qb_id": "qb-d", "starter_status": "CONFIRMED"},
                {"cfbd_game_id": 402, "team_id": 14, "team": "Gamma U", "qb_id": "qb-g", "starter_status": "CONFIRMED"}]
    return {"schema": asm.QB_SCHEMA, "season": season, "rows": rows}


def injury_doc(rows=None, reviewed=(401, 402), season=SEASON):
    if rows is None:
        rows = [{"cfbd_game_id": 401, "team_id": 12, "team": "Beta Tech", "player_id": "p-9", "player": "Fake WR",
                 "role": "STAR_SKILL", "status": "OUT"}]
    return {"schema": asm.INJURY_SCHEMA, "season": season, "games_reviewed": list(reviewed), "rows": rows}


def b(doc):
    return json.dumps(doc).encode()


def open_meteo_raw(kickoff, wind=9.0, lat=40.0, lon=-90.0):
    start = T(kickoff).replace(minute=0, second=0, microsecond=0) - timedelta(hours=24)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00") for h in range(48)]
    n = len(times)
    return b({"latitude": lat, "longitude": lon, "utc_offset_seconds": 0, "timezone": "GMT",
              "hourly_units": {"time": "iso8601", **open_meteo_pit.UNITS},
              "hourly": {"time": times, "temperature_2m": [50.0] * n, "wind_speed_10m": [wind] * n,
                         "wind_gusts_10m": [wind + 5] * n, "precipitation_probability": [10] * n,
                         "cloud_cover": [40] * n}})


class Fixture:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="cfb-card-test-"))
        os.chmod(self.root, 0o700)
        self.capture = self.root / "capture"
        self.weather = self.root / "weather"
        self.weather.mkdir(mode=0o700)
        self.cards = self.root / "cards"
        self.ledger = self.root / "ledger" / "cfb_ledger.jsonl"
        store.init_capture(self.capture, season=SEASON, week=WEEK)
        self.ratings_dirs = []

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def put(self, source, doc, captured=CAPTURED, observed=None, raw=None):
        return store.store_source(self.capture, source, raw if raw is not None else b(doc),
                                  provider="synthetic-test", observed_utc=observed or captured,
                                  captured_utc=captured)

    def sp(self, doc=None, observed=SP_OBSERVED, season=SEASON):
        d = self.root / f"ratings-{len(self.ratings_dirs)}"
        body = b(doc if doc is not None else sp_doc(season))
        src = ratings_capture.sources(season, season)[1]
        with mock.patch.dict(os.environ, {"CFBD_API_KEY": "synthetic-not-a-key"}):
            ratings_capture.capture(d, [src], fetch=lambda url, key: (200, body), clock=lambda: observed)
        self.ratings_dirs.append(d)

    def wx(self, gid, kickoff, captured=CAPTURED, wind=9.0, roof="OPEN", report_kickoff=None):
        eid = asm.weather_event_id(SEASON, gid)
        request = {"schema": open_meteo_pit.SCHEMA, "sport": "CFB", "event_id": eid,
                   "event_start_utc": store.stamp(T(report_kickoff or kickoff)), "venue_id": f"venue-{gid}",
                   "latitude": 40.0, "longitude": -90.0, "coordinate_source": "synthetic",
                   "roof_status": roof, "purpose": "PERSONAL_NONCOMMERCIAL_RESEARCH"}
        raw = open_meteo_raw(report_kickoff or kickoff, wind)
        rep = open_meteo_pit.parse_hourly(raw, request, now=captured)
        stem = eid + "_" + captured.strftime("%Y%m%dT%H%M%SZ")
        (self.weather / (stem + ".openmeteo.original.json")).write_bytes(raw)
        rep["original_file_basename"] = stem + ".openmeteo.original.json"
        rep["request_sha256"] = "sha256:" + sha256(b(request)).hexdigest()
        (self.weather / (stem + ".openmeteo.report.json")).write_bytes(b(rep))

    def standard(self, *, skip=()):
        for src, doc in (("cfbd_games", games_doc()), ("cfbd_advanced", advanced_doc()),
                         ("cfbd_talent", talent_doc()), ("cfbd_returning", returning_doc()),
                         ("operator_qb", qb_doc()), ("operator_injuries", injury_doc())):
            if src not in skip:
                self.put(src, doc)
        if "sp" not in skip:
            self.sp()
        if "weather" not in skip:
            self.wx(401, K1)
            self.wx(402, K2)
        return self

    def slate(self, frozen=FROZEN, quotes=None):
        return asm.assemble_slate(self.capture, frozen_utc=frozen, ratings_dirs=self.ratings_dirs,
                                  weather_dir=self.weather, quote_receipts=quotes)

    def card(self, frozen=FROZEN, quotes=()):
        return card_mod.build_card(self.capture, frozen_utc=frozen, quotes=quotes,
                                   ratings_dirs=self.ratings_dirs, weather_dir=self.weather)


def quotes_json(rows):
    return b({"schema": card_mod.QUOTE_SCHEMA, "rows": rows})


STANDARD_QUOTES = [
    {"cfbd_game_id": 401, "book": "bookA", "market": "ML", "home_price": -250, "away_price": 205,
     "captured_utc": "2026-11-28T14:00:00Z"},
    {"cfbd_game_id": 401, "book": "bookA", "market": "SPREAD", "line": -7.0, "home_price": -110,
     "away_price": -110, "captured_utc": "2026-11-28T14:00:00Z"},
    {"cfbd_game_id": 401, "book": "bookA", "market": "TOTAL", "line": 55.0, "over_price": -105,
     "under_price": -115, "captured_utc": "2026-11-28T14:00:00Z"},
]


def by_gid(slate_or_card, gid):
    return next(g for g in slate_or_card["games"] if g["cfbd_game_id"] == gid)


class NetworkOff(unittest.TestCase):
    def setUp(self):
        self._sock = mock.patch.object(socket, "socket", side_effect=AssertionError("network used"))
        self._sock.start()
        self.fx = Fixture()

    def tearDown(self):
        self._sock.stop()
        self.fx.cleanup()


class BaselineFreezeTests(NetworkOff):
    def test_frozen_model_file_and_weights_pinned(self):
        v = baselines.verify_frozen_model()
        self.assertEqual(v["module_sha256"], sha256(baselines.FROZEN_MODEL_FILE.read_bytes()).hexdigest())
        self.assertEqual(baselines.live_frozen_constants(), baselines.FROZEN_CONSTANTS)
        self.assertFalse(v["weights_validated"])
        # The pins themselves must match the model's documented untested starting values.
        self.assertEqual((runit.W_RATINGS, runit.W_MATCHUP, runit.SD_MARGIN, runit.SD_TOTAL), (0.5, 0.5, 15.5, 15.0))

    def test_constant_drift_refused(self):
        with mock.patch.object(runit, "W_RATINGS", 0.6):
            with self.assertRaisesRegex(baselines.ModelRefused, "CONSTANT_DRIFT"):
                baselines.verify_frozen_model()

    def test_file_drift_refused(self):
        with mock.patch.dict(baselines.FROZEN_RUNIT, {"module_sha256": "0" * 64}):
            with self.assertRaisesRegex(baselines.ModelRefused, "FILE_SHA_DRIFT"):
                baselines.verify_frozen_model()

    def test_ratings_only_math(self):
        h = {"offense": {"rating": 38.0}, "defense": {"rating": 18.0}}
        a = {"offense": {"rating": 30.0}, "defense": {"rating": 28.0}}
        f = baselines.ratings_only_forecast(h, a, neutral=False, means=(30.0, 25.0))
        self.assertAlmostEqual(f["pts_home"], 28 + 8 + 3 + 1.25)
        self.assertAlmostEqual(f["pts_away"], 28 + 0 - 7 - 1.25)
        self.assertAlmostEqual(f["p_home_win"], round(baselines.p_greater(f["margin_home"], 0, 15.5), 6))
        n = baselines.ratings_only_forecast(h, a, neutral=True, means=(30.0, 25.0))
        self.assertAlmostEqual(n["margin_home"], 18.0)

    def test_pass_requires_reason(self):
        with self.assertRaises(baselines.ModelRefused):
            baselines.pass_forecast("m", [])


class AssemblerTests(NetworkOff):
    def test_happy_path_ready_with_exact_ids_and_hashes(self):
        s = self.fx.standard().slate()
        g = by_gid(s, 401)
        self.assertEqual(g["status"], "READY", g["reasons"])
        self.assertEqual(g["event_id"], "cfbd:2026:401")
        self.assertEqual((g["home_team_id"], g["away_team_id"]), (11, 12))
        self.assertEqual(set(g["contract"]["normalized_source_sha256"]),
                         {"game", "team_stats", "qb", "weather", "injuries"})
        for lin in g["lineage"].values():
            self.assertRegex(lin["sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertLessEqual(store.utc(asm._zs(lin["captured_utc"])), store.utc(FROZEN))
        self.assertIn("open_meteo_forecast", g["lineage"])
        self.assertEqual(s["official_counted"], 0)

    def test_source_captured_after_freeze_is_ignored(self):
        self.fx.standard()
        late = qb_doc()
        late["rows"][0]["starter_status"] = "OUT"
        self.fx.put("operator_qb", late, captured=T("2026-11-28T15:30:00Z"))
        self.assertEqual(by_gid(self.fx.slate(), 401)["status"], "READY")
        # A later freeze does see it and HOLDs.
        g = by_gid(self.fx.slate(frozen="2026-11-28T16:00:00Z"), 401)
        self.assertEqual(g["status"], "HOLD")
        self.assertIn("QB_STARTER_NOT_CONFIRMED:cfbd-team:11", g["reasons"])

    def test_only_late_sources_means_pass_not_lookahead(self):
        self.fx.standard(skip=("cfbd_advanced",))
        self.fx.put("cfbd_advanced", advanced_doc(), captured=T("2026-11-28T15:00:01Z"))
        g = by_gid(self.fx.slate(), 401)
        self.assertEqual(g["status"], "PASS")
        self.assertIn("ADVANCED_STATS_FILE_MISSING", g["reasons"])

    def test_no_games_file_before_freeze_refused(self):
        self.fx.standard(skip=("cfbd_games",))
        self.fx.put("cfbd_games", games_doc(), captured=T("2026-11-28T16:00:00Z"))
        with self.assertRaisesRegex(store.CaptureRefused, "NO_GAMES_FILE"):
            self.fx.slate()

    def test_historical_capture_mode_refused(self):
        d = self.fx.root / "hist"
        with self.assertRaisesRegex(store.CaptureRefused, "NOT_PREGAME_EVIDENCE"):
            store.init_capture(d, season=SEASON, week=WEEK, mode="HISTORICAL_BACKFILL")
        doc = json.loads((self.fx.capture / "capture.json").read_bytes())
        doc["capture_mode"] = "HISTORICAL_BACKFILL"
        (self.fx.capture / "capture.json").write_bytes(b(doc))
        with self.assertRaisesRegex(store.CaptureRefused, "NOT_PREGAME_EVIDENCE"):
            self.fx.slate()

    def test_games_file_with_target_result_is_post_game(self):
        self.fx.standard(skip=("cfbd_games",))
        # File captured after the game (impossible pregame) but backdated: result before start => refused.
        self.fx.put("cfbd_games", games_doc({401: {"completed": True, "homePoints": 30, "awayPoints": 20}}))
        with self.assertRaisesRegex(store.CaptureRefused, "CLOCK_INCONSISTENT"):
            self.fx.slate()

    def test_completed_game_in_file_passes(self):
        self.fx.standard(skip=("cfbd_games",))
        early = games_doc({401: {"startDate": "2026-11-27T01:00:00.000Z", "completed": True,
                                   "homePoints": 30, "awayPoints": 20}})
        self.fx.put("cfbd_games", early)
        g = by_gid(self.fx.slate(), 401)
        self.assertEqual(g["status"], "PASS")
        self.assertIn("GAME_ALREADY_COMPLETED_IN_SOURCE_FILE_NOT_PREGAME", g["reasons"])
        self.assertIn("KICKOFF_NOT_AFTER_FREEZE", g["reasons"])

    def test_kickoff_before_freeze_passes(self):
        g = by_gid(self.fx.standard().slate(frozen="2026-11-28T21:00:00Z"), 401)
        self.assertEqual(g["status"], "PASS")
        self.assertIn("KICKOFF_NOT_AFTER_FREEZE", g["reasons"])
        self.assertEqual(by_gid(self.fx.slate(frozen="2026-11-28T21:00:00Z"), 402)["status"], "READY")

    def test_wrong_season_files_refused(self):
        self.fx.standard(skip=("cfbd_advanced",))
        self.fx.put("cfbd_advanced", advanced_doc(season=2025))
        with self.assertRaisesRegex(store.CaptureRefused, "ADVANCED_WRONG_SEASON"):
            self.fx.slate()

    def test_wrong_season_games_and_operator_files_refused(self):
        self.fx.standard(skip=("operator_qb",))
        self.fx.put("operator_qb", qb_doc(season=2025))
        with self.assertRaisesRegex(store.CaptureRefused, "OPERATOR_QB_SCHEMA_OR_SEASON"):
            self.fx.slate()

    def test_wrong_season_sp_is_not_eligible(self):
        self.fx.standard(skip=("sp",))
        self.fx.sp(season=2025)
        g = by_gid(self.fx.slate(), 401)
        self.assertEqual(g["status"], "PASS")
        self.assertIn("SP_RATINGS_NOT_ELIGIBLE_AT_FREEZE", g["reasons"])

    def test_stale_sp_not_eligible(self):
        self.fx.standard(skip=("sp",))
        self.fx.sp(observed=T("2026-11-10T10:00:00Z"))
        self.assertIn("SP_RATINGS_NOT_ELIGIBLE_AT_FREEZE", by_gid(self.fx.slate(), 401)["reasons"])

    def test_sp_after_freeze_not_used(self):
        self.fx.standard(skip=("sp",))
        self.fx.sp(observed=T("2026-11-28T15:30:00Z"))
        self.assertIn("SP_RATINGS_NOT_ELIGIBLE_AT_FREEZE", by_gid(self.fx.slate(), 401)["reasons"])

    def test_sp_missing_team_passes(self):
        self.fx.standard(skip=("sp",))
        self.fx.sp(doc=[r for r in sp_doc() if r["team"] != "Beta Tech"])
        self.assertIn("SP_RATING_MISSING:Beta Tech", by_gid(self.fx.slate(), 401)["reasons"])

    def test_borrowed_qb_team_id(self):
        rows = qb_doc()["rows"]
        rows[1] = {**rows[1], "team_id": 13, "team": "Delta Mines"}
        self.fx.standard(skip=("operator_qb",))
        self.fx.put("operator_qb", qb_doc(rows))
        g = by_gid(self.fx.slate(), 401)
        self.assertEqual(g["status"], "PASS")
        self.assertIn("QB_BORROWED_TEAM_ID", g["reasons"])

    def test_qb_name_disagrees_with_id(self):
        rows = qb_doc()["rows"]
        rows[0] = {**rows[0], "team": "Beta Tech"}
        self.fx.standard(skip=("operator_qb",))
        self.fx.put("operator_qb", qb_doc(rows))
        self.assertIn("QB_TEAM_NAME_ID_MISMATCH", by_gid(self.fx.slate(), 401)["reasons"])

    def test_games_name_id_conflict_refused(self):
        self.fx.standard(skip=("cfbd_games",))
        self.fx.put("cfbd_games", games_doc({402: {"awayId": 12, "awayTeam": "Gamma U"}}))
        with self.assertRaisesRegex(store.CaptureRefused, "GAMES_TEAM"):
            self.fx.slate()

    def test_borrowed_injury_team_id(self):
        self.fx.standard(skip=("operator_injuries",))
        self.fx.put("operator_injuries", injury_doc([{"cfbd_game_id": 401, "team_id": 14, "player_id": "p1",
                                                      "role": "QB", "status": "OUT"}]))
        self.assertIn("INJURY_BORROWED_TEAM_ID", by_gid(self.fx.slate(), 401)["reasons"])

    def test_uncertain_qb_holds(self):
        rows = qb_doc()["rows"]
        rows[1]["starter_status"] = "QUESTIONABLE"
        self.fx.standard(skip=("operator_qb",))
        self.fx.put("operator_qb", qb_doc(rows))
        g = by_gid(self.fx.slate(), 401)
        self.assertEqual(g["status"], "HOLD")
        self.assertEqual(g["reasons"], ["QB_STARTER_NOT_CONFIRMED:cfbd-team:12"])
        self.assertEqual(by_gid(self.fx.slate(), 402)["status"], "READY")

    def test_missing_qb_row_and_file_hold(self):
        self.fx.standard(skip=("operator_qb",))
        self.fx.put("operator_qb", qb_doc(qb_doc()["rows"][1:]))
        g = by_gid(self.fx.slate(), 401)
        self.assertEqual(g["status"], "HOLD")
        self.assertIn("QB_STATUS_UNKNOWN:11", g["reasons"])
        fx2 = Fixture()
        try:
            fx2.standard(skip=("operator_qb",))
            g2 = by_gid(fx2.slate(), 401)
            self.assertEqual((g2["status"], g2["reasons"]), ("HOLD", ["QB_STATUS_FILE_MISSING"]))
        finally:
            fx2.cleanup()

    def test_injury_file_rules(self):
        self.fx.standard(skip=("operator_injuries",))
        self.assertIn("INJURY_REPORT_MISSING", by_gid(self.fx.slate(), 401)["reasons"])
        self.fx.put("operator_injuries", injury_doc([], reviewed=(401,)))
        s = self.fx.slate()
        self.assertEqual(by_gid(s, 401)["status"], "READY")
        self.assertIn("INJURY_LIST_EMPTY_NOT_PROOF_OF_NO_INJURIES", by_gid(s, 401)["notes"])
        self.assertIn("INJURY_REPORT_NOT_REVIEWED_FOR_GAME", by_gid(s, 402)["reasons"])

    def test_questionable_injury_holds(self):
        self.fx.standard(skip=("operator_injuries",))
        self.fx.put("operator_injuries", injury_doc([{"cfbd_game_id": 401, "team_id": 11, "player_id": "p2",
                                                      "role": "OL", "status": "QUESTIONABLE"}]))
        g = by_gid(self.fx.slate(), 401)
        self.assertEqual((g["status"], g["reasons"]), ("HOLD", ["INJURY_PARTICIPATION_UNRESOLVED:p2"]))

    def test_weather_missing_or_mismatched_or_late(self):
        self.fx.standard(skip=("weather",))
        self.fx.wx(401, K1, report_kickoff="2026-11-28T17:00:00Z")
        self.fx.wx(402, K2, captured=T("2026-11-28T15:10:00Z"))
        s = self.fx.slate()
        self.assertIn("WEATHER_FORECAST_FOR_DIFFERENT_KICKOFF", by_gid(s, 401)["reasons"])
        self.assertIn("WEATHER_FORECAST_MISSING", by_gid(s, 402)["reasons"])

    def test_weather_report_tamper_refused(self):
        self.fx.standard()
        for p in self.fx.weather.glob("cfbd-2026-401_*.report.json"):
            rep = json.loads(p.read_bytes())
            rep["event_hour_forecast"]["wind_speed_10m"] = 1.0
            p.write_bytes(b(rep))
        self.assertIn("WEATHER_REPORT_DISAGREES_WITH_ORIGINAL", by_gid(self.fx.slate(), 401)["reasons"])

    def test_source_byte_tamper_refused(self):
        self.fx.standard()
        for p in self.fx.capture.glob("cfbd_advanced__*.bin"):
            p.write_bytes(b(advanced_doc()) + b" ")
        with self.assertRaisesRegex(store.CaptureRefused, "SOURCE_SHA_MISMATCH"):
            self.fx.slate()

    def test_duplicate_json_key_refused(self):
        with self.assertRaisesRegex(store.CaptureRefused, "DUPLICATE_JSON_KEY"):
            self.fx.put("cfbd_talent", None, raw=b'[{"year":2026,"year":2026}]')

    def test_early_season_requires_priors(self):
        fx = Fixture.__new__(Fixture)
        fx.root = Path(tempfile.mkdtemp())
        os.chmod(fx.root, 0o700)
        fx.capture, fx.weather, fx.ratings_dirs = fx.root / "c", fx.root / "w", []
        fx.weather.mkdir(mode=0o700)
        try:
            store.init_capture(fx.capture, season=SEASON, week=2)
            docs = games_doc()
            for g in docs:
                g["week"] = 2
            fx.put("cfbd_games", docs)
            for src, doc in (("cfbd_advanced", advanced_doc()), ("operator_qb", qb_doc()),
                             ("operator_injuries", injury_doc())):
                fx.put(src, doc)
            fx.sp()
            fx.wx(401, K1)
            g = by_gid(fx.slate(), 401)
            self.assertEqual(g["status"], "PASS")
            self.assertIn("PRESEASON_PRIOR_MISSING:TALENT", g["reasons"])
        finally:
            shutil.rmtree(fx.root, ignore_errors=True)

    def test_repo_path_refused(self):
        with self.assertRaisesRegex(store.CaptureRefused, "OUTSIDE_PUBLIC_REPO"):
            store.private_dir(Path(__file__).resolve().parent)


class CardTests(NetworkOff):
    def quotes(self, rows=STANDARD_QUOTES):
        return card_mod.load_operator_quotes(quotes_json(rows))

    def test_every_game_projected_or_pass_and_priced(self):
        c = self.fx.standard().card(quotes=self.quotes())
        fid, rid = baselines.FROZEN_RUNIT["model_id"], baselines.RATINGS_ONLY_SP["model_id"]
        self.assertEqual(c["counts"], {"READY": 2, "HOLD": 0, "PASS": 0})
        g = by_gid(c, 401)
        self.assertEqual({f["status"] for f in g["forecasts"].values()}, {"PROJECTED"})
        self.assertEqual(len(g["quotes"]), 3)
        for q in g["quotes"]:
            self.assertAlmostEqual(q["market_novig_a"] + q["market_novig_b"], 1.0, places=5)
            for mid in (fid, rid):
                m = q["models"][mid]
                self.assertAlmostEqual(m["ev_a"], m["p_model_a"] * card_mod.decimal_odds(q["price_a"]) - 1, places=5)
            self.assertEqual((q["state"], q["stake_u"], q["official_counted"], q["approved_stake_u"]),
                             ("PAPER", 0, 0, 0))
        g2 = by_gid(c, 402)
        self.assertEqual(g2["market_status"], "NO_QUOTE")
        self.assertEqual(g2["markets_without_prefreeze_quote"], ["ML", "SPREAD", "TOTAL"])
        self.assertEqual(g2["forecasts"][fid]["status"], "PROJECTED")
        self.assertFalse(c["predictive_validation"])
        self.assertIn(fid, c["models"])
        self.assertEqual(c["models"][fid]["module_sha256"], baselines.FROZEN_RUNIT["module_sha256"])

    def test_frozen_forecast_equals_untouched_model(self):
        self.fx.standard()
        slate = self.fx.slate()
        rec = by_gid(slate, 401)
        raw = runit.run_game(rec["_model"]["game_row"], rec["_model"]["ctx"])
        f = baselines.frozen_runit_forecast(rec["_model"]["game_row"], rec["_model"]["ctx"])
        self.assertAlmostEqual(f["margin_home"], raw["margin"], places=3)
        self.assertAlmostEqual(f["total"], raw["total"], places=3)
        self.assertTrue(any("Fake WR STAR_SKILL OUT" in n for n in f["model_notes"]))

    def test_hold_and_pass_games_have_reasons_both_models(self):
        rows = qb_doc()["rows"]
        rows[0]["starter_status"] = "UNKNOWN"
        self.fx.standard(skip=("operator_qb", "weather"))
        self.fx.put("operator_qb", qb_doc(rows))
        self.fx.wx(402, K2)
        c = self.fx.card(quotes=self.quotes())
        g = by_gid(c, 401)
        self.assertEqual(g["status"], "PASS")  # weather missing => PASS (plus QB hold reason)
        for f in g["forecasts"].values():
            self.assertEqual(f["status"], "PASS")
            self.assertTrue(f["pass_reasons"])
        for q in g["quotes"]:
            self.assertEqual({m["status"] for m in q["models"].values()}, {"PASS"})

    def test_quote_after_freeze_or_one_sided_or_bad(self):
        late = [{**STANDARD_QUOTES[0], "captured_utc": "2026-11-28T15:00:01Z"}]
        c = self.fx.standard().card(quotes=self.quotes(late))
        self.assertEqual(by_gid(c, 401)["market_status"], "NO_QUOTE")
        one = [{k: v for k, v in STANDARD_QUOTES[0].items() if k != "away_price"}]
        with self.assertRaisesRegex(card_mod.QuoteRefused, "NOT_TWO_SIDED"):
            self.quotes(one)
        with self.assertRaisesRegex(card_mod.QuoteRefused, "ML_QUOTE_HAS_LINE"):
            self.quotes([{**STANDARD_QUOTES[0], "line": -3}])
        with self.assertRaisesRegex(card_mod.QuoteRefused, "OUT_OF_SCOPE"):
            self.quotes([{**STANDARD_QUOTES[0], "market": "TEAM_TOTAL"}])
        with self.assertRaisesRegex(card_mod.QuoteRefused, "AMERICAN_PRICE"):
            self.quotes([{**STANDARD_QUOTES[0], "home_price": 50}])

    def test_latest_prefreeze_quote_per_book_market(self):
        rows = STANDARD_QUOTES + [{**STANDARD_QUOTES[1], "line": -7.5, "captured_utc": "2026-11-28T14:30:00Z"}]
        g = by_gid(self.fx.standard().card(quotes=self.quotes(rows)), 401)
        spread = [q for q in g["quotes"] if q["market"] == "SPREAD"]
        self.assertEqual([q["line"] for q in spread], [-7.5])

    def test_csv_quotes(self):
        csv_raw = (b"cfbd_game_id,book,market,line,home_price,away_price,over_price,under_price,captured_utc\n"
                   b"401,bookB,SPREAD,-6.5,-108,-112,,,2026-11-28T13:00:00Z\n")
        qs = card_mod.load_operator_quotes(csv_raw)
        self.assertEqual((qs[0]["line"], qs[0]["price_a"], qs[0]["price_b"]), (-6.5, -108, -112))

    def test_odds_api_archive_needs_exact_crosswalk(self):
        ev = [{"id": "oddsevent0001", "sport_key": "americanfootball_ncaaf", "home_team": "Alpha State Hawks",
               "away_team": "Beta Tech Owls", "commence_time": "2026-11-28T20:00:00Z",
               "bookmakers": [{"key": "draftkings", "markets": [
                   {"key": "h2h", "last_update": "2026-11-28T13:59:00Z", "outcomes": [
                       {"name": "Alpha State Hawks", "price": -240}, {"name": "Beta Tech Owls", "price": 200}]},
                   {"key": "spreads", "outcomes": [{"name": "Alpha State Hawks", "price": -110, "point": -6.5},
                                                   {"name": "Beta Tech Owls", "price": -110, "point": 6.5}]},
                   {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 54.5},
                                                  {"name": "Under", "price": -110, "point": 54.5}]}]}]}]
        raw = b(ev)
        summary = {"sport": "CFB", "original_raw_sha256": "sha256:" + sha256(raw).hexdigest(),
                   "captured_utc": "2026-11-28T14:00:00+00:00"}
        xw = {"schema": card_mod.CROSSWALK_SCHEMA, "rows": [
            {"odds_event_id": "oddsevent0001", "cfbd_game_id": 401, "home_team_odds_name": "Alpha State Hawks",
             "away_team_odds_name": "Beta Tech Owls"}]}
        qs = card_mod.load_odds_api_archive(raw, summary, xw)
        self.assertEqual(sorted(q["market"] for q in qs), ["ML", "SPREAD", "TOTAL"])
        xw["rows"][0]["home_team_odds_name"] = "Alpha State"
        with self.assertRaisesRegex(card_mod.QuoteRefused, "CROSSWALK_TEAM_NAME_MISMATCH"):
            card_mod.load_odds_api_archive(raw, summary, xw)
        with self.assertRaisesRegex(card_mod.QuoteRefused, "SCOPE_OR_SHA"):
            card_mod.load_odds_api_archive(raw, {**summary, "sport": "NFL"}, xw)


class LedgerGradingTests(NetworkOff):
    def frozen(self, quotes=STANDARD_QUOTES, frozen=FROZEN, now=None):
        c = self.fx.card(frozen=frozen, quotes=card_mod.load_operator_quotes(quotes_json(quotes)))
        return c, card_mod.freeze_card(c, self.fx.cards, self.fx.ledger,
                                       now=now or T(frozen) + timedelta(minutes=1))

    def finals(self, p401=(31, 24), p402=(34, 31), captured="2026-11-29T08:00:00Z", **over):
        docs = games_doc()
        for g, (h, a) in ((docs[0], p401), (docs[1], p402)):
            g.update(completed=True, homePoints=h, awayPoints=a)
        for gid, extra in over.items():
            next(g for g in docs if g["id"] == int(gid[1:])).update(extra)
        raw = b(docs)
        return raw, {"provider": "synthetic-final", "sha256": "sha256:" + sha256(raw).hexdigest(),
                     "captured_utc": captured}

    def test_freeze_registers_and_card_immutable(self):
        self.fx.standard()
        c, res = self.frozen()
        ents = ledger.verify(self.fx.ledger)
        self.assertEqual([e["type"] for e in ents], ["CARD_FROZEN"])
        self.assertEqual(ents[0]["card_sha256"], res["card_sha256"])
        with self.assertRaises(FileExistsError):
            card_mod.freeze_card(c, self.fx.cards, self.fx.ledger, now=T(FROZEN) + timedelta(minutes=2))
        p = Path(res["card_file"])
        doc = json.loads(p.read_bytes())
        doc["games"][0]["forecasts"] = {}
        p.write_bytes(b(doc))
        raw, rec = self.finals()
        with self.assertRaisesRegex(grading.GradeRefused, "FROZEN_CARD_MODIFIED"):
            grading.grade(self.fx.ledger, self.fx.cards, raw, rec)

    def test_late_card_write_refused(self):
        self.fx.standard()
        c = self.fx.card()
        with self.assertRaisesRegex(store.CaptureRefused, "TOO_LONG_AFTER_FREEZE"):
            card_mod.freeze_card(c, self.fx.cards, self.fx.ledger, now=T(FROZEN) + timedelta(hours=2))

    def test_ledger_rewrite_detected(self):
        self.fx.standard()
        self.frozen()
        raw, rec = self.finals()
        grading.grade(self.fx.ledger, self.fx.cards, raw, rec, now=T("2026-11-29T09:00:00Z"))
        lines = self.fx.ledger.read_bytes().splitlines()
        e = json.loads(lines[1])
        e["home_points"] = 99
        lines[1] = json.dumps(e, sort_keys=True, separators=(",", ":")).encode()
        self.fx.ledger.write_bytes(b"\n".join(lines) + b"\n")
        with self.assertRaisesRegex(ledger.LedgerRefused, "REWRITTEN"):
            ledger.verify(self.fx.ledger)
        self.fx.ledger.write_bytes(b"\n".join(lines[:1] + lines[2:]) + b"\n")
        with self.assertRaises(ledger.LedgerRefused):
            ledger.verify(self.fx.ledger)

    def test_grading_results_ot_push_and_retained_rows(self):
        self.fx.standard()
        q = STANDARD_QUOTES + [{"cfbd_game_id": 402, "book": "bookA", "market": "SPREAD", "line": -3.0,
                                "home_price": -110, "away_price": -110, "captured_utc": "2026-11-28T14:00:00Z"}]
        self.frozen(quotes=q)
        raw, rec = self.finals(p401=(31, 24), p402=(34, 31))  # 402 decided in OT: 34-31
        out = grading.grade(self.fx.ledger, self.fx.cards, raw, rec, now=T("2026-11-29T09:00:00Z"))
        self.assertEqual(out["graded"], 2)
        ents = [e for e in ledger.verify(self.fx.ledger) if e["type"] == "GAME_GRADED"]
        g1 = next(e for e in ents if e["cfbd_game_id"] == 401)
        res = {x["market"]: (x["result_a"], x["result_b"]) for x in g1["quotes"]}
        self.assertEqual(res["ML"], ("WIN", "LOSS"))
        self.assertEqual(res["SPREAD"], ("PUSH", "PUSH"))   # 31-24 = 7 vs -7
        self.assertEqual(res["TOTAL"], ("PUSH", "PUSH"))     # 31+24 = 55 vs 55
        g2 = next(e for e in ents if e["cfbd_game_id"] == 402)
        self.assertEqual(g2["quotes"][0]["result_a"], "PUSH")  # OT final 34-31 vs -3
        self.assertTrue(g2["final_includes_overtime"])
        # Re-grading the same finals is idempotent; nothing is rewritten.
        before = self.fx.ledger.read_bytes()
        self.assertEqual(grading.grade(self.fx.ledger, self.fx.cards, raw, rec,
                                       now=T("2026-11-29T10:00:00Z"))["graded"], 0)
        self.assertEqual(self.fx.ledger.read_bytes(), before)
        raw2, rec2 = self.finals(p401=(31, 21))
        with self.assertRaisesRegex(grading.GradeRefused, "FINAL_CONFLICT"):
            grading.grade(self.fx.ledger, self.fx.cards, raw2, rec2, now=T("2026-11-29T11:00:00Z"))
        self.assertEqual(self.fx.ledger.read_bytes(), before)

    def test_pass_and_no_quote_rows_are_graded_and_kept(self):
        rows = qb_doc()["rows"]
        rows[0]["starter_status"] = "OUT"
        self.fx.standard(skip=("operator_qb",))
        self.fx.put("operator_qb", qb_doc(rows))
        self.frozen(quotes=[])
        raw, rec = self.finals()
        grading.grade(self.fx.ledger, self.fx.cards, raw, rec, now=T("2026-11-29T09:00:00Z"))
        ents = {e["cfbd_game_id"]: e for e in ledger.verify(self.fx.ledger) if e["type"] == "GAME_GRADED"}
        self.assertEqual(ents[401]["card_status"], "HOLD")
        self.assertEqual(ents[402]["market_status"], "NO_QUOTE")

    def test_final_identity_and_timing(self):
        self.fx.standard()
        self.frozen()
        raw, rec = self.finals(g401={"homeId": 99})
        with self.assertRaisesRegex(grading.GradeRefused, "FINAL_TEAM_ID_MISMATCH"):
            grading.grade(self.fx.ledger, self.fx.cards, raw, rec)
        raw, rec = self.finals(captured="2026-11-28T19:00:00Z")
        with self.assertRaisesRegex(grading.GradeRefused, "BEFORE_KICKOFF"):
            grading.grade(self.fx.ledger, self.fx.cards, raw, rec)
        raw, rec = self.finals()
        with self.assertRaisesRegex(grading.GradeRefused, "SHA_MISMATCH"):
            grading.grade(self.fx.ledger, self.fx.cards, raw + b" ", rec)

    def test_evaluation_separates_accuracy_and_returns(self):
        self.fx.standard()
        self.frozen()
        closing = card_mod.load_operator_quotes(quotes_json([
            {**STANDARD_QUOTES[0], "home_price": -300, "away_price": 240, "captured_utc": "2026-11-28T19:55:00Z"},
            {**STANDARD_QUOTES[1], "captured_utc": "2026-11-28T19:55:00Z"},
            {**STANDARD_QUOTES[2], "captured_utc": "2026-11-28T20:05:00Z"},  # after kickoff: ignored
        ]))
        raw, rec = self.finals()
        grading.grade(self.fx.ledger, self.fx.cards, raw, rec, closing_quotes=closing,
                      now=T("2026-11-29T09:00:00Z"))
        ent = next(e for e in ledger.verify(self.fx.ledger) if e["type"] == "GAME_GRADED" and e["cfbd_game_id"] == 401)
        closing_by = {x["market"]: x["closing"] for x in ent["quotes"]}
        self.assertIsNotNone(closing_by["ML"])
        self.assertIsNone(closing_by["TOTAL"])
        rep = grading.evaluate(self.fx.ledger, self.fx.cards)
        fid, rid = baselines.FROZEN_RUNIT["model_id"], baselines.RATINGS_ONLY_SP["model_id"]
        self.assertEqual(rep["games_evaluated"], 2)
        acc = rep["accuracy"]
        self.assertEqual(acc["common_set"]["margin_mae"]["market"]["n"], 1)  # only 401 quoted
        self.assertEqual(acc["own_coverage"]["margin_mae"][fid]["n"], 2)
        for k in (fid, rid, "market"):
            self.assertIn(k, acc["common_set"]["ml_brier"])
        self.assertIn("returns_separate_from_accuracy", rep)
        self.assertEqual(rep["returns_separate_from_accuracy"][fid]["label"],
                         "HYPOTHETICAL_1U_FLAT_PAPER_NOT_COUNTED")
        self.assertTrue(rep["sample_warning"])
        self.assertFalse(rep["validation_certified"])
        self.assertEqual((rep["official_counted"], rep["approved_stake_u"]), (0, 0))
        late = grading.evaluate(self.fx.ledger, self.fx.cards, holdout_start_utc="2026-12-01T00:00:00Z")
        self.assertEqual(late["games_evaluated"], 0)
        self.assertEqual(late["excluded"], {"PRE_REGISTRATION_NOT_UNTOUCHED_HOLDOUT": 2})

    def test_pre_registration_games_never_holdout(self):
        self.assertGreaterEqual(baselines.FROZEN_RUNIT["registered_utc"], "2026-11-15")
        self.fx.standard()
        self.frozen()
        raw, rec = self.finals()
        grading.grade(self.fx.ledger, self.fx.cards, raw, rec, now=T("2026-11-29T09:00:00Z"))
        with mock.patch.dict(baselines.FROZEN_RUNIT, {"registered_utc": "2026-11-29T00:00:00Z"}):
            rep = grading.evaluate(self.fx.ledger, self.fx.cards)
        self.assertEqual(rep["excluded"], {"PRE_REGISTRATION_NOT_UNTOUCHED_HOLDOUT": 2})

    def test_card_registered_after_kickoff_excluded(self):
        self.fx.standard()
        # Freeze declared pregame, but ledger registration happens after the first kickoff.
        frozen = "2026-11-28T19:55:00Z"
        self.frozen(frozen=frozen, now=T("2026-11-28T20:01:00Z"))
        raw, rec = self.finals()
        grading.grade(self.fx.ledger, self.fx.cards, raw, rec, now=T("2026-11-29T09:00:00Z"))
        rep = grading.evaluate(self.fx.ledger, self.fx.cards)
        self.assertEqual(rep["excluded"].get("CARD_NOT_FROZEN_AND_REGISTERED_BEFORE_KICKOFF"), 1)
        self.assertEqual(rep["games_evaluated"], 1)


class CaptureToolTests(NetworkOff):
    def test_missing_key_fails_closed_without_request(self):
        calls = []
        with mock.patch.dict(os.environ, {}, clear=True):
            out = cfbd_capture.capture(self.fx.root / "x", season=SEASON, week=WEEK,
                                       fetch=lambda u, k: calls.append(u))
        self.assertEqual(out["state"], "BLOCKED_KEY_ABSENT")
        self.assertEqual(calls, [])

    def test_capture_stores_four_sources_and_never_key(self):
        bodies = {"cfbd_games": games_doc(), "cfbd_advanced": advanced_doc(), "cfbd_talent": talent_doc(),
                  "cfbd_returning": returning_doc()}
        urls = cfbd_capture.endpoints(SEASON, WEEK)
        rev = {u: s for s, u in urls.items()}
        d = self.fx.root / "live"
        out = cfbd_capture.capture(d, season=SEASON, week=WEEK, key="synthetic-key-123",
                                   fetch=lambda u, k: (200, b(bodies[rev[u]])), clock=lambda: CAPTURED)
        self.assertEqual(out["state"], "CAPTURED")
        for p in d.iterdir():
            self.assertNotIn(b"synthetic-key-123", p.read_bytes())
        self.assertTrue(urls["cfbd_games"].startswith("https://api.collegefootballdata.com/games?"))


if __name__ == "__main__":
    unittest.main()
