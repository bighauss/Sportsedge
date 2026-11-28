"""Exhaustive settlement regressions (synthetic) + optional real nflverse check."""
import csv, glob, gzip, os, sys, unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from sportsedge.grading.settlement import (
    SettlementInputError, nflverse_players, period_points, settle)

# NFL: home 7-10-0-7 (24) +3 OT = 27 ; away 3-7-14-0 (24) + 0 OT = 24
NFL = {"sport": "NFL", "status": "final", "event_id": "E1",
       "home_score": 27, "away_score": 24,
       "home_periods": [7, 10, 0, 7, 3], "away_periods": [3, 7, 14, 0, 0]}
CBB = {"sport": "CBB", "status": "final", "event_id": "C1", "home_score": 80, "away_score": 78,
       "home_periods": [35, 39, 6], "away_periods": [40, 34, 4]}


def s(**kw):
    return dict({"sport": "NFL", "event_id": "E1", "price": -110, "period": "FG"}, **kw)


def c(**kw):
    return s(sport="CBB", event_id="C1", **kw)


def R(sel, ev=NFL, players=None):
    return settle(sel, ev, players).result


class GameMarkets(unittest.TestCase):
    def test_moneyline_fg_includes_ot(self):
        self.assertEqual(R(s(market="moneyline", side="home")), "W")
        self.assertEqual(R(s(market="moneyline", side="away")), "L")

    def test_period_moneyline_tie_pushes(self):
        tie = dict(NFL, home_periods=[7, 10, 7, 0, 3], away_periods=[7, 7, 7, 3, 0])
        self.assertEqual(R(s(market="moneyline", side="home", period="Q1"), tie), "P")
        self.assertEqual(R(s(market="moneyline", side="home", period="Q4"), NFL), "W")  # 7-0

    def test_spread_integer_push_and_half(self):
        self.assertEqual(R(s(market="spread", side="home", line=-3)), "P")
        self.assertEqual(R(s(market="spread", side="home", line=-2.5)), "W")
        self.assertEqual(R(s(market="spread", side="away", line=3)), "P")
        self.assertEqual(R(s(market="spread", side="away", line=2.5)), "L")

    def test_spread_pickem_zero(self):
        self.assertEqual(R(s(market="spread", side="home", line=0)), "W")

    def test_total_push_over_under(self):
        self.assertEqual(R(s(market="total", side="over", line=51)), "P")
        self.assertEqual(R(s(market="total", side="over", line=50.5)), "W")
        self.assertEqual(R(s(market="total", side="under", line=50.5)), "L")

    def test_team_total(self):
        self.assertEqual(R(s(market="team_total", team="away", side="under", line=24.5)), "W")
        self.assertEqual(R(s(market="team_total", team="away", side="over", line=24)), "P")

    def test_halves_ot_only_in_second_half(self):
        self.assertEqual(period_points(NFL, "home", "H1"), 17)
        self.assertEqual(period_points(NFL, "home", "H2"), 10)  # 0+7+3 OT
        self.assertEqual(R(s(market="total", side="over", period="H1", line=26.5)), "W")  # 27
        self.assertEqual(R(s(market="total", side="under", period="H2", line=34)), "W")    # 10+14=24

    def test_quarters_exclude_ot(self):
        self.assertEqual(period_points(NFL, "home", "Q4"), 7)

    def test_cbb_halves_and_no_quarters(self):
        self.assertEqual(period_points(CBB, "home", "H2"), 45)  # 39 + 6 OT
        self.assertEqual(R(c(market="moneyline", side="away", period="H1"), CBB), "W")
        with self.assertRaisesRegex(SettlementInputError, "PERIOD_NOT_PLAYED_IN_SPORT"):
            settle(c(market="total", side="over", period="Q1", line=30), CBB)

    def test_period_scores_must_sum_to_final(self):
        bad = dict(NFL, home_periods=[7, 10, 0, 7, 0])
        with self.assertRaisesRegex(SettlementInputError, "DO_NOT_SUM"):
            settle(s(market="total", side="over", period="H1", line=1), bad)

    def test_missing_period_scores_ungraded(self):
        ev = {k: v for k, v in NFL.items() if not k.endswith("_periods")}
        self.assertEqual(R(s(market="total", side="over", period="H1", line=20.5), ev), "UNGRADED")
        self.assertEqual(R(s(market="total", side="over", line=50.5), ev), "W")


