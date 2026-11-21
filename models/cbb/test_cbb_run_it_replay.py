"""SHADOW REPLAY: rebuilds a frozen card from stored evidence, read-only, no ledger."""
import csv, hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1]))
import cbb_run_it as R
import cbbd_paper_synthetic as S
import test_cbb_run_it as T

def make_evidence(d):
    ev = Path(d) / "ev"; (ev / "capture" / "ratings").mkdir(parents=True); (ev / "capture" / "games").mkdir(); (ev / "card").mkdir()
    games, boxes = T.provider()
    today = [g for g in games if g["status"] != "final"]; season = [g for g in games if g["status"] == "final"]
    body = S.ratings_body(); rec = S.receipt(body)
    w = lambda p, b: (p.write_bytes(b), hashlib.sha256(b).hexdigest())[1]
    (ev / "capture" / "ratings" / "receipt.json").write_text(json.dumps({"receipts": [rec]}))
    w(ev / "capture" / "ratings" / "cbbd_ratings_adjusted.json", body)
    th = w(ev / "capture" / "games" / "cbbd_games_2027_X.raw.json", json.dumps(today).encode())
    (ev / "capture" / "games" / "cbbd_games_2027_X.manifest.json").write_text(json.dumps({"source_sha256": th, "local_observed_utc": T.OBS}))
    sh = w(ev / "capture" / "games" / "cbbd_games_season.raw.json", json.dumps(season).encode())
    bh = w(ev / "capture" / "games" / "cbbd_games_teams.raw.json", json.dumps(boxes).encode())
    eh = w(ev / "capture" / "games" / "espn_scoreboard.raw.json", json.dumps(T.espn()).encode())
    with open(ev / "board.csv", "w", newline="") as f:
        cw = csv.DictWriter(f, ["sport", "home", "away", "market", "line", "price_a", "price_b"]); cw.writeheader(); cw.writerows(T.BOARD)
    board_h = hashlib.sha256((ev / "board.csv").read_bytes()).hexdigest()
    card, _, _ = R.build(work=Path(d) / "w0", season=S.SEASON, now_utc=T.NOW, games=season + today, boxes=boxes,
                         observed_utc=T.OBS, ratings_body=body, ratings_receipt=rec, espn=T.espn(), espn_sha=eh,
                         espn_captured="2026-11-21T14:30:00Z", board_rows=T.BOARD, board_captured_utc="2026-11-21T14:30:00Z")
    (ev / "card" / "cbb_card.json").write_text(json.dumps(card))
    (ev / "card" / "receipts.json").write_text(json.dumps([
        {"source": "cbbd_games_season", "sha256": sh}, {"source": "cbbd_games_teams", "sha256": bh},
        {"source": "espn_scoreboard", "sha256": eh, "observed_utc": "2026-11-21T14:30:00Z"},
        {"source": "dk_board", "sha256": board_h, "observed_utc": "2026-11-21T14:30:00Z"}]))
    return ev

class Replay(unittest.TestCase):
    def test_replay_reproduces_frozen_card_without_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            ev = make_evidence(d)
            rc = R.main(["--replay-evidence", str(ev), "--season", str(S.SEASON), "--out", str(Path(d) / "out")])
            self.assertEqual(rc, 0)
            md = (Path(d) / "out" / "cbb_replay.md").read_text()
            self.assertTrue(md.startswith("# SHADOW REPLAY / 0u"))
            self.assertIn("rows identical to frozen card: **True**", md)
            self.assertEqual(list(Path(d).rglob("*.jsonl")), [])                    # no ledger anywhere

    def test_replay_refuses_ledger_and_tampered_source(self):
        with tempfile.TemporaryDirectory() as d:
            ev = make_evidence(d)
            self.assertEqual(R.main(["--replay-evidence", str(ev), "--season", "2027", "--out", str(Path(d) / "o"),
                                     "--ledger", str(Path(d) / "l.jsonl")]), 2)
            p = ev / "capture" / "games" / "cbbd_games_teams.raw.json"; p.write_text("[]")
            with self.assertRaises(R.Hold):
                R.replay(ev, S.SEASON, Path(d) / "o2")

if __name__ == "__main__":
    unittest.main()
