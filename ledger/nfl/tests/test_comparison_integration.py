"""Synthetic P0+P1 regression tests for ledger/nfl/comparison.py. Not real performance."""
import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparison import (
    ProbabilityBindingError,
    PushSemanticsError,
    compare,
    compare_prospective_candidates,
    render,
)
from freeze import freeze, verify
from settle import settle
from scorecard import load_week


def prepared(runs, runs_dir):
    for run in runs:
        run["run_dir"] = os.path.join(runs_dir, run["manifest"]["run_id"])
    return runs


def _write_csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


class ComparisonP0P1Tests(unittest.TestCase):
    def _freeze_and_settle(self, root, *, game="CIN@WAS", away="CIN", home="WAS",
                           away_score=10, home_score=20, rows_by_label=None,
                           now=None, start_utc="2026-11-24T01:00:00Z"):
        now = now or datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)
        runs_dir, settlements = root / "runs", root / "settlements"
        tag = now.strftime("%Y%m%dT%H%M%SZ") + "_" + game.replace("@", "_")
        board = root / f"board_{tag}.csv"
        board.write_text("quote_id\nq1\n")
        proj = root / f"proj_{tag}.json"
        proj.write_text("{}")
        if rows_by_label is None:
            rows_by_label = {
                "baseline": [dict(
                    row_id=0, quote_id="q1", market="spread", pick=home, line=-3.5,
                    price=-110, model_p=0.8, market_p=0.5, blend_p=0.6,
                    selected_for_card="true", approved_stake_u=0,
                )],
                "challenger": [dict(
                    row_id=0, quote_id="q1", market="spread", pick=home, line=-3.5,
                    price=-110, model_p=0.6, market_p=0.5, blend_p=0.55,
                    selected_for_card="", approved_stake_u=0,
                )],
            }
        picks = {}
        for label, rows in rows_by_label.items():
            p = root / f"{label}_{tag}.csv"
            _write_csv(p, rows)
            picks[label] = str(p)
        run = freeze(game, str(board), str(proj), picks, runs_dir=str(runs_dir),
                     start_utc=start_utc, now=now)
        finals = dict(away=away, home=home, away_score=away_score, home_score=home_score)
        spath, _ = settle(run, finals, "SYNTHETIC TEST ONLY", settle_dir=str(settlements))
        return run, runs_dir, settlements, Path(spath), finals

    def test_legitimate_settlement_read_only_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, runs_dir, settlements, _, finals = self._freeze_and_settle(root)
            before = {str(p): p.read_bytes() for p in Path(run).rglob("*") if p.is_file()}
            saved = {str(p): p.read_bytes() for p in settlements.glob("*")}
            run_id = Path(run).name
            report = compare(
                prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                "baseline", "challenger",
                authenticated_finals={run_id: finals},
            )
            s = report["scores"]["model_p"]
            self.assertEqual(report["probabilities"], "reconciled_to_frozen_picks")
            self.assertAlmostEqual(s["left"], 0.04)
            self.assertAlmostEqual(s["right"], 0.16)
            self.assertEqual(s["n"], 1)
            self.assertIsNone(s["delta_brier_ci95"])
            self.assertEqual(report["selection"]["challenger"]["unknown"], 1)
            self.assertIn("# NFL paired ledger comparison", render(report))
            self.assertFalse(verify(run))
            self.assertEqual(before, {str(p): p.read_bytes() for p in Path(run).rglob("*") if p.is_file()})
            self.assertEqual(saved, {str(p): p.read_bytes() for p in settlements.glob("*")})

    def test_alter_each_settlement_probability_independently_rejected(self):
        for field in ("model_p", "market_p", "blend_p"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run, runs_dir, settlements, spath, _ = self._freeze_and_settle(root)
                hist = json.loads(spath.read_text())
                hist[-1]["graded"][0][field] = 0.123
                spath.write_text(json.dumps(hist))
                with self.assertRaises(ProbabilityBindingError):
                    compare(prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                            "baseline", "challenger")

    def test_deleted_duplicated_substituted_settlement_rows_rejected(self):
        for mode in ("delete", "duplicate", "substitute"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                rows_by_label = {
                    "baseline": [
                        dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                             price=-110, model_p=0.7, market_p=0.5, blend_p=0.6, approved_stake_u=0),
                        dict(row_id=1, quote_id="q2", market="total", pick="over", line=25.5,
                             price=-110, model_p=0.6, market_p=0.5, blend_p=0.55, approved_stake_u=0),
                    ],
                    "challenger": [
                        dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                             price=-110, model_p=0.6, market_p=0.5, blend_p=0.55, approved_stake_u=0),
                        dict(row_id=1, quote_id="q2", market="total", pick="over", line=25.5,
                             price=-110, model_p=0.55, market_p=0.5, blend_p=0.52, approved_stake_u=0),
                    ],
                }
                _, runs_dir, settlements, spath, _ = self._freeze_and_settle(root, rows_by_label=rows_by_label)
                hist = json.loads(spath.read_text())
                graded = hist[-1]["graded"]
                if mode == "delete":
                    graded.pop(0)
                elif mode == "duplicate":
                    graded.append(dict(graded[0]))
                else:
                    sub = dict(graded[0])
                    sub["row"] = 99
                    graded[0] = sub
                spath.write_text(json.dumps(hist))
                with self.assertRaises(ProbabilityBindingError):
                    compare(prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                            "baseline", "challenger")

    def test_altered_quote_id_line_price_or_outcome_rejected(self):
        mutations = [
            ("quote_id", "q_tampered"),
            ("line", -2.5),
            ("price", -125.0),
            ("result", "L"),
        ]
        for key, val in mutations:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _, runs_dir, settlements, spath, _ = self._freeze_and_settle(root)
                hist = json.loads(spath.read_text())
                hist[-1]["graded"][0][key] = val
                spath.write_text(json.dumps(hist))
                with self.assertRaises(ProbabilityBindingError):
                    compare(prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                            "baseline", "challenger")

    def test_authenticated_finals_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, runs_dir, settlements, _, _ = self._freeze_and_settle(root)
            run_id = Path(run).name
            wrong_finals = {run_id: dict(away="CIN", home="WAS", away_score=24, home_score=20)}
            with self.assertRaises(ProbabilityBindingError):
                compare(prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                        "baseline", "challenger", authenticated_finals=wrong_finals)

    def test_missing_vs_invalid_and_nonfinite_probabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows_by_label = {
                "baseline": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                                  price=-110, model_p="", market_p=0.5, blend_p=0.5, approved_stake_u=0)],
                "challenger": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                                    price=-110, model_p=0.6, market_p=0.5, blend_p=0.55, approved_stake_u=0)],
            }
            _, runs_dir, settlements, _, _ = self._freeze_and_settle(root, rows_by_label=rows_by_label)
            report = compare(prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                             "baseline", "challenger")
            self.assertEqual(report["scores"]["model_p"]["n"], 0)
            self.assertEqual(report["scores"]["model_p"]["missing_or_invalid"], 1)

        for bad in ("-0.1", "1.2", "nan", "inf", "not_a_number"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                rows_by_label = {
                    "baseline": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                                      price=-110, model_p=bad, market_p=0.5, blend_p=0.5, approved_stake_u=0)],
                    "challenger": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                                        price=-110, model_p=0.6, market_p=0.5, blend_p=0.55, approved_stake_u=0)],
                }
                _, runs_dir, settlements, _, _ = self._freeze_and_settle(root, rows_by_label=rows_by_label)
                with self.assertRaises(ProbabilityBindingError):
                    compare(prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                            "baseline", "challenger")

    def test_push_capable_market_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows_by_label = {
                "baseline": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.0,
                                  price=-110, model_p=0.6, market_p=0.5, blend_p=0.55,
                                  prob_definition="conditional_no_push", approved_stake_u=0)],
                "challenger": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.0,
                                    price=-110, model_p=0.55, market_p=0.5, blend_p=0.52,
                                    prob_definition="unconditional_win", approved_stake_u=0)],
            }
            _, runs_dir, settlements, _, _ = self._freeze_and_settle(root, rows_by_label=rows_by_label)
            with self.assertRaises(PushSemanticsError):
                compare(prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                        "baseline", "challenger")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows_by_label = {
                "baseline": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.0,
                                  price=-110, model_p=0.6, market_p=0.45, blend_p=0.5,
                                  prob_definition="unconditional_win", push_p=0.1, approved_stake_u=0)],
                "challenger": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.0,
                                    price=-110, model_p=0.45, market_p=0.45, blend_p=0.45,
                                    prob_definition="unconditional_win", push_p=0.1, approved_stake_u=0)],
            }
            _, runs_dir, settlements, _, _ = self._freeze_and_settle(root, rows_by_label=rows_by_label)
            report = compare(prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir)),
                             "baseline", "challenger")
            # Conditional prob for baseline: 0.6 / (1 - 0.1) = 2/3 -> Brier (2/3 - 1)^2 = 1/9
            self.assertAlmostEqual(report["scores"]["model_p"]["left"], (1.0 / 3.0) ** 2, places=6)

    def test_quarantined_records_excluded_from_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, runs_dir, settlements, _, _ = self._freeze_and_settle(root)
            target = Path(run) / "inputs" / "board.csv"
            os.chmod(target, 0o600)
            target.write_text("tampered\n")
            loaded = prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir))
            loaded[0]["quarantined"] = bool(verify(run))
            report = compare(loaded, "baseline", "challenger")
            self.assertEqual(report["counts"]["excluded_runs"], 1)
            self.assertEqual(report["scores"]["model_p"]["n"], 0)

    def test_repeated_captures_deduped_and_game_clustered_ci_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Game 1 captured twice; latest_pregame should keep only the second capture (p=0.8)
            g1_early = {
                "baseline": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                                  price=-110, model_p=0.2, market_p=0.5, blend_p=0.4, approved_stake_u=0)],
                "challenger": [dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                                    price=-110, model_p=0.5, market_p=0.5, blend_p=0.5, approved_stake_u=0)],
            }
            g1_late = {
                "baseline": [
                    dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                         price=-110, model_p=0.8, market_p=0.5, blend_p=0.6, approved_stake_u=0),
                    dict(row_id=1, quote_id="q2", market="total", pick="over", line=25.5,
                         price=-110, model_p=0.7, market_p=0.5, blend_p=0.56, approved_stake_u=0),
                ],
                "challenger": [
                    dict(row_id=0, quote_id="q1", market="spread", pick="WAS", line=-3.5,
                         price=-110, model_p=0.6, market_p=0.5, blend_p=0.53, approved_stake_u=0),
                    dict(row_id=1, quote_id="q2", market="total", pick="over", line=25.5,
                         price=-110, model_p=0.5, market_p=0.5, blend_p=0.5, approved_stake_u=0),
                ],
            }
            g2 = {
                "baseline": [dict(row_id=0, quote_id="q3", market="spread", pick="BUF", line=-2.5,
                                  price=-110, model_p=0.75, market_p=0.55, blend_p=0.61, approved_stake_u=0)],
                "challenger": [dict(row_id=0, quote_id="q3", market="spread", pick="BUF", line=-2.5,
                                    price=-110, model_p=0.55, market_p=0.55, blend_p=0.55, approved_stake_u=0)],
            }
            self._freeze_and_settle(root, game="CIN@WAS", away="CIN", home="WAS",
                                    away_score=10, home_score=20, rows_by_label=g1_early,
                                    now=datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc))
            r1_late, runs_dir, settlements, _, _ = self._freeze_and_settle(
                root, game="CIN@WAS", away="CIN", home="WAS", away_score=10, home_score=20,
                rows_by_label=g1_late, now=datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc))
            r2, _, _, _, _ = self._freeze_and_settle(
                root, game="MIA@BUF", away="MIA", home="BUF", away_score=17, home_score=24,
                rows_by_label=g2, now=datetime(2026, 11, 23, 22, 0, tzinfo=timezone.utc))

            loaded = prepared(load_week("2026-11-23", "2026-11-23", str(runs_dir), str(settlements)), str(runs_dir))
            report = compare(loaded, "baseline", "challenger")
            self.assertEqual(report["counts"]["superseded_runs"], 1)
            self.assertEqual(report["scores"]["model_p"]["n_games"], 2)
            self.assertEqual(report["scores"]["model_p"]["n"], 3)
            self.assertIsNotNone(report["scores"]["model_p"]["delta_brier_ci95"])
            self.assertIn("spread", report["by_family"]["model_p"])
            self.assertIn("total", report["by_family"]["model_p"])
            self.assertEqual(report["scores"]["model_p"]["clv"]["status"],
                             "NOT_AVAILABLE_NO_AUTHENTICATED_CLOSING_QUOTES")

            # Prospective 4-candidate evaluation on identical sample, with authentic closing quotes
            closing = {(Path(r1_late).name, "q1"): 0.54, (Path(r2).name, "q3"): 0.58}
            prosp = compare_prospective_candidates(loaded, "baseline", closing_quotes=closing)
            cands = prosp["candidates"]
            self.assertEqual(set(cands), {"market_only", "blend_90_10", "current_model", "independent_model"})
            self.assertEqual({c["n"] for c in cands.values()}, {3})
            self.assertEqual(cands["independent_model"]["clv"]["status"], "AUTHENTICATED_CLOSING_QUOTES")
            self.assertEqual(cands["independent_model"]["clv"]["n"], 2)
            self.assertAlmostEqual(cands["independent_model"]["clv"]["mean"], (0.04 + 0.03) / 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
