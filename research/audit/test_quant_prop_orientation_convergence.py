"""Integrated research-only player-prop marginal orientation regressions.

This is an exact-CI-discovered synthetic test, not authenticated evidence
of profitable same-game dependence or historical player-stat forecasts.
"""
import csv
import tempfile
import unittest
from pathlib import Path

from prop_joint_correlation import REQ, JOINT_REQ, audit


def put(path, cols, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def leg(event, player, stat, prob, outcome):
    return dict(
        event_id=event, sport="NBA", event_start_utc="2026-11-20T20:00:00Z",
        snapshot_id="s", asof_utc="2026-11-20T18:00:00Z",
        leg_id=player, player_id=player, team_id="TEAM", stat=stat,
        side="OVER", period="FG", line="10.5",
        predicted_p=prob, result=outcome,
        result_source="OFFICIAL_PLAYER_BOX_SCORE", model_mode="PROJECTION",
    )


class QuantPropOrientationConvergence(unittest.TestCase):
    def test_reversing_saved_rows_preserves_ast_pts_marginal_labels(self):
        rows = []
        for event, pts_prob, ast_prob, pts_hit, ast_hit in (
            ("G1", "0.90", "0.10", "WIN", "LOSS"),
            ("G2", "0.80", "0.20", "LOSS", "WIN"),
        ):
            rows.extend((
                leg(event, "A", "PTS", pts_prob, pts_hit),
                leg(event, "B", "AST", ast_prob, ast_hit),
            ))
        reports = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for reverse in (False, True):
                inp = root / ("backwards.csv" if reverse else "forwards.csv")
                out = root / ("backwards" if reverse else "forwards")
                put(inp, list(REQ) + ["model_mode"],
                    list(reversed(rows)) if reverse else rows)
                summary = audit(inp, None, out, iterations=100)
                self.assertEqual(summary["pair_rows"], 2)
                self.assertEqual(summary["frozen_joint_matched_pair_rows"], 0)
                with (out / "relationships.csv").open(newline="") as f:
                    relationships = list(csv.DictReader(f))
                with (out / "pair_rows.csv").open(newline="") as f:
                    pairs = list(csv.DictReader(f))
                self.assertEqual(len(relationships), 1)
                self.assertAlmostEqual(
                    float(relationships[0]["marginal_a_pred_mean"]), 0.15)
                self.assertAlmostEqual(
                    float(relationships[0]["marginal_b_pred_mean"]), 0.85)
                self.assertTrue(
                    all(p["leg_id_a"] == "B" and p["leg_id_b"] == "A"
                        for p in pairs))
                reports.append((relationships, pairs))
        self.assertEqual(reports[0], reports[1])

    def test_duplicate_joint_refusal_survives_marginal_sort(self):
        rows = [leg("G1", "A", "PTS", "0.8", "WIN"),
                leg("G1", "B", "AST", "0.2", "LOSS")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            put(root / "pred.csv", list(REQ) + ["model_mode"], rows)
            for reverse in (False, True):
                records = [
                    dict(event_id="G1", snapshot_id="s", leg_id_a="A",
                         leg_id_b="B", asof_utc="2026-11-20T18:00:00Z",
                         joint_p=x) for x in ("not-a-number", "0.25")
                ]
                put(root / "joint.csv", JOINT_REQ,
                    list(reversed(records)) if reverse else records)
                summary = audit(root / "pred.csv", root / "joint.csv",
                                root / ("rev" if reverse else "fwd"),
                                iterations=100)
                self.assertEqual(summary["pair_rows"], 1)
                self.assertEqual(summary["frozen_joint_matched_pair_rows"], 0)
                self.assertEqual(
                    summary["exclusion_counts"][
                        "DUPLICATE_FROZEN_JOINT_PAIR_ALL_COPIES"], 2)


if __name__ == "__main__":
    unittest.main()
