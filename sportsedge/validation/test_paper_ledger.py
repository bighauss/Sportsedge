"""Offline tests for exact market final grading and no-vig CLV; all fabricated."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from sportsedge.validation.paper_ledger import (
    Blocked, REPO_ROOT, grade_bundle, append_ledger, verify_chain)


class PaperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.event="TEST-2026-11-15-PIT-CIN"
        self.base_market=dict(sport="NFL",event_id=self.event,
                              kind="TOTAL",period="FG",selection="OVER",
                              line="42.5",settlement="INCLUDES_OT")
        opposite={**self.base_market,"selection":"UNDER"}
        self.taken={
            "book":"DraftKings","quote_id":"TAKE-001",
            "provider_event_id":"DK-EVT-100","provider_market_id":"DK-TOTAL-88",
            "market":self.base_market,"opposite_market":opposite,
            "price_american":-110,"opposite_price_american":-110}
        self.close={**self.taken,"quote_id":"CLOSE-002",
                    "price_american":-140,"opposite_price_american":120}
        self.final={
            "event_id":self.event,"sport":"NFL","final_status":"FINAL",
            "home_id":"CIN","away_id":"PIT",
            "roster_ids":[],
            "periods":{"Q1":[7,3],"Q2":[10,7],"Q3":[7,3],"Q4":[0,10]},
            "player_stats":{},"events":[],"events_complete":False}
        self.bundle={"pick_id":"TEST-SELECT-001","event_id":self.event,
                     "kickoff_utc":"2026-11-16T01:20:00Z"}
        self.save()

    def write(self,name,data,when):
        p=self.root/name
        raw=json.dumps(data,sort_keys=True).encode("utf-8")
        p.write_bytes(raw)
        p.chmod(0o600)
        return {"path":name,"sha256":hashlib.sha256(raw).hexdigest(),
                "captured_at_utc":when}

    def save(self):
        self.bundle["taken"]=self.write("take.json",self.taken,"2026-11-15T23:45:00Z")
        self.bundle["close"]=self.write("close.json",self.close,"2026-11-16T01:10:00Z")
        self.bundle["final"]=self.write("final.json",self.final,"2026-11-16T05:00:00Z")
        self.path=self.root/"bundle.json"
        self.path.write_text(json.dumps(self.bundle))
        self.path.chmod(0o600)

    def test_grade_novig_clv_and_private_research(self):
        r=grade_bundle(self.path)
        self.assertEqual(r["grade"],"W")
        self.assertGreater(r["clv_probability_pp"],0)
        self.assertEqual(r["status"],"PAPER_GRADED_UNAUTHENTICATED")
        self.assertFalse(r["source_authentication_independent"])
        self.assertEqual(r["approved_stake_u"],0)
        self.assertEqual(r["official_counted"],0)
        self.assertEqual(r["roi"],"UNAVAILABLE_NO_AUTHORITATIVE_BET_LEDGER")

    def test_no_close_is_research_grade_without_invented_clv(self):
        self.save()
        del self.bundle["close"]
        self.path.write_text(json.dumps(self.bundle))
        r=grade_bundle(self.path)
        self.assertEqual(r["grade"],"W")
        self.assertIsNone(r["clv_probability_pp"])
        self.assertEqual(r["close_status"],"NO_COMPARABLE_CLOSE")

    def test_wrong_line_or_period_not_comparable(self):
        self.close["market"]={**self.base_market,"line":"43.5"}
        self.close["opposite_market"]={**self.base_market,"line":"43.5",
                                       "selection":"UNDER"}
        self.save()
        with self.assertRaises(Blocked):
            grade_bundle(self.path)

    def test_same_quote_or_reverse_clock_blocked(self):
        self.close["quote_id"]=self.taken["quote_id"]
        self.save()
        with self.assertRaises(Blocked):grade_bundle(self.path)
        self.close["quote_id"]="DIFFERENT"
        self.save()
        self.bundle["close"]["captured_at_utc"]="2026-11-15T22:00:00Z"
        self.path.write_text(json.dumps(self.bundle))
        with self.assertRaises(Blocked):grade_bundle(self.path)

    def test_malformed_opposing_market_fails(self):
        self.taken["opposite_market"]["selection"]="OVER"
        self.save()
        with self.assertRaises(Blocked):
            grade_bundle(self.path)

    def test_nonfinal_game_and_source_tamper_fail(self):
        self.final["final_status"]="IN_PROGRESS"
        self.save()
        with self.assertRaises(Blocked):grade_bundle(self.path)
        self.final["final_status"]="FINAL"
        self.save()
        (self.root/"final.json").write_text("{}")
        with self.assertRaises(Blocked):grade_bundle(self.path)

    def test_postgame_result_before_kickoff_fails(self):
        self.save()
        self.bundle["final"]["captured_at_utc"]="2026-11-15T23:59:00Z"
        self.path.write_text(json.dumps(self.bundle))
        with self.assertRaises(Blocked):grade_bundle(self.path)

    def test_sqlite_atomic_dedupe_and_conflict(self):
        x=grade_bundle(self.path)
        db=self.root/"private.sqlite"
        self.assertEqual(append_ledger(db,x)["status"],"APPENDED_PAPER")
        self.assertEqual(append_ledger(db,x)["status"],"ALREADY_RECORDED")
        self.assertEqual(verify_chain(db),1)
        y={**x,"grade":"L"}
        with self.assertRaises(Blocked):append_ledger(db,y)
        self.assertEqual(verify_chain(db),1)

    def test_same_market_identity_new_pick_id_is_not_double_counted(self):
        first=grade_bundle(self.path)
        db=self.root/"private.sqlite"
        append_ledger(db,first)
        second={**first,"pick_id":"DIFFERENT-PICK-ID"}
        with self.assertRaisesRegex(Blocked,"Canonical selection already recorded"):
            append_ledger(db,second)
        self.assertEqual(verify_chain(db),1)

    def test_append_refuses_existing_corrupted_chain(self):
        first=grade_bundle(self.path)
        db=self.root/"private.sqlite"
        append_ledger(db,first)
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE ledger SET payload='{}' WHERE pick_id=?",(first["pick_id"],))
        second={**first,"pick_id":"SECOND-PICK-ID",
                "selection_identity":list(first["selection_identity"])+["other-market"]}
        with self.assertRaisesRegex(Blocked,"chain damaged"):
            append_ledger(db,second)
        with sqlite3.connect(db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0],1)

    def test_tampered_ledger_chain_caught(self):
        x=grade_bundle(self.path)
        db=self.root/"private.sqlite"
        append_ledger(db,x)
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE ledger SET payload='{}' WHERE pick_id=?",(x["pick_id"],))
        with self.assertRaises(Blocked):verify_chain(db)

    def test_placeholder_provider_ids_blocked(self):
        for key in ("quote_id","provider_event_id","provider_market_id"):
            self.taken[key]="NOT_CAPTURED"
            self.save()
            with self.assertRaisesRegex(Blocked,"provider original"):
                grade_bundle(self.path)
            self.taken[key]={
                "quote_id":"TAKE-001","provider_event_id":"DK-EVT-100",
                "provider_market_id":"DK-TOTAL-88"}[key]

    def test_close_outside_prestart_ten_minute_window(self):
        self.save()
        self.bundle["close"]["captured_at_utc"]="2026-11-16T00:30:00Z"
        self.path.write_text(json.dumps(self.bundle))
        with self.assertRaisesRegex(Blocked,"10-minute"):
            grade_bundle(self.path)

    def test_other_book_and_invalid_american_price_block(self):
        self.taken["book"]="OtherBook"
        self.save()
        with self.assertRaises(Blocked):grade_bundle(self.path)
        self.taken["book"]="DraftKings"
        self.taken["price_american"]=-99
        self.save()
        with self.assertRaises(Blocked):grade_bundle(self.path)


    def test_sqlite_is_created_owner_only_and_verify_never_creates_missing(self):
        x=grade_bundle(self.path)
        db=self.root/"owner_only.sqlite"
        with self.assertRaises(Blocked):
            verify_chain(db)
        self.assertFalse(db.exists())
        self.assertEqual(append_ledger(db,x)["status"],"APPENDED_PAPER")
        self.assertEqual(db.stat().st_mode & 0o777,0o600)
        self.assertEqual(verify_chain(db),1)

    def test_insecure_existing_database_refused(self):
        x=grade_bundle(self.path)
        db=self.root/"public_readable.sqlite"
        append_ledger(db,x)
        db.chmod(0o644)
        with self.assertRaisesRegex(Blocked,"owner-only"):
            append_ledger(db,x)
        with self.assertRaisesRegex(Blocked,"0600"):
            verify_chain(db)

    def test_public_repo_destinations_refused_without_creating_files(self):
        x=grade_bundle(self.path)
        db=REPO_ROOT/"NEVER_WRITE_PRIVATE_LEDGER.sqlite"
        with self.assertRaisesRegex(Blocked,"Public repository"):
            append_ledger(db,x)
        with self.assertRaisesRegex(Blocked,"Public repository"):
            verify_chain(db)
        with self.assertRaisesRegex(Blocked,"Public repository"):
            grade_bundle(REPO_ROOT/"NEVER_READ_PUBLIC_BUNDLE.json")
        self.assertFalse(db.exists())

    def test_public_readable_bundle_or_source_refused(self):
        self.path.chmod(0o644)
        with self.assertRaisesRegex(Blocked,"0600"):
            grade_bundle(self.path)
        self.path.chmod(0o600)
        (self.root/"take.json").chmod(0o644)
        with self.assertRaisesRegex(Blocked,"0600"):
            grade_bundle(self.path)

    def test_symlink_bundle_source_and_database_refused(self):
        alias=self.root/"bundle_alias.json"
        alias.symlink_to(self.path)
        with self.assertRaisesRegex(Blocked,"Symlinked"):
            grade_bundle(alias)
        source_alias=self.root/"take_alias.json"
        source_alias.symlink_to(self.root/"take.json")
        self.bundle["taken"]["path"]="take_alias.json"
        self.path.write_text(json.dumps(self.bundle))
        with self.assertRaisesRegex(Blocked,"Symlinked"):
            grade_bundle(self.path)
        self.bundle["taken"]["path"]="take.json"
        self.path.write_text(json.dumps(self.bundle))
        db=self.root/"ledger_alias.sqlite"
        db.symlink_to(self.path)
        with self.assertRaisesRegex(Blocked,"Symlinked"):
            append_ledger(db,grade_bundle(self.path))

    def test_duplicate_and_nonfinite_original_json_rejected_even_if_hash_matches(self):
        raw=b'{"book":"DraftKings","book":"DraftKings"}'
        (self.root/"take.json").write_bytes(raw)
        self.bundle["taken"]["sha256"]=hashlib.sha256(raw).hexdigest()
        self.path.write_text(json.dumps(self.bundle))
        with self.assertRaisesRegex(Blocked,"Duplicate original JSON field"):
            grade_bundle(self.path)
        raw=b'{"price_american":NaN}'
        (self.root/"take.json").write_bytes(raw)
        self.bundle["taken"]["sha256"]=hashlib.sha256(raw).hexdigest()
        self.path.write_text(json.dumps(self.bundle))
        with self.assertRaisesRegex(Blocked,"Nonfinite original JSON number"):
            grade_bundle(self.path)

    def test_source_parent_escape_and_absolute_paths_refused(self):
        for path in ("../secret.json", "/tmp/secret.json", "./take.json"):
            with self.subTest(path=path):
                self.bundle["taken"]["path"]=path
                self.path.write_text(json.dumps(self.bundle))
                with self.assertRaisesRegex(Blocked,"relative"):
                    grade_bundle(self.path)

    def test_private_directory_permission_required(self):
        self.root.chmod(0o755)
        self.addCleanup(lambda: self.root.chmod(0o700) if self.root.exists() else None)
        with self.assertRaisesRegex(Blocked,"0700"):
            grade_bundle(self.path)



if __name__=="__main__":
    unittest.main()
