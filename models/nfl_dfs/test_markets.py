"""Regression checks for DFS shared-sim market settlement and coverage.
No live book lines are imported; no claim about contest ROI or positive EV.

test_book_ev's cases are imported below so this module (already a CI step)
also runs them; unittest.main() collects every TestCase in the namespace.
"""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import markets as m
import book_ev
from test_book_ev import T as BookEvTests  # noqa: F401  (collected by unittest)


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
        scores=[(21,24),(22,23),(24,21),(25,19)]
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
        self.assertNotIn("book",out)
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

    def test_shared_raw_stream_and_moneyline_tie_condition(self):
        cfg={"tag":"ties","teams":{"AWY":{},"HOM":{}},
             "market":{"spread_home":3.5,"total":44.5},"players":{}}
        scores=[(20,27),(24,24),(17,31),(30,14)]
        def fake_run(cfg,n,seed=7,raw=None):
            raw.extend({"AWY":({},a),"HOM":({},h)} for a,h in scores)
            return {},scores
        with mock.patch.object(m.mc,"run",side_effect=fake_run) as runner:
            out=m.price(cfg,4,seed=7)
            runner.assert_called_once()
        self.assertEqual(out["game"]["moneyline"]["HOM"],m.american(2/3))
        self.assertEqual(out["game"]["moneyline"]["AWY"],m.american(1/3))
        self.assertEqual(out["game"]["p_tie"],0.25)
        self.assertEqual(out["game"]["HOM team total fair"],26.0)
        self.assertEqual(out["game"]["HOM over 26.0"],0.5)

    def test_lines_file_adds_book_block_from_same_single_run(self):
        cfg={"tag":"bk","teams":{"AWY":{},"HOM":{}},
             "market":{"spread_home":3.5,"total":44.5},"players":{}}
        scores=[(20,27),(24,24),(17,31),(30,14)]
        def fake_run(cfg,n,seed=7,raw=None):
            raw.extend({"AWY":({},a),"HOM":({},h)} for a,h in scores)
            return {},scores
        lines={"tag":"bk","source":"TEST","captured_at_utc":"2026-11-15T22:00:00Z",
               "markets":[{"market":"total","line":44.5,"over":-110,"under":-110},
                          {"market":"first_td","player":"X","yes":900}]}
        with mock.patch.object(m.mc,"run",side_effect=fake_run) as runner:
            out=m.price(cfg,4,lines=lines)
            runner.assert_called_once()
        self.assertTrue(out["book_prices_available"])
        self.assertIn("UNVALIDATED",out["market_ev"])
        self.assertIn("UNAUTHENTICATED",out["inventory"]["source_status"])
        book=out["book"]
        self.assertEqual(book["sims"],4)
        self.assertEqual(len(book["rows"]),2)
        self.assertEqual(len(book["unpriced"]),1)
        self.assertTrue(book["unpriced"][0]["reason"].startswith("NOT_MODELED_MARKET"))
        # totals 47,48,48,44: over 44.5 wins in 3 of 4 sims
        over=[r for r in book["rows"] if r["side"]=="over"][0]
        self.assertEqual(over["model"]["p_win"],0.75)
        # game block is identical with and without lines (same sims, same seed)
        with mock.patch.object(m.mc,"run",side_effect=fake_run):
            base=m.price(cfg,4)
        self.assertEqual(base["game"],out["game"])
        self.assertEqual(base["props"],out["props"])

    def test_lines_for_wrong_game_fail_closed(self):
        cfg={"tag":"bk","teams":{"AWY":{},"HOM":{}},
             "market":{"spread_home":3.5,"total":44.5},"players":{}}
        def fake_run(cfg,n,seed=7,raw=None):
            raw.extend({"AWY":({},a),"HOM":({},h)} for a,h in [(20,27),(24,24)])
            return {},[]
        bad={"tag":"other","source":"TEST","captured_at_utc":"t","markets":[]}
        with mock.patch.object(m.mc,"run",side_effect=fake_run):
            with self.assertRaises(book_ev.LinesError):
                m.price(cfg,2,lines=bad)

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
    import subprocess,sys
    subprocess.run([sys.executable,"test_usage_share_features.py"],check=True)
    unittest.main()
