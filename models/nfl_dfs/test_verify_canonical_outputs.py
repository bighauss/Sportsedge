"""Synthetic canonical DFS receipt tests; does not claim provider authentication."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from verify_canonical_outputs import verify


class TestReceipt(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for folder in ("games", "data", "out"):
            (self.root / folder).mkdir()
        self.tag = "TEST"
        (self.root / "showdown_mc.py").write_text("synthetic")
        (self.root / "games/TEST.json").write_text(json.dumps({
            "tag": self.tag, "salary_file": "data/DKSalaries_TEST.csv"}))
        self.players = ["A", "B", "C", "D", "E", "F"]
        with (self.root / "data/DKSalaries_TEST.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "Name", "ID", "Roster Position", "Salary", "TeamAbbrev", "Status"])
            w.writeheader()
            for i, name in enumerate(self.players):
                for slot, ident, cost in (("CPT", i + 100, 1500),
                                          ("FLEX", i + 200, 1000)):
                    w.writerow({"Name": name, "ID": ident, "Roster Position": slot,
                                "Salary": cost, "TeamAbbrev": "PIT", "Status": ""})
        with (self.root / "out/TEST_projections.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "player", "team", "cpt_sal", "flex_sal"])
            w.writeheader()
            for name in self.players:
                w.writerow({"player": name, "team": "PIT",
                            "cpt_sal": 1500, "flex_sal": 1000})
        self.data = {
            "summary": {"sims": 20000, "contest_ev": "BLOCKED"},
            "top_by_mean": [{"cpt": "A", "flex": self.players[1:], "salary": 6500}],
            "top_by_opt_rate": [{"cpt": "A", "flex": self.players[1:], "salary": 6500}],
        }
        self.save()

    def save(self):
        (self.root / "out/TEST_lineups.json").write_text(json.dumps(self.data))

    def modify_csv(self, *, key, value, player="A", slot="CPT"):
        path = self.root / "data/DKSalaries_TEST.csv"
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)
        for row in rows:
            if row["Name"] == player and row["Roster Position"] == slot:
                row[key] = str(value)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_valid_frozen_research(self):
        result = verify("TEST", self.root)
        self.assertEqual(result["players"], 6)
        self.assertEqual(result["official_stake_u"], 0)
        self.assertFalse(result["source_authentication_independent"])

    def test_path_traversal(self):
        with self.assertRaises(ValueError):
            verify("../TEST", self.root)

    def test_missing_engine(self):
        (self.root / "showdown_mc.py").unlink()
        with self.assertRaises(ValueError):
            verify("TEST", self.root)

    def test_contest_ev_fail_open(self):
        self.data["summary"]["contest_ev"] = "PROFIT"
        self.save()
        with self.assertRaises(ValueError):
            verify("TEST", self.root)

    def test_sim_count(self):
        self.data["summary"]["sims"] = 6000
        self.save()
        with self.assertRaises(ValueError):
            verify("TEST", self.root)

    def test_duplicate_lineup_player(self):
        self.data["top_by_mean"][0]["flex"][0] = "A"
        self.save()
        with self.assertRaises(ValueError):
            verify("TEST", self.root)

    def test_lineup_salary_mismatch(self):
        self.data["top_by_mean"][0]["salary"] = 6501
        self.save()
        with self.assertRaises(ValueError):
            verify("TEST", self.root)

    def test_projection_salary_cannot_disagree_with_original(self):
        self.modify_csv(key="Salary", value=1700)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            verify("TEST", self.root)

    def test_duplicate_salary_id(self):
        self.modify_csv(key="ID", value=201)
        with self.assertRaisesRegex(ValueError, "reused"):
            verify("TEST", self.root)

    def test_out_player_in_lineup_blocked(self):
        self.modify_csv(key="Status", value="OUT")
        with self.assertRaisesRegex(ValueError, "inactive"):
            verify("TEST", self.root)

    def test_team_mismatch_blocked(self):
        self.modify_csv(key="TeamAbbrev", value="CIN")
        with self.assertRaisesRegex(ValueError, "identity"):
            verify("TEST", self.root)


if __name__ == "__main__":
    unittest.main()
