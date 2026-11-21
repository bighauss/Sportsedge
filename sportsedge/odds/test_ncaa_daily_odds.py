"""Offline synthetic regressions for the NCAA (CBB/CFB) odds snapshot intake.

Network is patched off: every HTTP call goes to an in-memory fake provider.
No real API key, no live provider, no paid credit.
"""
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib
import io
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from sportsedge.odds import daily_pilot_artifact_gate as gate
from sportsedge.odds import ncaa_daily_odds as ncaa

KEY = "synthetic-key-NOT-REAL-0001"
BACKUP = "synthetic-backup-NOT-REAL-02"


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeResponse:
    def __init__(self, url, body, headers, status=200, final_url=None):
        self.url, self.body, self.headers, self.status = url, body, headers, status
        self.final = final_url or url

    def geturl(self):
        return self.final

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeProvider:
    def __init__(self, sport_key, now):
        self.sport_key, self.now = sport_key, now
        self.calls = []
        self.remaining = "480"
        self.odds_last = "3"
        self.active = True
        self.window_events = True
        self.odds_error = None
        self.redirect_preflight = False

    def events(self):
        soon = self.now + timedelta(minutes=45)
        later = self.now + timedelta(hours=8)
        return [
            {"id": "evt_soon_00001", "sport_key": self.sport_key, "commence_time": _iso(soon),
             "home_team": "Home U", "away_team": "Away St"},
            {"id": "evt_later_0002", "sport_key": self.sport_key, "commence_time": _iso(later),
             "home_team": "North Tech", "away_team": "South A&M"},
        ]

    def odds(self):
        upd = _iso(self.now - timedelta(minutes=1))
        ev1, ev2 = self.events()

        def mk(key, outcomes):
            return {"key": key, "last_update": upd, "outcomes": outcomes}

        ev1 = {**ev1, "bookmakers": [
            {"key": "draftkings", "last_update": upd, "markets": [
                mk("h2h", [{"name": "Home U", "price": -150}, {"name": "Away St", "price": 130}]),
                mk("spreads", [{"name": "Home U", "price": -110, "point": -3.5},
                               {"name": "Away St", "price": -110, "point": 3.5}]),
                mk("totals", [{"name": "Over", "price": -105, "point": 141.5},
                              {"name": "Under", "price": -115, "point": 141.5}]),
            ]},
            {"key": "fanduel", "last_update": upd, "markets": [
                # one-sided h2h and mismatched spread: both must be excluded
                mk("h2h", [{"name": "Home U", "price": -155}]),
                mk("spreads", [{"name": "Home U", "price": -110, "point": -3.5},
                               {"name": "Away St", "price": -110, "point": 4.5}]),
            ]},
        ]}
        ev2 = {**ev2, "bookmakers": [
            {"key": "pinnacle", "last_update": upd, "markets": [
                mk("totals", [{"name": "Over", "price": -102, "point": 55.5},
                              {"name": "Under", "price": -108, "point": 55.5}]),
            ]},
        ]}
        return [ev1, ev2]

    def __call__(self, req, timeout=None):
        url = req.full_url
        parts = urlsplit(url)
        q = parse_qs(parts.query)
        self.calls.append((parts.path, q))
        if parts.path == "/v4/sports":
            body = [{"key": self.sport_key, "active": self.active, "group": "x", "title": "x"}]
            hdr = {"x-requests-last": "0"}
            if self.remaining is not None:
                hdr["x-requests-remaining"] = self.remaining
            final = url + "&r=1" if self.redirect_preflight else url
            return FakeResponse(url, json.dumps(body).encode(), hdr, final_url=final)
        if parts.path == f"/v4/sports/{self.sport_key}/events":
            body = self.events() if self.window_events else []
            return FakeResponse(url, json.dumps(body).encode(), {"x-requests-last": "0"})
        if parts.path == f"/v4/sports/{self.sport_key}/odds":
            if self.odds_error:
                raise HTTPError(url, self.odds_error, "error " + url, {}, None)
            hdr = {"x-requests-last": self.odds_last, "x-requests-remaining": "477",
                   "Date": "Sat, 21 Nov 2026 15:00:00 GMT"}
            return FakeResponse(url, json.dumps(self.odds()).encode(), hdr)
        raise AssertionError("unexpected provider path " + parts.path)

    def paths(self):
        return [p for p, _ in self.calls]


def _no_network(*a, **k):
    raise AssertionError("NETWORK_DISABLED_IN_TESTS")


class NcaaDailyOddsTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "urllib.request.urlopen",
                       "sportsedge.odds.free_odds_aggregator_intake._secure_open",
                       "sportsedge.odds.ncaa_daily_odds._secure_open"):
            p = patch(target, _no_network)
            p.start()
            self.addCleanup(p.stop)
        d = TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "private"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.env = {"ODDS_API_KEY": KEY}

    def run_snap(self, sport="ncaab", snapshot="pregame", provider=None, env=None, now=None):
        provider = provider or FakeProvider(ncaa.SPORTS[ncaa.SPORT_CODES[sport]], self.now)
        out = ncaa.run_snapshot(sport, snapshot, self.root, execute=True, now=now or self.now,
                                opener=provider, env=self.env if env is None else env)
        return out, provider

    def test_budget_is_markets_times_regions_and_fixed(self):
        self.assertEqual(ncaa.MAX_CREDITS, 3)
        self.assertEqual(ncaa.credit_budget(("h2h",), tuple("abcdefghijk")), 2)
        self.assertEqual(ncaa.SPORTS["CBB"], "basketball_ncaab")
        self.assertEqual(ncaa.SPORTS["CFB"], "americanfootball_ncaaf")

    def test_dry_run_makes_no_request_and_no_disk(self):
        p = FakeProvider("basketball_ncaab", self.now)
        out = ncaa.run_snapshot("ncaab", "pregame", self.root, now=self.now, opener=p, env=self.env)
        self.assertEqual(out["state"], "DRY_RUN")
        self.assertEqual(p.calls, [])
        self.assertFalse(self.root.exists())

    def test_cbb_pregame_archives_exact_bytes_manifest_and_full_pairs_only(self):
        out, p = self.run_snap()
        self.assertEqual(out["state"], "ARCHIVED_PROVIDER_RESPONSE")
        self.assertEqual(p.paths(), ["/v4/sports", "/v4/sports/basketball_ncaab/events",
                                     "/v4/sports/basketball_ncaab/odds"])
        q = p.calls[2][1]
        self.assertEqual(q["markets"], ["h2h,spreads,totals"])
        self.assertEqual(q["bookmakers"], [",".join(ncaa.BOOKS)])
        self.assertEqual(out["credits_used"], 3)
        raw = (self.root / out["archive"]["raw_filename"]).read_bytes()
        self.assertEqual(raw, json.dumps(p.odds()).encode())
        manifest = json.loads((self.root / out["manifest_filename"]).read_text())
        self.assertEqual(manifest["original_raw_sha256"], "sha256:" + sha256(raw).hexdigest())
        self.assertEqual(manifest["schema"], "sportsedge-oddsapi-aggregator-raw-v1")
        self.assertEqual(manifest["sport"], "CBB")
        pairs = json.loads((self.root / out["pairs_filename"]).read_text())
        got = sorted((r["odds_event_id"], r["book"], r["market"]) for r in pairs["rows"])
        self.assertEqual(got, [("evt_later_0002", "pinnacle", "totals"),
                               ("evt_soon_00001", "draftkings", "h2h"),
                               ("evt_soon_00001", "draftkings", "spreads"),
                               ("evt_soon_00001", "draftkings", "totals")])
        self.assertEqual(pairs["census"]["partial_or_inconsistent_pairs"], 2)
        spread = [r for r in pairs["rows"] if r["market"] == "spreads"][0]
        self.assertEqual((spread["line"], spread["side_a"], spread["price_a"]), (-3.5, "Home U", -110))
        for path in self.root.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(KEY.encode(), path.read_bytes())

    def test_cfb_close_flags_only_window_rows_as_closing(self):
        out, p = self.run_snap("ncaaf", "close")
        self.assertEqual(out["state"], "ARCHIVED_PROVIDER_RESPONSE")
        self.assertIn("/v4/sports/americanfootball_ncaaf/odds", p.paths())
        ev_q = p.calls[1][1]
        self.assertEqual(ev_q["commenceTimeTo"], [_iso(self.now + timedelta(minutes=90))])
        pairs = json.loads((self.root / out["pairs_filename"]).read_text())
        self.assertEqual(pairs["sport"], "CFB")
        flags = {r["odds_event_id"]: r["in_snapshot_window"] for r in pairs["rows"]}
        self.assertEqual(flags, {"evt_soon_00001": True, "evt_later_0002": False})
        self.assertEqual(out["two_sided_pairs_in_window"], 3)

    def test_low_or_unverified_remaining_blocks_before_paid_call(self):
        for i, (remaining, state) in enumerate((("52", "BLOCKED_REMAINING_CREDITS_TOO_LOW"),
                                 (None, "BLOCKED_PREFLIGHT_QUOTA_UNVERIFIED"),
                                 ("lots", "BLOCKED_PREFLIGHT_QUOTA_UNVERIFIED"))):
            with self.subTest(remaining=remaining):
                p = FakeProvider("basketball_ncaab", self.now)
                p.remaining = remaining
                out, _ = self.run_snap(provider=p, now=self.now + timedelta(days=i))
                self.assertEqual(out["state"], state)
                self.assertEqual(p.paths(), ["/v4/sports"])
                self.assertEqual(out["credits_used"], 0)

    def test_out_of_season_or_empty_window_spends_nothing(self):
        p = FakeProvider("americanfootball_ncaaf", self.now)
        p.active = False
        out, _ = self.run_snap("ncaaf", "pregame", provider=p)
        self.assertEqual(out["state"], "SKIPPED_SPORT_NOT_IN_SEASON")
        self.assertEqual(p.paths(), ["/v4/sports"])
        p = FakeProvider("americanfootball_ncaaf", self.now)
        p.window_events = False
        out, _ = self.run_snap("ncaaf", "close", provider=p)
        self.assertEqual(out["state"], "SKIPPED_NO_EVENTS_IN_WINDOW")
        self.assertNotIn("/v4/sports/americanfootball_ncaaf/odds", p.paths())

    def test_one_attempt_per_sport_snapshot_central_date(self):
        first, p = self.run_snap()
        again, p2 = self.run_snap()
        self.assertEqual(again["state"], "SKIPPED_ALREADY_ATTEMPTED")
        self.assertEqual(p2.calls, [])
        other, _ = self.run_snap(snapshot="close")
        self.assertNotEqual(other["state"], "SKIPPED_ALREADY_ATTEMPTED")
        football, _ = self.run_snap(sport="ncaaf")
        self.assertNotEqual(football["state"], "SKIPPED_ALREADY_ATTEMPTED")

    def test_overcharge_writes_hold_and_blocks_later_runs(self):
        p = FakeProvider("basketball_ncaab", self.now)
        p.odds_last = "4"
        out, _ = self.run_snap(provider=p)
        self.assertEqual(out["state"], "ARCHIVED_UNEXPECTED_QUOTA_COST_PAUSE")
        self.assertTrue((self.root / ncaa.HOLD_FILENAME).exists())
        nxt, p2 = self.run_snap(sport="ncaaf", snapshot="close")
        self.assertEqual(nxt["state"], "BLOCKED_PRIOR_QUOTA_REVIEW")
        self.assertEqual(p2.calls, [])

    def test_http_error_is_not_retried_and_never_echoes_key(self):
        p = FakeProvider("basketball_ncaab", self.now)
        p.odds_error = 500
        buf = io.StringIO()
        with redirect_stdout(buf):
            out, _ = self.run_snap(provider=p)
        self.assertEqual(out["state"], "CAPTURE_FAILED_REVIEW_PRIVATELY")
        self.assertEqual(p.paths().count("/v4/sports/basketball_ncaab/odds"), 1)
        self.assertNotIn(KEY, json.dumps(out) + buf.getvalue())
        self.assertTrue((self.root / ncaa.HOLD_FILENAME).exists())

    def test_preflight_redirect_refused_before_paid_call(self):
        p = FakeProvider("basketball_ncaab", self.now)
        p.redirect_preflight = True
        out, _ = self.run_snap(provider=p)
        self.assertEqual(out["state"], "BLOCKED_PREFLIGHT_FAILED")
        self.assertEqual(p.paths(), ["/v4/sports"])

    def test_backup_key_only_when_primary_absent(self):
        self.assertEqual(ncaa.resolve_key({"ODDS_API_KEY": KEY, "ODDS_API_KEY_BACKUP": BACKUP}),
                         (KEY, "primary"))
        self.assertEqual(ncaa.resolve_key({"ODDS_API_KEY": "", "ODDS_API_KEY_BACKUP": BACKUP}),
                         (BACKUP, "backup"))
        out, p = self.run_snap(env={"ODDS_API_KEY_BACKUP": BACKUP})
        self.assertEqual(out["api_key_slot"], "backup")
        self.assertTrue(all(q["apiKey"] == [BACKUP] for _, q in p.calls))
        out, p = self.run_snap(snapshot="close", env={})
        self.assertEqual(out["state"], "BLOCKED_SOURCE_AUTH")
        self.assertEqual(p.calls, [])

    def test_claim_date_change_refused(self):
        with self.assertRaisesRegex(ValueError, "DATE_CHANGED"):
            self.run_snap(env={**self.env, "SPORTSEDGE_DAILY_CLAIM_DATE_CT": "1999-01-01"})

    def test_cli_log_shows_only_states_counts_credits(self):
        p = FakeProvider("basketball_ncaab", self.now)
        buf = io.StringIO()
        with patch.dict("os.environ", {"ODDS_API_KEY": KEY}, clear=False), \
                patch("sportsedge.odds.free_odds_aggregator_intake._secure_open", p), \
                patch("sportsedge.odds.ncaa_daily_odds._secure_open", p), redirect_stdout(buf):
            code = ncaa.main([str(self.root), "--sport", "ncaab", "--snapshot", "pregame", "--execute"])
        self.assertEqual(code, 0)
        log = json.loads(buf.getvalue())
        self.assertEqual(set(log), set(ncaa.LOG_FIELDS))
        self.assertEqual(log["credits_used"], 3)
        self.assertNotIn(KEY, buf.getvalue())
        self.assertNotIn("Home U", buf.getvalue())

    def test_manifest_matches_paper_card_odds_api_loader_contract(self):
        """Fields read by cbbd_paper_card.odds_api_quotes / cfb_paper_card.load_odds_api_archive."""
        for sport, code in (("ncaab", "CBB"), ("ncaaf", "CFB")):
            with self.subTest(sport=sport):
                out, _ = self.run_snap(sport=sport)
                raw = (self.root / out["archive"]["raw_filename"]).read_bytes()
                man = json.loads((self.root / out["manifest_filename"]).read_text())
                self.assertEqual(man["schema"], "sportsedge-oddsapi-aggregator-raw-v1")
                self.assertEqual(man["sport"], code)
                self.assertEqual(man["original_raw_sha256"], "sha256:" + sha256(raw).hexdigest())
                cap = datetime.fromisoformat(man["captured_utc"])
                self.assertEqual(cap.utcoffset(), timedelta(0))
                z = man["captured_utc"].replace("+00:00", "Z")
                self.assertTrue(z.endswith("Z"))
                datetime.fromisoformat(z[:-1] + "+00:00")
                events = json.loads(raw)
                self.assertIsInstance(events, list)
                self.assertTrue(all(e["sport_key"] == ncaa.SPORTS[code] for e in events))

    def test_real_cbb_paper_card_loader_accepts_archive(self):
        """End-to-end with the merged models/cbb/cbbd_paper_card.odds_api_quotes."""
        cbb_dir = str(Path(__file__).resolve().parents[2] / "models" / "cbb")
        if cbb_dir not in sys.path:
            sys.path.insert(0, cbb_dir)
        try:
            card = importlib.import_module("cbbd_paper_card")
        except ImportError as exc:  # card not present on this base
            self.skipTest("CBB paper card unavailable: " + type(exc).__name__)
        out, _ = self.run_snap()
        raw = (self.root / out["archive"]["raw_filename"]).read_bytes()
        man = json.loads((self.root / out["manifest_filename"]).read_text())
        xw = b"odds_event_id,game_id,odds_home_team,odds_away_team\nevt_soon_00001,123456,Home U,Away St\n"
        rows, census = card.odds_api_quotes(raw, man, xw)
        self.assertEqual(sorted(r["market"] for r in rows), ["moneyline", "spread", "total"])
        self.assertEqual(census, {"NOT_TWO_SIDED_OR_LINES_DISAGREE": 2, "UNMAPPED_PROVIDER_EVENT": 1})
        spread = [r for r in rows if r["market"] == "spread"][0]
        self.assertEqual((spread["line"], spread["price_a"], spread["price_b"]), (-3.5, -110, -110))


