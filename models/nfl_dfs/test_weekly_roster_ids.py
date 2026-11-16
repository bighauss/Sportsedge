"""One-to-one GSIS roster identity audit tests. No provider FP inputs."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import audit_weekly_roster_ids as roster
from build_game_inputs import Blocked


class TestWeeklyIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        weekly_path=self.root/"weekly.csv.gz"
        b=io.StringIO()
        w=csv.DictWriter(b,fieldnames=("player_id","player_display_name",
                                       "position","season","season_type","week","team",
                                       "passing_interceptions","FD Pts"))
        w.writeheader()
        w.writerows([
           {"player_id":"00-001","player_display_name":"Exact Receiver","position":"WR",
            "season":"2026","season_type":"REG","week":"9","team":"CIN",
            "passing_interceptions":"0","FD Pts":"50000"},
           {"player_id":"00-002","player_display_name":"Different Player","position":"RB",
            "season":"2026","season_type":"REG","week":"9","team":"PIT",
            "passing_interceptions":"0","FD Pts":"7000"}])
        self.weekly=gzip.compress(b.getvalue().encode(),mtime=0)
        weekly_path.write_bytes(self.weekly)
        salary_path=self.root/"owner.csv"
        with salary_path.open("w",newline="") as f:
            s=csv.DictWriter(f,fieldnames=("Name","TeamAbbrev","Position",
                  "Roster Position","Salary","ID","Status","AvgPointsPerGame"))
            s.writeheader()
            s.writerows([
             {"Name":"Exact Receiver","TeamAbbrev":"CIN","Position":"WR",
              "Roster Position":"FLEX","Salary":"5000","ID":"111","Status":"",
              "AvgPointsPerGame":"999"},
             {"Name":"Similar Name","TeamAbbrev":"PIT","Position":"RB",
              "Roster Position":"FLEX","Salary":"4000","ID":"222","Status":"",
              "AvgPointsPerGame":"999"},
             {"Name":"Exact Receiver","TeamAbbrev":"CIN","Position":"WR",
              "Roster Position":"CPT","Salary":"7500","ID":"333","Status":"",
              "AvgPointsPerGame":"999"}])
        self.meta={"kickoff_utc":"2026-11-16T01:20:00Z",
                   "weekly":self.spec(weekly_path),
                   "salaries":self.spec(salary_path)}
        self.manifest=self.root/"manifest.json"
        self.save()
    def spec(self,path):
        return {"path":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "captured_at_utc":"2026-11-15T22:19:56Z"}
    def save(self):
        self.manifest.write_text(json.dumps(self.meta))

    def test_exact_without_fuzzy_assignment(self):
        x=roster.audit(self.manifest)
        self.assertEqual((x["exact_count"],x["unmatched_count"]),(1,1))
        self.assertEqual(x["exact"][0]["gsis_id"],"00-001")
        self.assertEqual(x["unmatched"][0]["reason"],"NO_EXACT_PRIOR_WEEK_IDENTITY")
        self.assertTrue(x["blocked_for_full_auto_build"])
        self.assertNotIn("AvgPointsPerGame",json.dumps(x))
        self.assertNotIn("999",json.dumps(x))

    def test_bad_archive_hash_blocks(self):
        self.meta["weekly"]["sha256"]="0"*64
        self.save()
        with self.assertRaises(Blocked):roster.audit(self.manifest)

    def test_postkickoff_capture_blocks(self):
        self.meta["salaries"]["captured_at_utc"]="2026-11-16T02:00:00Z"
        self.save()
        with self.assertRaises(Blocked):roster.audit(self.manifest)

    def test_duplicate_identity_blocks(self):
        p=self.root/"owner.csv"
        raw=p.read_text()
        p.write_text(raw+raw.splitlines()[1]+"\n")
        self.meta["salaries"]=self.spec(p)
        self.save()
        with self.assertRaises(Blocked):roster.audit(self.manifest)


if __name__=="__main__":
    unittest.main()
