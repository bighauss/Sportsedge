"""Pregame prediction log v2: schema, chain integrity, pregame-only, duplicates,
full denominator, separate results via settle(), harness export, CBB wiring."""
import csv, json, os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "models" / "cbb"))
from ledger import pregame_log as L

ROW = {"sport": "CBB", "event_id": "9001", "team": None, "player_id": None, "player_name": None,
       "market": "spread", "period": "FG", "selection": "home",
       "quote_captured_utc": "2026-11-21T14:30:00Z", "prediction_utc": "2026-11-21T14:00:00Z",
       "game_start_utc": "2026-11-21T23:00:00Z", "book": "DraftKings", "line": -3.5,
       "price": -110, "opp_price": -110, "novig_p": 0.5, "projection": -5.0,
       "distribution_id": "normal(12.5)", "win_p": 0.55, "push_p": 0.0, "loss_p": 0.45,
       "raw_ev": 0.05, "adj_ev": None, "adj_ev_method": "NOT_COMPUTED",
       "model_version": "v", "model_commit_sha": "c" * 40, "model_code_sha256": "a" * 64,
       "config_sha256": "b" * 64, "source_provenance": {"board_sha256": "d" * 64},
       "selection_state": "SELECTED", "rejection_reason": None}
AWAY = dict(ROW, selection="away", line=3.5, win_p=0.45, loss_p=0.55, raw_ev=-0.14,
            selection_state="REJECTED", rejection_reason="NONPOSITIVE_RAW_EV", novig_p=0.5)
WITHHELD = dict(ROW, market="total", selection="over", line=None, price=None, opp_price=None, novig_p=None,
                win_p=None, push_p=None, loss_p=None, raw_ev=None, quote_captured_utc=None,
                selection_state="WITHHELD", rejection_reason="MISSING_QUOTE")
FINAL = {"event_id": "9001", "sport": "CBB", "status": "final", "home_score": 70, "away_score": 64}


