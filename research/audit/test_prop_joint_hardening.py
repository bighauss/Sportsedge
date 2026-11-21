"""Synthetic adversarial PIT audit tests: evidence is NOT real historical player data."""
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import unittest
from prop_joint_correlation import audit, REQ


def write(path, rows):
    with path.open("w", newline="", encoding="utf8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQ) + ["model_mode"])
        writer.writeheader()
        writer.writerows(rows)


def leg(event, player, snapshot, asof, team="TEAM", result="WIN"):
    return dict(
        event_id=event, sport="NBA",
        event_start_utc="2026-11-20T22:00:00Z",
        snapshot_id=snapshot, asof_utc=asof,
        leg_id=player, player_id=player, team_id=team,
        stat="PTS" if player == "A" else "AST", side="OVER",
        period="FG", line="10.5", predicted_p="0.5", result=result,
        result_source="OFFICIAL_PLAYER_BOX_SCORE", model_mode="PROJECTION",
    )


class TestHardening(unittest.TestCase):
    def test_cross_snapshot_team_mutation_quarantines_entire_game(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = []
            for snapshot, asof, team in (
                ("s1", "2026-11-20T18:00:00Z", "BOS"),
                ("s2", "2026-11-20T19:00:00Z", "LAL"),
            ):
                rows.extend([
                    leg("event", "A", snapshot, asof, team=team),
                    leg("event", "B", snapshot, asof, team="ATL"),
                ])
            write(directory / "p.csv", rows)
            report = audit(directory / "p.csv", None, directory / "out", iterations=100)
            self.assertEqual(report["pair_rows"], 0)
            self.assertEqual(
                report["exclusion_counts"]["PLAYER_TEAM_CHANGED_ACROSS_SNAPSHOTS"], 4
            )

    def test_cross_snapshot_result_flip_quarantines_entire_game(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = []
            for snapshot, asof, result in (
                ("s1", "2026-11-20T18:00:00Z", "WIN"),
                ("s2", "2026-11-20T19:00:00Z", "LOSS"),
            ):
                rows.extend([
                    leg("event", "A", snapshot, asof, result=result),
                    leg("event", "B", snapshot, asof),
                ])
            write(directory / "p.csv", rows)
            report = audit(directory / "p.csv", None, directory / "out", iterations=100)
            self.assertEqual(report["pair_rows"], 0)
            self.assertEqual(
                report["exclusion_counts"]["PLAYER_GRADE_CHANGED_ACROSS_SNAPSHOTS"], 4
            )

    def test_bootstrap_suppressed_below_30_independent_events(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows = []
            for index in range(6):
                rows.extend([
                    leg(str(index), "A", "s", "2026-11-20T18:00:00Z"),
                    leg(str(index), "B", "s", "2026-11-20T18:00:00Z"),
                ])
            write(directory / "p.csv", rows)
            audit(directory / "p.csv", None, directory / "out", iterations=100)
            with (directory / "out" / "relationships.csv").open() as handle:
                result = list(csv.DictReader(handle))[0]
            self.assertEqual(
                result["delta_event_cluster_bootstrap_95ci"], "N/A_LT_30_EVENTS"
            )


if __name__ == "__main__":
    unittest.main()
