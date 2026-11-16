"""Adversarial synthetic tests for offline historical odds sample normalization."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from ledger.oddsgap_historical_import import Blocked, export, ingest, SPORT_KEYS
from ledger.historical_clv_bridge import FIELDS, compare, parse_quote

BASE = {
    "snapshot_ts": "2026-10-20T00:11:00Z",
    "sport": "americanfootball_nfl",
    "away": "San Francisco 49ers",
    "home": "Washington Commanders",
    "commence_time": "2026-10-20T00:15:00Z",
    "market": "total",
    "side": "over",
    "line": "50.5",
    "book": "draftkings",
    "american_odds": "-110",
    "devig_fair_prob": "0.5",
    "best_price_flag": "0",
    "game_id": "nfl-2026-10-19-49ers-commanders",
}
COLS = list(BASE)

def fixture():
    a = dict(BASE)
    b = {**a, "side": "under", "american_odds": "-110"}
    home = {**a, "market":"spread", "side":"home","line":"-3.5"}
    away = {**home, "side":"away","line":"3.5", "american_odds":"+105"}
    mlhome = {**a, "market":"ml", "side":"home","line":"", "american_odds":"-135"}
    mlaway = {**mlhome, "side":"away","american_odds":"+115"}
    return [a,b,home,away,mlhome,mlaway]

def save(root:Path, rows=None, meta_overrides=None, raw_override=None):
    if rows is None: rows=fixture()
    if raw_override is None:
        sio=io.StringIO()
        writer=csv.DictWriter(sio,fieldnames=COLS,lineterminator="\n")
        writer.writeheader();writer.writerows(rows)
        raw=sio.getvalue().encode()
    else:
        raw=raw_override
    (root/"vendor.csv").write_bytes(raw)
    meta={
        "schema":"sportsedge-oddsgap-history-import-v1",
        "source_path":"vendor.csv",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "downloaded_at_utc":"2026-11-15T21:00:00Z",
        "source_url":"https://theoddsgap.com/api/odds-export.csv?sport=americanfootball_nfl",
        "x_data_sample":"1",
    }
    meta.update(meta_overrides or {})
    p=root/"source.manifest.json"
    p.write_text(json.dumps(meta))
    return p

class Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)

    def test_three_original_two_sided_sportsbook_markets(self):
        rows,audit=ingest(save(self.root))
        self.assertEqual(len(rows),6)
        self.assertEqual({r["market_kind"] for r in rows},{"TOTAL","SPREAD","MONEYLINE"})
        self.assertTrue(all(r["source"]=="ODDS_GAP" for r in rows))
        self.assertEqual(audit["raw_source_rows"],6)
        self.assertEqual(audit["market_groups_seen"],3)
        self.assertEqual(audit["official_counted"],0)

    def test_all_six_native_sports_from_published_schema(self):
        self.assertEqual(set(SPORT_KEYS.values()),{"NFL","CFB","CBB","NBA","MLB","NHL"})
        for raw,sport in SPORT_KEYS.items():
            with self.subTest(sport=sport):
                new=[{**r,"sport":raw} for r in fixture()]
                records,a=ingest(save(self.root,rows=new))
                self.assertEqual({r["sport"] for r in records},{sport})
                self.assertEqual(a["approved_stake_u"],0)

    def test_provider_game_id_is_kept_native_without_name_guess(self):
        rows,a=ingest(save(self.root))
        self.assertTrue(all(r["event_id"]==BASE["game_id"] for r in rows))
        self.assertTrue(all(r["source_event_id"]==BASE["game_id"] for r in rows))
        self.assertTrue(a["source_native_event_ids_not_cross_provider"])

    def test_normalized_spread_preserves_opposite_signed_lines(self):
        rows,_=ingest(save(self.root))
        home=[r for r in rows if r["market_kind"]=="SPREAD" and r["selection_id"]=="HOME"][0]
        self.assertEqual((home["line"],home["opposite_line"]),("-3.5","3.5"))

    def test_missing_opposite_offer_never_invented(self):
        rows,a=ingest(save(self.root,rows=fixture()[:1]))
        self.assertEqual(rows,[])
        self.assertEqual(a["blocked_rows_or_groups_by_reason"]["INCOMPLETE_OR_DUPLICATED_TWO_SIDED_GROUP"],1)

    def test_duplicate_book_quote_drops_entire_group(self):
        rows,a=ingest(save(self.root,rows=fixture()+[fixture()[0]]))
        self.assertEqual(len(rows),4)
        self.assertEqual(a["blocked_rows_or_groups_by_reason"]["INCOMPLETE_OR_DUPLICATED_TWO_SIDED_GROUP"],1)

    def test_opposite_spread_sign_does_not_coerce_or_match(self):
        rows=fixture()
        rows[3]["line"]="-3.5"
        out,a=ingest(save(self.root,rows=rows))
        self.assertEqual(len(out),4)
        # Both spread sides at the same signed line are invalid opposing handicaps.
        self.assertEqual(a["blocked_rows_or_groups_by_reason"]["OPPOSITE_SPREAD_SIGN_ERROR"],1)

    def test_alternative_total_line_is_not_mismatched(self):
        rows=fixture()
        rows[1]["line"]="51.5"
        out,a=ingest(save(self.root,rows=rows))
        self.assertEqual(len(out),4)
        self.assertGreaterEqual(a["blocked_rows_or_groups_by_reason"]["INCOMPLETE_OR_DUPLICATED_TWO_SIDED_GROUP"],1)

    def test_late_post_kickoff_snapshot_blocked(self):
        rows=[{**r,"snapshot_ts":"2026-10-20T00:15:00Z"} for r in fixture()]
        out,a=ingest(save(self.root,rows=rows))
        self.assertEqual(out,[])
        self.assertEqual(a["blocked_rows_or_groups_by_reason"]["POST_KICKOFF_QUOTE"],6)

    def test_future_observation_after_archive_download_blocked(self):
        rows=[{**r,"snapshot_ts":"2026-10-20T00:11:00Z"} for r in fixture()]
        out,a=ingest(save(self.root,rows=rows,meta_overrides={"downloaded_at_utc":"2026-10-19T00:00:00Z"}))
        self.assertEqual(out,[])
        self.assertEqual(a["blocked_rows_or_groups_by_reason"]["SOURCE_QUOTE_AFTER_DOWNLOAD"],6)

    def test_exchange_quotes_quarantined_without_sportsbook_conversion(self):
        rows=[{**r,"book":"kalshi"} for r in fixture()]
        out,a=ingest(save(self.root,rows=rows))
        self.assertEqual(out,[])
        self.assertEqual(a["blocked_rows_or_groups_by_reason"]["EXCHANGE_NOT_ORIGINAL_SPORTSBOOK"],6)

    def test_three_way_soccer_or_unknown_sport_blocked(self):
        rows=[{**r,"sport":"soccer_epl"} for r in fixture()]
        out,a=ingest(save(self.root,rows=rows))
        self.assertEqual(out,[])
        self.assertEqual(a["blocked_rows_or_groups_by_reason"]["SPORT_NOT_IN_SIX_SPORT_KERNEL"],6)

    def test_malformed_duplicate_headers_fail_closed(self):
        raw=("snapshot_ts,sport,away,home,commence_time,market,side,line,book,american_odds,game_id,game_id\n"
             "2026-10-20T00:11:00Z,americanfootball_nfl,A,B,2026-10-20T00:15:00Z,total,over,50.5,draftkings,-110,game,game\n").encode()
        with self.assertRaisesRegex(Blocked,"DUPLICATED_SOURCE_HEADERS"):
            ingest(save(self.root,raw_override=raw))

    def test_original_source_bytes_sha_must_match(self):
        p=save(self.root)
        (self.root/"vendor.csv").write_bytes(b"tampered")
        with self.assertRaisesRegex(Blocked,"RAW_SOURCE_SHA256_MISMATCH"):
            ingest(p)

    def test_source_path_escape_blocked(self):
        p=save(self.root,meta_overrides={"source_path":"../private-elsewhere.csv"})
        with self.assertRaisesRegex(Blocked,"RAW_SOURCE_PATH_ESCAPE"):
            ingest(p)

    def test_source_url_with_key_or_token_rejected(self):
        p=save(self.root,meta_overrides={
            "source_url":"https://theoddsgap.com/api/odds-export.csv?sport=americanfootball_nfl&key=secret"})
        with self.assertRaisesRegex(Blocked,"UNSAFE_SOURCE_QUERY_OR_SECRET"):
            ingest(p)

    def test_unexpected_host_or_endpoint_refused(self):
        p=save(self.root,meta_overrides={
            "source_url":"https://wrong.example/api/odds-export.csv"})
        with self.assertRaisesRegex(Blocked,"UNRECOGNIZED_OR_UNAUTHORIZED"):
            ingest(p)

    def test_private_create_only_csv_and_audit_preserve_hash(self):
        p=save(self.root);out=self.root/"normalized_history.csv"
        report=export(p,out)
        self.assertEqual(report["two_sided_quotes_written"],6)
        self.assertEqual(report["normalized_csv_sha256"],hashlib.sha256(out.read_bytes()).hexdigest())
        with out.open(newline="") as f:
            saved=list(csv.DictReader(f))
        self.assertEqual(len(saved),6)
        self.assertEqual(report["vendor_sample_flag_claim"],"1")
        self.assertFalse(report.get("provider_authenticated",False))
        self.assertEqual(json.loads((self.root/"normalized_history.csv.audit.json").read_text())["official_counted"],0)
        with self.assertRaisesRegex(Blocked,"CREATE_ONLY"):
            export(p,out)

    def test_failed_audit_sidecar_write_removes_new_csv(self):
        p=save(self.root)
        out=self.root/"normalized_history.csv"
        audit=out.with_name(out.name+".audit.json")
        from ledger import oddsgap_historical_import as module
        real_open=module.os.open
        def fail_audit(path, flags, mode=0o777):
            if Path(path) == audit:
                raise OSError("injected audit creation failure")
            return real_open(path, flags, mode)
        with patch.object(module.os, "open", side_effect=fail_audit):
            with self.assertRaisesRegex(OSError, "injected audit"):
                export(p,out)
        self.assertFalse(out.exists(), "orphan CSV must not survive without audit")
        self.assertFalse(audit.exists())

    def test_retrospective_history_is_reference_not_an_official_clv(self):
        rows,_=ingest(save(self.root))
        close=[r for r in rows if r["market_kind"]=="TOTAL" and r["selection_id"]=="OVER"][0]
        take={**close,
            "source":"DIRECT_BOOK",
            "source_url":"https://sportsbook.draftkings.com/",
            "price_american":"-105",
            "opposite_price_american":"-115",
            "observed_at_utc":"2026-10-20T00:01:00Z",
            "captured_at_utc":"2026-10-20T00:01:01Z",
        }
        report=compare([parse_quote(take,"TAKE")],[parse_quote(close,"HISTORY")])[0]
        self.assertEqual(report["status"],"CROSS_SOURCE_REFERENCE_ONLY")
        self.assertIsNone(report["clv_probability_points"])
        self.assertIsNotNone(report["reference_delta_probability_points"])
        self.assertEqual(report["official_counted"],0)

    def test_no_bet_selection_is_synthesized_from_vendor_history(self):
        rows, report=ingest(save(self.root))
        self.assertEqual(report["state"],"PAPER_RETROSPECTIVE_VENDOR_CLAIMS_ONLY")
        self.assertTrue(all(r["captured_at_utc"].startswith("2026-11-15") for r in rows))
        self.assertTrue(all(r["observed_at_utc"].startswith("2026-10-20") for r in rows))

if __name__=="__main__":
    unittest.main()
