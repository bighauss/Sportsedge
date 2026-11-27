"""Reproducibility tests for the CBB backtest inputs and evidence (offline; PAPER / 0u; NON_COUNTED).

Run:  PYTHONPATH=.:models/cbb python -m unittest research.cbb_backtest.test_reproducibility
FG1 (models.cbb.fullgame, grok-cbb/fullgame-ev-20261125 / PR #534) is optional: when it is not
importable the FG1 columns are skipped and everything else is still compared byte for byte.
RAW sources are optional too: set CBB_RAW_ROOT to a directory holding the parquet files and
espn_odds_all.jsonl.gz to also run the full re-derivation test.
"""
import csv
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from . import export_rows as X
from . import inputs as I
from . import replay as R

HERE = Path(__file__).parent
DATA = I.DATA_DIR
ROWS_2019 = HERE / "results" / "run3_final" / "rows" / "identical_rows_2019.csv"


class Manifest(unittest.TestCase):
    def test_committed_inputs_verify(self):
        self.assertEqual(I.verify_derivatives(DATA), [])

    def test_manifest_pins_every_external_source(self):
        m = I.load_manifest(DATA)
        self.assertEqual(len(m["external_sources"]), 18)         # 9 seasons x (schedule, team_box)
        for e in m["external_sources"]:
            self.assertEqual(len(e["sha256"]), 64)
            self.assertTrue(e["url"].startswith("https://github.com/sportsdataverse/"))
        self.assertEqual(len(m["external_odds_cache"]["sha256"]), 64)
        self.assertTrue(m["committed_results"])
        self.assertEqual(m["label"], "NON_COUNTED")

    def _copy(self):
        td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, td, True)
        shutil.copytree(HERE, td / "cbb_backtest", ignore=shutil.ignore_patterns("__pycache__"))
        return td / "cbb_backtest" / "data"

    def test_tampered_byte_fails(self):
        d = self._copy()
        p = d / "games_2021.csv"
        b = bytearray(p.read_bytes()); b[len(b) // 2] ^= 1; p.write_bytes(bytes(b))
        bad = I.verify_derivatives(d)
        self.assertTrue(any(x.startswith("SHA256 games_2021.csv") for x in bad), bad)
        self.assertEqual(I.main(["verify", "--data-dir", str(d)]), 1)       # non-zero exit status

    def test_missing_and_unpinned_files_fail(self):
        d = self._copy()
        (d / "odds_selected_2022.csv").unlink()
        (d / "extra.csv").write_text("x\n")
        bad = I.verify_derivatives(d)
        self.assertIn("MISSING odds_selected_2022.csv", bad)
        self.assertIn("UNPINNED extra.csv", bad)

    def test_changed_result_evidence_fails(self):
        d = self._copy()
        p = d.parent / "results" / "run3_final" / "rows" / "identical_rows_2020.csv"
        p.write_text(p.read_text().replace("2020", "2021", 1))
        self.assertTrue(any("result evidence file changed" in x for x in I.verify_derivatives(d)))

    def test_fetch_rejects_hash_mismatch(self):
        d = self._copy()
        src = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, src, True)
        (src / "a.bin").write_bytes(b"not the pinned bytes")
        m = I.load_manifest(d)
        m["external_sources"] = [{"name": "a.parquet", "kind": "schedule", "season": 2019, "url": (src / "a.bin").as_uri(),
                                  "bytes": 1, "sha256": "0" * 64}]
        (d / I.MANIFEST).write_text(json.dumps(m))
        out = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, out, True)
        bad = I.fetch_sources(d, out)
        self.assertTrue(bad and bad[0].startswith("SHA256 a.parquet"))
        self.assertTrue((out / "a.parquet.rejected").exists() and not (out / "a.parquet").exists())

    def test_verify_external_detects_missing_and_wrong(self):
        ext = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, ext, True)
        bad = I.verify_external(DATA, ext)
        self.assertEqual(len(bad), 19)                                        # 18 parquet + odds cache missing
        (ext / "team_box_2018.parquet").write_bytes(b"x")
        self.assertTrue(any(x.startswith("SHA256 team_box_2018.parquet") for x in I.verify_external(DATA, ext)))


class Normalized(unittest.TestCase):
    def test_games_load_with_census_and_types(self):
        g, c = I.load_games_normalized(DATA, 2019)
        self.assertEqual(len(g), c["admitted_schedule_finals"])
        self.assertEqual([x["event_id"] for x in g], sorted(x["event_id"] for x in g))
        x = g[0]
        self.assertIsInstance(x["neutral"], bool)
        self.assertEqual(x["margin"], x["home_points"] - x["away_points"])
        self.assertEqual(x["total"], x["home_points"] + x["away_points"])
        self.assertEqual(sum(1 for y in g if y["possessions"] is not None), c["complete_box_finals"])

    def test_odds_have_provider_and_no_open_lines(self):
        o, c = I.load_odds_normalized(DATA)
        self.assertGreater(len(o), 40000)
        self.assertEqual(c["selected"], 43047)
        for m in list(o.values())[:500]:
            self.assertTrue(m["provider"])
            self.assertTrue(all(m[k] is None for k in m if k.startswith("open_")))
        self.assertFalse(any(m["provider_id"] in {"1001", "1002", "1003", "59", "200"} for m in o.values()))


