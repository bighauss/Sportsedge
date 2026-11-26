"""Real-v5 CLI regression: engine/run_nfl_wpl.py in its own process prices from captured simulator mass."""
import csv
import glob
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_run_nfl as base  # noqa: E402

GAME_BASES = {"ML", "SPREAD", "TOTAL", "HOME_TT", "AWAY_TT"}
PERIOD_PREFIXES = {"1Q", "2Q", "3Q", "4Q", "1H", "2H"}
PROPS = [dict(player="WR1", team="HOM", market="REC_YDS", line=59.5, price_a=-110, price_b=-110, proj=70),
         dict(player="QB1", team="HOM", market="PASS_TDS", line=1.5, price_a=-110, price_b=-110, proj=2),
         dict(player="QB1", team="HOM", market="PASS_TDS", line=2.5, price_a=-110, price_b=-110, proj=2),
         dict(player="WR1", team="HOM", market="ATD", price_a=150, price_b=-190, proj=0.25)]


def is_game_line(x):
    market = x["bet_type"].split("|")[0]
    head, _, rest = market.partition("_")
    base_market = rest if rest and head in PERIOD_PREFIXES else market
    return base_market in GAME_BASES and not x["player"]


def run_cli(board):
    wd = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(HERE, "run_nfl_wpl.py"), board], cwd=wd,
                       capture_output=True, text=True, timeout=900)
    return wd, r


def read_rows(wd):
    files = glob.glob(os.path.join(wd, "picks_nfl_*.csv"))
    assert len(files) == 1, files
    with open(files[0], newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Cli(unittest.TestCase):
    def test_real_v5_cli_binds_every_game_line_row_by_selection_identity(self):
        wd, r = run_cli(os.path.abspath(base.board(base.game(24, 20))))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        rows = read_rows(wd)
        self.assertTrue(rows)
        for col in ("p_win", "p_push", "p_loss", "wpl_status", "wpl_source", "wpl_binding", "held", "bet_type", "player"):
            self.assertIn(col, rows[0])
        lines = [x for x in rows if is_game_line(x)]
        self.assertGreater(len(lines), 0)
        unbound = [(x["pick"], x["wpl_status"]) for x in lines if x["wpl_status"] != "CAPTURED"]
        self.assertEqual(unbound, [], "game-line rows not bound to simulator mass: %r" % unbound[:10])
        self.assertTrue(all(x["wpl_binding"] == "selection_identity" for x in lines))
        for x in rows:
            if x["wpl_status"] == "CAPTURED":
                p = [float(x[c]) for c in ("p_win", "p_push", "p_loss")]
                self.assertGreaterEqual(min(p), 0.0)
                self.assertAlmostEqual(sum(p), 1.0, places=9)
            else:
                self.assertIn("simulator W/P/L unavailable", x["held"])

    def test_real_v5_props_bind_by_label_or_are_held_with_reason(self):
        wd, r = run_cli(os.path.abspath(base.board(base.game(24, 20, extra=PROPS))))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        rows = read_rows(wd)
        by_market = {}
        for x in rows:
            by_market.setdefault(x["bet_type"].split("|")[0], []).append(x)
        for market in ("REC_YDS", "PASS_TDS", "ATD"):
            self.assertIn(market, by_market, "no priced rows for %s; markets: %s" % (market, sorted(by_market)))
        report = [(x["bet_type"], x["pick"], x["wpl_status"]) for m in ("REC_YDS", "PASS_TDS", "ATD") for x in by_market[m]]
        for market in ("REC_YDS", "PASS_TDS", "ATD"):
            for x in by_market[market]:
                self.assertEqual(x["wpl_status"], "CAPTURED", report)
                self.assertEqual(x["wpl_binding"], "selection_identity")
                self.assertAlmostEqual(sum(float(x[c]) for c in ("p_win", "p_push", "p_loss")), 1.0, places=9)
        picks = {x["pick"] for x in by_market["PASS_TDS"]}
        self.assertTrue(any("1.5" in p for p in picks) and any("2.5" in p for p in picks), picks)
        self.assertTrue(any(x["pick"].endswith("Anytime TD") for x in by_market["ATD"]), report)
        for x in rows:
            if x["wpl_status"] != "CAPTURED":
                self.assertIn("simulator W/P/L unavailable", x["held"])

    def test_cli_rejects_invalid_odds_before_pricing(self):
        wd = tempfile.mkdtemp()
        bad = os.path.join(wd, "bad.csv")
        with open(bad, "w", newline="") as f:
            f.write("sport,home,away,market,line,price_a,price_b\nNFL,A,B,TOTAL,44,110.5,-110\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "run_nfl_wpl.py"), bad], cwd=wd,
                           capture_output=True, text=True, timeout=300)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("invalid American odds", r.stderr)
        self.assertEqual(glob.glob(os.path.join(wd, "picks_nfl_*.csv")), [])


if __name__ == "__main__":
    unittest.main()
