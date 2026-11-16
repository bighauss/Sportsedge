import unittest
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
from audit_disagreement_calibration import audit, FIELDS, main
H="a"*64
def row(**changes):
 r=dict(event_id="e",market="moneyline",selection="home",model_p=".6",market_p=".5",outcome="1",snapshot_utc="2026-11-15T20:00:00Z",kickoff_utc="2026-11-15T21:00:00Z",final_utc="2026-11-16T00:00:00Z",model_sha256=H,source_sha256=H,odds="-110")
 r.update(changes);return r
class Tests(unittest.TestCase):
 def test_good(self):
  a=audit([row()]);self.assertEqual(a["accepted"],1);self.assertEqual(a["overall"]["brier"],.16)
 def test_lookahead(self):
  a=audit([row(snapshot_utc="2026-11-15T22:00:00Z")]);self.assertEqual(a["accepted"],0)
 def test_missing_hash(self):
  a=audit([row(source_sha256="bad")]);self.assertEqual(a["accepted"],0)
 def test_duplicate(self):
  a=audit([row(),row()]);self.assertEqual(a["accepted"],0);self.assertEqual(len(a["blocked"]),2)
 def test_bad_first_duplicate_cannot_poison_grade(self):
  bad=row(model_p="nan")
  for rr in ([bad,row()],[row(),bad]):
   report=audit(rr)
   self.assertEqual(report["accepted"],0)
   self.assertEqual(len(report["blocked"]),2)
   self.assertTrue(all(x["reason"]=="DUPLICATE" for x in report["blocked"]))
 def test_changed_odds_same_snapshot_all_blocked(self):
  report=audit([row(odds="+300"),row(odds="-110")])
  self.assertEqual(report["accepted"],0)
  self.assertEqual(len(report["blocked"]),2)
 def test_distinct_selection_identifiers_preserved(self):
  report=audit([row(),row(selection="away",market_p=".4",outcome="0")])
  self.assertEqual(report["accepted"],2)

 def test_push(self):self.assertEqual(audit([row(outcome="push")])["accepted"],0)
 def test_naive(self):self.assertEqual(audit([row(snapshot_utc="2026-11-15T20:00:00")])["accepted"],0)
 def test_invalid_probability(self):self.assertEqual(audit([row(model_p="1.2")])["accepted"],0)
 def test_market_split(self):
  a=audit([row(),row(event_id="e2",market_p=".7",outcome="0")])
  self.assertEqual(a["accepted"],2);self.assertEqual(len(a["disagreement"]),2)
 def test_deciles(self):
  a=audit([row(),row(event_id="e2",model_p=".21",outcome="0")])
  self.assertEqual([x["decile"] for x in a["calibration"]],[2,6])
 def test_exact_ten_pp(self):
  from audit_disagreement_calibration import bucket
  self.assertEqual(bucket(.6-.5),"10-20pp")
 def test_threshold_near_miss_is_not_promoted_by_rounding(self):
  from audit_disagreement_calibration import bucket
  self.assertEqual(bucket(.04996),"0-5pp")
  self.assertEqual(bucket(.09996),"5-10pp")
  self.assertEqual(bucket(.19996),"10-20pp")
  self.assertEqual(bucket(.05),"5-10pp")
  self.assertEqual(bucket(.1),"10-20pp")
  self.assertEqual(bucket(.2),"20pp+")
  self.assertEqual(bucket(.6-.5),"10-20pp")
  self.assertEqual(bucket(-(.6-.5)),"10-20pp")
 def test_actual_report_near_ten_pp_correct_bucket(self):
  rr=audit([row(model_p=".59996",market_p=".5")])
  self.assertEqual(rr["disagreement"][0]["bucket"],"5-10pp")
 def test_many_alt_lines_one_game_is_not_independent_sample(self):
  a=audit([row(event_id="same_game",market=f"altline_{i}",
               selection=f"under_{i}") for i in range(32)])
  self.assertEqual(a["overall"]["n"],32)
  self.assertEqual(a["overall"]["unique_events"],1)
  self.assertFalse(a["overall"]["insufficient_n30"])
  self.assertTrue(a["overall"]["insufficient_unique_events_30"])
  self.assertTrue(a["overall"]["event_dependent_selections"])
  self.assertIsNone(a["overall"]["observed_wilson_95"])
  self.assertTrue(a["overall"]["roi_descriptive_only"])
 def test_distinct_games_versus_distinct_selections(self):
  a=audit([row(event_id=str(i),selection="home") for i in range(30)])
  self.assertEqual(a["overall"]["unique_events"],30)
  self.assertFalse(a["overall"]["insufficient_unique_events_30"])
  self.assertFalse(a["overall"]["event_dependent_selections"])
  self.assertEqual(len(a["overall"]["observed_wilson_95"]),2)
 def test_roi_and_ci(self):
  a=audit([row()])
  self.assertAlmostEqual(a["overall"]["roi"],100/110,places=6)
  self.assertTrue(a["overall"]["insufficient_n30"])
  self.assertEqual(len(a["overall"]["observed_wilson_95"]),2)
 def test_stats_after_odds_tuple_expansion(self):
  a=audit([row(),row(event_id="second",model_p=".4",market_p=".3",outcome="0",odds="+250")])
  self.assertEqual(a["accepted"],2)
  self.assertEqual(a["overall"]["market_brier"],.17)
  self.assertAlmostEqual(a["overall"]["roi"],(100/110-1)/2,places=5)
  self.assertTrue(all(k in a["overall"] for k in ("market_log_loss","bias","observed","predicted")))
 def test_n30_and_wilson_bounds(self):
  a=audit([row(event_id=str(i),outcome="1" if i<15 else "0") for i in range(30)])
  self.assertFalse(a["overall"]["insufficient_n30"])
  self.assertLess(a["overall"]["observed_wilson_95"][0],.5)
  self.assertGreater(a["overall"]["observed_wilson_95"][1],.5)
 def test_invalid_odds(self):
  self.assertEqual(audit([row(odds="0")])["accepted"],0)
 def test_private_cli_create_only_source_hash_and_mode(self):
  with tempfile.TemporaryDirectory() as d:
   src,out=Path(d)/"original.csv",Path(d)/"report.json"
   with src.open("w",encoding="utf-8",newline="") as f:
    w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerow(row())
   raw=src.read_bytes()
   self.assertEqual(main([str(src),"--output",str(out)]),0)
   report=json.loads(out.read_text())
   self.assertEqual(report["input_sha256"],hashlib.sha256(raw).hexdigest())
   self.assertFalse(report["input_original_provider_authenticated"])
   self.assertEqual(report["accepted"],1)
   self.assertEqual(os.stat(out).st_mode & 0o777,0o600)

 def test_cli_never_overwrites_existing_report(self):
  with tempfile.TemporaryDirectory() as d:
   src,out=Path(d)/"original.csv",Path(d)/"report.json"
   with src.open("w",encoding="utf-8",newline="") as f:
    w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerow(row())
   out.write_text("SAVED HISTORICAL REPORT")
   with self.assertRaises(FileExistsError):
    main([str(src),"--output",str(out)])
   self.assertEqual(out.read_text(),"SAVED HISTORICAL REPORT")

 def test_cli_refuses_originals_and_outputs_in_public_repo(self):
  from audit_disagreement_calibration import REPO_ROOT
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/"original.csv"
   with src.open("w",encoding="utf-8",newline="") as f:
    w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerow(row())
   with self.assertRaisesRegex(ValueError,"INSIDE_PUBLIC_CHECKOUT"):
    main([str(Path(__file__).resolve()),"--output",str(Path(d)/"out.json")])
   with self.assertRaisesRegex(ValueError,"INSIDE_PUBLIC_CHECKOUT"):
    main([str(src),"--output",str(REPO_ROOT/"private_report.json")])

 def test_cli_refuses_duplicate_headers_and_truncated_rows(self):
  with tempfile.TemporaryDirectory() as d:
   src,out=Path(d)/"original.csv",Path(d)/"report.json"
   src.write_text(",".join(FIELDS)+",odds\n"+",".join(row()[f] for f in FIELDS)+",-110\n")
   with self.assertRaisesRegex(ValueError,"DUPLICATE_CSV_HEADER"):
    main([str(src),"--output",str(out)])
   self.assertFalse(out.exists())
   src.write_text(",".join(FIELDS)+"\n"+",".join(row()[f] for f in FIELDS[:-1])+"\n")
   with self.assertRaisesRegex(ValueError,"TRUNCATED_OR_OVERLONG_CSV_ROW"):
    main([str(src),"--output",str(out)])
   self.assertFalse(out.exists())
   src.write_text(",".join(FIELDS)+"\n"+",".join(row()[f] for f in FIELDS)+",EXTRA\n")
   with self.assertRaisesRegex(ValueError,"TRUNCATED_OR_OVERLONG_CSV_ROW"):
    main([str(src),"--output",str(out)])

 def test_cli_refuses_symlink_source_and_output(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/"original.csv"
   with src.open("w",encoding="utf-8",newline="") as f:
    w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerow(row())
   alias=Path(d)/"alias.csv";alias.symlink_to(src)
   with self.assertRaisesRegex(ValueError,"UNTRUSTED_SYMLINK"):
    main([str(alias),"--output",str(Path(d)/"out.json")])
   report=Path(d)/"report.json";report.write_text("PROTECTED")
   outalias=Path(d)/"alias.json";outalias.symlink_to(report)
   with self.assertRaisesRegex(ValueError,"UNTRUSTED_SYMLINK"):
    main([str(src),"--output",str(outalias)])
   self.assertEqual(report.read_text(),"PROTECTED")

if __name__=="__main__":unittest.main()
