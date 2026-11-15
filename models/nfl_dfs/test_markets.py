"""Regression checks for DFS shared-sim market settlement and coverage.
No live book lines are imported; no claim about contest ROI or positive EV.
"""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import markets as m


def rawstat(rtd=0, rctd=0):
    return {"py":0, "ptd":0, "ry":0, "rcy":0, "rec":0,
            "rtd":rtd, "rctd":rctd}


class MarketsTests(unittest.TestCase):
    def test_no_finite_odds_at_sample_extremes(self):
        self.assertIsNone(m.american(0))
        self.assertIsNone(m.american(1))
        self.assertEqual(m.american(0.5), -100)
        self.assertEqual(m.american(0.25), 300)
        self.assertEqual(m.american(0.75), -300)

    def test_pushes_are_separate_from_win_probabilities(self):
        cfg={"tag":"fixture", "teams":{"AWY":{}, "HOM":{}},
             "market":{"spread_home":3,"total":45},"players":{}}
        scores=[(21,24),(22,23),(24,21),(25,20)]
        def fake_run(cfg,n,seed=7,raw=None):
            self.assertEqual(n,4)
            raw.extend({"AWY":({},a),"HOM":({},h)} for a,h in scores)
            return {},scores
        with mock.patch.object(m.mc,"run",side_effect=fake_run):
            out=m.price(cfg,4)
        self.assertEqual(out["game"]["total_settlement"],
                         {"over":0.0, "under":0.25, "push":0.75})
        self.assertEqual(out["game"]["spread_settlement"],
                         {"home_cover":0.0,"away_cover":0.75,"push":0.25})
        self.assertEqual(out["game"]["p_tie"],0.0)
        self.assertFalse(out["book_prices_available"])
        self.assertIn("NO_ORDERED_SCORE_EVENTS",out["inventory"]["blocked"]["first_td"])
        self.assertIn("NO_PERIOD_SIMULATION",out["inventory"]["blocked"]["quarters"])
        self.assertIn("NOT_CAPTURED",out["inventory"]["blocked"]["alternate_lines"])
        self.assertIn("BLOCKED",out["market_ev"])

    def test_two_plus_touchdowns_on_exact_same_scenarios(self):
        cfg={"tag":"tds","teams":{"AWY":{},"HOM":{}},
             "market":{"spread_home":3.5,"total":44.5},
             "players":{"Test WR":{"team":"HOM","pos":"WR"}}}
        scores=[(20,23),(21,24),(22,25),(23,26)]
        count=[0,1,2,3]
        def fake_run(cfg,n,seed=7,raw=None):
            for (a,h),v in zip(scores,count):
                raw.append({"AWY":({},a),"HOM":({"Test WR":rawstat(rctd=v)},h)})
            return {"Test WR":[0.0]*4},scores
        with mock.patch.object(m.mc,"run",side_effect=fake_run):
            out=m.price(cfg,4)
        p={p["market"]:p for p in out["props"]}
        self.assertEqual(p["anytime_td"]["p_yes"],0.75)
        self.assertEqual(p["td_2plus"]["p_yes"],0.5)
        self.assertEqual(p["anytime_td"]["fair"],-300)
        self.assertEqual(p["td_2plus"]["fair"],-100)

    def test_current_owner_config_deterministic_and_research_only(self):
        here=Path(__file__).resolve().parent
        cfg=json.loads((here/"games"/"PIT_CIN_2026-11-15.json").read_text())
        a=m.price(cfg,100,seed=7)
        b=m.price(cfg,100,seed=7)
        self.assertEqual(a,b)
        self.assertEqual(a["label"],"RESEARCH / PAPER")
        self.assertIn("NO_AUTHENTICATED",a["market_ev"])
        self.assertEqual(set(a["game"]["spread_settlement"]),
                         {"home_cover","away_cover","push"})
        self.assertAlmostEqual(sum(a["game"]["spread_settlement"].values()),1,places=3)
        self.assertAlmostEqual(sum(a["game"]["total_settlement"].values()),1,places=3)
        self.assertNotIn("AvgPointsPerGame",json.dumps(a))
        self.assertTrue(all(row.get("player") in cfg["players"] for row in a["props"]))

    def test_invalid_simulation_count_fails(self):
        with self.assertRaises(ValueError):
            m.price({"teams":{"a":{},"b":{}}},0)
        with self.assertRaises(ValueError):
            m.price({"teams":{"a":{}}},10)


if __name__=="__main__":
    unittest.main()
