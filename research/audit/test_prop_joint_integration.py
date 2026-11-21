"""Synthetic integration tests: parent snapshot guards + joint-source all-copy quarantine.

No historical player-prop correlation or sportsbook edge is certified.
"""
import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from prop_joint_correlation import REQ, JOINT_REQ, audit


def save_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def leg(player, *, event="123", mode="PROJECTION", asof="2026-11-20T18:00:00Z"):
    return {
        "event_id": event, "sport": "NFL", "event_start_utc": "2026-11-20T20:00:00Z",
        "snapshot_id": "s1", "asof_utc": asof,
        "leg_id": player, "player_id": player, "team_id": "T",
        "stat": "PASS_YDS" if player == "A" else "REC_YDS",
        "side": "OVER", "period": "FG", "line": "59.5",
        "predicted_p": "0.50", "result": "WIN",
        "result_source": "OFFICIAL_PLAYER_BOX_SCORE", "model_mode": mode,
    }


class JointIntegrationTests(unittest.TestCase):
    def test_bad_first_good_second_and_reverse_are_equally_blocked(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_csv(root/"p.csv", list(REQ)+["model_mode"], [leg("A"),leg("B")])
            for reversed_order in (False, True):
                forecasts = [
                    {"event_id":"123","snapshot_id":"s1",
                     "leg_id_a":"A","leg_id_b":"B",
                     "asof_utc":"2026-11-20T18:00:00Z",
                     "joint_p":value}
                    for value in ("not-a-probability", "0.25")
                ]
                if reversed_order:
                    forecasts.reverse()
                save_csv(root/"j.csv", JOINT_REQ, forecasts)
                result = audit(root/"p.csv",root/"j.csv",
                               root/("backwards" if reversed_order else "forwards"),
                               iterations=100)
                self.assertEqual(result["pair_rows"],1)
                self.assertEqual(result["frozen_joint_matched_pair_rows"],0)
                self.assertEqual(
                    result["exclusion_counts"]["DUPLICATE_FROZEN_JOINT_PAIR_ALL_COPIES"],2)

    def test_no_model_mode_cannot_be_called_independent(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            save_csv(root/"p.csv",list(REQ)+["model_mode"],[
                leg("A", mode=""), leg("B", mode="")])
            result=audit(root/"p.csv",None,root/"result",iterations=100)
            self.assertEqual(result["pair_rows"],0)
            self.assertEqual(result["accepted_rows_before_snapshot_checks"],0)
            self.assertEqual(result["exclusion_counts"]["NON_INDEPENDENT_MODEL_MODE"],2)

    def test_output_is_create_only_and_prior_result_unchanged(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            save_csv(root/"p.csv",list(REQ)+["model_mode"],[leg("A"),leg("B")])
            destination=root/"result"
            original=audit(root/"p.csv",None,destination,iterations=100)
            self.assertEqual(original["pair_rows"],1)
            original_bytes=(destination/"coverage.json").read_bytes()
            with self.assertRaises(FileExistsError):
                audit(root/"p.csv",None,destination,iterations=100)
            self.assertEqual((destination/"coverage.json").read_bytes(),original_bytes)

    def test_cross_snapshot_grade_flip_not_saved_by_earliest_pair(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=[leg("A"),leg("B")]
            later=[{**a,"snapshot_id":"s2",
                    "asof_utc":"2026-11-20T18:20:00Z",
                    "result":"LOSS" if a["player_id"]=="A" else "WIN"}
                   for a in original]
            save_csv(root/"p.csv",list(REQ)+["model_mode"],original+later)
            result=audit(root/"p.csv",None,root/"result",iterations=100)
            self.assertEqual(result["pair_rows"],0)
            self.assertEqual(
                result["exclusion_counts"]["PLAYER_GRADE_CHANGED_ACROSS_SNAPSHOTS"],4)


if __name__ == "__main__":
    unittest.main()
