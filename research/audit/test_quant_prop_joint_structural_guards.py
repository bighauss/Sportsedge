"""Synthetic audit-only regression specification; deliberately RED until fixed.

A player-stat component/composite pair is not learned covariance, and final
settlement labels must satisfy exact same-player monotone/complement logic.
No original market data, no real predictions, no production changes.
"""
import csv
import tempfile
import unittest
from pathlib import Path

from prop_joint_correlation import REQ, audit


def row(leg, *, stat="PTS", side="OVER", line="20.5", result="WIN"):
    return {
        "event_id": "NBA-GAME-SYNTHETIC-1",
        "sport": "NBA",
        "event_start_utc": "2026-11-20T22:00:00Z",
        "snapshot_id": "snapshot-1",
        "asof_utc": "2026-11-20T19:00:00Z",
        "leg_id": leg,
        "player_id": "NBA-PLAYER-SYNTHETIC-1",
        "team_id": "NBA-TEAM-SYNTHETIC-1",
        "stat": stat,
        "side": side,
        "period": "FG",
        "line": line,
        "predicted_p": "0.60",
        "result": result,
        "result_source": "OFFICIAL_PLAYER_BOX_SCORE",
        "model_mode": "PROJECTION",
    }


def assess(rows):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name)
    source = path / "synthetic_input.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQ) + ["model_mode"])
        writer.writeheader()
        writer.writerows(rows)
    report = audit(source, None, path / "synthetic_audit_out", iterations=100)
    with (path / "synthetic_audit_out" / "pair_rows.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        pairs = list(csv.DictReader(handle))
    with (path / "synthetic_audit_out" / "excluded.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        exclusions = list(csv.DictReader(handle))
    directory.cleanup()
    return report, pairs, exclusions


class QuantSamePlayerStructuralSafety(unittest.TestCase):
    def test_component_composite_overlap_is_not_empirical_covariance(self):
        report, pairs, exclusions = assess([
            row("pts", stat="PTS", line="20.5", result="WIN"),
            row("pra", stat="PRA", line="29.5", result="WIN"),
        ])
        self.assertEqual(report["pair_rows"], 1)
        self.assertEqual(len(pairs), 1)
        self.assertIn("COMPOSITE_OVERLAP", pairs[0]["relation"])
        self.assertNotEqual(
            pairs[0]["kind"], "EMPIRICAL_CANDIDATE",
            "PTS and PRA share a deterministic stat component; the relation "
            "must not be eligible for empirical independence/covariance claims",
        )

    def test_monotone_over_ladder_impossible_settlement_quarantined(self):
        report, pairs, exclusions = assess([
            row("high", line="20.5", side="OVER", result="WIN"),
            row("low", line="10.5", side="OVER", result="LOSS"),
        ])
        self.assertEqual(
            report["pair_rows"], 0,
            "A player cannot win Over 20.5 and lose Over 10.5 in one event",
        )
        self.assertGreaterEqual(
            len(exclusions), 2,
            "Preserve explicit source-level refusal for both contradictory legs",
        )

    def test_opposite_sides_same_half_point_cannot_both_win(self):
        report, pairs, exclusions = assess([
            row("over", line="20.5", side="OVER", result="WIN"),
            row("under", line="20.5", side="UNDER", result="WIN"),
        ])
        self.assertEqual(
            report["pair_rows"], 0,
            "At a non-push half-point threshold, Over and Under cannot both win",
        )
        self.assertGreaterEqual(len(exclusions), 2)


if __name__ == "__main__":
    unittest.main()
