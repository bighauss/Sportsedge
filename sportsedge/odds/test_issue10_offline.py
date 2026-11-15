"""Synthetic offline contracts only. Never connect to a sportsbook or place wagers."""
import dataclasses
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sportsedge.odds.adapters import bestbook_export_available, capture_authorized_export
from sportsedge.odds.evidence import (
    CLVTriple, FeatureSnapshot, MarketKey, PITBinding, QuoteReceipt,
    evaluate_dual_source, hash_payload,
)
from sportsedge.odds.storage import EvidenceChain
from sportsedge.odds.card_gate import gate_candidate

UTC = timezone.utc
D = datetime(2026, 11, 15, 17, 3, tzinfo=UTC)
START = D + timedelta(hours=3)
HASH = "sha256:" + "a" * 64


def quote(book="DraftKings", provider="DKDirect", upstream="DraftKings", *,
          raw_odds=-110, line="-3.5", observed=None, receipt_id=None):
    return QuoteReceipt(
        market=MarketKey("NFL", "NFL-2026-001", "SPREAD", "FG", "HOME", line=line),
        quote_id="q-" + book, provider=provider, upstream_book=upstream,
        upstream_provider=provider, provider_event_id="event1", provider_market_id="spread1",
        odds_american=raw_odds, observed_at_utc=observed or D-timedelta(minutes=2),
        ingested_at_utc=D-timedelta(minutes=1),
        game_start_utc=START, payload_sha256=HASH,
        receipt_id=receipt_id or "receipt-" + book,
        source_auth_method_claim="api_key_id_or_signed",
    )


class TestMarketAndDual(unittest.TestCase):
    def test_same_market_normalized_decimal(self):
        a = quote(line="-3.50").market
        b = quote(line="-3.5").market
        self.assertEqual(a.key(), b.key())

    def test_mismatch_line_blocks_even_if_same_odds(self):
        a = quote()
        b = quote(book="FanDuel", upstream="FanDuel", line="-2.5")
        out = evaluate_dual_source(a, b, D, market_mapping_verified=True)
        self.assertEqual(out.state, "BLOCK")
        self.assertIn("MARKET_IDENTITY_MISMATCH", out.reasons)

    def test_primary_missing(self):
        out = evaluate_dual_source(None, quote(book="FD"), D)
        self.assertEqual(out.state, "BLOCK")
        self.assertIn("PRIMARY_MISSING", out.reasons)

    def test_missing_secondary_blocks(self):
        out = evaluate_dual_source(quote(), None, D)
        self.assertEqual(out.state, "BLOCK")
        self.assertEqual(out.approved_stake_u, 0)

    def test_same_upstream_book_cannot_double_count_bestbook(self):
        a = quote()
        b = quote(book="BB-DK", provider="BestBook", upstream="DraftKings")
        out = evaluate_dual_source(a, b, D, market_mapping_verified=True)
        self.assertIn("NO_INDEPENDENT_UPSTREAM_BOOK", out.reasons)

    def test_unverified_mapping_blocks(self):
        out = evaluate_dual_source(quote(), quote("FD", "FanDuel", "FanDuel"), D)
        self.assertIn("CROSS_PROVIDER_MARKET_MAP_UNVERIFIED", out.reasons)

    def test_fresh_independent_prices_still_paper_only(self):
        out = evaluate_dual_source(quote(), quote("FD", "FanDuel", "FanDuel"),
                                   D, market_mapping_verified=True)
        self.assertEqual(out.state, "RESEARCH_ONLY")
        self.assertEqual(out.official_counted, 0)
        self.assertIn("UPSTREAM_SOURCE_AUTHENTICATION_UNVERIFIED", out.reasons)

    def test_stale_price_rejected(self):
        stale = quote(observed=D - timedelta(minutes=6))
        out = evaluate_dual_source(stale, quote("FD", "FanDuel", "FanDuel"),
                                   D, market_mapping_verified=True)
        self.assertIn("PRIMARY_STALE", out.reasons)

    def test_price_beyond_start_rejected(self):
        out = evaluate_dual_source(quote(), quote("FD", "FanDuel", "FanDuel"),
                                   START, market_mapping_verified=True)
        self.assertIn("PRIMARY_EVENT_ALREADY_STARTED", out.reasons)

    def test_invalid_american_odds_rejected(self):
        with self.assertRaises(ValueError):
            quote(raw_odds=-99)

    def test_non_utc_time_rejected(self):
        from datetime import timezone
        with self.assertRaisesRegex(ValueError, "NON_UTC_TIMESTAMP"):
            quote(observed=D.astimezone(timezone(timedelta(hours=-6))))

    def test_no_research_object_can_authorize_stake(self):
        from sportsedge.odds.evidence import DualSourceDecision
        with self.assertRaisesRegex(ValueError, "BET_PROMOTION_FORBIDDEN"):
            DualSourceDecision("RESEARCH_ONLY", (), "one", "two", None, approved_stake_u=1)


