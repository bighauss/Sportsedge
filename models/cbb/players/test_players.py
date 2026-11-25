"""Unit tests for models/cbb/players (stdlib unittest; numpy needed for fit)."""
from datetime import date, timedelta
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from players import distributions as D           # noqa: E402
from players import features as F                # noqa: E402
from players import identity as I                # noqa: E402


class Distributions(unittest.TestCase):
    def test_poisson_limit_and_sum(self):
        p = D.nb_pmf(3.0, 0.0)
        self.assertAlmostEqual(sum(p), 1.0, places=9)
        self.assertAlmostEqual(p[0], math.exp(-3), places=9)

    def test_nb_moments(self):
        mu, a = 12.0, 0.25
        p = D.nb_pmf(mu, a)
        m = sum(k * x for k, x in enumerate(p))
        v = sum((k - m) ** 2 * x for k, x in enumerate(p))
        self.assertAlmostEqual(m, mu, places=5)
        self.assertAlmostEqual(v, mu + a * mu * mu, places=3)

    def test_zero_mean(self):
        self.assertEqual(D.nb_pmf(0.0, 0.3), [1.0])
        self.assertEqual(D.prob_at_least([1.0], 1), 0.0)

    def test_invalid(self):
        for mu in (-1, float("nan")):
            with self.assertRaises(ValueError):
                D.nb_pmf(mu, 0.1)

    def test_crps_point_mass(self):
        self.assertEqual(D.crps_discrete([0, 0, 1.0], 2), 0.0)
        self.assertAlmostEqual(D.crps_discrete([0, 0, 1.0], 0), 2.0)
        with self.assertRaises(ValueError):
            D.crps_discrete([1.0], -1)

    def test_crps_prefers_truth(self):
        y = 5
        self.assertLess(D.crps_discrete(D.nb_pmf(5, .1), y), D.crps_discrete(D.nb_pmf(12, .1), y))

    def test_at_least_monotone(self):
        p = D.nb_pmf(10, .2)
        vals = [D.prob_at_least(p, n) for n in range(0, 30)]
        self.assertEqual(vals[0], 1.0)
        self.assertTrue(all(a >= b for a, b in zip(vals, vals[1:])))

    def test_push_aware_settlement(self):
        p = [0.25, 0.25, 0.25, 0.25]
        self.assertEqual(D.settle_probs(p, "OVER", 2), (0.25, 0.25, 0.5))
        self.assertEqual(D.settle_probs(p, "UNDER", 2), (0.5, 0.25, 0.25))
        w, push, l = D.settle_probs(p, "OVER", 1.5)
        self.assertEqual((w, push, l), (0.5, 0.0, 0.5))
        self.assertEqual(D.settle_probs(p, "AT_LEAST", 2), (0.5, 0.0, 0.5))
        with self.assertRaises(ValueError):
            D.settle_probs(p, "AT_LEAST", 2.5)
        with self.assertRaises(ValueError):
            D.settle_probs(p, "OVER", 2.3)

    def test_ev_uncapped_and_push_refund(self):
        self.assertAlmostEqual(D.expected_value(0.5, 0.0, 0.5, 3500), 17.0)
        self.assertAlmostEqual(D.expected_value(0.4, 0.2, 0.4, 100), 0.0)
        self.assertAlmostEqual(D.expected_value(0.5, 0.0, 0.5, -110), 0.5 * 100 / 110 - 0.5)
        with self.assertRaises(ValueError):
            D.american_to_decimal(50)

    def test_fair_american(self):
        self.assertAlmostEqual(D.fair_american(0.5), -100.0)
        self.assertAlmostEqual(D.fair_american(0.2), 400.0)
        self.assertIsNone(D.fair_american(1.0))

    def test_combo_moment_correlation_widens(self):
        ind = D.combo_moments([10, 5], [.2, .1], {})
        cor = D.combo_moments([10, 5], [.2, .1], {(0, 1): .4})
        self.assertEqual(ind[0], cor[0])
        self.assertGreater(cor[1], ind[1])

    def test_copula_matches_moment_mean_and_independence(self):
        mus, al = [8.0, 4.0], [0.2, 0.1]
        pmf = D.combo_pmf_copula(mus, al, [[1, 0], [0, 1]], draws=20000, seed=1)
        m = sum(k * p for k, p in enumerate(pmf))
        self.assertAlmostEqual(m, 12.0, delta=0.15)
        self.assertEqual(pmf, D.combo_pmf_copula(mus, al, [[1, 0], [0, 1]], draws=20000, seed=1))
        pos = D.combo_pmf_copula(mus, al, [[1, .6], [.6, 1]], draws=20000, seed=1)
        var = lambda q: sum((k - 12) ** 2 * p for k, p in enumerate(q))
        self.assertGreater(var(pos), var(pmf))