class GateProfileTests(unittest.TestCase):
    def test_existing_profiles_unchanged(self):
        self.assertEqual(gate._profile("nfl"), ("nfl-daily-odds-attempt-", "nfl-daily-claim.json",
                                                "nfl-daily-odds-quota-hold"))
        self.assertEqual(gate._profile("ratings"), ("daily-ratings-attempt-",
                                                    "daily-ratings-claim.json", None))
        with self.assertRaises(gate.Blocked):
            gate._profile("ncaa")

    def test_ncaa_claims_are_per_sport_snapshot_and_share_hold(self):
        names = {gate._profile(p)[0] for p in gate.NCAA_PILOTS}
        self.assertEqual(len(names), 4)
        self.assertEqual({gate._profile(p)[2] for p in gate.NCAA_PILOTS},
                         {"ncaa-daily-odds-quota-hold"})
        with TemporaryDirectory() as d:
            seen = []

            def lookup(repo, token, name):
                seen.append(name)
                return {"total_count": 0, "artifacts": []}
            at = datetime.fromisoformat("2026-11-21T16:00:00+00:00")
            r = gate.reserve(d, repository="bighauss/Sportsedge", run_id="7", token="t",
                             now=at, lookup=lookup, pilot="ncaaf-close")
            self.assertEqual(r["name"], "ncaaf-close-daily-odds-attempt-2026-11-21")
            self.assertTrue((Path(d) / "ncaaf-close-daily-claim.json").exists())
            self.assertEqual(seen, ["ncaa-daily-odds-quota-hold",
                                    "ncaaf-close-daily-odds-attempt-2026-11-21"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
