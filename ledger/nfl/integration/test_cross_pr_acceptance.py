"""Cross-PR acceptance of runner->CSV->frozen ledger, SYNTHETIC ONLY.

Executed in a fresh GitHub Actions checkout of PR #474 plus a *pinned* independent
checkout of PR #472. No provider odds, actual finals, live wagering, or real
model validation. The v5 model output is deliberately a deterministic fixture,
while the runner's guard, selection, CSV exporter, freeze, grading and
scorecard are real code executed end-to-end.
"""
import contextlib
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "runner-src"
sys.path.insert(0, str(RUNNER / "engine"))
sys.path.insert(0, str(ROOT / "ledger" / "nfl"))

import run_nfl
import freeze
import settle
import scorecard


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def sample(pick, bet_type, model_p, market_p, price, ev, player=""):
    return {
        "sport": "NFL", "game": "CIN @ WAS", "mode": "PROJECTION",
        "pick": pick, "price": price, "model_p": model_p,
        "fair_odds": -110, "market_p": market_p,
        "edge": model_p - market_p if market_p is not None else None,
        "ev": ev, "score": 55, "stars": 3, "player": player, "bet_type": bet_type,
    }


ROWS = [
    sample("WAS +3.5", "SPREAD|0|", .60, .50, 110, .26),
    sample("CIN -3.5", "SPREAD|1|", .40, .50, -110, -.23636),
    sample("Under 54.5", "TOTAL|1|", .60, .50, 110, .26),
    sample("Over 54.5", "TOTAL|0|", .80, .50, -110, .52727),  # held: probability guard
    sample("WAS ML", "ML|0|", .60, .50, 110, .26),
    sample("Tee Higgins Under 74.5 Rec Yds", "REC_YDS|1|", .55, None, -110, .05, "Tee Higgins"),
    sample("Ja'Marr Chase First TD", "FTD|0|", .35, None, 400, .20, "Ja'Marr Chase"),
]


