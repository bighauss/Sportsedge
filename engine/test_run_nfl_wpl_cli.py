"""Real-v5 CLI regression: the canonical run_nfl.py and run_nfl_wpl.py price from captured simulator mass."""
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
         dict(player="QB1", team="HOM", market="PASS_YDS", line=249.5, price_a=-110, price_b=-110, proj=262),
         dict(player="RB1", team="HOM", market="RUSH_YDS", line=79.5, price_a=-110, price_b=-110, proj=85),
         dict(player="QB1", team="HOM", market="PASS_TDS", line=1.5, price_a=-110, price_b=-110, proj=2),
         dict(player="QB1", team="HOM", market="PASS_TDS", line=2.5, price_a=-110, price_b=-110, proj=2),
         dict(player="WR1", team="HOM", market="ATD", price_a=150, price_b=-190, proj=0.25),
         dict(player="WR1", team="HOM", market="FTD", price_a=900, price_b=-2000, proj=0.05),
         dict(player="WR1", team="HOM", market="TD2", price_a=800, price_b=-1500, proj=0.06)]
EXPECTED = {("REC_YDS", "WR1 Over 59.5 Rec Yds"), ("PASS_YDS", "QB1 Over 249.5 Pass Yds"),
            ("RUSH_YDS", "RB1 Over 79.5 Rush Yds"), ("PASS_TDS", "QB1 Over 1.5 Pass Tds"),
            ("PASS_TDS", "QB1 Over 2.5 Pass Tds"), ("ATD", "WR1 Anytime TD"), ("FTD", "WR1 First TD"),
            ("TD2", "WR1 2+ TDs")}


def is_game_line(x):
    market = x["bet_type"].split("|")[0]
    head, _, rest = market.partition("_")
    base_market = rest if rest and head in PERIOD_PREFIXES else market
    return base_market in GAME_BASES and not x["player"]


def run_cli(board, script="run_nfl_wpl.py", extra_args=()):
    wd = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(HERE, script), *extra_args, board], cwd=wd,
                       capture_output=True, text=True, timeout=900)
    return wd, r


def read_rows(wd):
    files = glob.glob(os.path.join(wd, "picks_nfl_*.csv"))
    assert len(files) == 1, files
    with open(files[0], newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Cli(unittest.TestCase):
    def check_game_lines(self, rows):
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

    def test_real_v5_cli_binds_every_game_line_row_by_selection_identity(self):
        wd, r = run_cli(os.path.abspath(base.board(base.game(24, 20))))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        self.check_game_lines(read_rows(wd))

    def test_canonical_run_nfl_entry_prices_from_captured_mass(self):
        wd, r = run_cli(os.path.abspath(base.board(base.game(24, 20))), script="run_nfl.py")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        self.check_game_lines(read_rows(wd))

    def test_legacy_flag_keeps_the_unpriced_path(self):
        wd, r = run_cli(os.path.abspath(base.board(base.game(24, 20))), script="run_nfl.py",
                        extra_args=("--legacy-unpriced",))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        self.assertNotIn("wpl_status", read_rows(wd)[0])

    def test_every_expected_prop_selection_appears_and_is_captured(self):
        wd, r = run_cli(os.path.abspath(base.board(base.game(24, 20, extra=PROPS))))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        rows = read_rows(wd)
        got = {(x["bet_type"].split("|")[0], x["pick"]): x for x in rows}
        missing = sorted(EXPECTED - set(got))
        report = sorted((k, v["wpl_status"]) for k, v in got.items() if k[0] in {m for m, _ in EXPECTED})
        self.assertEqual(missing, [], "expected selections absent from output; present: %r" % report)
        for key in sorted(EXPECTED):
            x = got[key]
            self.assertEqual(x["wpl_status"], "CAPTURED", (key, x["wpl_status"], x["held"]))
            self.assertEqual(x["wpl_binding"], "selection_identity")
            self.assertAlmostEqual(sum(float(x[c]) for c in ("p_win", "p_push", "p_loss")), 1.0, places=9)
        for x in rows:
            if x["wpl_status"] != "CAPTURED":
                self.assertIn("simulator W/P/L unavailable", x["held"])

    def test_game_line_thresholds_that_g_cannot_distinguish_are_held(self):
        import numpy as np
        import nfl_wpl_capture as cm
        import sportsedge_v5 as v5

        def priced(r, d):
            return v5.wl(d)

        a = dict(sport="NFL", home="DET", away="CHI", market="TOTAL", line=44.00001, player="", sgp="",
                 price_a=-110.0, price_b=-110.0)
        saved = cm.CALLSITE_MODULES
        cm.CALLSITE_MODULES = {v5.__name__, __name__}
        try:
            d = np.array([1, 0, -1, 0, 2, -3, 0, 5])
            with cm.capturing() as calls:
                w, l = priced(a, d)
        finally:
            cm.CALLSITE_MODULES = saved
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0]["ident"]["labels"])
        row = dict(sport="NFL", game="CHI @ DET", bet_type="TOTAL|0|", player="", price=-110, pick="Over 44",
                   model_p=v5.cond(w, l), ev=w * v5.payout(-110) - l)
        cm.attach([row], calls)
        self.assertIsNone(row["p_win"])

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
