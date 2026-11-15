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

    def test_moneyline_blank_and_zero_aliases_have_one_market_identity(self):
        first = MarketKey("NFL", "match-1", "MONEYLINE", "FG", "HOME", line="")
        second = MarketKey("NFL", "match-1", "MONEYLINE", "FG", "HOME", line="0")
        self.assertEqual(first.key(), second.key())
        self.assertEqual(first.line, second.line)

    def test_touchdown_yes_no_markets_reject_fabricated_numeric_lines(self):
        for kind in ("ATTD", "FIRST_TD", "TD_2PLUS"):
            for invalid_line in ("0", "1", "0.5"):
                with self.subTest(kind=kind, line=invalid_line):
                    with self.assertRaisesRegex(ValueError, "YES_NO_MARKET_CANNOT_HAVE_LINE"):
                        MarketKey("NFL", "match-1", kind, "FG", "YES",
                                  line=invalid_line, player_id="player-1")

    def test_mlb_first_five_and_first_inning_quote_contract(self):
        m=MarketKey("MLB","MLB-GAME","MONEYLINE","F5","HOME",
                    settlement="POSTED_RULES")
        self.assertEqual((m.period,m.side),("F5","HOME"))
        n=MarketKey("MLB","MLB-GAME","NRFI","1IN","YES",
                    settlement="POSTED_RULES")
        self.assertEqual(n.kind,"NRFI")

    def test_market_kind_spelling_canonicalizes_ml(self):
        a=MarketKey("NFL","GAME","ML","FG","HOME",line="0")
        b=MarketKey("NFL","GAME","MONEYLINE","FG","HOME",line="")
        self.assertEqual(a.key(),b.key())

    def test_market_side_mismatch_blocks(self):
        for kind,side,line in (
            ("MONEYLINE","OVER",""),
            ("SPREAD","UNDER","-3.5"),
            ("TOTAL","HOME","41.5"),
            ("TEAM_TOTAL","AWAY","20.5"),
            ("PLAYER_PROP","YES","99.5"),
            ("ATTD","OVER",""),
            ("FIRST_TD","AWAY",""),
            ("TD_2PLUS","UNDER",""),
            ("FIRST_BASKET","OVER",""),
            ("NRFI","HOME",""),
        ):
            with self.subTest(kind=kind,side=side):
                with self.assertRaisesRegex(ValueError,
                            "TEAM_SIDE_REQUIRED|OVER_UNDER_REQUIRED|YES_NO_REQUIRED"):
                    MarketKey("NFL" if kind!="NRFI" else "MLB",
                        "GAME",kind,"FG" if kind!="NRFI" else "1IN",
                        side,line=line,
                        team_id="HOME" if kind=="TEAM_TOTAL" else "",
                        player_id="P" if kind in (
                            "PLAYER_PROP","ATTD","FIRST_TD","TD_2PLUS","FIRST_BASKET") else "",
                        stat="PASS_YDS" if kind=="PLAYER_PROP" else "")

    def test_mlb_cannot_use_basketball_quarters(self):
        with self.assertRaisesRegex(ValueError,"PERIOD_UNSUPPORTED_FOR_BASEBALL"):
            MarketKey("MLB","G","TOTAL","1Q","OVER",line="4.5")

    def test_football_cannot_use_first_five_innings(self):
        with self.assertRaisesRegex(ValueError,"BASEBALL_PERIOD_ON_OTHER_SPORT"):
            MarketKey("NFL","G","TOTAL","F5","OVER",line="24.5")

    def test_first_inning_yes_no_only_mlb(self):
        for sport,period in (("NBA","FG"),("MLB","FG")):
            with self.subTest(sport=sport,period=period):
                with self.assertRaisesRegex(ValueError,
                                  "FIRST_INNING_ONLY_MLB"):
                    MarketKey(sport,"G","YRFI",period,"YES")

    def test_first_basket_only_nba_cbb_full_game(self):
        good=MarketKey("CBB","G","FIRST_BASKET","FG","YES",player_id="P")
        self.assertEqual(good.sport,"CBB")
        for sport,period in (("NFL","FG"),("NBA","1H")):
            with self.subTest(sport=sport,period=period):
                with self.assertRaisesRegex(ValueError,
                            "FIRST_BASKET_ONLY_BASKETBALL_FG"):
                    MarketKey(sport,"G","FIRST_BASKET",period,"YES",player_id="P")

    def test_at_td_only_football(self):
        with self.assertRaisesRegex(ValueError,"TOUCHDOWN_MARKET_ONLY_FOOTBALL"):
            MarketKey("NBA","G","ATTD","FG","YES",player_id="P")

    def test_negative_prop_or_team_total_line_blocked(self):
        for kind,team,player,stat in (
            ("TOTAL","","",""),("TEAM_TOTAL","HOME","",""),
            ("PLAYER_PROP","","P","POINTS"),
        ):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError,"NEGATIVE_OVER_UNDER_LINE"):
                    MarketKey("NBA","G",kind,"FG","OVER",line="-2.5",
                              team_id=team,player_id=player,stat=stat)

    def test_posted_market_settlement_cannot_be_arbitrary(self):
        with self.assertRaisesRegex(ValueError,"UNKNOWN_SETTLEMENT_CONTRACT"):
            MarketKey("MLB","G","MONEYLINE","FG","HOME",
                      settlement="INCLUDES_EXTRA_UNCERTAIN")

    def test_forged_sport_is_not_a_quote_market(self):
        with self.assertRaisesRegex(ValueError,"INVALID_SPORT_OR_MARKET_KIND"):
            MarketKey("SOCCER","G","TOTAL","FG","OVER",line="2.5")

    def test_number_normalization_for_dk_player_lines(self):
        a=MarketKey("NBA","G","PLAYER_PROP","FG","OVER",
                    "25.50",player_id="P",stat="POINTS")
        b=MarketKey("NBA","G","PLAYER_PROP","FG","OVER",
                    "25.5",player_id="P",stat="POINTS")
        self.assertEqual(a.key(),b.key())

    def test_distinct_book_logos_same_aggregator_chain_still_blocked(self):
        from dataclasses import replace
        first=quote("DK-offer",provider="BestBookFeed",upstream="DraftKings")
        second=quote("FD-offer",provider="BestBookFeed",upstream="FanDuel")
        second=replace(second,upstream_provider="BestBookFeed",receipt_id="fd-unique")
        result=evaluate_dual_source(first,second,D,market_mapping_verified=True)
        self.assertEqual(result.state, "BLOCK")
        self.assertIn("NO_INDEPENDENT_CAPTURE_PATH",result.reasons)

    def test_distinct_transport_names_shared_underlying_feed_still_blocked(self):
        from dataclasses import replace
        first=quote("DK-offer",provider="BestBookFeed",upstream="DraftKings")
        second=quote("FD-offer",provider="MirrorOfBestBook",upstream="FanDuel")
        second=replace(second,upstream_provider="BestBookFeed")
        result=evaluate_dual_source(first,second,D,market_mapping_verified=True)
        self.assertIn("NO_INDEPENDENT_CAPTURE_PATH",result.reasons)

    def test_clv_close_from_different_book_is_not_same_book_clv(self):
        from dataclasses import replace
        o=quote(raw_odds=-105,observed=D-timedelta(minutes=4),receipt_id="clv-open")
        t=quote(raw_odds=-110,observed=D-timedelta(minutes=3),receipt_id="clv-taken")
        c=quote("FD", "FanDuel", "FanDuel", raw_odds=-120,
                observed=D-timedelta(minutes=2),receipt_id="clv-close")
        self.assertIn("CLV_BOOK_MISMATCH",CLVTriple(o,t,c).audit()["reason"])
        self.assertFalse(CLVTriple(o,t,c).audit()["valid_structural_match"])

    def test_clv_vendor_market_id_changed_is_not_same_market_triple(self):
        from dataclasses import replace
        o=quote(raw_odds=-105,observed=D-timedelta(minutes=4),receipt_id="clv-open")
        t=quote(raw_odds=-110,observed=D-timedelta(minutes=3),receipt_id="clv-taken")
        c=replace(quote(raw_odds=-120,observed=D-timedelta(minutes=2),
                        receipt_id="clv-close"),provider_market_id="another-market")
        report=CLVTriple(o,t,c).audit()
        self.assertIn("CLV_PROVIDER_MARKET_MISMATCH",report["reason"])
        self.assertFalse(report["valid_structural_match"])

    def test_clv_replayed_same_timestamp_close_is_not_forward_close(self):
        o=quote(raw_odds=-105,observed=D-timedelta(minutes=4),receipt_id="clv-open")
        t=quote(raw_odds=-110,observed=D-timedelta(minutes=3),receipt_id="clv-taken")
        c=quote(raw_odds=-120,observed=D-timedelta(minutes=3),receipt_id="clv-close")
        self.assertIn("CLV_TIME_ORDER_INVALID",CLVTriple(o,t,c).audit()["reason"])

    def test_genuinely_distinct_book_and_collection_path_still_research_only(self):
        primary=quote("DK",provider="DKDirect",upstream="DraftKings")
        secondary=quote("FD",provider="FDDirect",upstream="FanDuel")
        result=evaluate_dual_source(primary,secondary,D,market_mapping_verified=True)
        self.assertEqual(result.state,"RESEARCH_ONLY")
        self.assertEqual(result.approved_stake_u,0)

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
