"""RUN IT runner vs PAPER pipeline parity on ONE frozen synthetic fixture. Offline.

The canonical fixture is the PAPER suite's synthetic slate
(models/cfb/test_cfb_paper_card.py: Fixture().standard() + STANDARD_QUOTES).
``runner_inputs`` translates it into the runner's (capture, intake, weather)
format. Only formats are translated; numbers are copied, never re-derived.
Translation-only additions are listed in TRANSLATION_ARTIFACTS.
See docs/audits/run_it_vs_paper_parity_20261121.md for the classification
of every difference. Fake teams, fake prices: NOT predictive validation.
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import socket
import sys
import unittest
from unittest import mock

from models.cfb import cfb_baselines as baselines
from models.cfb import cfb_paper_card as card_mod
from models.cfb import test_cfb_paper_card as P

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfb_run_it as R  # noqa: E402
import sportsedge_cfb_model as M  # noqa: E402

FID = baselines.FROZEN_RUNIT["model_id"]
NOW = P.T(P.FROZEN)  # runner run time == paper freeze time
TRANSLATION_ARTIFACTS = (
    "games[].venueId + venues[] (lat/lon 40,-90 as in the paper weather request): runner needs a venue row",
    "weather_fetch returns the paper's event-hour wind; precipitation 'none' (paper: not_in_forecast_fields, also 0 adj)",
    "intake.lines built from STANDARD_QUOTES (book bookA, home handicap = runner 'spread')",
    "intake.injuries = the paper assembler's model rows (team name, role, status)",
    "history games (default mode only): 10 completed games per team so games-played is known",
)


def runner_inputs(history=False):
    games = [dict(g, venueId=900 + g["id"]) for g in P.games_doc()]
    if history:
        teams = sorted({r["team"] for r in P.advanced_doc()})
        games += [{"id": 5000 + 20 * i + k, "season": P.SEASON, "week": k + 1, "homeTeam": t, "awayTeam": "Hist",
                   "startDate": f"2026-09-{k + 1:02d}T18:00:00.000Z", "completed": True}
                  for i, t in enumerate(teams) for k in range(10)]
    cap = {"games": games, "advanced": P.advanced_doc(), "team_stats": [], "talent": P.talent_doc(),
           "returning": P.returning_doc(), "ratings": P.sp_doc(), "teams": [],
           "venues": [{"id": 900 + g["id"], "dome": False, "latitude": 40.0, "longitude": -90.0}
                      for g in P.games_doc()],
           "player_rushing": [], "player_passing": [], "player_receiving": []}
    q = {r["market"]: r for r in P.STANDARD_QUOTES}
    line = {"awayTeam": "Beta Tech", "homeTeam": "Alpha State", "cfbd_game_id": 401,
            "homeMoneyline": q["ML"]["home_price"], "awayMoneyline": q["ML"]["away_price"],
            "spread": q["SPREAD"]["line"], "spreadHomeOdds": q["SPREAD"]["home_price"],
            "spreadAwayOdds": q["SPREAD"]["away_price"], "overUnder": q["TOTAL"]["line"],
            "overOdds": q["TOTAL"]["over_price"], "underOdds": q["TOTAL"]["under_price"]}
    inj = [{"team": "Beta Tech", "player": "Fake WR", "role": "STAR_SKILL", "status": "OUT"}]
    intake = {"captured": "2026-11-28T14:00:00Z", "injuries": inj, "injuries_reviewed_utc": "2026-11-28T14:00:00Z",
              "lines": [line]}
    wx = lambda *_: {"windSpeed": 9.0, "precipitation_type": "none", "isForecast": True}  # noqa: E731
    return cap, intake, wx


class Parity(unittest.TestCase):
    def setUp(self):
        self._sock = mock.patch.object(socket, "socket", side_effect=AssertionError("network used"))
        self._sock.start()
        self.fx = P.Fixture().standard()
        quotes = card_mod.load_operator_quotes(P.quotes_json(P.STANDARD_QUOTES))
        self.card = self.fx.card(quotes=quotes)
        self.g401 = P.by_gid(self.card, 401)

    def tearDown(self):
        self._sock.stop()
        self.fx.cleanup()

    def runner(self, legacy=True, history=False, **over):
        cap, intake, wx = runner_inputs(history)
        intake.update(over)
        return R.run(intake, cap, NOW, wx, legacy_inputs=legacy)

    # ---------------- same frozen model
    def test_both_use_the_pinned_model_file(self):
        self.assertEqual(R.sha256(open(M.__file__, "rb").read()), baselines.FROZEN_RUNIT["module_sha256"])
        self.assertEqual(R.MODEL_SHA256_PIN, baselines.FROZEN_RUNIT["module_sha256"])
        self.assertEqual(os.path.realpath(M.__file__), os.path.realpath(baselines.runit.__file__))
        self.assertEqual(self.card["models"][FID]["module_sha256"], R.MODEL_SHA256_PIN)

    def test_runner_refuses_model_drift(self):  # defect D1 (was: hash recorded, never gated)
        with mock.patch.object(R, "MODEL_SHA256_PIN", "0" * 64):
            with self.assertRaises(R.Fail) as e:
                self.runner()
        self.assertIn("FROZEN_MODEL_FILE_SHA_DRIFT", str(e.exception))

    # ---------------- projections (legacy inputs == paper's games-fallback inputs)
    def test_projection_parity_legacy_inputs(self):
        _, projs, wh, _ = self.runner(legacy=True)
        self.assertEqual([p["game"]["id"] for p in projs], [401])
        p, f = projs[0], self.g401["forecasts"][FID]
        for a, b in (("pts_home", "pts_home"), ("pts_away", "pts_away"), ("margin", "margin_home"), ("total", "total")):
            self.assertAlmostEqual(p[a], f[b], places=4)
        self.assertEqual(p["notes"], f["model_notes"])
        self.assertEqual(p["hfa"], f["hfa"])

    def test_default_runner_inputs_differ_by_games_played_only(self):
        _, projs, wh, ctx = self.runner(legacy=False, history=True)
        self.assertEqual(len(projs), 1, wh)
        self.assertEqual(ctx["adv"]["Alpha State"]["games"], 10)
        f = self.g401["forecasts"][FID]
        self.assertNotAlmostEqual(projs[0]["total"], f["total"], places=2)  # (i) games=10 vs drives/12=10.42
        # Same rows with the paper's implied games count reproduce the paper number.
        cap, intake, wx = runner_inputs()
        adv = [dict(r, games=r["offense"]["drives"] / 12.0) for r in cap["advanced"]]
        ctx2 = dict(ctx, adv=M.by(adv, "team"), lm=M.league_means(adv))
        self.assertAlmostEqual(M.run_game(projs[0]["game"], ctx2)["total"], f["total"], places=4)

    def test_default_runner_without_history_withholds(self):  # (iv) paper fixture has no completed games
        _, projs, wh, _ = self.runner(legacy=False)
        self.assertEqual(projs, [])
        self.assertIn("games played unknown", " ".join(w for _, w in wh))

    # ---------------- probability construction
    def test_probabilities_and_ev_match_per_quote(self):
        _, projs, _, _ = self.runner(legacy=True)
        _, intake, _ = runner_inputs()
        rows = M.price_game(projs[0], intake["lines"][0])
        key = {("ML", "HOME"): ("ML", "Alpha State"), ("ML", "AWAY"): ("ML", "Beta Tech"),
               ("SPREAD", "HOME"): ("Spread", "Alpha State -7"), ("SPREAD", "AWAY"): ("Spread", "Beta Tech +7"),
               ("TOTAL", "OVER"): ("Total", "Over 55.0"), ("TOTAL", "UNDER"): ("Total", "Under 55.0")}
        by = {(r["market"], r["pick"]): r for r in rows}
        self.assertEqual(len(rows), 6)
        for q in self.g401["quotes"]:
            m = q["models"][FID]
            for side, s in (("a", q["side_a"]), ("b", q["side_b"])):
                r = by[key[(q["market"], s)]]
                # 1e-5: the paper prices from margin/total rounded to 4 dp (difference P2).
                self.assertAlmostEqual(r["p_model"], m["p_model_" + side], delta=1e-5)
                self.assertAlmostEqual(r["p_market"], q["market_novig_" + side], places=6)
                self.assertAlmostEqual(r["ev_raw"], m["ev_" + side], delta=1e-5)
                self.assertAlmostEqual(r["p_blend"], 0.3 * r["p_model"] + 0.7 * r["p_market"])
                self.assertAlmostEqual(r["ev_blend"], r["p_blend"] * M.dec(r["odds"]) - 1)

    def test_card_admission_differs_by_contract(self):
        card, projs, wh, _ = self.runner(legacy=True)
        # paper: both slate games recorded (402 NO_QUOTE); runner: only intake lines.
        self.assertEqual([g["cfbd_game_id"] for g in self.card["games"]], [401, 402])
        self.assertEqual(P.by_gid(self.card, 402)["market_status"], "NO_QUOTE")
        self.assertNotIn(402, [p["game"]["id"] for p in projs])
        # paper keeps every quote; runner keeps only blended +EV, non-contradicting rows.
        self.assertEqual(len(self.g401["quotes"]), 3)
        self.assertTrue(all(r["ev_blend"] > 0 for r in card))
        self.assertEqual(sorted((r["market"], r["pick"]) for r in card),
                         [("ML", "Alpha State"), ("Spread", "Alpha State -7")])

    # ---------------- gates
    def test_kickoff_check_uses_game_date_not_run_date(self):  # defect D2
        cap, intake, wx = runner_inputs()
        intake["lines"][0]["kickoff_ct"] = "2:00 PM"   # 20:00Z on 11-28 is 2:00 PM CT
        day_before = P.T("2026-11-27T23:00:00Z")      # 5:00 PM CT 11-27; paper freeze would accept this
        _, projs, wh, _ = R.run(intake, cap, day_before, wx, legacy_inputs=True)
        self.assertEqual([p["game"]["id"] for p in projs], [401], wh)
        intake["lines"][0]["kickoff_ct"] = "11:00 AM"
        _, projs, wh, _ = R.run(intake, cap, day_before, wx, legacy_inputs=True)
        self.assertEqual(projs, [])
        self.assertIn("kickoff mismatch", " ".join(w for _, w in wh))

    def test_kickoff_at_or_before_run_is_refused_by_both(self):
        frozen = "2026-11-28T20:00:00Z"
        late = self.fx.card(frozen=frozen)
        self.assertIn("KICKOFF_NOT_AFTER_FREEZE", P.by_gid(late, 401)["reasons"])
        cap, intake, wx = runner_inputs()
        _, projs, wh, _ = R.run(intake, cap, P.T(frozen), wx, legacy_inputs=True)
        self.assertEqual(projs, [])
        self.assertIn("kicked off", " ".join(w for _, w in wh))

    def test_paper_admits_missing_advanced_keys_runner_withholds(self):  # (iii) P1, documented only
        adv = P.advanced_doc()
        del adv[0]["offense"]["successRate"]          # Alpha State
        fx = P.Fixture()
        try:
            for src, doc in (("cfbd_games", P.games_doc()), ("cfbd_advanced", adv), ("cfbd_talent", P.talent_doc()),
                             ("cfbd_returning", P.returning_doc()), ("operator_qb", P.qb_doc()),
                             ("operator_injuries", P.injury_doc())):
                fx.put(src, doc)
            fx.sp(); fx.wx(401, P.K1); fx.wx(402, P.K2)
            self.assertEqual(P.by_gid(fx.card(), 401)["status"], "READY")  # league mean silently used
        finally:
            fx.cleanup()
        cap, intake, wx = runner_inputs(history=True)
        cap["advanced"] = copy.deepcopy(adv)
        _, projs, wh, _ = R.run(intake, cap, NOW, wx)
        self.assertEqual(projs, [])
        self.assertIn("offense.successRate", " ".join(w for _, w in wh))

    def test_qb_unknown_holds_paper_runner_has_no_qb_gate(self):  # (i)
        fx = P.Fixture().standard(skip=("operator_qb",))
        try:
            self.assertEqual(P.by_gid(fx.card(), 401)["status"], "HOLD")
        finally:
            fx.cleanup()
        _, projs, _, _ = self.runner()
        self.assertEqual(len(projs), 1)

    def test_output_records_are_both_paper_zero_units(self):
        card, projs, wh, _ = self.runner()
        _, intake, _ = runner_inputs()
        doc = R.to_doc(card, projs, wh, intake, NOW, [])
        self.assertEqual(doc["card"]["eligibility"]["approved_stake_u"], 0)
        self.assertEqual(doc["card"]["eligibility"]["official_counted"], 0)
        self.assertEqual(self.card["approved_stake_u"], 0)
        self.assertEqual(doc["model_projections"]["model_file_sha256"], self.card["models"][FID]["module_sha256"])


if __name__ == "__main__":
    unittest.main()
