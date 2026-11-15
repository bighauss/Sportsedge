import json,tempfile,unittest,subprocess,sys
from pathlib import Path
from sportsedge_cfb_event_completeness_r4 import run
class R4(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.d=Path(self.tmp.name)
  event={'id':'1','competitions':[{'competitors':[{'homeAway':'home','team':{'id':'11'}},{'homeAway':'away','team':{'id':'22'}}]}]}
  self.payload={'events':[event]}
  self.meta={'independent_census_verified':True,'independent_census_source_url':'https://example.org/census','primary_url':'https://example.org/a','control_url':'https://example.org/b','captured_at_utc':'2026-11-12T20:00:00Z','census_captured_at_utc':'2026-11-12T19:00:00Z'}
  self.paths={k:self.d/(k+'.json' if k!='team_map' else '.csv') for k in ('primary','control','census','team_map','metadata')}
  self.write()
 def tearDown(self):self.tmp.cleanup()
 def write(self):
  for k,v in [('primary',self.payload),('control',self.payload),('census',{'event_ids':['1']}),('metadata',self.meta)]:self.paths[k].write_text(json.dumps(v))
  self.paths['team_map'].write_text('team_id,team_name\n11,A\n22,B\n')
 def test_structural_pass_never_authenticates(self):
  x=run(self.paths);self.assertEqual(x['status'],'STRUCTURAL_PASS_SOURCE_AUTH_PENDING');self.assertFalse(x['source_admitted']);self.assertEqual(len(x['sha256']),5)
 def test_string_false_quarantines(self):
  self.meta['independent_census_verified']='false';self.write();self.assertEqual(run(self.paths)['status'],'QUARANTINE')
 def test_blank_id_quarantines(self):
  self.payload['events'][0]['competitions'][0]['competitors'][0]['team']['id']='';self.write();self.assertEqual(run(self.paths)['status'],'QUARANTINE')
 def test_same_roles_quarantines(self):
  self.payload['events'][0]['competitions'][0]['competitors'][0]['homeAway']='away';self.write();self.assertEqual(run(self.paths)['status'],'QUARANTINE')
 def test_malformed_json_quarantines(self):
  self.paths['primary'].write_text('{');self.assertEqual(run(self.paths)['status'],'QUARANTINE')
 def test_cli_exit_is_nonzero_on_structural_pass(self):
  out=self.d/'out.json';cmd=[sys.executable,str(Path(__file__).with_name('sportsedge_cfb_event_completeness_r4.py')),*map(str,self.paths.values()),'--out',str(out)]
  x=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(x.returncode,4);self.assertEqual(json.loads(out.read_text())['status'],'STRUCTURAL_PASS_SOURCE_AUTH_PENDING')
if __name__=='__main__':unittest.main()