class StatusAndMoney(unittest.TestCase):
    def test_void_and_not_final(self):
        for st in ("cancelled", "canceled"):
            r = settle(s(market="moneyline", side="home"), dict(NFL, status=st))
            self.assertEqual((r.result, r.profit_units), ("VOID", 0.0))
        # Book rules for these depend on resumption / decided markets: never an irreversible VOID.
        for st in ("postponed", "abandoned", "suspended"):
            r = settle(s(market="moneyline", side="home"), dict(NFL, status=st))
            self.assertEqual((r.result, r.profit_units), ("UNGRADED", 0.0))
        self.assertEqual(R(s(market="moneyline", side="home"), dict(NFL, status="in_progress")), "UNGRADED")

    def test_profit_units(self):
        self.assertAlmostEqual(settle(s(market="moneyline", side="home", price=150), NFL).profit_units, 1.5)
        self.assertAlmostEqual(settle(s(market="moneyline", side="home"), NFL).profit_units, 100 / 110)
        self.assertEqual(settle(s(market="moneyline", side="away"), NFL).profit_units, -1.0)
        self.assertEqual(settle(s(market="spread", side="home", line=-3), NFL).profit_units, 0.0)

    def test_bad_price_and_event_mismatch_refused(self):
        for p in (0, 99, -110.5, "x", None, True):
            with self.subTest(p=p), self.assertRaises(SettlementInputError):
                settle(s(market="moneyline", side="home", price=p), NFL)
        with self.assertRaisesRegex(SettlementInputError, "EVENT_ID_MISMATCH"):
            settle(s(market="moneyline", side="home", event_id="E2"), NFL)

    def test_record_is_immutable_paper_and_hashes_original(self):
        sel = s(market="moneyline", side="home", model_p=0.61, model_version="v1")
        r = settle(sel, NFL)
        sel["price"] = 500
        self.assertEqual(r.selection["price"], -110)
        with self.assertRaises(TypeError):
            r.selection["price"] = 1
        with self.assertRaises(Exception):
            r.result = "L"
        self.assertEqual((r.state, r.official_counted, r.approved_stake_u), ("PAPER_0U_NON_COUNTED", 0, 0))
        self.assertEqual(r.selection["model_version"], "v1")
        self.assertEqual(len(r.selection_sha256), 64)

    def test_bad_side_refused(self):
        with self.assertRaises(SettlementInputError):
            settle(s(market="total", side="home", line=50.5), NFL)


BOX = {"WR1": {"participated": True, "team": "HOM", "receiving_yards": 55, "receptions": 5,
               "rushing_yards": 0, "rushing_tds": 0, "receiving_tds": 1, "special_teams_tds": 0},
       "QB1": {"participated": True, "team": "HOM", "passing_yards": 250, "passing_tds": 3,
               "rushing_tds": 0, "receiving_tds": 0, "special_teams_tds": 0},
       "RB9": {"participated": False, "team": "AWY"}}


