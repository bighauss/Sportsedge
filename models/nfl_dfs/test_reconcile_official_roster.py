"""Offline test of official roster/GSIS reconciliation; no real DK salary rows."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from reconcile_official_roster import reconcile, Blocked


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.dk=[
            ("Alias WR","PIT","WR",""),
            ("Exact QB","PIT","QB",""),
            ("No History RB","PIT","RB",""),
            ("Practice WR","CIN","WR",""),
            ("IR WR","CIN","WR","IR"),
            ("FB Person","PIT","RB",""),
            ("LS Person","CIN","TE","")]
        self.official=[
            ("Alias WR","PIT","WR","ACTIVE_ROSTER","Provider WR"),
            ("Exact QB","PIT","QB","ACTIVE_ROSTER",""),
            ("No History RB","PIT","RB","ACTIVE_ROSTER",""),
            ("Practice WR","CIN","WR","PRACTICE_SQUAD",""),
            ("IR WR","CIN","","NOT_LISTED",""),
            ("FB Person","PIT","FB","ACTIVE_ROSTER",""),
            ("LS Person","CIN","LS","ACTIVE_ROSTER","")]
        self.weekly=[
            ("00-1","Provider WR","PIT","WR"),
            ("00-2","Exact QB","PIT","QB"),
            ("00-4","Practice WR","CIN","WR"),
            ("00-6","FB Person","PIT","FB"),
            ("00-7","LS Person","CIN","LS")]
        self.meta={"kickoff_utc":"2026-11-16T01:20:00Z",
                   "season":2026,"week":10,
                   "official_roster_source_url":"https://static.clubs.nfl.com/gameprogram"}
        self.save()

    def csvfile(self,name,rows):
        buf=io.StringIO()
        w=csv.DictWriter(buf,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
        p=self.root/name
        raw=buf.getvalue().encode("utf-8")
        if name.endswith(".gz"):raw=gzip.compress(raw,mtime=0)
        p.write_bytes(raw)
        return {"path":name,"sha256":hashlib.sha256(raw).hexdigest(),
                "captured_at_utc":"2026-11-15T23:00:00Z"}

    def save(self):
        dkrows=[]
        for i,(n,t,pos,status) in enumerate(self.dk):
            for j,role in enumerate(("FLEX","CPT")):
                dkrows.append({"Name":n,"TeamAbbrev":t,"Position":pos,
                    "ID":str(100+i*2+j),"Roster Position":role,
                    "Salary":str(2000 if role=="FLEX" else 3000),
                    "Game Info":"PIT@CIN 11/15/2026",
                    "Status":status,"AvgPointsPerGame":"999999"})
        self.meta["owner_dk"]=self.csvfile("dk.csv",dkrows)
        r=[{"dk_name":n,"team":t,
            "official_name":n if bucket!="NOT_LISTED" else "",
            "official_role":role,"program_group":bucket,"nflverse_name":alias}
           for n,t,role,bucket,alias in self.official]
        self.meta["official_roster"]=self.csvfile("roster.csv",r)
        w=[{"player_id":pid,"player_display_name":n,"team":t,
            "position":pos,"season":"2026","week":"8","season_type":"REG",
            "fantasy_points_ppr":"12345"} for pid,n,t,pos in self.weekly]
        self.meta["weekly"]=self.csvfile("weekly.csv.gz",w)
        (self.root/"manifest.json").write_text(json.dumps(self.meta))

    def audit(self):
        return reconcile(self.root/"manifest.json")

    def test_alias_explicit_but_not_final_inactive(self):
        r=self.audit()
        names={x["dk_name"]:x for x in r["player_audit"]}
        self.assertEqual(names["Alias WR"]["gsis_id"],"00-1")
        self.assertTrue(names["Alias WR"]["explicit_alias"])
        self.assertTrue(names["Alias WR"]["can_research_prior_role_features"])
        self.assertFalse(names["Alias WR"]["can_enter_contest"])
        self.assertEqual(r["contest_ready"],0)
        self.assertNotIn("999999",json.dumps(r))
        self.assertNotIn("12345",json.dumps(r))

    def test_practice_squad_and_ir_blocked(self):
        v={x["dk_name"]:x for x in self.audit()["player_audit"]}
        for n in ("Practice WR","IR WR"):
            self.assertEqual(v[n]["block_reason"],"NOT_ACTIVE_ROSTER_OR_DK_OUT")

    def test_positions_fb_and_long_snapper_not_rebranded(self):
        v={x["dk_name"]:x for x in self.audit()["player_audit"]}
        for n in ("FB Person","LS Person"):
            self.assertEqual(v[n]["block_reason"],"STATS_POSITION_DIFFERS_FROM_DK_ROLE")

    def test_missing_prior_stats_not_fabricated_as_zero(self):
        v={x["dk_name"]:x for x in self.audit()["player_audit"]}
        self.assertIsNone(v["No History RB"]["gsis_id"])
        self.assertEqual(v["No History RB"]["block_reason"],"NO_PRIOR_SAME_TEAM_GSIS_ID")

    def test_unapproved_alias_never_fuzzily_matched(self):
        self.official[0]=("Alias WR","PIT","WR","ACTIVE_ROSTER","")
        self.save()
        v={x["dk_name"]:x for x in self.audit()["player_audit"]}
        self.assertIsNone(v["Alias WR"]["gsis_id"])

    def test_source_digest_and_future_capture_block(self):
        self.meta["weekly"]["sha256"]="0"*64
        (self.root/"manifest.json").write_text(json.dumps(self.meta))
        with self.assertRaises(Blocked):self.audit()
        self.save()
        self.meta["official_roster"]["captured_at_utc"]="2026-11-16T03:00:00Z"
        (self.root/"manifest.json").write_text(json.dumps(self.meta))
        with self.assertRaises(Blocked):self.audit()

    def test_missing_roster_entry_fails_closed(self):
        self.official.pop()
        self.save()
        with self.assertRaises(Blocked):self.audit()

    def test_duplicate_dk_flex_player_fails_closed(self):
        self.dk.append(self.dk[0])
        self.save()
        with self.assertRaises(Blocked):self.audit()


if __name__=="__main__":
    unittest.main()
