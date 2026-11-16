"""Synthetic end-to-end tests: no API key, network, or real quote bytes."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import json
import tempfile
import unittest
import os
from unittest.mock import patch
from pathlib import Path

from sportsedge.odds.free_odds_aggregator_intake import SPORTS
from sportsedge.odds.the_odds_api_clv_export import convert, load_evidence, write_export, Blocked
from ledger.historical_clv_bridge import compare, parse_quote

CAPTURE = "2026-11-15T20:00:00Z"
OBSERVED = "2026-11-15T19:59:00Z"
START = "2026-11-16T01:20:00Z"

def e(sport="NFL", books=True):
    markets=[
      {"key":"h2h","last_update":OBSERVED,"outcomes":[
          {"name":"Home Team","price":-110},{"name":"Away Team","price":+100}]},
      {"key":"spreads","last_update":OBSERVED,"outcomes":[
          {"name":"Home Team","price":-115,"point":-3.5},
          {"name":"Away Team","price":+105,"point":+3.5}]},
      {"key":"totals","last_update":OBSERVED,"outcomes":[
          {"name":"Over","price":-110,"point":48.5},
          {"name":"Under","price":-110,"point":48.5}]},
    ]
    return {"id":"0123456789abcdef0123456789abcdef","sport_key":SPORTS[sport],
         "commence_time":START,"home_team":"Home Team","away_team":"Away Team",
         "bookmakers":[{"key":"draftkings","markets":markets}] if books else []}

def evidence(root, payload=None, sport="NFL", captured=CAPTURE):
    doc = [e(sport)] if payload is None else payload
    raw = json.dumps(doc).encode("utf-8")
    (root/"original.json").write_bytes(raw)
    meta={"schema":"sportsedge-oddsapi-aggregator-raw-v1",
          "sport":sport,"captured_utc":captured,
          "read_only_endpoint":"https://api.the-odds-api.com/v4/sports/"+SPORTS[sport]+"/odds",
          "raw_filename":"original.json",
          "original_raw_sha256":"sha256:"+hashlib.sha256(raw).hexdigest(),
          "events_returned":len(doc)}
    path=root/"original.manifest.json";path.write_text(json.dumps(meta))
    return path

class TestProspectiveCLVExport(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)

    def test_six_sports_documented_keys_available(self):
        self.assertEqual(set(SPORTS),{"NFL","CFB","CBB","NBA","MLB","NHL"})
        for sport in SPORTS:
            with self.subTest(sport=sport):
                p=evidence(self.root,sport=sport)
                rows, audit=convert(p)
                self.assertEqual(len(rows),6)
                self.assertEqual(audit["sport"],sport)
                self.assertEqual({r["sport"] for r in rows},{sport})
                self.assertEqual(audit["official_counted"],0)

    def test_three_main_market_two_sided_rows(self):
        rows,a=convert(evidence(self.root))
        self.assertEqual(len(rows),6)
        self.assertEqual(a["market_groups_quarantined_by_reason"]["ACCEPTED_TWO_SIDED_MARKET"],3)
        self.assertEqual({r["market_kind"] for r in rows},{"MONEYLINE","SPREAD","TOTAL"})
        spread=[r for r in rows if r["market_kind"]=="SPREAD" and r["selection_id"]=="HOME"][0]
        self.assertEqual((spread["line"],spread["opposite_line"]),("-3.5","3.5"))
        self.assertEqual(spread["source"],"THE_ODDS_API")
        self.assertEqual(spread["event_id"],spread["source_event_id"])
        self.assertEqual(spread["settlement"],"POSTED_RULES_UNVERIFIED")

    def test_book_prices_are_never_upstream_authenticated(self):
        _,audit=convert(evidence(self.root))
        self.assertFalse(audit["bookmakers_independently_authenticated"])
        self.assertFalse(audit["claimed_market_clocks_externally_verified"])
        self.assertTrue(audit["source_native_event_ids_not_cross_provider"])
        self.assertEqual(audit["approved_stake_u"],0)

    def test_stale_market_blocked_but_not_fabricated(self):
        event=e()
        event["bookmakers"][0]["markets"][0]["last_update"]="2026-11-15T19:00:00Z"
        rows,a=convert(evidence(self.root,payload=[event]))
        self.assertEqual(len(rows),4)
        self.assertEqual(a["market_groups_quarantined_by_reason"]["STALE_QUOTE_OVER_FIVE_MINUTES"],1)

    def test_after_kickoff_capture_blocks_all_rows(self):
        rows,a=convert(evidence(self.root,captured="2026-11-16T01:21:00Z"))
        self.assertEqual(rows,[])
        self.assertEqual(a["state"],"BLOCK_NO_VALID_TWO_SIDED_QUOTES")
        self.assertEqual(a["market_groups_quarantined_by_reason"]["CAPTURE_NOT_PREGAME"],3)

    def test_missing_opposite_quote_blocked(self):
        event=e()
        event["bookmakers"][0]["markets"][0]["outcomes"].pop()
        rows,a=convert(evidence(self.root,payload=[event]))
        self.assertEqual(len(rows),4)
        self.assertIn("MARKET_NOT_TWO_SIDED",a["market_groups_quarantined_by_reason"])

    def test_unsupported_alt_market_kept_as_quarantined(self):
        event=e()
        event["bookmakers"][0]["markets"].append({"key":"alternate_totals","last_update":OBSERVED,"outcomes":[]})
        rows,a=convert(evidence(self.root,payload=[event]))
        self.assertEqual(len(rows),6)
        self.assertEqual(a["market_groups_quarantined_by_reason"]["MARKET_FAMILY_UNSUPPORTED"],1)

    def test_spread_sign_error_blocked_not_silently_repaired(self):
        event=e()
        event["bookmakers"][0]["markets"][1]["outcomes"][1]["point"]=-3.5
        rows,a=convert(evidence(self.root,payload=[event]))
        self.assertEqual(len(rows),4)
        self.assertEqual(a["market_groups_quarantined_by_reason"]["SPREAD_OPPOSITE_SIGN_ERROR"],1)

    def test_invalid_stale_or_future_provider_clock_blocked(self):
        event=e()
        event["bookmakers"][0]["markets"][0]["last_update"]="2026-11-15T20:01:00Z"
        rows,a=convert(evidence(self.root,payload=[event]))
        self.assertEqual(len(rows),4)
        self.assertEqual(a["market_groups_quarantined_by_reason"]["PROVIDER_TIME_LOOKAHEAD"],1)

    def test_original_manifest_rejects_duplicate_critical_keys_at_every_depth(self):
        # Before this repair, Python json.loads used the LAST duplicate key,
        # silently changing alleged capture time, upstream endpoint or digest.
        for field,replacement in (
            ("captured_utc", "2026-11-16T01:15:00Z"),
            ("read_only_endpoint", "https://invalid.example/wrong"),
            ("sport", "CBB"),
            ("original_raw_sha256", "sha256:" + "b" * 64),
        ):
            with self.subTest(field=field):
                path = evidence(self.root)
                original = path.read_text()
                assert original.endswith("}")
                corrupt = original[:-1] + ', "' + field + '": ' + json.dumps(replacement) + "}"
                path.write_text(corrupt, encoding="utf-8")
                with self.assertRaisesRegex(Blocked, "ORIGINAL_MANIFEST_DUPLICATE_OR_INVALID_JSON"):
                    load_evidence(path)
        manifest = evidence(self.root)
        original = json.loads(manifest.read_text())
        original["extra"] = {"proof": 1}
        corrupt = json.dumps(original).replace('"proof": 1', '"proof": 1, "proof": 2')
        manifest.write_text(corrupt, encoding="utf-8")
        with self.assertRaisesRegex(Blocked, "ORIGINAL_MANIFEST_DUPLICATE_OR_INVALID_JSON"):
            convert(manifest)

    def test_original_manifest_rejects_nonfinite_and_non_object_payload(self):
        for bad in ('{"captured_utc": NaN}', '{"captured_utc": Infinity}',
                    '{"clock": 1e999}', '["not a manifest"]'):
            with self.subTest(bad=bad):
                manifest = evidence(self.root)
                manifest.write_text(bad, encoding="utf-8")
                reason = ("ORIGINAL_MANIFEST_OBJECT_REQUIRED" if bad.startswith("[")
                          else "ORIGINAL_MANIFEST_DUPLICATE_OR_INVALID_JSON")
                with self.assertRaisesRegex(Blocked, reason):
                    load_evidence(manifest)

    def test_bad_manifest_does_not_create_clv_csv_or_audit(self):
        path = evidence(self.root)
        saved = path.read_text(encoding="utf-8")
        path.write_text(saved[:-1] + ', "captured_utc": "2026-11-16T01:20:00Z"}',
                        encoding="utf-8")
        out = self.root/"blocked.csv"
        with self.assertRaisesRegex(Blocked, "ORIGINAL_MANIFEST_DUPLICATE_OR_INVALID_JSON"):
            write_export(path, out)
        self.assertFalse(out.exists())
        self.assertFalse((self.root/"blocked.csv.audit.json").exists())
        self.assertTrue((self.root/"original.json").exists())

    def test_hash_tamper_refusal(self):
        p=evidence(self.root)
        (self.root/"original.json").write_bytes(b'{"tampered":true}')
        with self.assertRaisesRegex(Blocked,"HASH_MISMATCH"):
            load_evidence(p)

    def test_path_traversal_refusal(self):
        p=evidence(self.root)
        meta=json.loads(p.read_text());meta["raw_filename"]="../outside.json"
        p.write_text(json.dumps(meta))
        with self.assertRaisesRegex(Blocked,"PATH_INVALID"):
            convert(p)

    def test_private_csv_audit_write_create_only_and_hash(self):
        p=evidence(self.root);out=self.root/"take.csv"
        a=write_export(p,out)
        self.assertEqual(a["rows_generated"],6)
        self.assertEqual(a["normalized_csv_sha256"],"sha256:"+hashlib.sha256(out.read_bytes()).hexdigest())
        with out.open(newline="") as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),6)
        self.assertTrue(all(r["source"]=="THE_ODDS_API" for r in rows))
        self.assertEqual(json.loads((self.root/"take.csv.audit.json").read_text())["approved_stake_u"],0)
        with self.assertRaisesRegex(Blocked,"CREATE_ONLY"):
            write_export(p,out)

    def test_end_to_end_source_native_close_stays_paper(self):
        p=evidence(self.root)
        takes,_=convert(p,"TAKE")
        later=e()
        for market in later["bookmakers"][0]["markets"]:
            market["last_update"]="2026-11-16T01:16:30Z"
        later["bookmakers"][0]["markets"][0]["outcomes"][0]["price"]=-125
        later["bookmakers"][0]["markets"][0]["outcomes"][1]["price"]=+105
        p2=evidence(self.root,payload=[later],captured="2026-11-16T01:17:00Z")
        closes,_=convert(p2,"HISTORY")
        rows=compare([parse_quote(x,"TAKE") for x in takes],
                     [parse_quote(x,"HISTORY") for x in closes])
        self.assertEqual(len(rows),6)
        self.assertEqual(sum(r["clv_probability_points"] is not None for r in rows),6)
        self.assertTrue(all(r["official_counted"]==0 for r in rows))
        self.assertTrue(any(float(r["clv_probability_points"])>0 for r in rows))
    def test_no_events_cannot_claim_coverage(self):
        p=evidence(self.root,payload=[])
        rows,a=convert(p)
        self.assertEqual(rows,[])
        self.assertEqual(a["state"],"BLOCK_NO_VALID_TWO_SIDED_QUOTES")

    def test_duplicate_provider_market_all_copies_quarantined(self):
        event=e()
        event["bookmakers"][0]["markets"].append(
            json.loads(json.dumps(event["bookmakers"][0]["markets"][0])))
        rows,audit=convert(evidence(self.root,payload=[event]))
        self.assertEqual(len(rows),4)
        self.assertEqual(audit["market_groups_quarantined_by_reason"][
            "DUPLICATE_CANONICAL_MARKET_ALL_COPIES_QUARANTINED"],2)
        self.assertFalse(any(r["market_kind"]=="MONEYLINE" for r in rows))

    def test_conflicting_duplicate_price_all_copies_quarantined(self):
        event=e()
        changed=json.loads(json.dumps(event["bookmakers"][0]["markets"][0]))
        changed["outcomes"][0]["price"]=-155
        event["bookmakers"][0]["markets"].append(changed)
        rows,audit=convert(evidence(self.root,payload=[event]))
        self.assertEqual(len(rows),4)
        self.assertFalse(any(r["market_kind"]=="MONEYLINE" for r in rows))
        self.assertEqual(audit["market_groups_quarantined_by_reason"][
            "DUPLICATE_CANONICAL_MARKET_ALL_COPIES_QUARANTINED"],2)

    def test_different_snapshot_times_preserved_without_false_duplicate(self):
        event=e()
        changed=json.loads(json.dumps(event["bookmakers"][0]["markets"][0]))
        changed["last_update"]="2026-11-15T19:59:30Z"
        event["bookmakers"][0]["markets"].append(changed)
        rows,audit=convert(evidence(self.root,payload=[event]))
        self.assertEqual(len(rows),8)
        self.assertNotIn("DUPLICATE_CANONICAL_MARKET_ALL_COPIES_QUARANTINED",
                         audit["market_groups_quarantined_by_reason"])

    def test_failed_audit_creation_rolls_back_own_normalized_csv(self):
        from sportsedge.odds import the_odds_api_clv_export as module
        manifest=evidence(self.root)
        out=self.root/"paper.csv"
        original_write=module._write_private
        def failing(path,content):
            if str(path).endswith(".audit.json"):
                raise OSError("injected audit-sidecar failure")
            return original_write(path,content)
        with patch.object(module,"_write_private",side_effect=failing):
            with self.assertRaisesRegex(OSError,"injected audit-sidecar failure"):
                write_export(manifest,out)
        self.assertFalse(out.exists())
        self.assertFalse((self.root/"paper.csv.audit.json").exists())
        self.assertTrue((self.root/"original.json").exists())

    def test_fsync_failure_rolls_back_own_partial_csv(self):
        from sportsedge.odds import the_odds_api_clv_export as module
        manifest=evidence(self.root)
        out=self.root/"fsync.csv"
        with patch.object(module.os,"fsync",side_effect=OSError("injected fsync failure")):
            with self.assertRaisesRegex(OSError,"injected fsync failure"):
                write_export(manifest,out)
        self.assertFalse(out.exists())
        self.assertFalse((self.root/"fsync.csv.audit.json").exists())

    def test_symlink_target_output_refused_without_creating_target(self):
        manifest=evidence(self.root)
        target=self.root/"absent-target.csv"
        link=self.root/"out.csv"
        link.symlink_to(target)
        with self.assertRaisesRegex(Blocked,"OUTPUT_SYMLINK_REFUSED"):
            write_export(manifest,link)
        self.assertFalse(target.exists())
        self.assertTrue(link.is_symlink())

    def test_private_original_manifest_in_public_checkout_refused(self):
        from sportsedge.odds import the_odds_api_clv_export as module
        checkout=self.root/"fake-public-checkout"
        checkout.mkdir()
        manifest=evidence(checkout)
        with patch.object(module,"REPO_ROOT",checkout):
            with self.assertRaisesRegex(Blocked,"ODDS_SOURCE_OR_OUTPUT_IN_PUBLIC_REPO"):
                convert(manifest)

    def test_lexical_public_symlink_to_private_source_refused(self):
        from sportsedge.odds import the_odds_api_clv_export as module
        checkout=self.root/"fake-public-checkout"
        checkout.mkdir()
        private=self.root/"restricted"
        private.mkdir()
        manifest=evidence(private)
        link=checkout/"private-link"
        link.symlink_to(private,target_is_directory=True)
        with patch.object(module,"REPO_ROOT",checkout):
            with self.assertRaisesRegex(Blocked,"ODDS_SOURCE_OR_OUTPUT_IN_PUBLIC_REPO"):
                convert(link/manifest.name)

    def test_lexical_public_symlink_to_private_output_refused(self):
        from sportsedge.odds import the_odds_api_clv_export as module
        checkout=self.root/"fake-public-checkout"
        checkout.mkdir()
        private=self.root/"restricted"
        private.mkdir()
        manifest=evidence(private)
        link=checkout/"private-link"
        link.symlink_to(private,target_is_directory=True)
        with patch.object(module,"REPO_ROOT",checkout):
            with self.assertRaisesRegex(Blocked,"ODDS_SOURCE_OR_OUTPUT_IN_PUBLIC_REPO"):
                write_export(manifest,link/"out.csv")
        self.assertFalse((private/"out.csv").exists())

    def test_existing_audit_file_is_never_overwritten(self):
        manifest=evidence(self.root)
        out=self.root/"no-overwrite.csv"
        audit=self.root/"no-overwrite.csv.audit.json"
        audit.write_text("prior evidence",encoding="utf-8")
        with self.assertRaisesRegex(Blocked,"AUDIT_OUTPUT_ALREADY_EXISTS"):
            write_export(manifest,out)
        self.assertFalse(out.exists())
        self.assertEqual(audit.read_text(),"prior evidence")

if __name__ == "__main__":
    unittest.main()