class PlayerMarkets(unittest.TestCase):
    def p(self, **kw):
        return R(s(**kw), NFL, BOX)

    def test_over_under_and_integer_push(self):
        self.assertEqual(self.p(market="rec_yds", player_id="WR1", side="over", line=54.5), "W")
        self.assertEqual(self.p(market="rec_yds", player_id="WR1", side="under", line=54.5), "L")
        self.assertEqual(self.p(market="rec_yds", player_id="WR1", side="over", line=55), "P")

    def test_combo_prop(self):
        self.assertEqual(self.p(market="rush_rec_yds", player_id="WR1", side="over", line=54.5), "W")

    def test_dnp_is_void_never_loss(self):
        r = settle(s(market="rush_yds", player_id="RB9", side="over", line=40.5), NFL, BOX)
        self.assertEqual((r.result, r.reason, r.profit_units), ("VOID", "PLAYER_DID_NOT_PARTICIPATE", 0.0))
        self.assertEqual(self.p(market="anytime_td", player_id="RB9", side="yes"), "VOID")

    def test_missing_player_or_stat_is_ungraded_not_zero(self):
        self.assertEqual(self.p(market="rec_yds", player_id="NOPE", side="under", line=0.5), "UNGRADED")
        self.assertEqual(self.p(market="rush_yds", player_id="QB1", side="under", line=0.5), "UNGRADED")
        self.assertEqual(R(s(market="rec_yds", player_id="WR1", side="over", line=1.5), NFL, None), "UNGRADED")

    def test_props_never_from_team_totals(self):
        # no box score supplied -> never inferred from the team's points
        r = settle(s(market="pass_yds", player_id="QB1", side="under", line=300.5), NFL, {})
        self.assertEqual(r.result, "UNGRADED")

    def test_td_markets_exclude_passing_tds(self):
        self.assertEqual(self.p(market="anytime_td", player_id="WR1", side="yes"), "W")
        self.assertEqual(self.p(market="td_2plus", player_id="WR1", side="yes"), "L")
        self.assertEqual(self.p(market="anytime_td", player_id="QB1", side="yes"), "L")  # 3 passing TDs
        self.assertEqual(self.p(market="anytime_td", player_id="QB1", side="no"), "W")

    def test_player_team_mismatch_refused(self):
        with self.assertRaisesRegex(SettlementInputError, "PLAYER_TEAM_MISMATCH"):
            settle(s(market="rec_yds", player_id="WR1", team="AWY", side="over", line=1.5), NFL, BOX)

    def test_unknown_participation_ungraded(self):
        box = {"X": {"team": "HOM", "receiving_yards": 10}}
        self.assertEqual(R(s(market="rec_yds", player_id="X", side="over", line=5.5), NFL, box), "UNGRADED")


class RealNflverse(unittest.TestCase):
    """Real public data check; skipped where /tmp/nflv is not present (CI)."""
    def test_real_week_grades_from_box_score(self):
        f = sorted(glob.glob("/tmp/nflv/ps_2024.csv.gz"))
        if not f:
            self.skipTest("nflverse fixture not present")
        rows = list(csv.DictReader(gzip.open(f[0], "rt")))
        box = nflverse_players(rows, 2024, 1)
        self.assertGreater(len(box), 300)
        pid, rec = next((k, v) for k, v in box.items() if float(v.get("receiving_yards") or 0) >= 50)
        y = float(rec["receiving_yards"])
        ev = dict(NFL)
        self.assertEqual(R(s(market="rec_yds", player_id=pid, side="over", line=y - 0.5), ev, box), "W")
        self.assertEqual(R(s(market="rec_yds", player_id=pid, side="over", line=y), ev, box), "P")
        self.assertEqual(R(s(market="rec_yds", player_id="00-NOT-REAL", side="over", line=1.5), ev, box), "UNGRADED")

    def test_real_td_scorer_uses_all_categories(self):
        """2024 W1 Mike Evans (TB): 2 receiving TDs, all three TD categories present."""
        f = sorted(glob.glob("/tmp/nflv/ps_2024.csv.gz"))
        if not f:
            self.skipTest("nflverse fixture not present")
        rows = list(csv.DictReader(gzip.open(f[0], "rt")))
        pid = next(r["player_id"] for r in rows if r["season"] == "2024" and r["week"] == "1"
                   and r["player_display_name"] == "Mike Evans")
        box = nflverse_players(rows, 2024, 1)
        self.assertEqual(R(s(market="td_2plus", player_id=pid, side="yes"), NFL, box), "W")
        self.assertEqual(R(s(market="td_3plus", player_id=pid, side="yes"), NFL, box), "L")
        partial = {pid: {k: v for k, v in box[pid].items() if k != "receiving_tds"}}
        self.assertEqual(R(s(market="anytime_td", player_id=pid, side="yes"), NFL, partial), "UNGRADED")


if __name__ == "__main__":
    unittest.main()
