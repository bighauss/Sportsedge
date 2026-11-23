from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.validation import paper_grade_batch as batch, paper_ledger as ledger


DAY = "2026-11-21T"
NOW = datetime(2026, 11, 22, tzinfo=timezone.utc)


class BatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.manifest = self.root / "batch.json"
        self.db = self.root / "results.sqlite"
        self.market = dict(sport="NFL", event_id="event", kind="TOTAL", period="1H",
                           selection="OVER", line="20", settlement="REGULATION")
        self.pick = dict(pick_id="pick-1", home_id="H", away_id="A", market=self.market,
                         decision_at_utc=DAY+"17:00:00Z", kickoff_utc=DAY+"18:00:00Z")
        self.final = dict(sport="NFL", event_id="event", final_status="FINAL", home_id="H", away_id="A",
                          final_available_utc=DAY+"21:00:00Z",
                          periods={"Q1": [7, 3], "Q2": [7, 3]}, roster_ids=[])
        self.price = dict(book="DraftKings", quote_id="Q1", provider_event_id="P1", provider_market_id="M1",
                          market=self.market, opposite_market={**self.market, "selection": "UNDER"},
                          price_american=-110, opposite_price_american=-110)

    def source(self, name, doc, hour):
        path = self.root / name
        raw = json.dumps(doc).encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        return dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), captured_at_utc=DAY+hour)

    def entry(self, *, price=False, final=True, index=""):
        row = dict(kickoff_utc=self.pick["kickoff_utc"],
                   pick=self.source(f"pick{index}.json", self.pick, "17:00:00Z"))
        if price:
            row["taken"] = self.source(f"taken{index}.json", self.price, "16:59:00Z")
        if final:
            row["final"] = self.source(f"final{index}.json", self.final, "21:01:00Z")
        return row

    def run_rows(self, *rows, append=False, now=NOW):
        self.source(self.manifest.name, {"schema": batch.SCHEMA, "entries": list(rows)}, "23:00:00Z")
        return batch.run_batch(self.manifest, database=self.db if append else None, now=now)

    def test_no_saved_price_can_grade_push_and_idempotently_append(self):
        row = self.entry()
        self.assertEqual(self.run_rows(row)["ledger"], {"DRY_RUN": 1})
        self.assertFalse(self.db.exists())
        report = self.run_rows(row, append=True)
        self.assertEqual(report["results"], {"PAPER_RESULT_GRADED": 1})
        self.assertEqual(report["prices"], {"NO_SAVED_PRICE": 1})
        self.assertEqual(report["ledger"], {"APPENDED_PAPER": 1})
        row["taken"] = self.source("price.json", self.price, "16:59:00Z")
        report = self.run_rows(row, append=True)
        self.assertEqual(report["prices"], {"EXACT_PRICE_EVIDENCE_UNAUTHENTICATED": 1})
        self.assertEqual(report["ledger"], {"ALREADY_RECORDED": 1})
        self.assertEqual(ledger.verify_chain(self.db), 1)
        with ledger.sqlite3.connect(self.db) as conn:
            result = json.loads(conn.execute("SELECT payload FROM ledger").fetchone()[0])
        self.assertEqual(result["grade"], "P")
        self.assertNotIn("taken_novig_p", result)
        self.assertEqual(result["approved_stake_u"], 0)

    def test_ineligible_price_does_not_block_result(self):
        row = self.entry()
        row["taken"] = self.source("after.json", self.price, "17:01:00Z")
        report = self.run_rows(row)
        self.assertEqual(report["prices"], {"PRICE_EVIDENCE_BLOCKED": 1})
        self.assertEqual(report["results"], {"PAPER_RESULT_GRADED": 1})

    def test_pending_is_distinct_from_invalid_final(self):
        self.assertEqual(self.run_rows(self.entry(final=False))["results"], {"PENDING_FINAL": 1})
        self.final["final_status"] = "IN_PROGRESS"
        self.assertEqual(self.run_rows(self.entry())["results"], {"PENDING_FINAL": 1})
        self.final.update(final_status="FINAL", home_id="A", away_id="H")
        self.assertEqual(self.run_rows(self.entry())["results"], {"FINAL_OR_SETTLEMENT_BLOCKED": 1})

    def test_invalid_finals_future_missing_split_bad_flags_and_player_ids(self):
        for changes in ({"final_available_utc": DAY+"21:02:00Z"}, {"periods": {"Q1": [7, 3]}},
                        {"events_complete": "true"}, {"player_stats": {"unrostered": {"RUSH_YDS": 10}}}):
            with self.subTest(changes=changes):
                row = self.entry()
                row["final"] = self.source("badfinal.json", {**self.final, **changes}, "21:01:00Z")
                self.assertEqual(self.run_rows(row)["results"], {"FINAL_OR_SETTLEMENT_BLOCKED": 1})

    def test_unseen_final_and_tampered_pick_are_blocked(self):
        row = self.entry()
        self.assertEqual(self.run_rows(row, now=datetime.fromisoformat(DAY+"20:59:00+00:00"))["results"],
                         {"FINAL_OR_SETTLEMENT_BLOCKED": 1})
        (self.root / row["pick"]["path"]).write_text("{}")
        self.assertEqual(self.run_rows(row)["picks"], {"PICK_EVIDENCE_BLOCKED": 1})

    def test_duplicate_id_and_canonical_market_quarantined_before_any_writes(self):
        a = self.entry(index="a")
        self.pick["pick_id"] = "different"
        b = self.entry(index="b")
        report = self.run_rows(a, b, append=True)
        self.assertEqual(report["picks"], {"DUPLICATE_PICK_OR_MARKET_BLOCKED": 2})
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
