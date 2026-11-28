"""Pregame prediction log: chain integrity, pregame-only, duplicates, CBB wiring, harness export."""
import copy, csv, json, os, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "models" / "cbb"))
from ledger import pregame_log as L

ROW = {"event_id": "9001", "sport": "CBB", "market": "spread", "period": "FG", "selection": "home",
       "line": -3.5, "model_p": 0.52, "push_p": 0.0, "model_version": "v", "model_sha256": "a" * 64,
       "price": -110, "opp_price": -110, "book": "DraftKings",
       "quote_captured_utc": "2026-11-21T14:30:00Z", "forecast_freeze_utc": "2026-11-21T14:00:00Z",
       "kickoff_utc": "2026-11-21T23:00:00Z", "eligibility": "PRICED_UNVALIDATED"}


class LogCore(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.p = os.path.join(self.d, "log.jsonl")

    def test_append_and_read_roundtrip_with_chain(self):
        L.append(self.p, [ROW, dict(ROW, selection="away", line=3.5)])
        L.append(self.p, [dict(ROW, market="total", selection="over", line=140.5)])
        self.assertEqual(len(L.read(self.p)), 3)

    def test_post_kickoff_capture_or_freeze_rejected(self):
        for kw, why in ((dict(quote_captured_utc="2026-11-21T23:00:00Z"), "QUOTE_NOT_PREGAME"),
                        (dict(quote_captured_utc="2026-11-22T01:00:00Z"), "QUOTE_NOT_PREGAME"),
                        (dict(forecast_freeze_utc="2026-11-21T23:00:00Z"), "FORECAST_NOT_PREGAME")):
            with self.subTest(**kw), self.assertRaisesRegex(L.LogError, why):
                L.append(self.p, [dict(ROW, **kw)])
        self.assertEqual(L.read(self.p), [])

    def test_duplicates_rejected_within_and_across_batches_all_or_nothing(self):
        with self.assertRaisesRegex(L.LogError, "DUPLICATE_SELECTION"):
            L.append(self.p, [ROW, dict(ROW, price=-120)])
        self.assertEqual(L.read(self.p), [])
        L.append(self.p, [ROW])
        with self.assertRaisesRegex(L.LogError, "DUPLICATE_SELECTION"):
            L.append(self.p, [dict(ROW, selection="away"), ROW])
        self.assertEqual(len(L.read(self.p)), 1)

    def test_tampering_detected(self):
        L.append(self.p, [ROW, dict(ROW, selection="away", line=3.5)])
        lines = open(self.p).read().splitlines()
        for mutate in (lambda s: s.replace('"model_p":0.52', '"model_p":0.62'),
                       lambda s: s.replace('"seq":2', '"seq":3')):
            with self.subTest():
                open(self.p, "w").write(lines[0] + "\n" + mutate(lines[1]) + "\n")
                with self.assertRaises(L.LogError):
                    L.read(self.p)
        open(self.p, "w").write(lines[1] + "\n")  # deleted first row
        with self.assertRaisesRegex(L.LogError, "CHAIN_BROKEN"):
            L.read(self.p)

    def test_malformed_values_rejected(self):
        for kw in (dict(model_p=1.2), dict(model_p=float("nan")), dict(push_p=True), dict(model_p=0.7, push_p=0.4),
                   dict(price=-110.5), dict(opp_price=50), dict(line=float("inf")), dict(kickoff_utc="2026-11-21"),
                   dict(model_sha256=""), dict(selection=" ")):
            with self.subTest(**{k: repr(v) for k, v in kw.items()}), self.assertRaises(L.LogError):
                L.append(self.p, [dict(ROW, **kw)])
        with self.assertRaisesRegex(L.LogError, "FIELDS_MISMATCH"):
            L.append(self.p, [dict(ROW, extra=1)])

    def test_withheld_rows_keep_denominator_and_are_not_exported(self):
        wh = dict(ROW, selection="away", line=None, model_p=None, push_p=None, price=None, opp_price=None,
                  quote_captured_utc=None, eligibility="WITHHELD:MISSING_QUOTE")
        L.append(self.p, [ROW, wh])
        self.assertEqual(len(L.read(self.p)), 2)
        out = os.path.join(self.d, "h.csv")
        c = L.export_harness(self.p, {L.selection_id(ROW): "W"}, out)
        self.assertEqual(c, {"exported": 1, "withheld_not_exported": 1, "ungraded": 0})

    def test_export_matches_harness_columns_and_skips_ungraded(self):
        L.append(self.p, [ROW, dict(ROW, selection="away", line=3.5)])
        out = os.path.join(self.d, "h.csv")
        c = L.export_harness(self.p, {L.selection_id(ROW): "P"}, out)
        self.assertEqual(c["exported"], 1); self.assertEqual(c["ungraded"], 1)
        rows = list(csv.DictReader(open(out)))
        self.assertEqual(list(rows[0]), L.HARNESS_COLUMNS)
        self.assertEqual((rows[0]["price"], rows[0]["opp_price"], rows[0]["outcome"]), ("-110", "-110", "P"))
        self.assertEqual(rows[0]["date"], "2026-11-21")


class CbbWiring(unittest.TestCase):
    def test_card_rows_cover_every_market_and_both_sides(self):
        import test_cbb_run_it as T
        with tempfile.TemporaryDirectory() as d:
            card, names, extra = T.run(d)
        rows = L.rows_from_cbb_card(card, names, extra)
        n_markets = sum(len(r["markets"]) for r in card["rows"]) + len(extra.get("ladders", []))
        self.assertEqual(len(rows), 2 * n_markets)
        priced = [r for r in rows if r["eligibility"] != "WITHHELD" and not r["eligibility"].startswith("WITHHELD:")]
        self.assertTrue(priced)
        for r in priced:
            m = next(m for g in card["rows"] for m in g["markets"]
                     if str(g["game_id"]) == r["event_id"] and m["market"] == r["market"])
            self.assertEqual(r["model_p"], m["model_prob"][r["selection"]])
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
            rc = R.main(["--board", str(board), "--board-captured-utc", "2026-11-21T14:30:00Z",
                         "--season", str(T.S.SEASON), "--private-dir", str(Path(d) / "priv"),
                         "--out", str(Path(d) / "out"), "--fixture-dir", str(fx),
                         "--now", "2026-11-21T15:00:00+00:00", *extra])
            self.assertEqual(rc, 0)
            return (Path(d) / "out" / "cbb_card.md").read_text()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            plain = go(a, [])
            log = str(Path(b) / "pregame.jsonl")
            logged = go(b, ["--prediction-log", log])
            self.assertEqual(plain, logged)
            rows = L.read(log)
            self.assertTrue(rows)
            self.assertTrue(all(r["forecast_freeze_utc"] < r["kickoff_utc"] for r in rows))


if __name__ == "__main__":
    unittest.main()
