"""Post-sim DK Showdown exporter tests; synthetic receipt is NOT official."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import export_verified_showdown as m


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.names={"A":"PIT","B":"PIT","C":"PIT","D":"CIN",
                    "E":"CIN","F":"CIN","G":"CIN"}
        self.salary=self.base/"owner.csv"
        self.rows=[]
        for i,(name,tm) in enumerate(self.names.items()):
            for slot,cost,pid in (("CPT",3000,str(1000+i)),
                                  ("FLEX",2000,str(2000+i))):
                self.rows.append(dict(Name=name,TeamAbbrev=tm,Position="WR",
                    ID=pid,**{"Roster Position":slot,"Salary":cost,
                              "Game Info":"PIT@CIN 11/15/2026 08:20PM ET",
                              "Status":"","AvgPointsPerGame":999}))
        self.write_salaries()
        self.lineups=self.base/"lineups.json"
        self.write_lineups()
        self.raw=self.base/"official.txt"
        self.raw.write_text("TEST FIXTURE—not a real official inactive report")
        self.inactive=self.base/"inactives.json"
        self.payload={"game":"PIT@CIN","kickoff_utc":"2026-11-16T01:20:00Z",
                 "captured_at_utc":"2026-11-15T23:50:00Z",
                 "source_url":"https://www.nfl.com/news/fixture",
                 "original_file":"official.txt",
                 "sha256":hashlib.sha256(self.raw.read_bytes()).hexdigest(),
                 "inactive_players":["F"],"teams_confirmed_complete":True}
        self.write_receipt()

    def write_salaries(self):
        with self.salary.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(self.rows[0]))
            w.writeheader();w.writerows(self.rows)

    def write_lineups(self):
        lines=[
            {"cpt":"A","flex":["B","C","D","E","F"],"mean":100},
            {"cpt":"D","flex":["A","B","C","E","G"],"mean":95}]
        self.lineups.write_text(json.dumps({
            "summary":{"label":"RESEARCH / PAPER - not Model_P, unvalidated"},
            "top_by_mean":lines,"top_by_opt_rate":lines}))

    def write_receipt(self):
        self.inactive.write_text(json.dumps(self.payload))

    def export(self):
        return m.export(self.lineups,self.salary,self.inactive,
                        "2026-11-16T01:20:00Z","PIT@CIN")

    def test_export_filters_inactive_and_has_correct_slot_ids(self):
        ids,audit=self.export()
        self.assertEqual(len(ids),1)
        self.assertEqual(ids[0][0],"1003")  # D CPT
        self.assertEqual(ids[0][1],"2000")  # A FLEX
        self.assertEqual(audit["rejected_inactive"][0]["inactive_or_ir"],["F"])
        self.assertEqual(audit["lineups"][0]["salary"],13000)
        self.assertFalse(audit["ready_for_automated_entry"])
        self.assertFalse(audit["source_authentication_independent"])
        self.assertNotIn("AvgPointsPerGame",json.dumps(audit))

    def test_wrong_game_and_mixed_slates_block(self):
        self.payload["game"]="OTHER"
        self.write_receipt()
        with self.assertRaises(m.ExportBlocked):self.export()
        self.payload["game"]="PIT@CIN"
        self.write_receipt()
        self.rows[0]["Game Info"]="LAR@SEA 11/15/2026"
        self.write_salaries()
        with self.assertRaises(m.ExportBlocked):self.export()

    def test_receipt_hash_and_timing_block(self):
        self.payload["sha256"]="a"*64
        self.write_receipt()
        with self.assertRaises(m.ExportBlocked):self.export()
        self.payload["sha256"]=hashlib.sha256(self.raw.read_bytes()).hexdigest()
        self.payload["captured_at_utc"]="2026-11-16T02:00:00Z"
        self.write_receipt()
        with self.assertRaises(m.ExportBlocked):self.export()

    def test_unpaired_slot_and_bad_captain_price_block(self):
        self.rows=[x for x in self.rows if not
                   (x["Name"]=="G" and x["Roster Position"]=="FLEX")]
        self.write_salaries()
        with self.assertRaises(m.ExportBlocked):self.export()
        self.rows.append(dict(Name="G",TeamAbbrev="CIN",Position="WR",
                    ID="2006",**{"Roster Position":"FLEX","Salary":2000,
                          "Game Info":"PIT@CIN 11/15/2026 08:20PM ET",
                          "Status":"","AvgPointsPerGame":999}))
        self.rows[0]["Salary"]=2800
        self.write_salaries()
        with self.assertRaises(m.ExportBlocked):self.export()

    def test_duplicate_player_or_ineligible_player_block(self):
        x=json.loads(self.lineups.read_text())
        x["top_by_mean"][1]["flex"]=["A","B","C","D","E"]
        self.lineups.write_text(json.dumps(x))
        with self.assertRaises(m.ExportBlocked):self.export()

    def test_no_receipt_disallows_generation(self):
        self.inactive.unlink()
        with self.assertRaises(FileNotFoundError):self.export()


if __name__=="__main__":
    unittest.main()
