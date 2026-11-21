"""Dedicated workflow-discovered regression for #368 marginal orientation.

The normal test_prop_joint_correlation module is not selected by the
research/audit quant-eightpack workflow's test_quant_*.py filter. This
standalone, no-network test ensures the new behavior actually runs in CI.
Synthetic input only; not evidence of real market correlation or +EV.
"""
import csv
import tempfile
import unittest
from pathlib import Path
from prop_joint_correlation import audit, REQ


class QuantPropMarginalOrderingTests(unittest.TestCase):
    def test_two_event_ast_pts_marginals_survive_complete_csv_reversal(self):
        frozen_rows = []
        for event, pts_p, ast_p, pts_result, ast_result in (
            ("G1", "0.9", "0.1", "WIN", "LOSS"),
            ("G2", "0.8", "0.2", "LOSS", "WIN"),
        ):
            for leg, stat, p, outcome in (
                ("A", "PTS", pts_p, pts_result),
                ("B", "AST", ast_p, ast_result),
            ):
                frozen_rows.append(dict(
                    event_id=event, sport="NBA",
                    event_start_utc="2026-11-20T20:00:00Z",
                    snapshot_id="s", asof_utc="2026-11-20T18:00:00Z",
                    leg_id=leg, player_id=leg, team_id="TEAM",
                    stat=stat, side="OVER", period="FG", line="10.5",
                    predicted_p=p, result=outcome,
                    result_source="OFFICIAL_PLAYER_BOX_SCORE",
                    model_mode="PROJECTION",
                ))
        results=[]
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            for flip in (False, True):
                input_file=folder/("reversed.csv" if flip else "original.csv")
                out_dir=folder/("reversed_out" if flip else "original_out")
                with input_file.open("w", encoding="utf-8", newline="") as f:
                    writer=csv.DictWriter(f, fieldnames=list(REQ)+["model_mode"])
                    writer.writeheader()
                    writer.writerows(list(reversed(frozen_rows)) if flip else frozen_rows)
                audit_result=audit(input_file,None,out_dir,iterations=100)
                self.assertEqual(audit_result["pair_rows"],2)
                with (out_dir/"relationships.csv").open(newline="") as f:
                    relationship=list(csv.DictReader(f))
                with (out_dir/"pair_rows.csv").open(newline="") as f:
                    pair_rows=list(csv.DictReader(f))
                self.assertEqual(len(relationship),1)
                self.assertAlmostEqual(float(relationship[0]["marginal_a_pred_mean"]),0.15)
                self.assertAlmostEqual(float(relationship[0]["marginal_b_pred_mean"]),0.85)
                self.assertTrue(all(p["leg_id_a"]=="B" and p["leg_id_b"]=="A"
                                    for p in pair_rows))
                results.append((relationship,pair_rows))
            self.assertEqual(results[0],results[1])


if __name__ == "__main__":
    unittest.main()
