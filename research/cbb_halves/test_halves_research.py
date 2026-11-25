"""Research-side tests: dataset integrity vs its manifest, no look-ahead in the point-in-time
projector, and parity between the vectorised evaluator and the stdlib runtime PMF.

Run from repo root:  python -m unittest -v research.cbb_halves.test_halves_research
Requires numpy, pandas, scipy (offline; uses only committed files).
"""
import hashlib
import json
import sys
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


class ProtocolTests(unittest.TestCase):
    def test_dev_report_never_touched_test_season(self):
        dev = json.loads((HERE / "results" / "dev_report.json").read_text())
        self.assertEqual(sorted(int(s) for s in dev["folds"]), list(FH.DEV_SEASONS))
        self.assertNotIn(FH.TEST_SEASON, FH.DEV_SEASONS)
        self.assertEqual(dev["label"], "PAPER_0U"); self.assertEqual(dev["counting"], "NON_COUNTED")
        self.assertEqual(dev["dataset_sha256"], FH.dataset_sha256())


if __name__ == "__main__":
    unittest.main()
