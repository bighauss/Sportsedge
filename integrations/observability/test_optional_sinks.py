"""Synthetic aggregate-only telemetry tests: no SDK/network required."""
import copy
import os
import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

import optional_sinks as sinks
import quality_gate as gate


def summary():
    return {
        "schema": "SPORTSEDGE_OBSERVABILITY_V1",
        "source_authenticated": False, "official": False, "stake_u": 0,
        "input_rows": 2, "clock_consistent_rows": 1, "blocked_rows": 1,
        "rows": [{"private_event": "do-not-upload"}],
        "metrics": {"n_decided": 1, "n_clv_matched": 0, "n_clv_unmatched": 1,
                    "brier_descriptive_not_forward_certified": 0.1764,
                    "log_loss_descriptive_not_forward_certified": 0.54,
                    "clv_prob_gain_same_selection": None},
    }


class LocalSinkTests(unittest.TestCase):
    def test_export_whitelist_strips_row_level_data(self):
        s = sinks.metrics_only(summary())
        self.assertEqual(s["blocked_rows"], 1)
        self.assertNotIn("rows", s)
        self.assertNotIn("do-not-upload", str(s))
        self.assertNotIn("clv_prob_gain_same_selection", s)

    def test_bad_census_rejected(self):
        r = summary()
        r["input_rows"] = 3
        with self.assertRaisesRegex(sinks.ExportBlocked, "ROW_CENSUS_MISMATCH"):
            sinks.metrics_only(r)

    def test_outcome_cannot_become_certified(self):
        r = summary()
        r["official"] = True
        with self.assertRaisesRegex(sinks.ExportBlocked, "ADMISSION_CANNOT"):
            sinks.metrics_only(r)

    def test_nonfinite_metric_rejected(self):
        r = summary()
        r["metrics"]["log_loss_descriptive_not_forward_certified"] = float("nan")
        with self.assertRaisesRegex(sinks.ExportBlocked, "INVALID_METRIC"):
            sinks.metrics_only(r)

    def test_langfuse_disallowed_by_default(self):
        with self.assertRaisesRegex(sinks.ExportBlocked, "EXPLICIT_CONSENT"):
            sinks.trace_langfuse_aggregate(summary())

    def test_langfuse_opt_in_requires_keys(self):
        with patch.dict(os.environ, {"SPORTSEDGE_ENABLE_LANGFUSE": "1",
                                     "LANGFUSE_PUBLIC_KEY": "",
                                     "LANGFUSE_SECRET_KEY": ""}):
            with self.assertRaisesRegex(sinks.ExportBlocked, "KEYS_NOT_CONFIGURED"):
                sinks.trace_langfuse_aggregate(summary(), explicit_consent=True)

    def test_mlflow_adapter_uses_local_store_and_aggregates(self):
        events = []
        class FakeRun:
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        fake = types.SimpleNamespace(
            set_tracking_uri=lambda uri: events.append(("uri", uri)),
            set_experiment=lambda name: events.append(("experiment", name)),
            start_run=lambda: FakeRun(),
            log_params=lambda params: events.append(("params", params)),
            log_metrics=lambda metrics: events.append(("metrics", metrics)),
        )
        with tempfile.TemporaryDirectory() as d:
            with patch.dict("sys.modules", {"mlflow": fake}):
                result = sinks.write_mlflow_local(summary(), Path(d)/"mlruns")
            self.assertEqual(result["status"], "LOCAL_ONLY")
            self.assertTrue(events[0][1].startswith("file://"))
            self.assertNotIn("rows", events[-1][1])

    def test_local_whylogs_profile_never_includes_events(self):
        events = []
        class FakeSeries:
            def __init__(self, rows):
                self.rows = rows
        class FakeWriter:
            def write(self, dest):
                Path(dest).write_bytes(b"fake-profile")
                events.append(("dest", dest))
        class FakeResult:
            def writer(self, mode):
                events.append(("mode", mode))
                return FakeWriter()
        fake_pd = types.SimpleNamespace(DataFrame=lambda rows: FakeSeries(rows))
        fake_why = types.SimpleNamespace(log=lambda df: (events.append(("values", df.rows))
                                                           or FakeResult()))
        with tempfile.TemporaryDirectory() as d:
            with patch.dict("sys.modules", {"pandas": fake_pd, "whylogs": fake_why}):
                result = sinks.write_whylogs_local(summary(), Path(d)/"quality.bin")
            self.assertEqual(result["status"], "LOCAL_ONLY")
            self.assertEqual(events[0][0], "values")
            self.assertNotIn("do-not-upload", str(events))

    def test_whylogs_create_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"profile.bin"
            p.write_bytes(b"saved")
            with self.assertRaisesRegex(sinks.ExportBlocked, "OUTPUT_EXISTS"):
                sinks.write_whylogs_local(summary(), p)


if __name__ == "__main__":
    unittest.main()
