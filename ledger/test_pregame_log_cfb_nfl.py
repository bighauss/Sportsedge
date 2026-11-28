"""CFB + NFL adapters for the shared pregame log: full denominator, honest labels,
pregame-only, card unchanged, grade + export end to end. Synthetic fixtures only."""
import copy, csv, datetime as dt, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "models" / "cfb", ROOT / "models" / "nfl"):
    sys.path.insert(0, str(p))
from ledger import pregame_log as L
import cfb_run_it as CR
import runit_ledger as NL
from test_cfb_run_it import INTAKE as CFB_INTAKE, fixture as cfb_fixture
from test_runit_ledger import GAME as NFL_GAME, PROPS as NFL_PROPS, PROJ as NFL_PROJ, ABBR as NFL_ABBR

CAP = "2026-11-21T14:30:00Z"
NOW = "2026-11-21T15:00:00+00:00"


def cfb_run(intake):
    cap = cfb_fixture()
    return CR.run(intake, cap, dt.datetime.fromisoformat(NOW), lambda *_: cap["_weather"])


def cfb_rows(intake=None):
    intake = intake or dict(CFB_INTAKE, captured_utc=CAP)
    card, projs, wh, ctx = cfb_run(intake)
    rows, unl = L.rows_from_cfb_run(card, projs, wh, ctx, intake, dt.datetime.fromisoformat(NOW),
                                    "a" * 64, commit_sha="b" * 40)
    return card, projs, wh, ctx, rows, unl


NFL_META = {"kickoff_utc": {"AAA@BBB": "2026-11-22T18:00:00Z"}, "quote_captured_utc": "2026-11-22T15:00:00Z",
            "prediction_utc": "2026-11-22T15:05:00Z", "model_version": "nfl-run-it-v3",
            "model_code_sha256": "c" * 64, "config": {"SD_MARGIN": 13.5}, "provenance": {"source": "fixture"}}


