"""run_nfl.py (PR #472) output -> ledger compatibility. python3 -m unittest discover -s ledger/nfl/tests"""
import csv, json, os, sys, tempfile, unittest
from datetime import datetime, timezone

NFL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, NFL)
import freeze, settle, scorecard  # noqa: E402
from common import normalize_row, projection_numbers  # noqa: E402

# Exact run_nfl.py column layout (picks_nfl_<UTC>.csv at PR #472 head 342d0cc)
F = ["sport", "game", "mode", "pick", "price", "model_p", "fair_odds", "market_p", "edge", "ev",
     "score", "stars", "player", "bet_type", "model_ev", "blend_p", "held", "status", "approved_stake_u"]


def R(pick, price, bet_type, player="", held="", status="BLENDED"):
    return dict(sport="NFL", game="CIN @ WAS", mode="PROJECTION", pick=pick, price=price, model_p=0.55,
                fair_odds=-122, market_p=0.5, edge=0.05, ev=0.03, score=55, stars=3, player=player,
                bet_type=bet_type, model_ev=0.05, blend_p=0.515, held=held, status=status,
                approved_stake_u=0)


ROWS = [
    R("WAS +6", -107, "SPREAD|0|"), R("CIN -6", -112, "SPREAD|1|"),
    R("Over 54.5", -113, "TOTAL|0|", held="full-game projection -7.5 pts off this total quote (>6)"),
    R("Under 54.5", -106, "TOTAL|1|", held="full-game projection -7.5 pts off this total quote (>6)"),
    R("WAS ML", 241, "ML|0|"), R("CIN ML", -296, "ML|1|"),
    R("1H WAS +3.5", -105, "1H_SPREAD|0|"), R("1Q Under 10.5", -142, "1Q_TOTAL|1|"),
    R("1H CIN Under 15.5", -110, "1H_AWAY_TT|1|"), R("WAS Over 21.5", -110, "HOME_TT|0|"),
    R("Tee Higgins Under 74.5 Rec Yds", -114, "REC_YDS|1|", player="Tee Higgins"),
    R("Ja'Marr Chase Anytime TD", -150, "ATD|0|", player="Ja'Marr Chase"),
    R("Ja'Marr Chase First TD", 500, "FTD|0|", player="Ja'Marr Chase"),
    R("Overtime - Yes", 900, "OT|0|"),
]
FINALS = {"away": "CIN", "home": "WAS", "away_score": 27, "home_score": 24,
          "periods": {"1H": [14, 10], "1Q": [7, 3]}}
STATS = [["CIN@WAS", "Tee Higgins", "rec_yds", "61"], ["CIN@WAS", "Ja'Marr Chase", "atd", "1"]]
EXPECT = {  # (pick, bet_type) -> result
    ("WAS +6", "SPREAD|0|"): "W", ("CIN -6", "SPREAD|1|"): "L",
    ("Over 54.5", "TOTAL|0|"): "L", ("Under 54.5", "TOTAL|1|"): "W",
    ("WAS ML", "ML|0|"): "L", ("CIN ML", "ML|1|"): "W",
    ("1H WAS +3.5", "1H_SPREAD|0|"): "L",            # 10+3.5=13.5 vs 14
    ("1Q Under 10.5", "1Q_TOTAL|1|"): "W",            # 10
    ("1H CIN Under 15.5", "1H_AWAY_TT|1|"): "W",      # CIN 1H 14
    ("WAS Over 21.5", "HOME_TT|0|"): "W",             # 24
    ("Tee Higgins Under 74.5 Rec Yds", "REC_YDS|1|"): "W",
    ("Ja'Marr Chase Anytime TD", "ATD|0|"): "W",
    ("Ja'Marr Chase First TD", "FTD|0|"): "NG", ("Overtime - Yes", "OT|0|"): "NG",
}


def _w(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r if isinstance(r, dict) else dict(zip(fields, r)))


