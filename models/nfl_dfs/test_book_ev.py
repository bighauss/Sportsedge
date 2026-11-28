"""Synthetic checks for book_ev.py. No real prices; no claim about edge."""
import unittest
import book_ev as b

CFG = {"tag": "fx", "teams": {"AWY": {}, "HOM": {}},
       "players": {"QB1": {"team": "HOM", "pos": "QB"},
                   "WR1": {"team": "HOM", "pos": "WR"},
                   "K1": {"team": "HOM", "pos": "K"}}}
PROPS = {"pass_yds": lambda s: s["py"], "pass_tds": lambda s: s["ptd"],
         "rush_yds": lambda s: s["ry"], "rec_yds": lambda s: s["rcy"],
         "receptions": lambda s: s["rec"],
         "anytime_td": lambda s: s["rtd"] + s["rctd"]}


def st(py=0, rcy=0, rctd=0):
    return {"py": py, "ptd": 0, "ry": 0, "rcy": rcy, "rec": 0, "rtd": 0, "rctd": rctd}


def raw4():
    scores = [(20, 27), (24, 24), (17, 31), (30, 14)]
    tds = [0, 1, 2, 0]
    return [{"AWY": ({}, a),
             "HOM": ({"QB1": st(py=250 + 10 * i), "WR1": st(rcy=60, rctd=tds[i])}, h)}
            for i, (a, h) in enumerate(scores)]


def lines(markets):
    return {"tag": "fx", "source": "TEST", "captured_at_utc": "2026-11-15T22:00:00Z",
            "markets": markets}


def run(markets):
    return b.price_lines(CFG, raw4(), "AWY", "HOM", lines(markets), PROPS)


class T(unittest.TestCase):
    def test_odds_math(self):
        self.assertAlmostEqual(b.profit_per_unit(-110), 100 / 110)
        self.assertAlmostEqual(b.profit_per_unit(150), 1.5)
        self.assertAlmostEqual(b.implied(-200), 2 / 3)
        for bad in (0, 50, -50, True, float("nan"), "x"):
            with self.assertRaises(ValueError):
                b.profit_per_unit(bad)
        qa, qb = b.devig(-110, -110)
        self.assertAlmostEqual(qa, .5)
        self.assertAlmostEqual(qa + qb, 1)

    def test_total_push_and_ev(self):
        # totals 47,48,48,44 -> over 48: 0 win, 2 push, 2 lose
        out = run([{"market": "total", "line": 48, "over": 100, "under": 100}])
        o = [r for r in out["rows"] if r["side"] == "over"][0]
        self.assertEqual(o["model"], {"p_win": 0.0, "p_push": 0.5, "p_lose": 0.5})
        self.assertAlmostEqual(o["ev_raw"], -0.5)
        u = [r for r in out["rows"] if r["side"] == "under"][0]
        self.assertAlmostEqual(u["model"]["p_win"], .5)
        self.assertAlmostEqual(u["ev_raw"], .5)  # win +1 at +100, push returns stake
        self.assertEqual(out["rows"][0]["side"], "under")
        self.assertEqual(out["rows"][0]["rank"], 1)

    def test_blended_ev_matches_hand_calc(self):
        out = run([{"market": "total", "line": 48, "over": -110, "under": -110}])
        u = [r for r in out["rows"] if r["side"] == "under"][0]
        b_ = 100 / 110
        self.assertAlmostEqual(u["model"]["p_push"], .5)
        nonpush = u["model"]["p_win"] + u["model"]["p_lose"]
        cond = .4 * (u["model"]["p_win"] / nonpush) + .6 * .5
        self.assertAlmostEqual(u["ev_blended"], round(nonpush * (cond * (b_ + 1) - 1), 4), places=4)

    def test_moneyline_ties_push(self):
        out = run([{"market": "moneyline", "prices": {"HOM": -200, "AWY": 170}}])
        h = [r for r in out["rows"] if r["side"] == "HOM"][0]
        self.assertEqual(h["model"], {"p_win": 0.5, "p_push": 0.25, "p_lose": 0.25})

    def test_spread_uses_book_line(self):
        # margins 7,0,14,-16. Home -6.5 covers when margin>6.5 -> 2/4
        out = run([{"market": "spread", "home_line": -6.5, "home": -110, "away": -110}])
        h = [r for r in out["rows"] if r["side"] == "HOM"][0]
        self.assertEqual(h["model"]["p_win"], .5)
        self.assertEqual(h["line"], -6.5)
        a = [r for r in out["rows"] if r["side"] == "AWY"][0]
        self.assertEqual(a["model"]["p_win"], .5)
        # whole-number line pushes: home -7 pushes on margin 7 only
        out = run([{"market": "spread", "home_line": -7, "home": -110, "away": -110}])
        h = [r for r in out["rows"] if r["side"] == "HOM"][0]
        self.assertEqual(h["model"], {"p_win": .25, "p_push": .25, "p_lose": .5})

    def test_player_props_and_td_yes_no(self):
        out = run([{"market": "anytime_td", "player": "WR1", "yes": 100, "no": -120},
                   {"market": "td_2plus", "player": "WR1", "yes": 400},
                   {"market": "pass_yds", "player": "QB1", "line": 264.5,
                    "over": -115, "under": -105}])
        yes = [r for r in out["rows"] if r["market"] == "anytime_td" and r["side"] == "yes"][0]
        self.assertEqual(yes["model"]["p_win"], .5)
        two = out["rows"][[r["market"] for r in out["rows"]].index("td_2plus")]
        self.assertEqual(two["model"]["p_win"], .25)
        self.assertIn("ONE_SIDED_VIG_INCLUDED", two["flags"])
        self.assertLessEqual(two["stars"], 3)
        py = [r for r in out["rows"] if r["market"] == "pass_yds" and r["side"] == "over"][0]
        self.assertEqual(py["model"]["p_win"], .5)  # 250,260,270,280 > 264.5 -> 2/4

    def test_unpriced_reasons_never_guessed(self):
        out = run([{"market": "pass_yds", "player": "WR1", "line": 10.5, "over": -110},
                   {"market": "anytime_td", "player": "Nobody", "yes": 100},
                   {"market": "anytime_td", "player": "K1", "yes": 100},
                   {"market": "first_td", "player": "WR1", "yes": 900},
                   {"market": "total", "line": 45.5, "over": 50},
                   {"market": "team_total", "team": "XXX", "line": 20.5, "over": -110}])
        reasons = [u["reason"] for u in out["unpriced"]]
        self.assertEqual(len(reasons), 6)
        self.assertTrue(any(r.startswith("NOT_MODELED_NON_QB") for r in reasons))
        self.assertTrue(any(r.startswith("NOT_MODELED_PLAYER") for r in reasons))
        self.assertTrue(any(r.startswith("NOT_MODELED_POSITION") for r in reasons))
        self.assertTrue(any(r.startswith("NOT_MODELED_MARKET") for r in reasons))
        self.assertTrue(any(r.startswith("INVALID_AMERICAN_ODDS") for r in reasons))
        self.assertTrue(any(r.startswith("UNKNOWN_TEAM") for r in reasons))
        self.assertEqual(out["rows"], [])

    def test_provenance_and_tag_required(self):
        for bad in ({"tag": "other", "source": "x", "captured_at_utc": "t", "markets": []},
                    {"tag": "fx", "captured_at_utc": "t", "markets": []},
                    {"tag": "fx", "source": "x", "markets": []},
                    {"tag": "fx", "source": "x", "captured_at_utc": "t"}):
            with self.assertRaises(b.LinesError):
                b.price_lines(CFG, raw4(), "AWY", "HOM", bad, PROPS)

    def test_stars_rules(self):
        self.assertEqual(b.stars_for(-.01, .05, 0, False), 0)
        self.assertEqual(b.stars_for(.1, -.01, 0, False), 0)
        self.assertEqual(b.stars_for(.1, .07, 0, False), 5)
        self.assertEqual(b.stars_for(.1, .07, 0, True), 3)
        self.assertEqual(b.stars_for(.02, .07, .05, False), 1)
        self.assertEqual(b.stars_for(.1, .005, 0, False), 1)

    def test_ranking_descending_by_blended_ev(self):
        out = run([{"market": "total", "line": 48, "over": -110, "under": -110},
                   {"market": "moneyline", "prices": {"HOM": -200, "AWY": 170}},
                   {"market": "anytime_td", "player": "WR1", "yes": 100, "no": -120}])
        ev = [r["ev_blended"] for r in out["rows"]]
        self.assertEqual(ev, sorted(ev, reverse=True))
        self.assertEqual([r["rank"] for r in out["rows"]], list(range(1, len(ev) + 1)))
        self.assertEqual(out["status"], "RESEARCH_PAPER_UNVALIDATED")


