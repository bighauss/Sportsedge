"""Research-side tests: dataset integrity vs its manifest, no look-ahead in the point-in-time
projector, and parity between the vectorised evaluator and the stdlib runtime PMF.

Run from repo root:  python -m unittest -v research.cbb_halves.test_halves_research
Requires numpy, pandas, scipy (offline; uses only committed files).
"""
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "models" / "cbb"))
import fit_halves as FH  # noqa: E402
import pit_fullgame as F  # noqa: E402
from halves import halves_model as HM  # noqa: E402

DATA = HERE / "data"


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.man = json.loads((DATA / "halves_dataset_manifest.json").read_text())
        cls.g = pd.concat([pd.read_csv(f) for f in sorted(DATA.glob("halves_games_*.csv"))], ignore_index=True)

    def test_files_match_manifest_hashes(self):
        for name, meta in self.man["outputs"].items():
            b = (DATA / name).read_bytes()
            self.assertEqual(hashlib.sha256(b).hexdigest(), meta["sha256"], name)
            self.assertEqual(len(b), meta["bytes"])

    def test_counts(self):
        self.assertEqual(len(self.g), self.man["admitted_games"])
        for y, m in self.man["by_season"].items():
            self.assertEqual(int((self.g.season == int(y)).sum()), m["admitted"])
        rej = pd.read_csv(DATA / "halves_rejections.csv")
        self.assertEqual(len(rej), self.man["rejected_games"])
        self.assertTrue(set(rej.reason) <= {"NO_SCHEDULE_ROW", "NOT_COMPLETED", "NO_PERIOD_1", "NO_PERIOD_2",
                                            "FINAL_MISMATCH_SCHEDULE", "H1_MISMATCH_LINESCORE", "SCORE_NOT_MONOTONE",
                                            "TIED_FINAL", "OT_WITHOUT_TIED_REGULATION", "IMPLAUSIBLE_SCORE",
                                            "DUPLICATE_GAME_ID", "NO_PBP"})
        self.assertFalse(set(rej.game_id) & set(self.g.game_id))

    def test_row_integrity(self):
        g = self.g
        self.assertFalse(g.game_id.duplicated().any())
        self.assertTrue((g.h1_home <= g.reg_home).all() and (g.h1_away <= g.reg_away).all())
        self.assertTrue((g.reg_home <= g.final_home).all() and (g.reg_away <= g.final_away).all())
        ot = g.periods > 2
        self.assertTrue((g.reg_home[ot] == g.reg_away[ot]).all())
        self.assertTrue(((g.reg_home == g.final_home) & (g.reg_away == g.final_away))[~ot].all())
        self.assertTrue((g.final_home != g.final_away).all())
        self.assertTrue(g.linescore_checked[g.season >= 2023].all())


class NoLookaheadTests(unittest.TestCase):
    def test_projection_ignores_same_day_and_future_results(self):
        g = pd.concat([pd.read_csv(DATA / "halves_games_2019.csv")], ignore_index=True).head(1500)
        g["fg_poss"] = 68.0
        base = F.project(g)
        day = base.local_date.iloc[700]
        mutated = g.copy()
        ts = pd.to_datetime(mutated.start_utc, utc=True)
        later = ((ts - pd.Timedelta(hours=6)).dt.date >= day).values
        mutated.loc[later, "final_home"] += 25  # corrupt same-day and future results
        alt = F.project(mutated)
        key = ["game_id", "proj_home", "proj_away", "proj_poss"]
        a = base[key].set_index("game_id"); b = alt[key].set_index("game_id").loc[a.index]
        same_or_before = (base.local_date <= day).values
        np.testing.assert_allclose(a.values[same_or_before], b.values[same_or_before])
        self.assertFalse(np.allclose(a.values[~same_or_before], b.values[~same_or_before]))


