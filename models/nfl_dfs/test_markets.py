"""Synthetic-only invariants for the shared DFS/market simulation.

These checks do NOT authenticate book prices, calibrate probabilities, or permit stakes.
Run from models/nfl_dfs: python -m unittest test_markets.py
"""
import math
import unittest
from unittest.mock import patch

import markets


def stat(**kw):
    s = dict(py=0, ptd=0, ints=0, ry=0, rtd=0, rec=0, rcy=0, rctd=0, fum=0)
    s.update(kw)
    return s


class MarketsSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "tag": "SYNTHETIC_NO_BOOK_PRICES",
            "teams": {"PIT": {}, "CIN": {}},
            "market": {"spread_home": 3.5, "total": 40.5},
            "players": {
                "QB A": {"team": "PIT", "pos": "QB"},
                "WR A": {"team": "PIT", "pos": "WR"},
                "QB B": {"team": "CIN", "pos": "QB"},
                "WR B": {"team": "CIN", "pos": "WR"},
                "K B": {"team": "CIN", "pos": "K"},
            },
        }
        self.samples = [
            {"PIT": ({"QB A": stat(py=200, ptd=1), "WR A": stat(rcy=60, rec=5, rctd=1)}, 20),
             "CIN": ({"QB B": stat(py=260, ptd=2), "WR B": stat(rcy=80, rec=7, rctd=1)}, 27)},
            {"PIT": ({"QB A": stat(py=240), "WR A": stat(rcy=40, rec=4)}, 24),
             "CIN": ({"QB B": stat(py=180), "WR B": stat(rcy=30, rec=3)}, 24)},
            {"PIT": ({"QB A": stat(py=190), "WR A": stat(rcy=20, rec=2)}, 17),
             "CIN": ({"QB B": stat(py=310, ptd=3), "WR B": stat(rcy=110, rec=9, rtd=1, rctd=1)}, 31)},
            {"PIT": ({"QB A": stat(py=280, ptd=2), "WR A": stat(rcy=100, rec=8, rctd=1)}, 30),
             "CIN": ({"QB B": stat(py=170), "WR B": stat(rcy=10, rec=1)}, 14)},
        ]

    def priced(self):
        def fake_run(cfg, n, seed=7, raw=None):
            self.assertEqual(n, len(self.samples))
            self.assertEqual(seed, 7)
            self.assertIsNotNone(raw)
            raw.extend(self.samples)
            return {}, []
        with patch.object(markets.mc, "run", side_effect=fake_run) as runner:
            result = markets.price(self.cfg, len(self.samples), seed=7)
            runner.assert_called_once()
        return result

    def test_uses_exactly_one_shared_sim_stream(self):
        r = self.priced()
        self.assertEqual(r["sims"], 4)
        self.assertEqual(r["label"], "RESEARCH / PAPER")
        self.assertEqual(r["game"]["proj"]["PIT"], 22.75)
        self.assertEqual(r["game"]["proj"]["CIN"], 24.0)
        self.assertEqual(r["game"]["proj"]["total"], 46.75)

    def test_moneyline_excludes_ties_without_claiming_settlement(self):
        r = self.priced()
        # Home wins 2, away wins 1, one regulation tie; conditional ML is 2/3.
        self.assertEqual(r["game"]["moneyline"]["CIN"], markets.american(2 / 3))
        self.assertEqual(r["game"]["moneyline"]["PIT"], markets.american(1 / 3))

    def test_spread_and_total_are_strict_cover_not_push(self):
        g = self.priced()["game"]
        self.assertEqual(g["CIN -3.5"], 0.5)
        self.assertEqual(g["over 40.5"], 0.75)

    def test_team_totals_derive_from_same_team_samples(self):
        g = self.priced()["game"]
        self.assertEqual(g["PIT team total fair"], 22.5)
        self.assertEqual(g["PIT over 22.5"], 0.5)
        self.assertEqual(g["CIN team total fair"], 26.0)
        self.assertEqual(g["CIN over 26.0"], 0.5)

    def test_prop_stat_identity_and_td_union(self):
        props = self.priced()["props"]
        by = {(x["player"], x["market"]): x for x in props}
        self.assertEqual(by[("WR B", "anytime_td")]["p_yes"], 0.5)
        self.assertEqual(by[("WR A", "anytime_td")]["p_yes"], 0.5)
        self.assertEqual(by[("QB B", "pass_tds")]["mean"], 1.25)
        self.assertEqual(by[("WR A", "receptions")]["mean"], 4.75)
        self.assertNotIn(("K B", "anytime_td"), by)

    def test_no_book_ev_or_stake_in_result(self):
        r = self.priced()
        serialized = str(r).lower()
        for forbidden in ("book_price", "roi", "stake", "ownership", "expected_value"):
            self.assertNotIn(forbidden, serialized)

    def test_american_implied_round_trip_at_supported_odds(self):
        for odds in (-200, -110, 100, 125, 300):
            p = markets.implied(odds)
            self.assertTrue(math.isfinite(p))
            self.assertLessEqual(abs(markets.american(p) - odds), 1)


if __name__ == "__main__":
    unittest.main()