class DuplicateQuotes(unittest.TestCase):
    """Duplicate board entries must not double-count or price conflicting quotes."""
    TOT = {"market": "total", "line": 45.5, "over": -110, "under": -110}

    def test_identical_duplicates_collapse_to_one_selection(self):
        out = run([dict(self.TOT), dict(self.TOT), dict(self.TOT)])
        self.assertEqual(len(out["rows"]), 2)
        self.assertEqual([u["reason"] for u in out["unpriced"]], ["DUPLICATE_QUOTE_COLLAPSED"] * 2)

    def test_conflicting_duplicates_are_all_withheld(self):
        out = run([dict(self.TOT), dict(self.TOT, over=-125, under=105)])
        self.assertEqual(out["rows"], [])
        self.assertEqual([u["reason"] for u in out["unpriced"]], ["DUPLICATE_CONFLICTING_QUOTE"] * 2)

    def test_conflicting_player_prop_duplicates_withheld(self):
        a = {"market": "pass_yds", "player": "QB1", "line": 255.5, "over": -110, "under": -110}
        out = run([a, dict(a, over=120, under=-150)])
        self.assertEqual(out["rows"], [])

    def test_distinct_lines_are_not_duplicates(self):
        out = run([dict(self.TOT), dict(self.TOT, line=48.5)])
        self.assertEqual(len(out["rows"]), 4)
        self.assertEqual(out["unpriced"], [])

    def test_duplicate_spread_and_moneyline(self):
        sp = {"market": "spread", "home_line": -3.5, "home": -110, "away": -110}
        ml = {"market": "moneyline", "prices": {"HOM": -150, "AWY": 130}}
        out = run([sp, dict(sp), ml, {"market": "moneyline", "prices": {"HOM": -160, "AWY": 140}}])
        self.assertEqual(sorted({r["market"] for r in out["rows"]}), ["spread"])
        self.assertEqual(len(out["rows"]), 2)

    def test_board_order_does_not_change_rows(self):
        ms = [dict(self.TOT), {"market": "spread", "home_line": -3.5, "home": -110, "away": -110},
              dict(self.TOT)]
        self.assertEqual(run(ms)["rows"], run(list(reversed(ms)))["rows"])


if __name__ == "__main__":
    unittest.main()
