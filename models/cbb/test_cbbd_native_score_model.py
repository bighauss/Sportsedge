"""OFFLINE synthetic tests for the CBBD-native score model. Not predictive validation."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import unittest

import cbbd_native_score_model as m
from cbbd_paper_synthetic import FREEZE, SEASON, prior_games, ratings_body, ratings_rows


def ctx(**kw):
    args = dict(season=SEASON, freeze_utc=FREEZE)
    args.update(kw)
    body = args.pop("body", ratings_body())
    prior = args.pop("prior", prior_games())
    return m.fit_context(body, prior, **args)


class SeparationTest(unittest.TestCase):
    def test_never_imports_or_names_frozen_v5_or_torvik(self):
        src = Path(m.__file__).read_text()
        for forbidden in ("import sportsedge_cbb_model", "from sportsedge_cbb_model",
                          "import torvik", "from torvik"):
            self.assertNotIn(forbidden, src)

    def test_no_default_hca_constant(self):
        rows = prior_games()
        for g in rows:
            g["neutral"] = True
        c = ctx(prior=rows)
        m.project(c, "1", "2", neutral=True)  # neutral still projects
        self.assertIsNone(c["hca"]["value"])
        with self.assertRaisesRegex(m.Pass, "HCA_UNMEASURED"):
            m.project(c, "1", "2", neutral=False)


class RatingsTest(unittest.TestCase):
    def test_wrong_season_rejected(self):
        with self.assertRaisesRegex(m.Pass, "RATINGS_WRONG_SEASON"):
            m.parse_ratings(ratings_body(season=2026), SEASON)

    def test_duplicate_team_id_rejected(self):
        rows = ratings_rows()
        rows[1]["teamId"] = rows[0]["teamId"]
        with self.assertRaisesRegex(m.Pass, "DUPLICATE_TEAM_ID"):
            m.parse_ratings(json.dumps(rows).encode(), SEASON)

    def test_string_or_zero_team_id_rejected(self):
        for bad in ("1", 0, -3, True):
            rows = ratings_rows()
            rows[0]["teamId"] = bad
            with self.assertRaises(m.Pass):
                m.parse_ratings(json.dumps(rows).encode(), SEASON)

    def test_net_inconsistent_and_duplicate_json_key(self):
        rows = ratings_rows()
        rows[0]["netRating"] += 5
        with self.assertRaisesRegex(m.Pass, "NET_INCONSISTENT"):
            m.parse_ratings(json.dumps(rows).encode(), SEASON)
        with self.assertRaisesRegex(m.Pass, "DUPLICATE_JSON_KEY"):
            m.parse_ratings(b'[{"teamId":1,"teamId":2}]', SEASON)

    def test_unmapped_team_passes(self):
        with self.assertRaisesRegex(m.Pass, "UNMAPPED_CBBD_TEAM_ID"):
            m.project(ctx(), "1", "999", neutral=True)


class LeakageTest(unittest.TestCase):
    def test_future_finals_are_rejected_and_do_not_change_projection(self):
        base = ctx()
        future = deepcopy(prior_games(n=40, start="2026-11-21T14:00:00Z"))
        for i, g in enumerate(future):
            g["game_id"] = str(70000 + i)
            g["home_points"], g["away_points"] = 150, 20  # absurd, must not leak
        leaked = ctx(prior=prior_games() + future)
        self.assertGreater(sum(v for k, v in leaked["prior_game_census"].items()
                               if "FUTURE_FINAL_AFTER_FREEZE" in k), 0)
        for neutral in (True, False):
            self.assertEqual(m.project(base, "1", "2", neutral=neutral),
                             m.project(leaked, "1", "2", neutral=neutral))

    def test_final_captured_exactly_at_freeze_is_future(self):
        g = prior_games(n=1)[0]
        g["tipoff_utc"], g["final_captured_utc"] = "2026-11-21T12:00:00Z", FREEZE
        _, census = m.eligible_prior_games([g], season=SEASON, freeze=m.utc(FREEZE, "f"))
        self.assertEqual(census, {"rejected:FUTURE_FINAL_AFTER_FREEZE": 1})

    def test_prospective_residuals_after_freeze_ignored(self):
        late = [{"final_captured_utc": "2026-11-22T00:00:00Z", "margin_residual": 50.0,
                 "total_residual": 50.0}] * 40
        c = ctx(prior_residuals=late)
        self.assertEqual(c["sd"]["prospective_available"], 0)
        self.assertTrue(c["sd"]["basis"].startswith("RETRO"))

    def test_prospective_residuals_used_when_enough(self):
        early = [{"final_captured_utc": "2026-11-20T00:00:00Z",
                  "margin_residual": float((i % 7) - 3) * 4, "total_residual": float(i % 5) * 3}
                 for i in range(30)]
        c = ctx(prior_residuals=early)
        self.assertEqual(c["sd"]["basis"], "PROSPECTIVE_PRIOR_CARD_RESIDUALS")
        self.assertEqual(c["sd"]["n"], 30)


class PriorGameAdmissionTest(unittest.TestCase):
    def census(self, rows):
        return m.eligible_prior_games(rows, season=SEASON, freeze=m.utc(FREEZE, "f"))[1]

    def test_duplicate_ids_quarantine_every_copy(self):
        rows = prior_games(n=3)
        rows[2]["game_id"] = rows[0]["game_id"]
        self.assertEqual(self.census(rows)["rejected:DUPLICATE_GAME_ID_ALL_COPIES"], 2)

    def test_wrong_season_noncanonical_ids_and_bad_flags(self):
        rows = prior_games(n=5)
        rows[0]["season"] = 2026
        rows[1]["game_id"] = "0123"
        rows[2]["home_team_id"] = "Duke"
        rows[3]["neutral"] = "yes"
        rows[4]["possessions"] = float("nan")
        c = self.census(rows)
        for code in ("WRONG_SEASON", "GAME_ID_NONCANONICAL", "TEAM_IDS_INVALID",
                     "NEUTRAL_FLAG_INVALID", "POSSESSIONS_INVALID"):
            self.assertEqual(c["rejected:" + code], 1, code)

    def test_unknown_neutral_prior_game_not_used_for_hca(self):
        rows = prior_games()
        for g in rows:
            g["neutral"] = None
        self.assertEqual(ctx(prior=rows)["hca"]["n"], 0)

    def test_missing_pace_history(self):
        with self.assertRaisesRegex(m.Pass, "MISSING_PACE_HISTORY"):
            m.project(ctx(), "1", "300", neutral=True)
        with self.assertRaisesRegex(m.Pass, "MISSING_LEAGUE_PACE"):
            m.project(ctx(prior=prior_games(n=10)), "1", "2", neutral=True)


class ProjectionTest(unittest.TestCase):
    def test_hca_recorded_with_sample_size_and_recovers_synthetic_value(self):
        c = ctx()
        self.assertEqual(c["hca"]["n"], 180)
        self.assertAlmostEqual(c["hca"]["value"], 3.0, delta=3 * c["hca"]["se"])

    def test_identities_and_neutral_has_no_hca(self):
        c = ctx()
        n, h = m.project(c, "1", "2", neutral=True), m.project(c, "1", "2", neutral=False)
        for p in (n, h):
            self.assertAlmostEqual(p["margin"], p["home_points"] - p["away_points"])
            self.assertAlmostEqual(p["total"], p["home_points"] + p["away_points"])
        self.assertEqual(n["hca_applied"], 0.0)
        self.assertAlmostEqual(h["margin"] - n["margin"], c["hca"]["value"])
        self.assertAlmostEqual(h["total"], n["total"])

    def test_unknown_neutral_passes(self):
        with self.assertRaisesRegex(m.Pass, "NEUTRAL_SITE_UNKNOWN"):
            m.project(ctx(), "1", "2", neutral=None)

    def test_sd_unmeasured_passes(self):
        with self.assertRaisesRegex(m.Pass, "PREDICTIVE_SD_UNMEASURED"):
            m.project(ctx(settings={"min_sd_games": 10_000}), "1", "2", neutral=True)


class ProbabilityTest(unittest.TestCase):
    P = {"margin": 2.0, "total": 140.0, "sd_margin": 10.0, "sd_total": 12.0}

    def test_probabilities_sum_to_one_and_integer_lines_push(self):
        for market, line in (("moneyline", None), ("spread", -3.5), ("spread", -3.0),
                             ("total", 140.5), ("total", 140.0)):
            a, push, b = m.market_probs(self.P, market, line)
            self.assertAlmostEqual(a + push + b, 1.0)
            self.assertEqual(push > 0, line is not None and float(line).is_integer())

    def test_spread_direction(self):
        fav, _, _ = m.market_probs(self.P, "spread", -10.5)
        dog, _, _ = m.market_probs(self.P, "spread", +10.5)
        self.assertLess(fav, 0.5)
        self.assertGreater(dog, 0.5)

    def test_no_vig_and_ev_at_price(self):
        a, b, over = m.no_vig(-110, -110)
        self.assertAlmostEqual(a, 0.5)
        self.assertAlmostEqual(b, 0.5)
        self.assertAlmostEqual(over, 2 / 1.909090909 - 1, places=6)
        self.assertAlmostEqual(m.ev_per_unit(0.5, 0.0, 100), 0.0)
        self.assertAlmostEqual(m.ev_per_unit(0.5, 0.0, -110), 0.5 * 100 / 110 - 0.5)
        self.assertAlmostEqual(m.ev_per_unit(0.4, 0.2, 100), 0.0)
        for bad in (99, -99, 0, 1.5, True, "110"):
            with self.assertRaises(m.Pass):
                m.decimal_odds(bad)

    def test_sd_must_be_positive(self):
        with self.assertRaises(m.Pass):
            m.market_probs({**self.P, "sd_total": 0.0}, "total", 140.5)
        self.assertTrue(math.isfinite(m.market_probs(self.P, "moneyline")[0]))


if __name__ == "__main__":
    unittest.main()
