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


    def test_each_sport_accepts_one_valid_total(self):
        for sport in ("NFL","CFB","CBB","NBA","MLB"):
            with self.subTest(sport=sport):
                m=MarketKey(sport,"game", "TOTAL","FG","OVER",line="44.50")
                self.assertEqual(m.line,"44.5")

    def test_market_kind_rejects_wrong_side(self):
        cases=[("MONEYLINE","OVER", "", "TEAM_SIDE_REQUIRED"),
               ("SPREAD","YES","-3.5","TEAM_SIDE_REQUIRED"),
               ("TOTAL","HOME","42.5","OVER_UNDER_REQUIRED"),
               ("PLAYER_PROP","YES","19.5","OVER_UNDER_REQUIRED"),
               ("ATTD","OVER","","YES_NO_REQUIRED"),
               ("NRFI","HOME","","YES_NO_REQUIRED")]
        for kind,side,line,expected in cases:
            sport="MLB" if kind=="NRFI" else "NFL"
            period="1IN" if kind=="NRFI" else "FG"
            kwargs={"player_id":"P1","stat":"REC_YDS"} if kind=="PLAYER_PROP" else (
                {"player_id":"P1"} if kind=="ATTD" else {})
            with self.subTest(kind=kind,side=side), self.assertRaisesRegex(ValueError,expected):
                MarketKey(sport,"game",kind,period,side,line=line,**kwargs)

    def test_categorical_market_not_numeric_line(self):
        for sport,kind,period in (("NFL","ATTD","FG"),
                                  ("NFL","FIRST_TD","FG"),
                                  ("NFL","TD_2PLUS","FG"),
                                  ("NBA","FIRST_BASKET","FG"),
                                  ("MLB","NRFI","1IN"),
                                  ("MLB","YRFI","1IN")):
            kwargs={"player_id":"player-1"} if kind not in ("NRFI","YRFI") else {}
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError,"YES_NO_MARKET_CANNOT_HAVE_LINE"):
                MarketKey(sport,"game",kind,period,"YES",line="0.5",**kwargs)

    def test_sport_market_crossovers_are_refused(self):
        cases=[("NBA","ATTD","FG","TOUCHDOWN_MARKET_REQUIRES_FG_FOOTBALL"),
               ("MLB","FIRST_TD","FG","TOUCHDOWN_MARKET_REQUIRES_FG_FOOTBALL"),
               ("CFB","FIRST_BASKET","FG","FIRST_BASKET_REQUIRES_FG_BASKETBALL"),
               ("NFL","NRFI","1IN","PERIOD_NOT_SUPPORTED_BY_SPORT"),
               ("NBA","YRFI","FG","FIRST_INNING_ONLY_MLB")]
        for sport,kind,period,reason in cases:
            kwargs={"player_id":"player-1"} if kind not in ("NRFI","YRFI") else {}
            with self.subTest(sport=sport,kind=kind), self.assertRaisesRegex(ValueError,reason):
                MarketKey(sport,"game",kind,period,"YES",**kwargs)

    def test_real_supported_market_families_accept_valid_identity(self):
        items=[("NFL","FIRST_TD","FG","YES",{"player_id":"P"}),
               ("CFB","TD_2PLUS","FG","YES",{"player_id":"P"}),
               ("NBA","FIRST_BASKET","FG","NO",{"player_id":"P"}),
               ("CBB","FIRST_BASKET","FG","YES",{"player_id":"P"}),
               ("MLB","NRFI","1IN","YES",{}),
               ("MLB","YRFI","1IN","NO",{})]
        for sport,kind,period,side,kwargs in items:
            with self.subTest(sport=sport,kind=kind):
                self.assertEqual(MarketKey(sport,"game",kind,period,side,**kwargs).kind,kind)

    def test_mlb_period_restrictions_and_first_five(self):
        ok=MarketKey("MLB","game","TOTAL","F5","OVER",line="4.5")
        self.assertEqual(ok.period,"F5")
        with self.assertRaisesRegex(ValueError,"PERIOD_NOT_SUPPORTED_BY_SPORT"):
            MarketKey("MLB","game","TOTAL","1H","OVER",line="4.5")
        with self.assertRaisesRegex(ValueError,"PERIOD_NOT_SUPPORTED_BY_SPORT"):
            MarketKey("NFL","game","SPREAD","F5","HOME",line="-1.5")

    def test_first_td_not_second_quarter_only(self):
        with self.assertRaisesRegex(ValueError,"TOUCHDOWN_MARKET_REQUIRES_FG_FOOTBALL"):
            MarketKey("NFL","game","FIRST_TD","1Q","YES",player_id="P1")

    def test_categorical_player_market_requires_player_id(self):
        with self.assertRaisesRegex(ValueError,"MISSING_PLAYER_ID"):
            MarketKey("NBA","game","FIRST_BASKET","FG","YES")
        with self.assertRaisesRegex(ValueError,"MISSING_PLAYER_ID"):
            MarketKey("NFL","game","TD_2PLUS","FG","YES")

    def test_team_total_requires_team_id_even_when_line_and_side_valid(self):
        with self.assertRaisesRegex(ValueError,"MISSING_TEAM_ID"):
            MarketKey("NFL","game","TEAM_TOTAL","FG","OVER",line="25.5")

    def test_total_cannot_have_player_id_or_stat(self):
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_PLAYER_STAT_ID"):
            MarketKey("NFL","game","TOTAL","FG","UNDER",line="42.5",player_id="P")
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_PLAYER_STAT_ID"):
            MarketKey("NBA","game","SPREAD","FG","HOME",line="-5.5",stat="POINTS")

    def test_numeric_total_negative_rejected_but_negative_spread_valid(self):
        with self.assertRaisesRegex(ValueError,"NEGATIVE_NON_SPREAD_LINE"):
            MarketKey("CBB","game","TOTAL","FG","OVER",line="-1.5")
        with self.assertRaisesRegex(ValueError,"NEGATIVE_NON_SPREAD_LINE"):
            MarketKey("NBA","game","PLAYER_PROP","FG","OVER",line="-0.5",player_id="P1",stat="POINTS")
        self.assertEqual(MarketKey("NFL","game","SPREAD","FG","AWAY",line="-7.50").line,"-7.5")

    def test_draw_not_conflated_with_two_way_moneyline(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PERIOD_OR_SIDE"):
            MarketKey("CFB","game","MONEYLINE","FG","DRAW")

    def test_blank_sport_and_unknown_sport_refused(self):
        for sport in ("NHL","SOCCER","nfl"):
            with self.subTest(sport=sport), self.assertRaisesRegex(ValueError,"INVALID_SPORT_OR_MARKET_KIND"):
                MarketKey(sport,"game","TOTAL","FG","OVER",line="44.5")

    def test_settlement_not_inferable_from_arbitrary_strings(self):
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_SETTLEMENT_RULE"):
            MarketKey("NFL","game","MONEYLINE","FG","HOME",settlement="OT_PROBABLY")

    def test_mlb_innings_scored_without_line_identity_collision(self):
        a=MarketKey("MLB","game","TOTAL","FG","OVER",line="8.5",settlement="INCLUDES_OT")
        b=MarketKey("MLB","game","TOTAL","F5","OVER",line="8.5",settlement="REGULATION")
        self.assertNotEqual(a.key(),b.key())



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