def _box_rows(n_games=8, start=date(2025, 11, 3)):
    rows = []
    for g in range(n_games):
        d = (start + timedelta(days=3 * g)).isoformat()
        gid = str(1000 + g)
        for team, opp in (("10", "20"), ("20", "10")):
            for pl in range(1, 4):
                pid = f"{team}{pl}"
                rows.append(dict(game_id=gid, game_date=d, athlete_id=pid, athlete_display_name=f"Player {pid}",
                                 team_id=team, opponent_team_id=opp, minutes="30", did_not_play="false",
                                 points=str(10 + pl), rebounds=str(pl + 2), assists="2",
                                 three_point_field_goals_made="1", field_goals_attempted="10",
                                 offensive_rebounds="1", turnovers="2", free_throws_attempted="4",
                                 starter="true"))
            rows.append(dict(rows[-1], athlete_id=f"{team}9", athlete_display_name="Bench Guy",
                             minutes="", did_not_play="TRUE", points="", rebounds="", assists="",
                             three_point_field_goals_made="", field_goals_attempted="",
                             offensive_rebounds="", turnovers="", free_throws_attempted=""))
    return rows


def _write(rows):
    import csv
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    f.close()
    return f.name


class Features(unittest.TestCase):
    def setUp(self):
        self.path = _write(_box_rows())
        self.apps, self.tg, self.census = F.load_player_box(self.path)

    def tearDown(self):
        os.unlink(self.path)

    def test_dnp_not_zero(self):
        self.assertEqual(self.census["DID_NOT_PLAY_ROW"], 16)
        self.assertFalse(any(a["player_id"].endswith("9") for a in self.apps))

    def test_duplicate_drops_all_copies(self):
        rows = _box_rows()
        rows.append(dict(rows[0], points="40"))
        p = _write(rows)
        try:
            apps, _, c = F.load_player_box(p)
        finally:
            os.unlink(p)
        self.assertEqual(c["DUPLICATE_PLAYER_GAME_ALL_COPIES"], 2)
        self.assertFalse(any(a["player_id"] == rows[0]["athlete_id"] and a["game_id"] == rows[0]["game_id"] for a in apps))

    def _engine(self):
        # League baseline needs >= 50 team-games; replicate the toy league with id offsets.
        apps, tg = list(self.apps), dict(self.tg)
        for k in range(1, 8):
            for a in self.apps:
                apps.append(dict(a, player_id=a["player_id"] + f"x{k}", team_id=a["team_id"] + f"{k}",
                                 opp_id=a["opp_id"] + f"{k}", game_id=a["game_id"] + f"{k}"))
            for (g, t), v in self.tg.items():
                tg[(g + f"{k}", t + f"{k}")] = dict(v, game_id=g + f"{k}", team_id=t + f"{k}", opp_id=v["opp_id"] + f"{k}")
        return F.Engine(apps, tg), apps

    def test_prior_only_and_lag(self):
        eng, apps = self._engine()
        target = date(2025, 11, 3) + timedelta(days=21)  # game 8
        row, hold = eng.features("101", "10", "20", target)
        self.assertIsNone(hold)
        cut = target - timedelta(days=F.LAG_DAYS)
        self.assertTrue(all(eng.player_hist["101"][i]["day"] <= cut for i in range(len(eng.player_hist["101"]))))
        self.assertEqual(len(row["history_game_ids"]), 7)
        self.assertNotIn("1007", row["history_game_ids"])
        with self.assertRaises(RuntimeError):
            eng.features("101", "10", "20", target - timedelta(days=6))

    def test_future_values_do_not_change_features(self):
        eng1, apps = self._engine()
        target = date(2025, 11, 3) + timedelta(days=21)
        a, _ = eng1.features("101", "10", "20", target)
        for x in apps:
            if x["day"] >= target - timedelta(days=1):
                x["stats"] = dict(x["stats"], POINTS=99)
        eng2 = F.Engine(apps, eng1.team_games)
        b, _ = eng2.features("101", "10", "20", target)
        self.assertEqual(a, b)

    def test_insufficient_and_transfer_holds(self):
        eng, _ = self._engine()
        _, hold = eng.features("101", "10", "20", date(2025, 11, 9))
        self.assertEqual(hold, "INSUFFICIENT_PRIOR_APPEARANCES")
        eng, _ = self._engine()
        _, hold = eng.features("101", "20", "10", date(2025, 11, 24))
        self.assertEqual(hold, "TEAM_TRANSFER_OR_MIXED_HISTORY")


