"""Regression: exception safety and serialization of the frozen-v5 execution wrapper."""
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_nfl  # noqa: E402
import test_run_nfl as base  # noqa: E402


class Isolation(unittest.TestCase):
    def setUp(self):
        self.board = base.board(base.game(24, 20))
        self.cwd = os.getcwd()
        self.work = tempfile.mkdtemp()
        os.chdir(self.work)

    def tearDown(self):
        os.chdir(self.cwd)

    def same_dir(self, a, b):
        return os.path.realpath(a) == os.path.realpath(b)

    def test_state_restored_when_scratch_creation_fails(self):
        before = run_nfl.v5.N_FIT
        with mock.patch.object(run_nfl.tempfile, "mkdtemp", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                run_nfl.build(self.board)
        self.assertEqual(run_nfl.v5.N_FIT, before)
        self.assertTrue(self.same_dir(os.getcwd(), self.work))

    def test_state_and_scratch_restored_when_chdir_fails(self):
        before = run_nfl.v5.N_FIT
        made = []
        real = tempfile.mkdtemp

        def spy(*a, **k):
            d = real(*a, **k)
            made.append(d)
            return d
        with mock.patch.object(run_nfl.tempfile, "mkdtemp", side_effect=spy), \
                mock.patch.object(run_nfl.os, "chdir", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                run_nfl.build(self.board)
        self.assertEqual(run_nfl.v5.N_FIT, before)
        self.assertTrue(made)
        self.assertFalse(os.path.exists(made[0]))
        self.assertTrue(self.same_dir(os.getcwd(), self.work))

    def test_production_n_fit_and_scratch_cwd_only_during_run(self):
        seen = {}
        before = run_nfl.v5.N_FIT

        def fake_run(path):
            seen["n_fit"] = run_nfl.v5.N_FIT
            seen["cwd"] = os.getcwd()
            return []
        with mock.patch.object(run_nfl.v5, "run", side_effect=fake_run):
            run_nfl.build(self.board)
        self.assertEqual(seen["n_fit"], run_nfl.N_FIT)
        self.assertFalse(self.same_dir(seen["cwd"], self.work))
        self.assertFalse(os.path.exists(seen["cwd"]))
        self.assertEqual(run_nfl.v5.N_FIT, before)
        self.assertTrue(self.same_dir(os.getcwd(), self.work))

    def test_state_restored_when_v5_run_raises(self):
        before = run_nfl.v5.N_FIT
        with mock.patch.object(run_nfl.v5, "run", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                run_nfl.build(self.board)
        self.assertEqual(run_nfl.v5.N_FIT, before)
        self.assertTrue(self.same_dir(os.getcwd(), self.work))

    def test_concurrent_builds_are_serialized(self):
        state = {"active": 0, "max": 0}
        guard = threading.Lock()

        def fake_run(path):
            with guard:
                state["active"] += 1
                state["max"] = max(state["max"], state["active"])
            time.sleep(0.05)
            with guard:
                state["active"] -= 1
            return []
        errors = []

        def work():
            try:
                run_nfl.build(self.board)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)
        with mock.patch.object(run_nfl.v5, "run", side_effect=fake_run):
            threads = [threading.Thread(target=work) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(errors, [])
        self.assertEqual(state["max"], 1)


if __name__ == "__main__":
    unittest.main()
