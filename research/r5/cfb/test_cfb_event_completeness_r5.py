import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sportsedge_cfb_event_completeness_r5 as m
class R5Tests(unittest.TestCase):
 def test_missing_file_quarantine(self):
  with tempfile.TemporaryDirectory() as d:
   p={k:Path(d)/k for k in m.KEYS}
   r=m.run(p)
   self.assertEqual(r['status'],'QUARANTINE');self.assertFalse(r['source_admitted'])
 def test_exact_hashes(self):
  with tempfile.TemporaryDirectory() as d:
   p={k:Path(d)/k for k in m.KEYS}
   for k in m.KEYS:p[k].write_text('[]' if k=='team_map' else '{}')
   r=m.run(p)
   self.assertEqual(r['sha256']['primary'],hashlib.sha256(b'{}').hexdigest())
 def test_read_once(self):
  with tempfile.TemporaryDirectory() as d:
   p={k:Path(d)/k for k in m.KEYS}
   for k in m.KEYS:p[k].write_text('x')
   original=Path.read_bytes; counts={}
   def counted(path):
    counts[str(path)]=counts.get(str(path),0)+1
    return original(path)
   with patch.object(Path,'read_bytes',counted):m.run(p)
   self.assertTrue(all(x==1 for x in counts.values()));self.assertEqual(len(counts),5)
 def test_source_not_admitted_even_if_audit_claims_success(self):
  with tempfile.TemporaryDirectory() as d:
   p={k:Path(d)/k for k in m.KEYS}
   for k in m.KEYS:p[k].write_text('team_id\n' if k=='team_map' else '{}')
   with patch.object(m,'audit',return_value={'status':'STRUCTURAL_PASS_SOURCE_AUTH_PENDING','source_admitted':True}):r=m.run(p)
   self.assertFalse(r['source_admitted']);self.assertEqual(r['release_status'],'PAPER_0U')
 def test_append_only_output(self):
  with tempfile.TemporaryDirectory() as d:
   p={k:Path(d)/k for k in m.KEYS}
   for k in m.KEYS:p[k].write_text('{}')
   out=Path(d)/'out.json';out.write_text('ORIGINAL')
   args=[str(p[k]) for k in m.KEYS]+['--out',str(out)]
   self.assertEqual(m.main(args),5);self.assertEqual(out.read_text(),'ORIGINAL')
 def test_new_output_exit4(self):
  with tempfile.TemporaryDirectory() as d:
   p={k:Path(d)/k for k in m.KEYS}
   for k in m.KEYS:p[k].write_text('{}')
   out=Path(d)/'out.json';args=[str(p[k]) for k in m.KEYS]+['--out',str(out)]
   self.assertEqual(m.main(args),4);self.assertFalse(json.loads(out.read_text())['source_admitted'])
if __name__=='__main__':unittest.main()