class CFBAdapter(unittest.TestCase):
    def test_full_denominator(self):
        card, projs, wh, ctx, rows, unl = cfb_rows()
        self.assertEqual(len(rows) + len(unl), len(ctx["priced_rows_all"]) + len(wh))
        self.assertTrue(rows)
        for r in rows:
            L.validate(r)

    def test_every_card_row_is_selected_or_flagged(self):
        card, *_, rows, _ = cfb_rows()
        sel = [r for r in rows if r["selection_state"] == "SELECTED"]
        flagged = [r for r in rows if r["rejection_reason"] and "card_state=SELECTED" in r["rejection_reason"]]
        self.assertEqual(len(sel) + len(flagged), len(card))

    def test_props_labelled_market_anchored_and_withheld_one_sided(self):
        *_, rows, _ = cfb_rows()
        props = [r for r in rows if r["source_provenance"].get("projection_mode") == "MARKET_ANCHORED_RESEARCH"]
        self.assertTrue(props)
        for r in props:
            self.assertTrue(r["distribution_id"].startswith("MARKET_ANCHORED"))
            self.assertEqual(r["selection_state"], "WITHHELD")
            self.assertIn("ONE_SIDED_QUOTE", r["rejection_reason"])
        self.assertFalse(any("INDEPENDENT" in r["distribution_id"] for r in rows))

    def test_game_rows_two_sided_and_settle_vocabulary(self):
        *_, rows, _ = cfb_rows()
        priced = [r for r in rows if r["selection_state"] != "WITHHELD"]
        self.assertTrue(priced)
        for r in priced:
            self.assertIn(r["market"], ("moneyline", "spread", "total", "team_total"))
            self.assertIn(r["selection"], ("home", "away", "over", "under"))
            self.assertIsInstance(r["opp_price"], int)

    def test_missing_capture_time_withholds_priced_rows(self):
        *_, rows, _ = cfb_rows(dict(CFB_INTAKE))   # fixture intake has no captured_utc
        self.assertFalse([r for r in rows if r["selection_state"] != "WITHHELD"])
        self.assertTrue(any("QUOTE_CAPTURE_TIME_MISSING" in (r["rejection_reason"] or "") for r in rows))

    def test_rejected_at_or_after_kickoff(self):
        *_, rows, _ = cfb_rows()
        r = copy.deepcopy(rows[0]); r["prediction_utc"] = r["game_start_utc"]
        with self.assertRaisesRegex(L.LogError, "PREDICTION_NOT_PREGAME"):
            L.validate(r)
        r = copy.deepcopy([x for x in rows if x["quote_captured_utc"]][0]); r["quote_captured_utc"] = r["game_start_utc"]
        with self.assertRaisesRegex(L.LogError, "QUOTE_NOT_PREGAME"):
            L.validate(r)

    def test_grade_and_export_end_to_end(self):
        *_, projs, wh, ctx, rows, _ = cfb_rows()
        with tempfile.TemporaryDirectory() as d:
            log, res, out = (os.path.join(d, n) for n in ("log.jsonl", "res.jsonl", "h.csv"))
            L.append(log, rows)
            gid = rows[0]["event_id"]
            ev = {"event_id": gid, "sport": "CFB", "status": "final", "home_score": 27, "away_score": 20}
            c = L.grade_log(log, res, {gid: ev}, settled_utc="2026-11-22T06:00:00Z")
            self.assertGreater(c["graded"], 0)
            L.export_harness(log, res, out)
            got = list(csv.DictReader(open(out)))
            self.assertEqual(len(got), c["graded"])
            self.assertTrue(all(g["outcome"] in ("W", "L", "P", "V") for g in got))

    def test_cli_card_byte_identical_with_and_without_flag(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "i.json"); json.dump(dict(CFB_INTAKE, captured_utc=CAP), open(f, "w"))
            fx = os.path.join(d, "fx.json"); json.dump(cfb_fixture(), open(fx, "w"))
            outs = []
            for tag, extra in (("a", []), ("b", ["--prediction-log", os.path.join(d, "log.jsonl")])):
                o = os.path.join(d, tag)
                r = subprocess.run([sys.executable, str(ROOT / "models" / "cfb" / "cfb_run_it.py"), f, "--season", "2026",
                                    "--out", o, "--fixture", fx, "--now", NOW, *extra], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                outs.append({n: open(os.path.join(o, n), "rb").read() for n in ("cfb_run_it.json", "cfb_card.md")})
            self.assertEqual(outs[0], outs[1])
            self.assertIn("PREDICTION_LOG appended", r.stdout)
            self.assertTrue(L.read(os.path.join(d, "log.jsonl")))


class NFLAdapter(unittest.TestCase):
    def setUp(self):
        self.lrows, self.summary = NL.build_ledger([NFL_GAME], NFL_PROPS, NFL_PROJ, NFL_ABBR)
        self.rows, self.unl = L.rows_from_nfl_ledger(self.lrows, NFL_META, commit_sha="d" * 40)

    def test_full_denominator_and_valid(self):
        self.assertEqual(len(self.rows) + len(self.unl), len(self.lrows))
        for r in self.rows:
            L.validate(r)

    def test_states_follow_ledger(self):
        on_card = sum(r["status"] == "on_card" for r in self.lrows)
        sel = sum(r["selection_state"] == "SELECTED" for r in self.rows)
        flagged = sum("card_state=SELECTED" in (r["rejection_reason"] or "") for r in self.rows)
        self.assertEqual(sel + flagged, on_card)
        rej_in = sum(r["status"] == "rejected_input" for r in self.lrows if r["game"] in NFL_META["kickoff_utc"])
        self.assertGreaterEqual(sum(r["selection_state"] == "WITHHELD" for r in self.rows), rej_in)

    def test_game_markets_two_sided_settle_vocab_with_lines(self):
        priced = [r for r in self.rows if r["selection_state"] != "WITHHELD"]
        self.assertEqual(len(priced), 12)
        for r in priced:
            self.assertIn(r["market"], ("spread", "total", "moneyline"))
            self.assertIn(r["selection"], ("home", "away", "over", "under"))
            self.assertIn(r["period"], ("FG", "H1"))
            if r["market"] != "moneyline":
                self.assertIsNotNone(r["line"])
        sp = {r["selection"]: r["line"] for r in priced if r["market"] == "spread" and r["period"] == "FG"}
        self.assertEqual(sp, {"home": -3.5, "away": 3.5})

    def test_props_market_anchored_withheld(self):
        props = [r for r in self.rows if r["source_provenance"]["projection_mode"] == "MARKET_ANCHORED_RESEARCH"]
        self.assertTrue(props)
        self.assertTrue(all(r["selection_state"] == "WITHHELD" for r in props))

    def test_missing_kickoff_is_counted_not_dropped(self):
        rows, unl = L.rows_from_nfl_ledger(self.lrows, dict(NFL_META, kickoff_utc={}))
        self.assertEqual(rows, []); self.assertEqual(len(unl), len(self.lrows))

    def test_prediction_at_kickoff_rejected(self):
        rows, _ = L.rows_from_nfl_ledger(self.lrows, dict(NFL_META, prediction_utc="2026-11-22T18:00:00Z"))
        with self.assertRaisesRegex(L.LogError, "PREDICTION_NOT_PREGAME"):
            L.validate(rows[0])

    def test_grade_and_export_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            log, res, out = (os.path.join(d, n) for n in ("log.jsonl", "res.jsonl", "h.csv"))
            L.append(log, self.rows)
            ev = {"event_id": "AAA@BBB", "sport": "NFL", "status": "final", "home_score": 24, "away_score": 21,
                  "home_periods": [7, 7, 3, 7], "away_periods": [7, 3, 7, 4]}
            c = L.grade_log(log, res, {"AAA@BBB": ev}, settled_utc="2026-11-23T06:00:00Z")
            self.assertEqual((c["graded"], c["ungraded"]), (12, 0))
            L.export_harness(log, res, out)
            got = list(csv.DictReader(open(out)))
            self.assertEqual(len(got), 12)
            out_ = {(g["market"], g["selection"]): g["outcome"] for g in got}
            # 24-21 final, 1H 14-10: home -3.5 loses, away +3.5 wins, total 45 > 44.5, home ML wins
            self.assertEqual(out_[("NFL:spread:FG", "home")], "L")
            self.assertEqual(out_[("NFL:spread:FG", "away")], "W")
            self.assertEqual(out_[("NFL:total:FG", "over")], "W")
            self.assertEqual(out_[("NFL:moneyline:FG", "home")], "W")
            self.assertEqual(out_[("NFL:spread:H1", "home")], "W")
            self.assertTrue(all(g["opp_price"] for g in got))


if __name__ == "__main__":
    unittest.main()
