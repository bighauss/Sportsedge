"""Offline tests: grading frozen CFB RUN IT rows into the hash-chained ledger."""
import datetime as dt, json, os, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from models.cfb import cfb_ledger as ledger
from models.cfb import cfb_run_it_grade as G

NOW = dt.datetime(2026, 11, 22, 12, tzinfo=dt.timezone.utc)
ROWS = [
    {"game": "UCLA @ Michigan", "cfbd_game_id": "1", "market": "Spread", "pick": "UCLA -3.5", "line": -3.5, "odds": -110, "p_model": .63, "p_market": .5, "p_blend": .54},
    {"game": "UCLA @ Michigan", "cfbd_game_id": "1", "market": "Total", "pick": "Under 36.5", "line": 36.5, "odds": -110, "p_model": .65, "p_market": .5, "p_blend": .55},
    {"game": "UCLA @ Michigan", "cfbd_game_id": "1", "market": "ML", "pick": "UCLA", "line": None, "odds": -180, "p_model": .72, "p_market": .62, "p_blend": .65},
    {"game": "UCLA @ Michigan", "cfbd_game_id": "1", "market": "Michigan TT", "pick": "Under 14.5", "line": 14.5, "odds": 105, "p_model": .63, "p_market": .45, "p_blend": .51},
    {"game": "UCLA @ Michigan", "cfbd_game_id": "1", "market": "Prop rush_yds", "pick": "Anthony Woods Over 29.5", "line": 29.5, "odds": 118, "p_model": .6, "p_market": .46, "p_blend": .5, "player_id": "77"},
    {"game": "UCLA @ Michigan", "cfbd_game_id": "1", "market": "1H Total", "pick": "Under 17.5", "line": 17.5, "odds": -108, "p_model": .58, "p_market": .5, "p_blend": .52},
    {"game": "LSU @ Tennessee", "cfbd_game_id": "2", "market": "Total", "pick": "Over 45.5", "line": 45.5, "odds": -108, "p_model": .6, "p_market": .5, "p_blend": .53}]
FINALS = [{"id": 1, "homeTeam": "Michigan", "awayTeam": "UCLA", "completed": True, "homePoints": 10, "awayPoints": 24,
           "homeLineScores": [0, 3, 7, 0], "awayLineScores": [7, 7, 3, 7]},
          {"id": 2, "homeTeam": "Tennessee", "awayTeam": "LSU", "completed": False, "homePoints": None, "awayPoints": None}]
PLAYERS = [{"id": 1, "teams": [{"categories": [{"name": "rushing", "types": [{"name": "YDS", "athletes": [{"id": 77, "stat": "41"}]}]}]}]}]

def seed(d):
    p = os.path.join(d, "priv", "ledger.jsonl")
    ledger.append(p, {"type": "CARD_FROZEN", "source": "cfb_run_it", "card_sha256": "c" * 64, "game_ids": ["1", "2"], "rows": ROWS}, now=NOW - dt.timedelta(hours=30))
    return p

class Grade(unittest.TestCase):
    def test_results_and_pending(self):
        with tempfile.TemporaryDirectory() as d:
            p = seed(d)
            c = G.grade(p, FINALS, PLAYERS, [{"source": "cfbd_games", "sha256": "x"}], now=NOW)
            self.assertEqual(c["graded"], 6); self.assertEqual(c["pending_no_final"], 1)
            g = {e["market"]: e["result"] for e in ledger.verify(p) if e["type"] == "GAME_GRADED"}
            self.assertEqual(g, {"Spread": "W", "Total": "W", "ML": "W", "Michigan TT": "W", "Prop rush_yds": "W", "1H Total": "W"})
            again = G.grade(p, FINALS, PLAYERS, [], now=NOW + dt.timedelta(minutes=1))
            self.assertEqual(again["already_graded"], 6)                          # never re-graded
            rep = G.evaluate(p)
            self.assertEqual(rep["all_decided"]["n"], 6); self.assertEqual(rep["all_decided"]["wins"], 6)
            self.assertIn("p_market", rep["all_decided"]["brier"])

    def test_losses_kept_and_tamper_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = seed(d)
            f = [dict(FINALS[0], homePoints=30, awayPoints=10, homeLineScores=[14, 7, 3, 6], awayLineScores=[3, 0, 7, 0])]
            G.grade(p, f, [], [], now=NOW)
            res = [e["result"] for e in ledger.verify(p) if e["type"] == "GAME_GRADED"]
            self.assertIn("L", res)
            un = [e["ungraded_reason"] for e in ledger.verify(p) if e["type"] == "GAME_GRADED" and e["result"] is None]
            self.assertIn("PROP_PLAYER_NO_GAME_STATS", un)
            raw = Path(p).read_text().replace('"result":"L"', '"result":"W"', 1); Path(p).write_text(raw)
            with self.assertRaises(ledger.LedgerRefused):
                G.evaluate(p)

if __name__ == "__main__":
    unittest.main()