class RunnerCompat(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.runs, self.sdir = os.path.join(self.t, "runs"), os.path.join(self.t, "settle")
        self.picks = os.path.join(self.t, "picks_nfl_20261124T002900Z.csv")
        _w(self.picks, ROWS, F)
        self.board = os.path.join(self.t, "board.csv")
        _w(self.board, [["NFL", "WAS", "CIN"]], ["sport", "home", "away"])
        self.proj = os.path.join(self.t, "frozen.json")   # CIN@WAS package layout
        with open(self.proj, "w") as f:
            json.dump({"game": ["CIN@WAS", 26.04, 21.31, 47.35, 54.5, -6], "player_means": []}, f)
        self.stats = os.path.join(self.t, "stats.csv")
        _w(self.stats, STATS, ["game", "player", "stat", "value"])
        self.now = datetime(2026, 11, 23, 22, 29, tzinfo=timezone.utc)

    def test_normalize_mapping(self):
        n = {(r["pick"], r["bet_type"]): normalize_row(r) for r in ROWS}
        self.assertEqual((n[("CIN -6", "SPREAD|1|")]["market"], n[("CIN -6", "SPREAD|1|")]["line"]), ("spread", -6.0))
        self.assertEqual(n[("1Q Under 10.5", "1Q_TOTAL|1|")]["market"], "1q_total")
        self.assertEqual(n[("1H CIN Under 15.5", "1H_AWAY_TT|1|")]["market"], "1h_away_tt")
        self.assertEqual((n[("Tee Higgins Under 74.5 Rec Yds", "REC_YDS|1|")]["market"],
                          n[("Tee Higgins Under 74.5 Rec Yds", "REC_YDS|1|")]["pick"]), ("prop_rec_yds", "under"))
        self.assertTrue(n[("Overtime - Yes", "OT|0|")]["market"].startswith("unsupported_"))

    def test_freeze_settle_scorecard_end_to_end(self):
        before = open(self.picks, "rb").read()
        rd = freeze.freeze("CIN@WAS", self.board, self.proj, {"challenger": self.picks},
                           {"run_nfl": "342d0cc"}, "2026-11-24T01:15:00Z", runs_dir=self.runs, now=self.now)
        self.assertEqual(freeze.verify(rd), [])
        path, rec = settle.settle(rd, FINALS, "synthetic test finals", self.stats, self.sdir, now=self.now)
        got = {(ROWS[g["row"]]["pick"], ROWS[g["row"]]["bet_type"]): g for g in rec["graded"]}
        for k, res in EXPECT.items():
            self.assertEqual(got[k]["result"], res, k)
        self.assertTrue(got[("Under 54.5", "TOTAL|1|")]["held"])          # reason string = held
        self.assertFalse(got[("WAS +6", "SPREAD|0|")]["held"])
        self.assertTrue(all(g["approved_stake_u"] == 0 for g in rec["graded"]))
        self.assertEqual(freeze.verify(rd), [])                            # frozen run untouched
        self.assertEqual(open(self.picks, "rb").read(), before)           # source untouched
        md = scorecard.build(scorecard.load_week("2026-11-23", "2026-11-23", self.runs, self.sdir))
        self.assertIn("Total: model", md)                                  # package projection layout read

    def _frz(self, picks=None):
        return freeze.freeze("CIN@WAS", self.board, self.proj, {"challenger": picks or self.picks},
                             {}, None, runs_dir=self.runs, now=self.now)

    def test_integrity_failure_refused_or_quarantined(self):
        rd = self._frz()
        f = os.path.join(rd, "challenger", "picks_nfl.csv")
        os.chmod(f, 0o644)
        with open(f, "a") as fh:
            fh.write("tampered\n")
        with self.assertRaises(settle.SettlementError):
            settle.settle(rd, FINALS, "x", self.stats, self.sdir, now=self.now)
        settle.settle(rd, FINALS, "x", self.stats, self.sdir, now=self.now, quarantine=True)
        wk = scorecard.load_week("2026-11-23", "2026-11-23", self.runs, self.sdir)
        self.assertTrue(wk[0]["quarantined"] and wk[0]["settlement"] is None)
        self.assertIn("QUARANTINED", scorecard.build(wk))

    def test_wrong_game_finals_and_stats_refused(self):
        rd = self._frz()
        other = dict(FINALS, away="PIT", home="BAL")
        with self.assertRaises(settle.SettlementError):
            settle.settle(rd, other, "x", self.stats, self.sdir, now=self.now)
        swapped = dict(FINALS, away="WAS", home="CIN")
        with self.assertRaises(settle.SettlementError):
            settle.settle(rd, swapped, "x", self.stats, self.sdir, now=self.now)
        bad_stats = os.path.join(self.t, "bad_stats.csv")
        _w(bad_stats, [["PIT@BAL", "Tee Higgins", "rec_yds", "99"]], ["game", "player", "stat", "value"])
        with self.assertRaises(settle.SettlementError):
            settle.settle(rd, FINALS, "x", bad_stats, self.sdir, now=self.now)
        unbound = os.path.join(self.t, "unbound.csv")
        _w(unbound, [["Tee Higgins", "rec_yds", "99"]], ["player", "stat", "value"])
        with self.assertRaises(settle.SettlementError):
            settle.settle(rd, FINALS, "x", unbound, self.sdir, now=self.now)

    def test_nonzero_approved_stake_refused(self):
        p = os.path.join(self.t, "staked.csv")
        rows = [dict(r) for r in ROWS]
        for bad in (1, 0.25, "abc", "nan"):
            rows[0]["approved_stake_u"] = bad
            _w(p, rows, F)
            rd = freeze.freeze("CIN@WAS", self.board, self.proj, {"challenger": p}, {}, None,
                               runs_dir=os.path.join(self.t, f"runs_{bad}"), now=self.now)
            with self.assertRaises(settle.SettlementError, msg=repr(bad)):
                settle.settle(rd, FINALS, "x", self.stats, self.sdir, now=self.now)

    def test_scorecard_never_pools_pick_sets(self):
        rd = freeze.freeze("CIN@WAS", self.board, self.proj, {"baseline": self.picks, "challenger": self.picks},
                           {}, None, runs_dir=self.runs, now=self.now)
        settle.settle(rd, FINALS, "x", self.stats, self.sdir, now=self.now)
        md = scorecard.build(scorecard.load_week("2026-11-23", "2026-11-23", self.runs, self.sdir))
        self.assertIn("- baseline", md)
        self.assertIn("- challenger", md)
        self.assertEqual(md.count("## Overall"), 2)
        self.assertIn("Unheld priced candidates", md)
        self.assertIn("Card selections: selection not recorded", md)

    def test_selected_for_card_reported_separately(self):
        p = os.path.join(self.t, "sel.csv")
        rows = [dict(r, selected_for_card=(i == 0)) for i, r in enumerate(ROWS)]
        _w(p, rows, F + ["selected_for_card"])
        rd = self._frz(p)
        _, rec = settle.settle(rd, FINALS, "x", self.stats, self.sdir, now=self.now)
        self.assertEqual([g["row"] for g in rec["graded"] if g["on_card"]], [0])
        self.assertTrue(all(g["on_card"] is False for g in rec["graded"] if g["row"] != 0))
        self.assertTrue(all(g["approved_stake_u"] == 0 for g in rec["graded"]))
        md = scorecard.build(scorecard.load_week("2026-11-23", "2026-11-23", self.runs, self.sdir))
        self.assertIn("- Card selections: 1-0-0", md)                      # WAS +6 won

    def test_projection_layouts(self):
        p = projection_numbers({"game": ["X@Y", 20.0, 24.0, 44.0, 45.5, 3.0]})
        self.assertEqual((p["proj_margin"], p["proj_total"], p["market_total"], p["market_margin"]),
                         (4.0, 44.0, 45.5, 3.0))
        self.assertEqual(projection_numbers({"proj_margin": 1})["proj_margin"], 1)


if __name__ == "__main__":
    unittest.main()