class Export(unittest.TestCase):
    def test_format_rules(self):
        self.assertEqual(X.fmt("native_frozen_margin", "-8.812"), "-8.81")
        self.assertEqual(X.fmt("FG1_sd_margin", "12.265"), repr(float(__import__("numpy").round(12.265, 2))))
        self.assertEqual(X.fmt("mkt_close_ml_home", "180"), "180.0")
        self.assertEqual(X.fmt("mkt_close_ml_home", ""), "")
        self.assertEqual(X.fmt("mkt_provider", "Unibet"), "Unibet")
        self.assertEqual(X.fmt("home", "356"), "356")

    def test_only_identical_rows_are_kept(self):
        rows = [{"identical_row": "False", "event_id": "1"}, {"identical_row": "True", "event_id": "2"}]
        out = list(X.project(rows))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], "2")


class SliceReproduction(unittest.TestCase):
    """Rebuild the fixed slice (season 2019, origins through 2018-12-17) from the COMMITTED inputs and
    compare with the committed evidence rows string by string."""

    @classmethod
    def setUpClass(cls):
        cls.committed = R.committed_slice(ROWS_2019)

    def test_committed_slice_is_nonempty_and_fixed(self):
        self.assertEqual(len(self.committed), 709)
        self.assertEqual(max(r[3] for r in self.committed), R.SLICE_LAST_ORIGIN)

    def test_non_fg1_columns_reproduce_byte_identically(self):
        cols, rebuilt = R.rebuild_slice_rows(DATA, include_fg1=False)
        keep = [i for i, c in enumerate(cols) if not c.startswith("FG1_")]
        by = {r[0]: r for r in rebuilt}
        missing = [r[0] for r in self.committed if r[0] not in by]
        self.assertEqual(missing, [])
        for r in self.committed:
            self.assertEqual([r[i] for i in keep], [by[r[0]][i] for i in keep], r[0])

    def test_fg1_columns_and_row_set_reproduce_when_fg1_present(self):
        if not R.fg1_available():
            self.skipTest("FG1 not importable (PR #534 / grok-cbb/fullgame-ev-20261125 not on PYTHONPATH)")
        cols, rebuilt = R.rebuild_slice_rows(DATA, include_fg1=True)
        self.assertEqual(cols, list(X.COLS))
        self.assertEqual(rebuilt, self.committed)        # every column, every row, same order

    def test_slice_rebuild_is_deterministic(self):
        a = R.rebuild_slice_rows(DATA, include_fg1=False)[1]
        b = R.rebuild_slice_rows(DATA, include_fg1=False)[1]
        self.assertEqual(a, b)


@unittest.skipUnless(os.environ.get("CBB_RAW_ROOT"), "set CBB_RAW_ROOT to the raw parquet + odds cache dir")
class FullRederivation(unittest.TestCase):
    def test_raw_sources_verify_and_rederive_identically(self):
        raw = Path(os.environ["CBB_RAW_ROOT"])
        self.assertEqual(I.verify_external(DATA, raw), [])
        work = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, work, True)
        self.assertEqual(I.rederive(DATA, raw, raw / "espn_odds_all.jsonl.gz", work), [])



class HistoricalThreeOutcomeReport(unittest.TestCase):
    """Execute the real driver on committed historical inputs; no provider or mocks."""
    def test_full_historical_companion_report(self):
        from . import harness as H
        self.assertEqual(I.verify_derivatives(DATA), [])
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            meta, _ = H.run(None, None, out, list(range(2019, 2027)),
                            reps=100, data_dir=DATA, push_score_report=True)
            self.assertEqual(meta["leakage"]["violation_count"], 0)
            with (out / "probability_metrics_3class.csv").open() as f:
                rows = list(csv.DictReader(f))
            self.assertTrue((out / "probability_metrics.csv").is_file())
            all_groups = [r for r in rows if r["group"] == "ALL"]
            self.assertEqual(len(all_groups), len(meta["models"]) * len(H.FAMILIES))
            for family in H.FAMILIES:
                subset = [r for r in all_groups if r["family"] == family]
                self.assertEqual(len({r["n"] for r in subset}), 1)
                self.assertGreater(int(subset[0]["n"]), 0)
                self.assertEqual(len({r["observed_pushes"] for r in subset}), 1)
                if family != "ml":
                    self.assertGreater(int(subset[0]["observed_pushes"]), 0)
                for r in subset:
                    self.assertEqual(int(r["n"]) + int(r["held_events"]), meta["identical_rows"])
                    self.assertEqual(int(r["all_forecast_rows"]), meta["total_rows"])
                    self.assertEqual(r["evaluation_state"], "RETROSPECTIVE_NOT_UNTOUCHED")
                    self.assertGreaterEqual(float(r["brier_3class_sum"]), 0)
                    self.assertLessEqual(float(r["brier_3class_sum"]), 2)
                    print("CBB_HISTORICAL_WPL " + json.dumps(r, sort_keys=True), flush=True)
            self.assertEqual(meta["approved_stake_u"], 0)
            self.assertEqual(meta["official_counted"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