class Schema(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.p = os.path.join(self.d, "log.jsonl")

    def test_roundtrip_keeps_selected_rejected_and_withheld(self):
        L.append(self.p, [ROW, AWAY, WITHHELD])
        rows = L.read(self.p)
        self.assertEqual([r["selection_state"] for r in rows], ["SELECTED", "REJECTED", "WITHHELD"])

    def test_required_fields_exact(self):
        with self.assertRaisesRegex(L.LogError, "FIELDS_MISMATCH"):
            L.append(self.p, [dict(ROW, extra=1)])
        r = dict(ROW); del r["config_sha256"]
        with self.assertRaisesRegex(L.LogError, "FIELDS_MISMATCH"):
            L.append(self.p, [r])

    def test_not_pregame_rejected(self):
        for kw, why in ((dict(quote_captured_utc="2026-11-21T23:00:00Z"), "QUOTE_NOT_PREGAME"),
                        (dict(prediction_utc="2026-11-21T23:00:01Z"), "PREDICTION_NOT_PREGAME")):
            with self.subTest(**kw), self.assertRaisesRegex(L.LogError, why):
                L.append(self.p, [dict(ROW, **kw)])
        self.assertEqual(L.read(self.p), [])

    def test_state_and_reason_consistency(self):
        for kw, why in ((dict(rejection_reason="X"), "SELECTED_WITH_REJECTION_REASON"),
                        (dict(selection_state="REJECTED"), "BAD_TEXT:rejection_reason"),
                        (dict(selection_state="MAYBE"), "BAD_SELECTION_STATE")):
            with self.subTest(**kw), self.assertRaisesRegex(L.LogError, why):
                L.append(self.p, [dict(ROW, **kw)])

    def test_malformed_values_rejected(self):
        for kw in (dict(win_p=1.2), dict(win_p=float("nan")), dict(push_p=True), dict(loss_p=0.5),
                   dict(price=-110.5), dict(opp_price=50), dict(line=float("inf")), dict(game_start_utc="2026-11-21"),
                   dict(model_commit_sha=""), dict(source_provenance={}), dict(adj_ev_method="GUESS"),
                   dict(quote_captured_utc=None), dict(selection=" ")):
            with self.subTest(**{k: repr(v) for k, v in kw.items()}), self.assertRaises(L.LogError):
                L.append(self.p, [dict(ROW, **kw)])

    def test_duplicates_rejected_all_or_nothing(self):
        with self.assertRaisesRegex(L.LogError, "DUPLICATE_SELECTION"):
            L.append(self.p, [ROW, dict(ROW, price=-120)])
        self.assertEqual(L.read(self.p), [])
        L.append(self.p, [ROW])
        with self.assertRaisesRegex(L.LogError, "DUPLICATE_SELECTION"):
            L.append(self.p, [AWAY, ROW])
        self.assertEqual(len(L.read(self.p)), 1)

    def test_selection_id_distinguishes_players_and_teams(self):
        a = dict(ROW, market="rec_yds", player_id="P1", selection="over", line=55.5)
        self.assertNotEqual(L.selection_id(a), L.selection_id(dict(a, player_id="P2")))
        self.assertNotEqual(L.selection_id(dict(ROW, market="team_total", team="home")),
                            L.selection_id(dict(ROW, market="team_total", team="away")))

    def test_tampering_and_deletion_detected(self):
        L.append(self.p, [ROW, AWAY])
        a, b = open(self.p).read().splitlines()
        for bad in (a + "\n" + b.replace('"win_p":0.45', '"win_p":0.65') + "\n",
                    a + "\n" + b.replace('"seq":2', '"seq":3') + "\n", b + "\n"):
            with self.subTest():
                open(self.p, "w").write(bad)
                with self.assertRaises(L.LogError):
                    L.read(self.p)


class Results(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.p = os.path.join(self.d, "log.jsonl")
        self.res = os.path.join(self.d, "results.jsonl")
        L.append(self.p, [ROW, AWAY, WITHHELD])

    def test_grading_writes_separate_results_and_never_mutates_pregame(self):
        before = open(self.p, "rb").read()
        c = L.grade_log(self.p, self.res, {"9001": FINAL}, settled_utc="2026-11-22T06:00:00Z")
        self.assertEqual(open(self.p, "rb").read(), before)
        self.assertEqual(c["graded"], 2); self.assertEqual(c["withheld_skipped"], 1)
        out = {r["selection_id"]: r for r in L.read_results(self.res)}
        self.assertEqual(out[L.selection_id(ROW)]["outcome"], "W")      # home -3.5, won by 6
        self.assertEqual(out[L.selection_id(AWAY)]["outcome"], "L")
        self.assertAlmostEqual(out[L.selection_id(ROW)]["research_pnl_units"], 100 / 110)

    def test_final_outcomes_written_once_ungraded_regraded(self):
        L.grade_log(self.p, self.res, {"9001": dict(FINAL, status="in_progress")})
        self.assertEqual({r["outcome"] for r in L.read_results(self.res)}, {"UNGRADED"})
        L.grade_log(self.p, self.res, {"9001": FINAL})
        c = L.grade_log(self.p, self.res, {"9001": FINAL})
        self.assertEqual(c["already_final"], 2)
        self.assertEqual(len(L.read_results(self.res)), 4)

    def test_void_and_push(self):
        L.grade_log(self.p, self.res, {"9001": dict(FINAL, status="postponed")})
        self.assertEqual({r["outcome"] for r in L.read_results(self.res)}, {"VOID"})
        p2, r2 = os.path.join(self.d, "l2.jsonl"), os.path.join(self.d, "r2.jsonl")
        L.append(p2, [dict(ROW, line=-6.0)])
        L.grade_log(p2, r2, {"9001": FINAL})
        self.assertEqual(L.read_results(r2)[0]["outcome"], "P")

    def test_results_tampering_detected(self):
        L.grade_log(self.p, self.res, {"9001": FINAL})
        s = open(self.res).read().replace('"outcome":"L"', '"outcome":"W"')
        open(self.res, "w").write(s)
        with self.assertRaises(L.LogError):
            L.read_results(self.res)

    def test_export_matches_harness_format(self):
        L.grade_log(self.p, self.res, {"9001": FINAL})
        out = os.path.join(self.d, "h.csv")
        c = L.export_harness(self.p, self.res, out)
        self.assertEqual(c, {"exported": 2, "withheld_not_exported": 1, "ungraded": 0})
        rows = list(csv.DictReader(open(out)))
        self.assertEqual(list(rows[0]), L.HARNESS_COLUMNS)
        self.assertEqual((rows[0]["model_p"], rows[0]["outcome"], rows[1]["outcome"]), ("0.55", "W", "L"))


class CbbWiring(unittest.TestCase):
    def test_card_rows_cover_every_market_both_sides_and_validate(self):
        import test_cbb_run_it as T
        with tempfile.TemporaryDirectory() as d:
            card, names, extra = T.run(d)
        rows = L.rows_from_cbb_card(card, names, extra, commit_sha="c" * 40)
        n = sum(len(r["markets"]) for r in card["rows"]) + len(extra.get("ladders", []))
        self.assertEqual(len(rows), 2 * n)
        self.assertEqual({r["selection_state"] for r in rows} - set(L.STATES), set())
        for r in rows:
            if r["selection_state"] != "WITHHELD":
                m = next(m for g in card["rows"] for m in g["markets"]
                         if str(g["game_id"]) == r["event_id"] and m["market"] == r["market"])
                self.assertEqual(r["win_p"], m["model_prob"][r["selection"]])
                self.assertEqual(r["raw_ev"], m["paper_ev_per_1u_at_price"][r["selection"]])
        p = os.path.join(tempfile.mkdtemp(), "log.jsonl")
        L.append(p, rows)
        self.assertEqual(len(L.read(p)), len(rows))

    def test_cli_flag_logs_without_changing_card(self):
        import test_cbb_run_it as T
        import cbb_run_it as R
        def go(d, extra):
            fx = Path(d) / "fx"; fx.mkdir()
            games, boxes = T.provider(); body = T.S.ratings_body()
            (fx / "ratings.json").write_bytes(body)
            (fx / "receipt.json").write_text(json.dumps(T.S.receipt(body)))
            (fx / "games.json").write_text(json.dumps(games)); (fx / "boxes.json").write_text(json.dumps(boxes))
            (fx / "espn.json").write_text(json.dumps(T.espn()))
            board = Path(d) / "board.csv"
            with open(board, "w", newline="") as f:
                w = csv.DictWriter(f, ["sport", "home", "away", "market", "line", "price_a", "price_b"])
                w.writeheader(); w.writerows(T.BOARD)
            self.assertEqual(R.main(["--board", str(board), "--board-captured-utc", "2026-11-21T14:30:00Z",
                                     "--season", str(T.S.SEASON), "--private-dir", str(Path(d) / "priv"),
                                     "--out", str(Path(d) / "out"), "--fixture-dir", str(fx),
                                     "--now", "2026-11-21T15:00:00+00:00", *extra]), 0)
            return (Path(d) / "out" / "cbb_card.md").read_text()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            log = str(Path(b) / "pregame.jsonl")
            self.assertEqual(go(a, []), go(b, ["--prediction-log", log]))
            rows = L.read(log)
            self.assertTrue(rows)
            self.assertTrue(all(r["prediction_utc"] < r["game_start_utc"] for r in rows))


if __name__ == "__main__":
    unittest.main()
