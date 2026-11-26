"""Real-v5 CLI regression: the canonical run_nfl.py and run_nfl_wpl.py price from captured simulator mass."""
import collections
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
TD_NAMES = {"ATD": "Anytime TD", "FTD": "First TD", "TD2": "2+ TDs"}
HEADER = "sport,home,away,market,line,price_a,price_b\n"
HEADER_P = "sport,home,away,market,player,line,price_a,price_b\n"
PROPS = [dict(player="WR1", team="HOM", market="REC_YDS", line=59.5, price_a=-110, price_b=-115, proj=70),
         dict(player="QB1", team="HOM", market="PASS_YDS", line=249.5, price_a=-110, price_b=-110, proj=262),
         dict(player="RB1", team="HOM", market="RUSH_YDS", line=79.5, price_a=-105, price_b=-125, proj=85),
         dict(player="QB1", team="HOM", market="PASS_TDS", line=1.5, price_a=-120, price_b=100, proj=2),
         dict(player="QB1", team="HOM", market="PASS_TDS", line=2.5, price_a=140, price_b=-170, proj=2),
         dict(player="WR1", team="HOM", market="ATD", price_a=150, price_b=-190, proj=0.25),
         dict(player="WR1", team="HOM", market="FTD", price_a=900, price_b=-2000, proj=0.05),
         dict(player="WR1", team="HOM", market="TD2", price_a=800, price_b=-1500, proj=0.06)]


def expected_selections():
    """Both sides of every fixture row as (market, pick, price), built independently of the adapter."""
    out = collections.Counter()
    for p in PROPS:
        m, who = p["market"], p["player"]
        if m in TD_NAMES:
            picks = ("%s %s" % (who, TD_NAMES[m]), "%s No %s" % (who, TD_NAMES[m]))
        else:
            name = m.replace("_", " ").title()
            picks = ("%s Over %g %s" % (who, p["line"], name), "%s Under %g %s" % (who, p["line"], name))
        out[(m, picks[0], p["price_a"])] += 1
        out[(m, picks[1], p["price_b"])] += 1
    return out


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


def write_raw(text):
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    with open(p, "w", newline="") as f:
        f.write(text)
    return p


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

    def test_exact_two_sided_prop_selection_multiset_is_priced_and_captured(self):
        wd, r = run_cli(os.path.abspath(base.board(base.game(24, 20, extra=PROPS))))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        rows = read_rows(wd)
        fixture_markets = {m for m, _, _ in expected_selections()}
        prop_rows = [x for x in rows if x["bet_type"].split("|")[0] in fixture_markets and x["player"]]
        got = collections.Counter((x["bet_type"].split("|")[0], x["pick"], int(float(x["price"]))) for x in prop_rows)
        want = expected_selections()
        self.assertEqual(got, want, "missing: %r unexpected: %r" % (sorted((want - got).items()), sorted((got - want).items())))
        for x in prop_rows:
            self.assertEqual(x["wpl_status"], "CAPTURED", (x["bet_type"], x["pick"], x["wpl_status"], x["held"]))
            self.assertEqual(x["wpl_binding"], "selection_identity")
            self.assertAlmostEqual(sum(float(x[c]) for c in ("p_win", "p_push", "p_loss")), 1.0, places=9)
        for x in rows:
            if x["wpl_status"] != "CAPTURED":
                self.assertIn("simulator W/P/L unavailable", x["held"])

    def test_malformed_inputs_stop_before_frozen_v5_ever_reads_them(self):
        cases = [
            ("odds 1+10 would become +110", HEADER + "NFL,A,B,TOTAL,44,1+10,-110\n", "invalid American odds"),
            ("odds 110.5", HEADER + "NFL,A,B,TOTAL,44,110.5,-110\n", "invalid American odds"),
            ("odds 99", HEADER + "NFL,A,B,TOTAL,44,99,-110\n", "invalid American odds"),
            ("line 4+4 would become 44", HEADER + "NFL,A,B,TOTAL,4+4,-110,-110\n", "non-canonical line"),
            ("line 44.00001", HEADER + "NFL,A,B,TOTAL,44,-110,-110\nNFL,A,B,TOTAL,44.00001,-110,-110\n", "non-canonical line"),
            ("missing total line would default to 0", HEADER + "NFL,A,B,TOTAL,,-110,-110\n", "has no line"),
            ("missing period spread line", HEADER + "NFL,A,B,1H_SPREAD,,-110,-110\n", "has no line"),
            ("duplicate price column overwrites",
             "sport,home,away,market,line,price_a,price_a,price_b\nNFL,A,B,TOTAL,44,-110,-120,-110\n", "duplicate column"),
            ("passing-yards prop without a threshold", HEADER_P + "NFL,A,B,PASS_YDS,QB1,,-110,-110\n", "has no line"),
            ("total carrying a player name", HEADER_P + "NFL,A,B,TOTAL,Bob,44,-110,-110\n", "carries player"),
            ("extra csv cells", HEADER_P + "NFL,A,B,TOTAL,,44,-110,-110,zzz\n", "cells for"),
            ("both prices missing", HEADER_P + "NFL,A,B,TOTAL,,44,,\n", "neither price_a nor price_b"),
            ("missing home team", HEADER_P + "NFL,,B,TOTAL,,44,-110,-110\n", "no home team"),
            ("unknown market", HEADER_P + "NFL,A,B,FOO,,44,-110,-110\n", "unknown game-level market"),
            ("unknown period prefix", HEADER_P + "NFL,A,B,5Q_TOTAL,,4,-110,-110\n", "unknown game-level market"),
            ("missing sport column", "home,away,market,line,price_a,price_b\nA,B,TOTAL,44,-110,-110\n",
             "missing required column"),
        ]
        for name, text, expect in cases:
            with self.subTest(name):
                wd, r = run_cli(write_raw(text))
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(expect, r.stderr)
                self.assertEqual(glob.glob(os.path.join(wd, "picks_nfl_*.csv")), [])

    def test_valid_lineless_rows_with_correct_identity_are_not_rejected(self):
        """ATD needs a PLAYER (the earlier fixture omitted it and was rightly rejected)."""
        from importlib import util
        spec = util.spec_from_file_location("run_nfl_wpl_under_test", os.path.join(HERE, "run_nfl_wpl.py"))
        mod = util.module_from_spec(spec)
        sys.path.insert(0, HERE)
        spec.loader.exec_module(mod)
        mod.validate_input(write_raw(HEADER_P + "NFL,A,B,ML,,,-150,130\nNFL,A,B,ATD,WR1,,150,-190\n"
                                     "NFL,A,B,PASS_YDS,QB1,249.5,-110,-110\nNFL,A,B,1H_SPREAD,,-3.5,-110,-110\n"
                                     "CBB,A,B,TOTAL,,,50,x\n"))
        with self.assertRaises(ValueError):
            mod.validate_input(write_raw(HEADER_P + "NFL,A,B,ATD,,,150,-190\n"))


if __name__ == "__main__":
    unittest.main()
