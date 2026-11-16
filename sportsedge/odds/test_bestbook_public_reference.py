"""Synthetic-only bestbook public-page evidence tests. NO live website calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.odds.bestbook_public_reference import (
    HOME, ROBOTS, PublicReferenceError, _private, _public_get, analyze,
    fetch_once, save_report, _read_source, MAX_HTML,
)

NOW = datetime(2026, 11, 15, 20, tzinfo=timezone.utc)
PUBLIC_FIXTURE = """Best NFL odds this week
New England Patriots at Detroit Lions odds
Sun, Nov 15, 9:33 AM ET
Spread: DET −2.5 −111 at Novig; NE +2.5 +110 at DraftKings
Total: over 50.5 +102 at FanDuel; under 50.5 −104 at Novig
Moneyline: NE +133 at Novig; DET −135 at DraftKings
Buffalo Bills at New York Jets odds
Sun, Nov 15, 1:00 PM ET
Spread: BUF −8 +100 at theScore; NYJ +8 −109 at Bet105
Total: over 51 −103 at parx; under 51 −105 at Hard Rock
Moneyline: BUF −370 at Rebet; NYJ +365 at Novig
""".encode()


class FixtureResponse:
    def __init__(self, url, payload, content_type="text/html", status=200):
        self.url, self.payload, self.status = url, payload, status
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, limit):
        return self.payload[:limit]


class TestOpener:
    def __init__(self, robots, page, *, redirect=False):
        self.raw = [robots, page]
        self.calls = []
        self.redirect = redirect

    def open(self, req, timeout=None):
        self.calls.append((req.full_url, dict(req.header_items()), timeout))
        i = len(self.calls) - 1
        return FixtureResponse(
            "https://other.example/" if self.redirect else req.full_url,
            self.raw[i],
            "text/plain" if i == 0 else "text/html")


class BestBookPublicResearch(unittest.TestCase):
    def test_plain_text_two_games_twelve_reference_outcomes(self):
        result = analyze(PUBLIC_FIXTURE, read_at_utc=NOW)
        self.assertEqual(result["event_count"], 2)
        self.assertEqual(result["displayed_reference_quote_count"], 12)
        self.assertEqual(result["status"], "PAPER_0U_PUBLIC_PAGE_RESEARCH_ONLY")
        self.assertFalse(result["gate_a_closed"])
        self.assertFalse(result["gate_d_clv_closed"])
        self.assertEqual(result["approved_stake_u"], 0)
        self.assertEqual(result["official_counted"], 0)
        self.assertEqual(result["not_observed_sports"],
                         ["CFB", "CBB", "NBA", "MLB", "NHL", "PGA"])
        self.assertIn("PLAYER_PROP", result["not_observed_market_families"])

    def test_named_book_is_public_label_not_verified_original(self):
        result = analyze(PUBLIC_FIXTURE, read_at_utc=NOW)
        dk = [x for x in result["rows"] if x["displayed_book_label"] == "DraftKings"]
        self.assertEqual(len(dk), 2)
        for row in dk:
            self.assertIsNone(row["provider_quote_id"])
            self.assertIsNone(row["provider_original_quote_utc"])
            self.assertIsNone(row["book_direct_response_sha256"])
            self.assertEqual(row["quote_status"], "PUBLIC_PAGE_REFERENCE_UNVERIFIED")
            self.assertEqual(row["approved_stake_u"], 0)

    def test_lines_and_prices_keep_original_selections(self):
        report = analyze(PUBLIC_FIXTURE, read_at_utc=NOW)
        first = report["rows"][0]
        self.assertEqual(first["selection_label"], "DET")
        self.assertEqual(first["line"], "-2.5")
        self.assertEqual(first["price_american"], -111)
        totals = [x for x in report["rows"] if x["market_family"] == "TOTAL"]
        self.assertEqual({x["selection_label"] for x in totals}, {"OVER", "UNDER"})
        self.assertEqual({x["line"] for x in totals}, {"50.5", "51"})

    def test_html_visible_text_not_script_data(self):
        html = ("""<html><head><title>source</title></head><body>
        <script>Best NFL odds this week
        Fake Raiders at Fake Cowboys odds
        Moneyline: LV +200 at Fake; DAL -220 at Fake</script>
        <h2>Best NFL odds this week</h2>
        <article><h3>New England Patriots at Detroit Lions odds</h3>
        <p>Spread: DET −2.5 −111 at Novig; NE +2.5 +110 at DraftKings</p>
        <p>Total: over 50.5 +102 at FanDuel; under 50.5 −104 at Novig</p>
        <p>Moneyline: NE +133 at Novig; DET −135 at DraftKings</p>
        </article></body></html>""").encode()
        report = analyze(html, read_at_utc=NOW)
        self.assertEqual(report["event_count"], 1)
        self.assertEqual(report["displayed_reference_quote_count"], 6)
        self.assertNotIn("Fake", json.dumps(report))

    def test_missing_total_is_visible_gap(self):
        raw = PUBLIC_FIXTURE.replace(
            b"Total: over 51 \xe2\x88\x92103 at parx; under 51 \xe2\x88\x92105 at Hard Rock\n", b"")
        report = analyze(raw, read_at_utc=NOW)
        self.assertIn(("TOTAL", "NOT_CAPTURED_IN_PUBLIC_HOMEPAGE"),
                      {(x.get("market_family"), x["reason"])
                       for x in report["missing_or_blocked_public_rows"]})

    def test_wrong_total_line_is_blocked_not_fixed(self):
        raw = PUBLIC_FIXTURE.replace(
            b"Total: over 50.5 +102 at FanDuel; under 50.5",
            b"Total: over 50.5 +102 at FanDuel; under 51.5")
        report = analyze(raw, read_at_utc=NOW)
        self.assertIn("TOTAL_SIDES_OR_LINES_MISMATCH",
                      [x["reason"] for x in report["missing_or_blocked_public_rows"]])
        self.assertEqual(report["displayed_reference_quote_count"], 10)

    def test_invalid_odds_cannot_be_used(self):
        raw = PUBLIC_FIXTURE.replace(b"DET \xe2\x88\x92135", b"DET +99")
        report = analyze(raw, read_at_utc=NOW)
        # A two-digit +99 fails the exact ML-pair grammar before price parsing.
        self.assertIn("INVALID_DISPLAYED_ML_PAIR",
                      [x["reason"] for x in report["missing_or_blocked_public_rows"]])
        self.assertEqual(report["approved_stake_u"], 0)

    def test_duplicate_family_blocked(self):
        body = PUBLIC_FIXTURE.replace(
            b"Total: over 50.5",
            b"Spread: DET -2.5 -111 at Novig; NE +2.5 +110 at DraftKings\n"
            b"Total: over 50.5", 1)
        result = analyze(body, read_at_utc=NOW)
        self.assertIn("REPEATED_PUBLIC_FAMILY_BLOCK",
                      [x["reason"] for x in result["missing_or_blocked_public_rows"]])

    def test_missing_section_fails_closed(self):
        with self.assertRaisesRegex(PublicReferenceError, "SECTION_NOT_FOUND"):
            analyze(b"other site words", read_at_utc=NOW)

    def test_non_utc_timestamp_and_unlimited_payload_refused(self):
        with self.assertRaisesRegex(PublicReferenceError, "NON_UTC_CAPTURE_CLOCK"):
            analyze(PUBLIC_FIXTURE, read_at_utc=NOW.astimezone(
                timezone(timedelta(hours=-6))))
        with self.assertRaisesRegex(PublicReferenceError, "OVERSIZED"):
            analyze(b"x" * (MAX_HTML + 1), read_at_utc=NOW)

    def test_public_robots_denial_halts_page_request(self):
        opener = TestOpener(b"User-agent: *\nDisallow: /\n", PUBLIC_FIXTURE)
        with self.assertRaisesRegex(PublicReferenceError, "ROBOTS_POLICY_DENIES"):
            fetch_once(source_policy_reviewed=True, opener=opener)
        self.assertEqual(len(opener.calls), 1)

    def test_no_site_review_no_requests(self):
        opener = TestOpener(b"User-agent: *\nAllow: /\n", PUBLIC_FIXTURE)
        with self.assertRaisesRegex(PublicReferenceError, "SOURCE_TERMS_REVIEW_REQUIRED"):
            fetch_once(opener=opener)
        self.assertEqual(opener.calls, [])

    def test_allow_robots_then_two_public_gets_only(self):
        opener = TestOpener(b"User-agent: *\nAllow: /\n", PUBLIC_FIXTURE)
        result = fetch_once(source_policy_reviewed=True, opener=opener)
        self.assertEqual(result, PUBLIC_FIXTURE)
        self.assertEqual([x[0] for x in opener.calls], [ROBOTS, HOME])
        self.assertTrue(all("Authorization" not in x[1] and "Cookie" not in x[1]
                            for x in opener.calls))

    def test_redirect_and_hidden_endpoint_rejected(self):
        opener = TestOpener(b"User-agent: *\nAllow: /\n", PUBLIC_FIXTURE,
                            redirect=True)
        with self.assertRaisesRegex(PublicReferenceError, "NOT_200_OR_REDIRECT"):
            fetch_once(source_policy_reviewed=True, opener=opener)
        with self.assertRaisesRegex(PublicReferenceError, "UNAPPROVED_PUBLIC_SITE_URL"):
            _public_get("https://bestbook.app/api/odds", opener)

    def test_private_original_and_create_only_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            source = root / "original.txt"
            destination = root / "research.json"
            source.write_bytes(PUBLIC_FIXTURE)
            source.chmod(0o600)
            original = _read_source(source)
            self.assertEqual(original, PUBLIC_FIXTURE)
            report = save_report(original, destination,
                                 mode="AUTHORIZED_LOCAL_PAGE_SNAPSHOT", read_at_utc=NOW)
            self.assertEqual(source.read_bytes(), PUBLIC_FIXTURE)
            self.assertEqual(json.loads(destination.read_text())["source_page_sha256"],
                             report["source_page_sha256"])
            self.assertEqual(destination.stat().st_mode & 0o077, 0)
            with self.assertRaises(FileExistsError):
                save_report(original, destination,
                            mode="AUTHORIZED_LOCAL_PAGE_SNAPSHOT", read_at_utc=NOW)
            source.chmod(0o644)
            with self.assertRaisesRegex(PublicReferenceError, "0600_REQUIRED"):
                _read_source(source)

    def test_symlink_private_and_public_repo_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            source = root / "data"
            source.write_bytes(PUBLIC_FIXTURE)
            source.chmod(0o600)
            alias = root / "alias"
            alias.symlink_to(source)
            with self.assertRaisesRegex(PublicReferenceError, "SYMLINK"):
                _read_source(alias)
        with self.assertRaisesRegex(PublicReferenceError, "PUBLIC_REPOSITORY"):
            _private(Path(__file__).resolve().parents[2] / "private.json")


if __name__ == "__main__":
    unittest.main()
