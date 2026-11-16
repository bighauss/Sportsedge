"""Static safety/shape checks for the optional OpenMausBot import template.

This tests our repository-side contract, not a live OpenMausBot import.
No external dependencies and no network access.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
TEAM = (ROOT / "SPORTSEDGE_TEAM.md").read_text(encoding="utf-8")
RUNBOOK = (ROOT / "README.md").read_text(encoding="utf-8")

SPORT_AGENTS = {"nfl", "cfb", "cbb", "nba", "mlb", "nhl", "pga"}
SHARED_AGENTS = {"chief", "capture", "auditor", "guardian"}
REQUIRED_SECTIONS = {
    "Activation",
    "Mission",
    "Outcomes",
    "Connections",
    "Team",
    "Chief of Staff",
    "Shared rooms",
    "Playbooks",
    "Completion rule",
}


class TeamContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(TEAM.startswith("---\n"), "Missing YAML frontmatter")
        self.assertIn("\n---\n", TEAM[4:], "Missing frontmatter closing separator")
        self.frontmatter, self.body = TEAM[4:].split("\n---\n", 1)

    def test_markdown_v1_markers_and_required_sections(self):
        self.assertRegex(self.frontmatter, r"(?m)^botmrr: 1$")
        self.assertRegex(self.frontmatter, r"(?m)^id: sportsedge-engineering-crew$")
        self.assertRegex(self.frontmatter, r"(?m)^release: 1\.0\.0$")
        for field in ("name:", "agents:", "chiefOfStaff:", "rooms:", "playbooks:", "routines:"):
            self.assertIn("\n" + field, "\n" + self.frontmatter)
        headings = set(re.findall(r"(?m)^## (.+)$", self.body))
        self.assertFalse(REQUIRED_SECTIONS - headings)

    def test_roles_are_unique_and_cover_seven_sports(self):
        agent_block = self.frontmatter.split("\nagents:\n", 1)[1].split(
            "\nchiefOfStaff:", 1
        )[0]
        keys = re.findall(r"(?m)^  - key: ([a-z][a-z0-9-]*)$", agent_block)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), SPORT_AGENTS | SHARED_AGENTS)
        self.assertIn("\nchiefOfStaff: chief\n", self.frontmatter)

    def test_rooms_only_reference_declared_roles(self):
        room_block = self.frontmatter.split("\nrooms:\n", 1)[1].split(
            "\nroutines:", 1
        )[0]
        room_keys = re.findall(r"(?m)^  - key: ([a-z][a-z0-9-]*)$", room_block)
        self.assertEqual(set(room_keys), {
            "command",
            "seven-sport-models",
            "source-and-gates",
        })
        members = re.findall(r"(?m)^      - ([a-z][a-z0-9-]*)$", room_block)
        self.assertTrue(members)
        self.assertFalse(set(members) - (SPORT_AGENTS | SHARED_AGENTS))

    def test_no_activated_routine_or_financial_execution(self):
        self.assertIn("\nroutines: []\n", self.frontmatter)
        for phrase in ("PAPER / 0u", "Do not", "A-E", "GitHub"):
            self.assertIn(phrase, TEAM)
        self.assertIn("NOT installed", RUNBOOK)
        self.assertIn("never", RUNBOOK.lower())

    def test_no_obvious_embedded_secrets(self):
        combined = TEAM + RUNBOOK
        patterns = (
            r"gh[pousr]_[A-Za-z0-9]{20,}",
            r"sk-[A-Za-z0-9]{24,}",
            r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]{10,}",
            r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----",
        )
        for pattern in patterns:
            self.assertIsNone(re.search(pattern, combined))


if __name__ == "__main__":
    unittest.main()