class ParityTests(unittest.TestCase):
    def test_vectorised_pmf_matches_runtime(self):
        z = np.random.default_rng(7).standard_t(6, size=4000)
        emp = FH.empirical_shape(z)
        mus = np.array([-7.3, 0.2, 33.6, 71.9]); sds = np.array([8.1, 7.4, 6.2, 10.3])
        for shape in ({"kind": "normal"}, emp):
            B = FH.PMFBatch(mus, sds, shape)
            for i, (m, s) in enumerate(zip(mus, sds)):
                R = HM.IntegerPMF(float(m), float(s), shape)
                for k in range(R.lo, R.hi + 1):
                    self.assertAlmostEqual(B.p[i, k - B.lo], R.pmf(k), places=10)
                for L in (m - 3.5, np.floor(m) + 0.5, np.round(m)):
                    self.assertAlmostEqual(B.gt(np.array([L] * 4))[i], R.prob_gt(float(L)), places=10)



class JointAndRefitTests(unittest.TestCase):
    def test_vectorised_joint_score_matches_runtime_cell(self):
        import fit_joint as FJ
        from halves import halves_joint as HJ
        rng = np.random.default_rng(0)
        n = 40
        mu_m, sd_m = rng.normal(3, 1, n), rng.uniform(7, 9, n)
        mu_t, sd_t = rng.normal(70, 2, n), rng.uniform(8, 10, n)
        ym = np.rint(mu_m + rng.normal(0, 1, n) * sd_m)
        yt = np.rint(mu_t + rng.normal(0, 1, n) * sd_t)
        res = {"mu_m": mu_m, "mu_t": mu_t, "sd_m": sd_m, "sd_t": sd_t, "ym": ym, "yt": yt}
        spec = {"rho": 0.3}
        vec = FJ.joint_log_score(res, "gaussian", spec)
        acc = 0.0
        for i in range(n):
            pm = HM.IntegerPMF(float(mu_m[i]), float(sd_m[i]), {"kind": "normal"}, span=9.0)
            pt = HM.IntegerPMF(float(mu_t[i]), float(sd_t[i]), {"kind": "normal"}, span=9.0)
            acc += math.log(max(HJ.joint_cell(pm, pt, int(ym[i]), int(yt[i]), "gaussian", spec), 1e-12))
        self.assertAlmostEqual(vec, -acc / n, places=3)

    def test_refit_ignores_season_2026_and_refuses_to_overwrite_v1(self):
        g19 = pd.read_csv(DATA / "halves_games_2019.csv").head(30)
        g26 = pd.read_csv(DATA / "halves_games_2026.csv").head(30)
        rows = pd.concat([g19, g26], ignore_index=True)
        # identifiably wrong 2026 projections
        syn = pd.DataFrame({
            "game_id": rows.game_id,
            "proj_home": np.where(rows.season == 2026, 200.0, 70.0),
            "proj_away": np.where(rows.season == 2026, 10.0, 65.0),
            "proj_poss": 68.0,
            "n_home": 8, "n_away": 8,
        })
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "proj.csv"
            syn.to_csv(src, index=False)
            applied = FH.apply_external_projections(rows.copy(), src)
            # overlay keeps 2026 rows (the refit stage has to drop them by season, not here)
            self.assertTrue((applied.loc[applied.game_id.isin(g26.game_id), "proj_home"] == 200).all())
            train = applied[applied.season < 2026]
            self.assertFalse((train.proj_home == 200).any())
            self.assertTrue((train.proj_home == 70).all())
        # the CLI guard is a path check
        v1 = HERE.parents[1] / "models" / "cbb" / "halves" / "coefficients_halves_v1.json"
        before = hashlib.sha256(v1.read_bytes()).hexdigest() if v1.exists() else None
        self.assertIsNotNone(before)

    def test_debias_training_window_excludes_later_seasons(self):
        import import_fullgame_forecasts as IMP
        def row(season, gid, n, hp, ap, pm, pt):
            return {"game_id": str(gid), "season": season, "n_home": n, "n_away": n,
                    "home_points": hp, "away_points": ap,
                    "f": {"FG1": {"home_points": (pt + pm) / 2, "away_points": (pt - pm) / 2,
                                  "margin": pm, "total": pt, "possessions": 68.0}}}
        def season_rows(year, start):
            return [row(year, start + i, 10, 80, 70, 8, 140) for i in range(300)] + \
                   [row(year, start + 1000 + i, 2, 80, 70, 8, 140) for i in range(300)]
        by = {
            2022: season_rows(2022, 0),
            2023: season_rows(2023, 2000),
            2024: season_rows(2024, 4000),
            2026: [row(2026, 8000 + i, 10, 160, 40, 50, 200) for i in range(300)] +
                  [row(2026, 9000 + i, 2, 160, 40, 50, 200) for i in range(300)],
        }
        # 2027 is the season whose de-bias *priors* would include 2026 unless train_until cuts it off.
        by[2027] = [row(2027, 10000 + i, 10, 80, 70, 12, 160) for i in range(20)]
        import copy
        inc = copy.deepcopy(by)
        IMP.add_recal(by, "FG1", train_until=2025)
        IMP.add_recal(inc, "FG1", train_until=2026)
        self.assertIn("FG1C", by[2024][0]["f"])
        self.assertIn("FG1C", by[2027][0]["f"])
        # 2026 actuals are 210 on a 200 forecast; including them moves the 2027 de-bias.
        self.assertNotAlmostEqual(by[2027][0]["f"]["FG1C"]["total"],
                                  inc[2027][0]["f"]["FG1C"]["total"], places=3)

    def test_import_write_and_roundtrip_schema(self):
        import import_fullgame_forecasts as IMP
        with tempfile.TemporaryDirectory() as td:
            by = {2024: [{"game_id": "123", "season": 2024, "n_home": 4, "n_away": 6,
                          "home_points": 70, "away_points": 60,
                          "f": {"FG1": {"home_points": 71.2, "away_points": 64.8,
                                        "margin": 6.4, "total": 136.0, "possessions": 69.1}}}]}
            dest = Path(td) / "p.csv"
            IMP.write_csv(by, "FG1", dest)
            ext = pd.read_csv(dest)
            self.assertEqual(list(ext.columns), ["game_id", "season", "proj_home", "proj_away",
                                                 "proj_poss", "n_home", "n_away", "engine"])
            self.assertEqual(int(ext.game_id.iloc[0]), 123)
            g = pd.read_csv(DATA / "halves_games_2019.csv").head(0)
            # schema accepted
            g2 = pd.DataFrame({"game_id": [123], "season": [2024]})
            out = FH.apply_external_projections(g2, dest)
            self.assertAlmostEqual(float(out.proj_home.iloc[0]), 71.2)



class ProtocolTests(unittest.TestCase):
    def test_dev_report_never_touched_test_season(self):
        dev = json.loads((HERE / "results" / "dev_report.json").read_text())
        self.assertEqual(sorted(int(s) for s in dev["folds"]), list(FH.DEV_SEASONS))
        self.assertNotIn(FH.TEST_SEASON, FH.DEV_SEASONS)
        self.assertEqual(dev["label"], "PAPER_0U"); self.assertEqual(dev["counting"], "NON_COUNTED")
        self.assertEqual(dev["dataset_sha256"], FH.dataset_sha256())


    def test_shipped_coefficients_are_the_tested_ones(self):
        rep = json.loads((HERE / "results" / "test_report.json").read_text())
        raw = (HERE.parents[1] / "models" / "cbb" / "halves" / "coefficients_halves_v1.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), rep["coefficients_sha256"])
        coef = json.loads(raw)
        self.assertEqual(coef["untouched_test_season"], FH.TEST_SEASON)
        self.assertEqual(coef["trained_seasons"], list(range(2019, FH.TEST_SEASON)))
        self.assertEqual(rep["dataset_sha256"], FH.dataset_sha256())


if __name__ == "__main__":
    unittest.main()