class TestPITandCLV(unittest.TestCase):
    def test_missing_required_feature(self):
        pit = PITBinding((), frozenset({"starting_qb"}), D-timedelta(minutes=2))
        self.assertIn("REQUIRED_FEATURE_MISSING:starting_qb", pit.check(quote()))

    def test_feature_leak_rejected(self):
        feature = FeatureSnapshot("starting_qb", "team-feed",
                                  D-timedelta(minutes=1), HASH, "qb1")
        pit = PITBinding((feature,), frozenset({"starting_qb"}), D-timedelta(minutes=2))
        self.assertIn("FEATURE_LOOKAHEAD:starting_qb", pit.check(quote()))

    def test_good_pit_structural(self):
        feature = FeatureSnapshot("starting_qb", "team-feed",
                                  D-timedelta(minutes=4), HASH, "qb1")
        pit = PITBinding((feature,), frozenset({"starting_qb"}), D-timedelta(minutes=2))
        self.assertEqual(pit.check(quote()), ())

    def test_clv_raw_probability_move_positive(self):
        a = quote(raw_odds=-105, observed=D-timedelta(minutes=4), receipt_id="opening")
        b = quote(raw_odds=-110, observed=D-timedelta(minutes=3), receipt_id="taken")
        c = quote(raw_odds=-120, observed=D-timedelta(minutes=2), receipt_id="close")
        result = CLVTriple(a,b,c).audit()
        self.assertTrue(result["valid_structural_match"])
        self.assertGreater(float(result["raw_break_even_probability_gain"]), 0)
        self.assertFalse(result["official_counted"])

    def test_clv_line_mismatch_blocked(self):
        a = quote(raw_odds=-105, observed=D-timedelta(minutes=4), receipt_id="opening")
        b = quote(raw_odds=-110, observed=D-timedelta(minutes=3), receipt_id="taken")
        c = quote(raw_odds=-120, observed=D-timedelta(minutes=2), receipt_id="close", line="-4")
        self.assertFalse(CLVTriple(a,b,c).audit()["valid_structural_match"])


class TestExportAndStorage(unittest.TestCase):
    def test_authorized_export_is_not_authentication(self):
        raw = json.dumps({
            "sport":"NFL", "event_id":"NFL-2026-001", "market_kind":"SPREAD",
            "period":"FG", "side":"HOME", "line":"-3.5",
            "provider_event_id":"p-1", "provider_market_id":"m-1",
            "quote_id":"q-1", "odds_american":-110,
            "observed_at_utc": "2026-11-15T17:01:00Z",
            "game_start_utc": "2026-11-15T20:03:00Z"
        }).encode("utf-8")
        q = capture_authorized_export(raw,ingested_at_utc=D-timedelta(minutes=1),
           provider="BestBook",upstream_book="FanDuel",upstream_provider="BestBook",
           receipt_id="r1",mapping_version="vendor-doc-v1")
        self.assertEqual(q.payload_sha256, hash_payload(raw))
        self.assertEqual(q.source_auth_method_claim, "OFFLINE_EXPORT_UNVERIFIED")
        self.assertFalse(bestbook_export_available(True))

    def test_duplicate_export_json_key_rejected(self):
        raw = b'{"quote_id":"one","quote_id":"two"}'
        with self.assertRaisesRegex(ValueError, "DUPLICATE_RAW_JSON_KEY"):
            capture_authorized_export(raw,ingested_at_utc=D,
                provider="BestBook",upstream_book="DK",upstream_provider="BB",
                receipt_id="r",mapping_version="v1")

    def test_chain_detects_tampering_and_duplicate_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            chain = EvidenceChain(temp)
            payload={"decision_id":"bet1", "asof_utc":D.isoformat(),
                "state":"PAPER_0U", "approved_stake_u":0, "official_counted":0}
            head = chain.append(payload)
            self.assertEqual(chain.verify(), (1,head))
            with self.assertRaisesRegex(ValueError, "DECISION_ID_REUSED"):
                chain.append(payload)
            path = Path(temp) / "research_decisions.jsonl"
            path.write_bytes(path.read_bytes().replace(b'PAPER_0U',b'PAPER_XU'))
            with self.assertRaisesRegex(ValueError, "BROKEN_CHAIN_DIGEST"):
                chain.verify()

    def test_chain_denies_unknown_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            chain = EvidenceChain(temp)
            with self.assertRaisesRegex(ValueError,"FIELDS_NOT_ALLOWED"):
                chain.append({"api_key":"SECRET","decision_id":"b","asof_utc":D.isoformat(),
                              "approved_stake_u":0,"official_counted":0})

    def test_card_gate_calls_v21_and_never_emits_card(self):
        primary=quote()
        secondary=quote("FD","FanDuel","FanDuel")
        dual=evaluate_dual_source(primary,secondary,D,market_mapping_verified=True)
        feature=FeatureSnapshot("starting_qb","team-feed",D-timedelta(minutes=4),HASH,"QB1")
        pit=PITBinding((feature,),frozenset({"starting_qb"}),D-timedelta(minutes=2))
        with tempfile.TemporaryDirectory() as temp:
            store=EvidenceChain(temp)
            report=gate_candidate({"bet_id":"bet-1","source_receipt_verified":True},
                     dual,pit,primary,D,secondary=secondary,chain=store)
            self.assertEqual(report["status"], "PAPER_0U")
            self.assertIsNone(report["card"])
            self.assertEqual(report["approved_stake_u"],0)
            self.assertFalse(report["source_externally_authenticated"])
            self.assertEqual(store.verify()[0],1)

    def test_card_gate_rejects_missing_pit(self):
        primary=quote(); secondary=quote("FD","FanDuel","FanDuel")
        dual=evaluate_dual_source(primary,secondary,D,market_mapping_verified=True)
        report=gate_candidate({"bet_id":"bet-2"},dual,None,primary,D)
        self.assertEqual(report["status"], "BLOCK")
        self.assertIn("PIT_PACKAGE_MISSING",report["reasons"])


if __name__=="__main__":
    unittest.main()