class CrossPRRunnerLedgerAcceptance(unittest.TestCase):
    def test_pinned_revisions_and_original_bytes(self):
        expected_runner = os.environ["PINNED_RUNNER_SHA"]
        expected_ledger = os.environ["LEDGER_HEAD_SHA"]
        def git_sha(path):
            return subprocess.check_output(
                ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
            ).strip()
        self.assertEqual(git_sha(RUNNER), expected_runner)
        self.assertEqual(git_sha(ROOT), expected_ledger)
        self.assertEqual(len(expected_runner), 40)
        self.assertEqual(len(expected_ledger), 40)
        # A synthetic fixture must have both selected and unselected rows
        # and a separate MODEL_ONLY candidate.
        now = datetime(2026, 11, 23, 23, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            board = tmp / "board.csv"
            write_csv(board, [
                dict(sport="NFL", home="WAS", away="CIN", market="SPREAD",
                     line=-3.5, price_a=-110, price_b=-110,
                     home_proj="", away_proj=""),
                dict(sport="NFL", home="WAS", away="CIN", market="TOTAL",
                     line=54.5, price_a=-110, price_b=-110,
                     home_proj="", away_proj=""),
            ], ["sport", "home", "away", "market", "line", "price_a",
                "price_b", "home_proj", "away_proj"])
            projection = tmp / "projection.json"
            projection.write_text(json.dumps({"game": [
                "CIN@WAS", 26.0, 25.0, 51.0, 54.5, -3.5
            ]}))
            stats = tmp / "synthetic-stats.csv"
            write_csv(stats, [
                dict(game="CIN@WAS", player="Tee Higgins", stat="rec_yds", value=61)
            ], ["game", "player", "stat", "value"])
            inputs_before = {str(p): sha256(p) for p in (board, projection, stats)}

            # The actual runner guard/selector executes. Only upstream v5.run is
            # replaced by reproducible pregame projections, NOT final results.
            with patch.object(run_nfl.v5, "run", side_effect=lambda _p: copy.deepcopy(ROWS)):
                result = run_nfl.build(str(board))
            self.assertTrue(result["card"], "fixture must exercise nonempty card selection")
            self.assertTrue(result["held"])
            self.assertTrue(result["model_only"])
            self.assertTrue(all(c["selected_for_card"] is True for c in result["card"]))
            returned_card = {(r["row_id"], r["quote_id"]) for r in result["card"]}
            returned_out = {(r["row_id"], r["quote_id"]) for r in result["out"]
                            if r["selected_for_card"]}
            self.assertEqual(returned_card, returned_out)
            self.assertEqual(len(returned_card), len(result["card"]))
            self.assertTrue(all(r["approved_stake_u"] == 0 for r in
                                result["out"] + result["card"] + result["held"] +
                                result["model_only"] + result["doubted"]))

            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                with patch.object(run_nfl, "build", return_value=result):
                    with contextlib.redirect_stdout(io.StringIO()):
                        run_nfl.main(str(board))
            finally:
                os.chdir(cwd)
            exported = list(tmp.glob("picks_nfl_*.csv"))
            self.assertEqual(len(exported), 1)
            picks = exported[0]
            with picks.open(newline="") as f:
                rows = list(csv.DictReader(f))
            saved_ids = {(int(r["row_id"]), r["quote_id"]) for r in rows
                         if r["selected_for_card"] == "True"}
            self.assertEqual(saved_ids, returned_card)
            self.assertEqual(len({r["quote_id"] for r in rows}), len(rows))
            self.assertTrue(all(float(r["approved_stake_u"]) == 0 for r in rows))
            self.assertTrue(any(r["selected_for_card"] == "False" for r in rows))

            # Legacy is an intentionally unlabeled pick-set for the SAME
            # pregame board; absence of the marker must not mean unselected.
            legacy = tmp / "legacy-picks.csv"
            legacy_fields = [k for k in rows[0] if k != "selected_for_card"]
            write_csv(legacy, [
                {k: v for k, v in row.items() if k != "selected_for_card"}
                for row in rows
            ], legacy_fields)
            inputs_before.update({str(p): sha256(p) for p in (picks, legacy)})

            run_dir = freeze.freeze(
                "CIN@WAS", str(board), str(projection),
                {"challenger": str(picks), "legacy": str(legacy)},
                {"runner": expected_runner, "ledger": expected_ledger},
                "2026-11-24T01:15:00Z", runs_dir=str(tmp / "runs"), now=now
            )
            self.assertEqual(freeze.verify(run_dir), [])
            frozen_files = [p for p in Path(run_dir).rglob("*") if p.is_file()]
            frozen_before = {str(p): sha256(p) for p in frozen_files}
            manifest = json.loads((Path(run_dir) / "manifest.json").read_text())
            self.assertEqual(manifest["board_sha256"], sha256(board))
            self.assertEqual(manifest["commits"]["runner"], expected_runner)
            self.assertEqual(manifest["commits"]["ledger"], expected_ledger)

            finals = {"away": "CIN", "home": "WAS", "away_score": 27, "home_score": 24}
            _, settlement = settle.settle(
                run_dir, finals, "SYNTHETIC_FIXTURE_NOT_REAL_RESULTS",
                str(stats), str(tmp / "settlements"), now=now)
            self.assertTrue(settlement["run_integrity_ok"])
            graded_challenger = [g for g in settlement["graded"]
                                if g["pick_set"] == "challenger"]
            graded_legacy = [g for g in settlement["graded"] if g["pick_set"] == "legacy"]
            self.assertEqual(len(graded_challenger), len(rows))
            self.assertEqual(len(graded_legacy), len(rows))
            settlement_ids = {(g["row_id"], g["quote_id"]) for g in graded_challenger
                              if g["on_card"] is True}
            self.assertEqual(settlement_ids, returned_card)
            self.assertEqual({(g["row_id"], g["quote_id"]) for g in graded_challenger},
                             {(int(r["row_id"]), r["quote_id"]) for r in rows})
            self.assertEqual(sum(g["on_card"] is False for g in graded_challenger),
                             len(rows) - len(returned_card))
            self.assertTrue(all(g["on_card"] is None for g in graded_legacy))
            self.assertTrue(all(g["approved_stake_u"] == 0 for g in settlement["graded"]))
            self.assertEqual(freeze.verify(run_dir), [])
            self.assertEqual(frozen_before,
                             {str(p): sha256(p) for p in frozen_files})
            self.assertEqual(inputs_before,
                             {str(p): sha256(p) for p in (board, projection, stats, picks, legacy)})

            week = scorecard.load_week(
                "2026-11-23", "2026-11-23",
                str(tmp / "runs"), str(tmp / "settlements")
            )
            md = scorecard.build(week)
            self.assertIn("Unheld priced candidates:", md)
            self.assertIn("Card selections:", md)
            self.assertIn("Explicitly unselected:", md)
            self.assertIn("Selection not recorded (legacy):", md)
            self.assertIn("NFL weekly scorecard - challenger", md)
            self.assertIn("NFL weekly scorecard - legacy", md)
            print("SYNTHETIC RUNNER-LEDGER PASS", json.dumps({
                "runner_sha": expected_runner, "ledger_sha": expected_ledger,
                "board_sha256": sha256(board),
                "csv_sha256": sha256(picks),
                "manifest_sha256": sha256(Path(run_dir) / "manifest.json"),
                "row_count": len(rows),
                "selected_count": len(returned_card),
                "legacy_unknown_count": len(graded_legacy),
                "frozen_mismatches": len(freeze.verify(run_dir)),
                "approved_stake_u": 0,
                "synthetic_only": True,
            }, sort_keys=True))


    def test_real_v5_simulation_passes_through_runner_and_ledger(self):
        """No mock of v5.run: exercise a small synthetic board through real 100k MC.

        Independent of the deterministic selection-fixture test above. It
        proves the true simulation-backed runner export fits the ledger, not
        profitability, predictive calibration, or authentic odds.
        """
        now = datetime(2026, 11, 23, 23, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            board = tmp / "live-engine-synthetic-board.csv"
            base = dict(sport="NFL", home="WAS", away="CIN",
                        home_proj=24, away_proj=20)
            write_csv(board, [
                dict(base, market="SPREAD", line=-3.5, price_a=-110, price_b=-110),
                dict(base, market="TOTAL", line=44.5, price_a=-110, price_b=-110),
                dict(base, market="ML", line="", price_a=-180, price_b=150),
            ], ["sport", "home", "away", "home_proj", "away_proj",
                "market", "line", "price_a", "price_b"])
            projection = tmp / "real-model-projection.json"
            projection.write_text(json.dumps({
                "proj_margin": 4, "proj_total": 44,
                "market_margin": 3.5, "market_total": 44.5
            }))
            original_bytes = {str(p): sha256(p) for p in (board, projection)}
            result = run_nfl.build(str(board))     # genuinely calls v5.run, 100,000 MC
            self.assertGreater(len(result["out"]), 0)
            self.assertTrue(all(o["approved_stake_u"] == 0 for o in result["out"]))
            chosen = {(c["row_id"], c["quote_id"]) for c in result["card"]}
            self.assertEqual(chosen, {(o["row_id"], o["quote_id"])
                                      for o in result["out"] if o["selected_for_card"]})
            self.assertTrue(all(c["selected_for_card"] is True for c in result["card"]))
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                with patch.object(run_nfl, "build", return_value=result):
                    with contextlib.redirect_stdout(io.StringIO()):
                        run_nfl.main(str(board))
            finally:
                os.chdir(cwd)
            exports = list(tmp.glob("picks_nfl_*.csv"))
            self.assertEqual(len(exports), 1)
            with exports[0].open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), len(result["out"]))
            csv_chosen = {(int(r["row_id"]), r["quote_id"]) for r in rows
                          if r["selected_for_card"] == "True"}
            self.assertEqual(csv_chosen, chosen)
            original_bytes[str(exports[0])] = sha256(exports[0])
            run_dir = freeze.freeze(
                "CIN@WAS", str(board), str(projection), {"simulator": str(exports[0])},
                {"runner": os.environ["PINNED_RUNNER_SHA"],
                 "ledger": os.environ["LEDGER_HEAD_SHA"]},
                "2026-11-24T01:15:00Z", runs_dir=str(tmp / "runs-real"),
                now=now)
            frozen = {str(p): sha256(p) for p in Path(run_dir).rglob("*") if p.is_file()}
            _, record = settle.settle(
                run_dir, {"away": "CIN", "home": "WAS",
                          "away_score": 27, "home_score": 24},
                "SYNTHETIC_FIXTURE_NOT_REAL_RESULTS",
                settle_dir=str(tmp / "settlements-real"), now=now)
            self.assertTrue(record["run_integrity_ok"])
            self.assertEqual(len(record["graded"]), len(rows))
            self.assertEqual(chosen, {(g["row_id"], g["quote_id"])
                                      for g in record["graded"] if g["on_card"] is True})
            self.assertTrue(all(g["approved_stake_u"] == 0 for g in record["graded"]))
            self.assertEqual(freeze.verify(run_dir), [])
            self.assertEqual(frozen, {str(p): sha256(p) for p in
                                      Path(run_dir).rglob("*") if p.is_file()})
            self.assertEqual(original_bytes, {str(p): sha256(p)
                                              for p in (board, projection, exports[0])})
            print("SYNTHETIC REAL-SIMULATOR INTEGRATION PASS", json.dumps({
                "runner_sha": os.environ["PINNED_RUNNER_SHA"],
                "ledger_sha": os.environ["LEDGER_HEAD_SHA"],
                "board_sha256": sha256(board),
                "row_count": len(rows),
                "selected_count": len(chosen),
                "frozen_mismatches": len(freeze.verify(run_dir)),
                "approved_stake_u": 0,
                "synthetic_only": True,
            }, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
