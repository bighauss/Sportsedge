import csv,json,tempfile,unittest
from pathlib import Path
from verify_canonical_outputs import verify

class TestReceipt(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.r=Path(self.tmp.name)
  for d in ("games","data","out"): (self.r/d).mkdir()
  self.tag="TEST"
  (self.r/"showdown_mc.py").write_text("test")
  (self.r/"games/TEST.json").write_text(json.dumps({"tag":"TEST","salary_file":"data/DKSalaries_TEST.csv"}))
  (self.r/"data/DKSalaries_TEST.csv").write_text("Name\n")
  names=["A","B","C","D","E","F"]
  with (self.r/"out/TEST_projections.csv").open("w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=["player","cpt_sal","flex_sal"]);w.writeheader()
   for n in names:w.writerow({"player":n,"cpt_sal":1500,"flex_sal":1000})
  self.data={"summary":{"sims":20000,"contest_ev":"BLOCKED"},"top_by_mean":[{"cpt":"A","flex":names[1:],"salary":6500}],"top_by_opt_rate":[{"cpt":"A","flex":names[1:],"salary":6500}]}
  self.save()
 def save(self):(self.r/"out/TEST_lineups.json").write_text(json.dumps(self.data))
 def test_good(self):self.assertEqual(verify("TEST",self.r)["players"],6)
 def test_bad_tag(self):
  with self.assertRaises(ValueError):verify("../TEST",self.r)
 def test_missing(self):
  (self.r/"showdown_mc.py").unlink()
  with self.assertRaises(ValueError):verify("TEST",self.r)
 def test_ev(self):
  self.data["summary"]["contest_ev"]="PROFIT";self.save()
  with self.assertRaises(ValueError):verify("TEST",self.r)
 def test_sim_count(self):
  self.data["summary"]["sims"]=6000;self.save()
  with self.assertRaises(ValueError):verify("TEST",self.r)
 def test_duplicate(self):
  self.data["top_by_mean"][0]["flex"][0]="A";self.save()
  with self.assertRaises(ValueError):verify("TEST",self.r)
 def test_salary(self):
  self.data["top_by_mean"][0]["salary"]=6501;self.save()
  with self.assertRaises(ValueError):verify("TEST",self.r)
if __name__=="__main__":unittest.main()