class Identity(unittest.TestCase):
    ROSTER = {"1": {"11": "Taj Au-Duke", "12": "John Smith Jr."}, "2": {"21": "John Smith", "22": "Ari Fulton"}}

    def test_exact(self):
        self.assertEqual(I.resolve_player("Ari Fulton", "1", "2", self.ROSTER), ("22", "2", "EXACT_DISPLAY_NAME"))

    def test_normalized_ambiguous_fails_closed(self):
        r = {"1": {"12": "John Smith Jr."}, "2": {"21": "John Smith"}}
        # Exact pass finds the unique "John Smith" on team 2; no fallback needed.
        self.assertEqual(I.resolve_player("John Smith", "1", "2", r)[0], "21")
        # "John Smith III" only matches after normalization, where it is ambiguous.
        self.assertEqual(I.resolve_player("John Smith III", "1", "2", r), (None, None, "AMBIGUOUS_PROP_PLAYER"))

    def test_normalized_unique(self):
        self.assertEqual(I.resolve_player("Taj Au Duke", "1", "2", self.ROSTER), ("11", "1", "NORMALIZED_NAME"))

    def test_missing(self):
        self.assertEqual(I.resolve_player("Nobody", "1", "2", self.ROSTER)[2], "PROP_PLAYER_NOT_ON_EVENT_ROSTER")
        self.assertEqual(I.resolve_player("", "1", "2", self.ROSTER)[2], "PROP_SUBJECT_MISSING")

    SCHED = [dict(game_id="9", start_date="2026-11-25T15:00Z", home_location="Belmont", away_location="St. Bonaventure",
                  home_short_display_name="Belmont", away_short_display_name="St Bonaventure", home_id="1", away_id="2")]

    def test_event_exact_tip_and_dated_alias(self):
        g, why = I.resolve_event("Saint Bonaventure", "Belmont", "2026-11-25T15:00:00Z", self.SCHED)
        self.assertEqual((g["game_id"], why), ("9", None))
        self.assertEqual(I.resolve_event("Saint Bonaventure", "Belmont", "2026-11-25T16:00:00Z", self.SCHED)[1],
                         "EVENT_NOT_FOUND_EXACT_NAMES_AND_TIP")
        self.assertEqual(I.resolve_event("Belmont", "Saint Bonaventure", "2026-11-25T15:00:00Z", self.SCHED)[1],
                         "EVENT_HOME_AWAY_ORIENTATION_CONFLICT")
        with self.assertRaises(ValueError):
            I.parse_utc("2026-11-25 15:00")


class Fit(unittest.TestCase):
    def test_recovers_scale_dispersion_and_correlation(self):
        import random
        from players.fit import fit
        from players.model import predictive
        rng = random.Random(3)
        rows = []
        for i in range(8000):
            base = {"POINTS": rng.uniform(4, 20), "REBOUNDS": rng.uniform(2, 8), "ASSISTS": rng.uniform(1, 5),
                    "THREES": rng.uniform(.5, 3)}
            shared = rng.gammavariate(4, .25)          # common minutes-like shock -> positive correlation
            act = {k: _poisson(rng, 1.1 * v * shared) for k, v in base.items()}
            rows.append({"day": "2025-01-01", "base": base, "pace_ratio": 1.0,
                         "opp_factor": dict.fromkeys(base, 1.0), "actual": act})
        p = fit(rows)
        for s in ("POINTS", "REBOUNDS", "ASSISTS", "THREES"):
            self.assertAlmostEqual(p["stats"][s]["calibration"], 1.1, delta=0.03)
            self.assertAlmostEqual(p["stats"][s]["alpha"], 0.25, delta=0.04)
        self.assertGreater(p["rho"]["POINTS|REBOUNDS"], 0.2)
        pred = predictive(rows[0], p)
        self.assertAlmostEqual(pred["PRA"]["mean"], sum(pred[s]["mean"] for s in ("POINTS", "REBOUNDS", "ASSISTS")))
        self.assertAlmostEqual(sum(pred["PRA"]["pmf"]), 1.0, places=6)
        with self.assertRaises(ValueError):
            fit(rows[:10])


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


class Pricing(unittest.TestCase):
    def test_reject_paths(self):
        from players import pricing as P
        ctx = type("C", (), {"schedule": Identity.SCHED})()
        base = dict(away="Saint Bonaventure", home="Belmont", market="PLAYER_POINTS_AT_LEAST", line="10",
                    price_a="-110", period="FG", player="X", tip_utc="2026-11-25T15:00:00Z",
                    captured_utc="2026-11-25T12:00:00Z")
        cases = [({"market": "PLAYER_STEALS_AT_LEAST"}, "UNSUPPORTED_PLAYER_MARKET"),
                 ({"period": "1H"}, "UNSUPPORTED_PERIOD"),
                 ({"line": "10.5"}, "INVALID_MILESTONE_LINE"),
                 ({"price_a": ""}, "MISSING_OR_INVALID_PRICE"),
                 ({"captured_utc": "2026-11-25T15:30:00Z"}, "LIVE_OR_POST_TIP_CAPTURE"),
                 ({"home": "Lipscomb"}, "EVENT_NOT_FOUND_EXACT_NAMES_AND_TIP")]
        for change, code in cases:
            o = P.price_row(dict(base, **change), ctx, {})
            self.assertFalse(o["priced"])
            self.assertEqual(o["reason_code"], code)
            self.assertEqual((o["label"], o["status"], o["approved_stake_u"], o["official_counted"]),
                             ("PAPER_0U", "NON_COUNTED", 0, 0))

    def test_non_player_rows_ignored(self):
        from players import pricing as P
        self.assertFalse(P.is_player_row({"market": "SPREAD", "player": ""}))
        self.assertTrue(P.is_player_row({"market": "PLAYER_PR_AT_LEAST", "player": "A"}))


if __name__ == "__main__":
    unittest.main()
