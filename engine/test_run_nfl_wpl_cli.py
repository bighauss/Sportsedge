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


def write_board(lines):
    p = os.path.join(tempfile.mkdtemp(), "b.csv")
    with open(p, "w", newline="") as f:
        f.write("sport,home,away,market,line,price_a,price_b\n" + "".join(l + "\n" for l in lines))
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

    def test_board_mixing_valid_and_noncanonical_lines_is_rejected_before_pricing(self):
        board = write_board(["NFL,A,B,TOTAL,44,-110,-110", "NFL,A,B,TOTAL,44.00001,-110,-110"])
        wd, r = run_cli(board)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("non-canonical line", r.stderr)
        self.assertEqual(glob.glob(os.path.join(wd, "picks_nfl_*.csv")), [])

    def test_cli_rejects_invalid_odds_before_pricing(self):
        wd, r = run_cli(write_board(["NFL,A,B,TOTAL,44,110.5,-110"]))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("invalid American odds", r.stderr)
        self.assertEqual(glob.glob(os.path.join(wd, "picks_nfl_*.csv")), [])


if __name__ == "__main__":
    unittest.main()
