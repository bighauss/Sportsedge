"""Adversarial regressions for review findings on PR #574 (ChatGPT source review,
issuecomment-7241257599). Each test failed on head 308940b before the repair."""
import os, sys, unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from sportsedge.grading.settlement import SettlementInputError, settle

EV = {"sport": "NFL", "status": "final", "event_id": "nfl:2026:W12:KC@BUF",
      "home_score": 27, "away_score": 24,
      "home_periods": [7, 10, 0, 7, 3], "away_periods": [3, 7, 14, 0, 0]}


def sel(**kw):
    return dict({"sport": "NFL", "event_id": EV["event_id"], "price": -110, "period": "FG"}, **kw)


def full_td(**kw):
    return dict({"participated": True, "rushing_tds": 0, "receiving_tds": 0,
                 "special_teams_tds": 0}, **kw)


class IncompleteTouchdownStats(unittest.TestCase):
    """Finding 1: a missing TD category silently counted as zero -> wrong LOSS."""

    def test_missing_receiving_category_is_not_a_loss(self):
        # Receiver scored a receiving TD, but the box row only carries rushing_tds.
        players = {"P1": {"participated": True, "rushing_tds": 0}}
        g = settle(sel(market="anytime_td", side="yes", player_id="P1"), EV, players)
        self.assertEqual(g.result, "UNGRADED")
        self.assertEqual(g.reason, "TD_FIELDS_INCOMPLETE")

    def test_missing_return_category_is_not_a_win_for_no(self):
        players = {"P1": {"participated": True, "rushing_tds": 0, "receiving_tds": 0}}
        g = settle(sel(market="anytime_td", side="no", player_id="P1"), EV, players)
        self.assertEqual(g.result, "UNGRADED")

    def test_complete_categories_still_grade(self):
        players = {"P1": full_td(receiving_tds=1)}
        self.assertEqual(settle(sel(market="anytime_td", side="yes", player_id="P1"), EV, players).result, "W")
        self.assertEqual(settle(sel(market="td_2plus", side="yes", player_id="P1"), EV, players).result, "L")

    def test_negative_or_fractional_td_counts_rejected(self):
        for bad in (-1, 0.5):
            with self.assertRaises(SettlementInputError):
                settle(sel(market="anytime_td", side="yes", player_id="P1"), EV, {"P1": full_td(rushing_tds=bad)})


class EventIdentity(unittest.TestCase):
    """Finding 2a: settle() accepted a selection with no event identity."""

    def test_selection_without_event_id_rejected(self):
        s = sel(market="moneyline", side="home"); s.pop("event_id")
        with self.assertRaises(SettlementInputError):
            settle(s, EV)

    def test_event_without_event_id_rejected(self):
        ev = dict(EV); ev.pop("event_id")
        with self.assertRaises(SettlementInputError):
            settle(sel(market="moneyline", side="home"), ev)

    def test_sport_mismatch_rejected(self):
        with self.assertRaises(SettlementInputError):
            settle(sel(market="moneyline", side="home", sport="CFB"), EV)

    def test_selection_without_sport_rejected(self):
        s = sel(market="moneyline", side="home"); s.pop("sport")
        with self.assertRaises(SettlementInputError):
            settle(s, EV)


class FinalScoreValidation(unittest.TestCase):
    """Finding 2b: a half settled even when a final score was missing."""

    def test_half_with_missing_final_score_not_settled(self):
        ev = dict(EV); ev.pop("away_score")
        g = settle(sel(market="total", side="over", period="H1", line=20.5), ev)
        self.assertEqual(g.result, "UNGRADED")
        self.assertEqual(g.reason, "FINAL_SCORE_MISSING")

    def test_player_prop_requires_final_scores_too(self):
        ev = dict(EV); ev.pop("home_score")
        g = settle(sel(market="rec_yds", side="over", line=50.5, player_id="P1"), ev,
                   {"P1": {"participated": True, "receiving_yards": 80}})
        self.assertEqual(g.result, "UNGRADED")

    def test_negative_final_score_rejected(self):
        with self.assertRaises(SettlementInputError):
            settle(sel(market="moneyline", side="home"), dict(EV, home_score=-3))

    def test_fractional_final_score_rejected(self):
        with self.assertRaises(SettlementInputError):
            settle(sel(market="moneyline", side="home"), dict(EV, home_score=27.5))

    def test_negative_period_score_rejected(self):
        ev = dict(EV, home_periods=[7, 10, -1, 8, 3])
        with self.assertRaises(SettlementInputError):
            settle(sel(market="total", side="over", period="H1", line=20.5), ev)

    def test_boolean_score_rejected(self):
        with self.assertRaises(SettlementInputError):
            settle(sel(market="moneyline", side="home"), dict(EV, home_score=True))


class MoneylineWays(unittest.TestCase):
    """Finding 3a: two-way vs three-way moneyline must be explicit."""

    def test_three_way_moneyline_refused(self):
        with self.assertRaises(SettlementInputError):
            settle(sel(market="moneyline", side="home", ways=3), EV)

    def test_draw_side_refused(self):
        with self.assertRaises(SettlementInputError):
            settle(sel(market="moneyline", side="draw"), EV)

    def test_explicit_two_way_allowed(self):
        self.assertEqual(settle(sel(market="moneyline", side="home", ways=2), EV).result, "W")


class IrreversibleStatuses(unittest.TestCase):
    """Finding 3b: postponed/abandoned must not be settled VOID irreversibly before the
    applicable book rule is confirmed. Only cancelled is a final VOID."""

    def test_postponed_is_ungraded_not_void(self):
        g = settle(sel(market="moneyline", side="home"), dict(EV, status="postponed"))
        self.assertEqual(g.result, "UNGRADED")
        self.assertTrue(g.reason.startswith("EVENT_POSTPONED"))

    def test_abandoned_is_ungraded_not_void(self):
        g = settle(sel(market="moneyline", side="home"), dict(EV, status="abandoned"))
        self.assertEqual(g.result, "UNGRADED")

    def test_cancelled_is_void(self):
        self.assertEqual(settle(sel(market="moneyline", side="home"), dict(EV, status="cancelled")).result, "VOID")

    def test_suspended_is_ungraded(self):
        self.assertEqual(settle(sel(market="moneyline", side="home"), dict(EV, status="suspended")).result,
                         "UNGRADED")


if __name__ == "__main__":
    unittest.main()
