"""Synthetic tests only. No provider calls or real betting records."""
import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from historical_clv_bridge import Blocked, FIELDS, compare, load_csv, parse_quote, run

BASE = dict.fromkeys(FIELDS, "")
BASE.update(source="BESTBOOK", source_url="https://bestbook.app/", sport="NFL",
    event_id="nfl-2026-example", source_event_id="provider-event-1",
    source_market_id="source-market-1", mapping_version="manual-crosswalk-v1",
    book="DraftKings", market_kind="TOTAL", period="FG", settlement="INCLUDES_OT",
    selection_id="OVER", opposite_selection_id="UNDER", line="49.5", opposite_line="49.5",
    price_american="-110", opposite_price_american="-110",
    observed_at_utc="2026-11-15T20:00:00Z", captured_at_utc="2026-11-15T20:00:01Z",
    kickoff_utc="2026-11-16T01:20:00Z")

def q(role="TAKE", **kwargs):
    return parse_quote({**BASE, **kwargs}, role)

class Tests(unittest.TestCase):
    def test_positive_prob_clv_from_exact_two_sided_prices(self):
        take=q()
        close=q("HISTORY", observed_at_utc="2026-11-16T01:15:00Z",
                captured_at_utc="2026-11-16T01:15:01Z",
                price_american="-125", opposite_price_american="+105")
        r=compare([take],[close])[0]
        self.assertEqual(r["status"],"SAME_SOURCE_STRUCTURAL_PAPER")
        self.assertGreater(float(r["clv_probability_points"]),0)
        self.assertEqual(r["official_counted"],0)
    def test_cross_source_reference_only_even_if_same_book(self):
        take=q(source="DIRECT_BOOK",source_url="https://sportsbook.draftkings.com/")
        close=q("HISTORY",observed_at_utc="2026-11-16T01:17:00Z",captured_at_utc="2026-11-16T01:17:00Z")
        self.assertEqual(compare([take],[close])[0]["status"],"CROSS_SOURCE_REFERENCE_ONLY")
    def test_late_import_retroactive_unverified(self):
        close=q("HISTORY",observed_at_utc="2026-11-16T01:17:00Z",captured_at_utc="2026-11-17T02:00:00Z")
        self.assertEqual(compare([q()],[close])[0]["status"],"RETROSPECTIVE_HISTORY_UNVERIFIED")
    def test_line_change_not_matched(self):
        close=q("HISTORY",line="50.5",opposite_line="50.5",observed_at_utc="2026-11-16T01:17:00Z",captured_at_utc="2026-11-16T01:17:00Z")
        self.assertEqual(compare([q()],[close])[0]["status"],"NO_EXACT_MATCHED_CLOSE")
    def test_other_book_not_matched(self):
        close=q("HISTORY",book="FanDuel",observed_at_utc="2026-11-16T01:17:00Z",captured_at_utc="2026-11-16T01:17:00Z")
        self.assertEqual(compare([q()],[close])[0]["status"],"NO_EXACT_MATCHED_CLOSE")
    def test_after_kickoff_observation_rejected(self):
        with self.assertRaisesRegex(Blocked,"CHRONOLOGY"):
            q("HISTORY",observed_at_utc="2026-11-16T01:21:00Z",captured_at_utc="2026-11-16T01:21:00Z")
    def test_take_imported_after_kickoff_rejected(self):
        with self.assertRaisesRegex(Blocked,"TAKE_NOT"):
            q(captured_at_utc="2026-11-16T01:21:00Z")
    def test_close_outside_ten_minutes_is_absent(self):
        close=q("HISTORY",observed_at_utc="2026-11-16T00:50:00Z",captured_at_utc="2026-11-16T00:50:00Z")
        self.assertEqual(compare([q()],[close])[0]["status"],"NO_EXACT_MATCHED_CLOSE")
    def test_latest_observation_is_selected(self):
        earlier=q("HISTORY",observed_at_utc="2026-11-16T01:12:00Z",captured_at_utc="2026-11-16T01:12:00Z")
        latest=q("HISTORY",observed_at_utc="2026-11-16T01:18:00Z",captured_at_utc="2026-11-16T01:18:00Z")
        self.assertEqual(compare([q()],[earlier,latest])[0]["close_observed_utc"],latest.observed.isoformat())
    def test_same_source_tie_with_other_provider_prefers_take_source(self):
        t="2026-11-16T01:18:00Z"
        a=q("HISTORY",observed_at_utc=t,captured_at_utc=t)
        b=q("HISTORY",source="COVERS",source_url="https://www.covers.com/",observed_at_utc=t,captured_at_utc=t)
        self.assertEqual(compare([q()],[a,b])[0]["status"],"SAME_SOURCE_STRUCTURAL_PAPER")
    def test_spread_requires_opposite_signed_line(self):
        with self.assertRaisesRegex(Blocked,"SPREAD_OPPOSITE_SIGN"):
            q(market_kind="SPREAD",selection_id="HOME",opposite_selection_id="AWAY",
              line="+3.5",opposite_line="+3.5")
    def test_prop_requires_player_and_stat(self):
        with self.assertRaisesRegex(Blocked,"UNBOUND_PLAYER_PROP"):
            q(market_kind="PLAYER_PROP")
    def test_missing_opposite_odds_rejected(self):
        with self.assertRaisesRegex(Blocked,"MISSING_REQUIRED_EVIDENCE"):
            q(opposite_price_american="")
    def test_unknown_source_rejected(self):
        with self.assertRaisesRegex(Blocked,"UNSUPPORTED_SOURCE"):
            q(source="UNAUTHORIZED_SCRAPER")
    def test_source_observation_later_than_capture_rejected(self):
        with self.assertRaisesRegex(Blocked,"CHRONOLOGY"):
            q(observed_at_utc="2026-11-15T20:00:02Z")
    def test_same_source_mismatched_market_ids_research_flag(self):
        close=q("HISTORY", source_market_id="new-id", observed_at_utc="2026-11-16T01:17:00Z",captured_at_utc="2026-11-16T01:17:00Z")
        self.assertEqual(compare([q()],[close])[0]["status"],"PROVIDER_MARKET_CROSSWALK_UNVERIFIED")
    def test_duplicate_take_rejected(self):
        with self.assertRaisesRegex(Blocked,"DUPLICATE_CANONICAL_TAKE"):
            compare([q(),q()],[])
    def test_csv_hash_and_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"take.csv"
            with p.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerow(BASE)
            loaded,digest=load_csv(p,"TAKE")
            self.assertEqual(len(loaded),1)
            self.assertEqual(digest,hashlib.sha256(p.read_bytes()).hexdigest())
            with p.open("a",newline="") as f:
                csv.DictWriter(f,fieldnames=FIELDS).writerow(BASE)
            with self.assertRaisesRegex(Blocked,"DUPLICATE_SOURCE"):
                load_csv(p,"TAKE")
    def test_covers_no_individual_prices_not_fabricated(self):
        with self.assertRaisesRegex(Blocked,"MISSING_REQUIRED_EVIDENCE"):
            q(source="COVERS",source_url="https://www.covers.com/sportsoddshistory",source_event_id="")
    def test_result_denominator_retained_with_unmatched(self):
        with tempfile.TemporaryDirectory() as d:
            take=Path(d)/"take.csv"; hist=Path(d)/"hist.csv"
            with take.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerow(BASE)
            data={**BASE,"source":"SCORES_AND_ODDS","source_url":"https://www.scoresandodds.com/",
                  "book":"FanDuel","observed_at_utc":"2026-11-16T01:18:00Z","captured_at_utc":"2026-11-16T01:18:00Z"}
            with hist.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerow(data)
            result=run(take,[hist]);self.assertEqual(result["take_rows"],1)
            self.assertEqual(result["comparable_rows"],0)
            self.assertEqual(len(result["matches"]),1)

    def test_cross_source_has_reference_delta_but_no_clv(self):
        history=q("HISTORY",source="ACTION_NETWORK",source_url="https://www.actionnetwork.com/",
            observed_at_utc="2026-11-16T01:17:00Z",
            captured_at_utc="2026-11-16T01:17:00Z",
            price_american="-125",opposite_price_american="+105")
        r=compare([q()],[history])[0]
        self.assertEqual(r["status"],"CROSS_SOURCE_REFERENCE_ONLY")
        self.assertIsNone(r["clv_probability_points"])
        self.assertGreater(float(r["reference_delta_probability_points"]),0)
    def test_retroactive_history_has_reference_delta_but_no_clv(self):
        history=q("HISTORY",observed_at_utc="2026-11-16T01:17:00Z",
            captured_at_utc="2026-11-18T01:17:00Z",
            price_american="-125",opposite_price_american="+105")
        r=compare([q()],[history])[0]
        self.assertEqual(r["status"],"RETROSPECTIVE_HISTORY_UNVERIFIED")
        self.assertIsNone(r["clv_probability_points"])
        self.assertIsNotNone(r["reference_delta_probability_points"])
    def test_missing_market_id_remains_unverified_reference(self):
        history=q("HISTORY",source_market_id="",observed_at_utc="2026-11-16T01:17:00Z",
            captured_at_utc="2026-11-16T01:17:00Z",
            price_american="-125",opposite_price_american="+105")
        r=compare([q(source_market_id="")],[history])[0]
        self.assertEqual(r["status"],"PROVIDER_MARKET_CROSSWALK_UNVERIFIED")
        self.assertIsNone(r["clv_probability_points"])
    def test_invalid_opposing_side_on_total(self):
        with self.assertRaisesRegex(Blocked,"INVALID_OPPOSITE_MARKET_SIDES"):
            q(opposite_selection_id="HOME")
    def test_invalid_opposing_side_on_moneyline(self):
        with self.assertRaisesRegex(Blocked,"INVALID_OPPOSITE_MARKET_SIDES"):
            q(market_kind="MONEYLINE",selection_id="OVER",opposite_selection_id="UNDER",
              line="",opposite_line="")
    def test_invalid_opposing_side_on_attd(self):
        with self.assertRaisesRegex(Blocked,"INVALID_OPPOSITE_MARKET_SIDES"):
            q(market_kind="ATTD",selection_id="HOME",opposite_selection_id="AWAY",
              line="",opposite_line="")
    def test_moneyline_blank_and_zero_aliases_match(self):
        take=q(market_kind="MONEYLINE",selection_id="HOME",opposite_selection_id="AWAY",
            line="",opposite_line="")
        close=q("HISTORY",market_kind="MONEYLINE",selection_id="HOME",opposite_selection_id="AWAY",
            line="0",opposite_line="0",observed_at_utc="2026-11-16T01:17:00Z",
            captured_at_utc="2026-11-16T01:17:00Z",
            price_american="-125",opposite_price_american="+105")
        r=compare([take],[close])[0]
        self.assertEqual(r["status"],"SAME_SOURCE_STRUCTURAL_PAPER")
        self.assertGreater(float(r["clv_probability_points"]),0)
    def test_same_source_earlier_archival_clock_rejected(self):
        take=q(observed_at_utc="2026-11-15T20:00:00Z",
            captured_at_utc="2026-11-16T01:17:30Z")
        close=q("HISTORY",observed_at_utc="2026-11-16T01:18:00Z",
            captured_at_utc="2026-11-16T01:18:00Z")
        # A quote observed hours before the TAKE archive is stale even if a
        # later close looks structurally matched.
        self.assertEqual(compare([take],[close])[0]["status"],"TAKE_QUOTE_STALE_AT_CAPTURE")
        before=q("HISTORY",observed_at_utc="2026-11-16T01:16:00Z",
            captured_at_utc="2026-11-16T01:16:00Z")
        r=compare([take],[before])[0]
        self.assertEqual(r["status"],"CLOSE_ARCHIVED_BEFORE_TAKE")
        self.assertIsNone(r["clv_probability_points"])
    def test_counts_do_not_upgrade_unverified_reference_to_clv(self):
        with tempfile.TemporaryDirectory() as d:
            take=Path(d)/"take.csv";hist=Path(d)/"hist.csv"
            with take.open("w",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerow(BASE)
            row={**BASE,"source":"ACTION_NETWORK","source_url":"https://www.actionnetwork.com/",
                 "observed_at_utc":"2026-11-16T01:18:00Z",
                 "captured_at_utc":"2026-11-16T01:18:00Z",
                 "price_american":"-125","opposite_price_american":"+105"}
            with hist.open("w",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerow(row)
            result=run(take,[hist])
            self.assertEqual(result["comparable_rows"],0)
            self.assertEqual(result["reference_only_rows"],1)
            self.assertEqual(result["status_counts"]["CROSS_SOURCE_REFERENCE_ONLY"],1)
            self.assertIsNone(result["matches"][0]["clv_probability_points"])
    def test_original_structural_clv_retained(self):
        history=q("HISTORY",observed_at_utc="2026-11-16T01:17:00Z",
            captured_at_utc="2026-11-16T01:17:00Z",
            price_american="-125",opposite_price_american="+105")
        r=compare([q()],[history])[0]
        self.assertEqual(r["status"],"SAME_SOURCE_STRUCTURAL_PAPER")
        self.assertIsNotNone(r["clv_probability_points"])
        self.assertIsNone(r["reference_delta_probability_points"])

    def test_newer_cross_source_does_not_mask_genuine_same_source_close(self):
        t="2026-11-16T01:14:00Z"
        same=q("HISTORY",observed_at_utc=t,captured_at_utc=t,
               price_american="-125",opposite_price_american="+105")
        newer=q("HISTORY",source="ODDS_GAP",source_url="https://theoddsgap.com/data",
                observed_at_utc="2026-11-16T01:19:00Z",
                captured_at_utc="2026-11-17T10:00:00Z",
                price_american="-135",opposite_price_american="+115")
        r=compare([q()],[newer,same])[0]
        self.assertEqual(r["status"],"SAME_SOURCE_STRUCTURAL_PAPER")
        self.assertEqual(r["closing_source"],"BESTBOOK")
        self.assertEqual(r["close_observed_utc"],same.observed.isoformat())
        self.assertGreater(float(r["clv_probability_points"]),0)
        self.assertIsNone(r["reference_delta_probability_points"])

    def test_latest_same_source_bad_receipt_is_not_cherry_picked(self):
        t="2026-11-16T01:14:00Z"
        valid=q("HISTORY",observed_at_utc=t,captured_at_utc=t)
        late=q("HISTORY",observed_at_utc="2026-11-16T01:18:00Z",
               captured_at_utc="2026-11-17T10:00:00Z")
        result=compare([q()],[valid,late])[0]
        self.assertEqual(result["status"],"RETROSPECTIVE_HISTORY_UNVERIFIED")
        self.assertIsNone(result["clv_probability_points"])

    def test_two_same_source_close_records_at_latest_are_ambiguous(self):
        t="2026-11-16T01:18:00Z"
        one=q("HISTORY",observed_at_utc=t,captured_at_utc=t)
        two=q("HISTORY",observed_at_utc=t,captured_at_utc=t,
              price_american="-125",opposite_price_american="+105")
        result=compare([q()],[one,two])[0]
        self.assertEqual(result["status"],"AMBIGUOUS_LAST_CLOSE")
        self.assertIsNone(result["clv_probability_points"])

    def test_no_same_source_falls_back_to_last_reference_only(self):
        earlier=q("HISTORY",source="ACTION_NETWORK",source_url="https://www.actionnetwork.com/",
                  observed_at_utc="2026-11-16T01:12:00Z",
                  captured_at_utc="2026-11-16T01:12:00Z")
        later=q("HISTORY",source="COVERS",source_url="https://www.covers.com/",
                observed_at_utc="2026-11-16T01:18:00Z",
                captured_at_utc="2026-11-16T01:18:00Z")
        result=compare([q()],[later,earlier])[0]
        self.assertEqual(result["status"],"CROSS_SOURCE_REFERENCE_ONLY")
        self.assertEqual(result["closing_source"],"COVERS")
        self.assertIsNone(result["clv_probability_points"])

    def test_no_same_source_tied_latest_reference_stays_ambiguous(self):
        t="2026-11-16T01:18:00Z"
        a=q("HISTORY",source="ACTION_NETWORK",source_url="https://www.actionnetwork.com/",
            observed_at_utc=t,captured_at_utc=t)
        b=q("HISTORY",source="COVERS",source_url="https://www.covers.com/",
            observed_at_utc=t,captured_at_utc=t)
        result=compare([q()],[a,b])[0]
        self.assertEqual(result["status"],"AMBIGUOUS_LAST_CLOSE")

    def test_close_price_precedes_actual_take_capture(self):
        take=q(observed_at_utc="2026-11-16T01:11:59Z",
               captured_at_utc="2026-11-16T01:12:00Z")
        close=q("HISTORY",observed_at_utc="2026-11-16T01:11:59Z",
                captured_at_utc="2026-11-16T01:13:00Z",
                price_american="-125",opposite_price_american="+105")
        # Equal observed timestamps are not later close observations.
        result=compare([take],[close])[0]
        self.assertEqual(result["status"],"NO_EXACT_MATCHED_CLOSE")

    def test_later_observed_close_still_before_take_capture(self):
        take=q(observed_at_utc="2026-11-16T01:12:00Z",
               captured_at_utc="2026-11-16T01:16:00Z")
        close=q("HISTORY",observed_at_utc="2026-11-16T01:15:00Z",
                captured_at_utc="2026-11-16T01:17:00Z",
                price_american="-125",opposite_price_american="+105")
        r=compare([take],[close])[0]
        self.assertEqual(r["status"],"CLOSE_OBSERVED_BEFORE_TAKE_CAPTURE")
        self.assertIsNone(r["clv_probability_points"])
        self.assertIsNotNone(r["reference_delta_probability_points"])

    def test_take_stale_by_301_seconds(self):
        take=q(observed_at_utc="2026-11-16T01:12:00Z",
               captured_at_utc="2026-11-16T01:17:01Z")
        close=q("HISTORY",observed_at_utc="2026-11-16T01:18:00Z",
                captured_at_utc="2026-11-16T01:18:01Z")
        r=compare([take],[close])[0]
        self.assertEqual(r["status"],"TAKE_QUOTE_STALE_AT_CAPTURE")
        self.assertIsNone(r["clv_probability_points"])

    def test_take_exact_300_seconds_is_still_structurally_paper(self):
        take=q(observed_at_utc="2026-11-16T01:12:01Z",
               captured_at_utc="2026-11-16T01:17:01Z")
        close=q("HISTORY",observed_at_utc="2026-11-16T01:18:00Z",
                captured_at_utc="2026-11-16T01:18:01Z")
        r=compare([take],[close])[0]
        self.assertEqual(r["status"],"SAME_SOURCE_STRUCTURAL_PAPER")
        self.assertIsNotNone(r["clv_probability_points"])

    def test_close_stale_by_301_seconds(self):
        take=q(observed_at_utc="2026-11-16T01:10:00Z",
               captured_at_utc="2026-11-16T01:10:01Z")
        close=q("HISTORY",observed_at_utc="2026-11-16T01:12:00Z",
                captured_at_utc="2026-11-16T01:17:01Z",
                price_american="-125",opposite_price_american="+105")
        r=compare([take],[close])[0]
        self.assertEqual(r["status"],"CLOSE_QUOTE_STALE_AT_CAPTURE")
        self.assertIsNone(r["clv_probability_points"])

    def test_close_exact_300_seconds_is_still_structurally_paper(self):
        take=q(observed_at_utc="2026-11-16T01:10:00Z",
               captured_at_utc="2026-11-16T01:10:01Z")
        close=q("HISTORY",observed_at_utc="2026-11-16T01:12:00Z",
                captured_at_utc="2026-11-16T01:17:00Z")
        r=compare([take],[close])[0]
        self.assertEqual(r["status"],"SAME_SOURCE_STRUCTURAL_PAPER")

    def test_latest_stale_same_source_does_not_cherry_pick_older(self):
        take=q()
        old=q("HISTORY",observed_at_utc="2026-11-16T01:11:00Z",
              captured_at_utc="2026-11-16T01:11:01Z")
        newer=q("HISTORY",observed_at_utc="2026-11-16T01:14:00Z",
                captured_at_utc="2026-11-16T01:19:01Z")
        r=compare([take],[old,newer])[0]
        self.assertEqual(r["status"],"CLOSE_QUOTE_STALE_AT_CAPTURE")
        self.assertEqual(r["close_observed_utc"],newer.observed.isoformat())
        self.assertIsNone(r["clv_probability_points"])

if __name__ == "__main__":
    unittest.main()
