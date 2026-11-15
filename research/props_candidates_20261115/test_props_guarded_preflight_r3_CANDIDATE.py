import csv,copy,json,pathlib,subprocess,sys,tempfile,unittest
D=pathlib.Path(__file__).parent
from sportsedge_props_guarded_preflight_r3_CANDIDATE import audit

def put(p,headers,rows):
 with open(p,'w',newline='') as fh:
  w=csv.DictWriter(fh,fieldnames=headers);w.writeheader();w.writerows(rows)
class TestGuard(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.d=pathlib.Path(self.tmp.name)
  self.p=[dict(sport='NBA',player='Nikola Jokic',team='DEN',games='20',minutes='36',pts='25',reb='12',ast='9',threes='2'),
          dict(sport='NBA',player='Jamal Murray',team='DEN',games='20',minutes='35',pts='23',reb='4',ast='6',threes='3')]
  self.r=[{k:v for k,v in x.items() if k in ['team','player','minutes','pts','reb','ast','threes']} for x in self.p]
  self.b=[dict(sport='NBA',player='Nikola Jokic',team='DEN',market='POINTS',total='230')]
  self.o=[dict(player='Jamal Murray')]
 def tearDown(self):self.tmp.cleanup()
 def runcheck(self):
  put(self.d/'b.csv',['sport','player','team','market','total'],self.b)
  put(self.d/'p.csv',['sport','player','team','games','minutes','pts','reb','ast','threes'],self.p)
  put(self.d/'r.csv',['team','player','minutes','pts','reb','ast','threes'],self.r)
  put(self.d/'o.csv',['player'],self.o)
  return audit(self.d/'b.csv',self.d/'p.csv',self.d/'r.csv',self.d/'o.csv')[0]
 def codes(self):return [v['code'] for v in self.runcheck()]
 def test_clean(self):self.assertEqual(self.codes(),[])
 def test_clean_zeromin(self):self.p[0]['minutes']='0';self.assertEqual(self.codes(),[])
 def test_bad_player_minute(self):self.p[0]['minutes']='nan';self.assertIn('INVALID_NUMERIC',self.codes())
 def test_bad_roster_minute(self):self.r[0]['minutes']='-1';self.assertIn('INVALID_NUMERIC',self.codes())
 def test_bad_stat(self):self.p[0]['pts']='inf';self.assertIn('INVALID_NUMERIC',self.codes())
 def test_out_typo(self):self.o=[dict(player='Jamal Murrey')];self.assertIn('UNMATCHED_OUT',self.codes())
 def test_out_surname(self):self.o=[dict(player='Murray')];self.assertIn('UNMATCHED_OUT',self.codes())
 def test_out_duplicate(self):self.o.append(dict(player='Jamal Murray'));self.assertIn('DUPLICATE_OUT',self.codes())
 def test_out_no_roster(self):self.r=self.r[:1];self.assertIn('OUT_NOT_IN_ROSTER',self.codes())
 def test_player_team_mismatch(self):self.p[1]['team']='MEM';self.assertIn('PLAYERS_ROSTER_TEAM_MISMATCH',self.codes())
 def test_board_team_mismatch(self):self.b[0]['team']='LAL';self.assertIn('BOARD_TEAM_MISMATCH',self.codes())
 def test_player_duplicate(self):self.p.append(copy.copy(self.p[0]));self.assertIn('DUPLICATE_OR_COLLIDING_IDENTITY',self.codes())
 def test_collision_accent(self):self.p.append(dict(self.p[0],player='Nikola Jokić')) ;self.assertIn('DUPLICATE_OR_COLLIDING_IDENTITY',self.codes())
 def test_roster_cross_team(self):self.r.append(dict(self.r[1],team='MEM'));self.assertIn('DUPLICATE_OR_COLLIDING_IDENTITY',self.codes())
 def test_missing_board_name(self):self.b[0]['player']='Marcus Morris';self.assertIn('BOARD_PLAYER_UNMATCHED',self.codes())
 def test_alias_is_allowed(self):
  for d in (self.p,self.r,self.b):
   for row in d:row['team']='NOP' if d is not self.r else 'NO'
  self.assertEqual(self.codes(),[])
 def test_reject_extra_cell(self):
  self.runcheck();(self.d/'b.csv').write_text('sport,player,team,market\nNBA,Nikola Jokic,DEN,POINTS,EXTRA\n')
  issues,_=audit(self.d/'b.csv',self.d/'p.csv',self.d/'r.csv',self.d/'o.csv')
  self.assertIn('EXTRA_CELLS',[x['code'] for x in issues])
 def test_clean_wrapper_matches_engine_exact_bytes(self):
  self.o=[]
  self.runcheck()
  inp=[str(self.d/'b.csv'),str(self.d/'p.csv')]
  engine=str(D/'v04.py');wrapper=str(D/'sportsedge_props_guarded_preflight_r3_CANDIDATE.py')
  direct=subprocess.run([sys.executable,engine,*inp,'--rosters',str(self.d/'r.csv'),'--out',str(self.d/'base.csv')],capture_output=True)
  guarded=subprocess.run([sys.executable,wrapper,*inp,'--engine',engine,'--rosters',str(self.d/'r.csv'),'--out',str(self.d/'guarded.csv'),'--receipt',str(self.d/'r.json')],capture_output=True)
  self.assertEqual((direct.returncode,guarded.returncode),(0,0))
  self.assertEqual((self.d/'base.csv').read_bytes(),(self.d/'guarded.csv').read_bytes())
  self.assertEqual(json.loads((self.d/'r.json').read_text())['status'],'PAPER_PREFLIGHT_PASS')
 def test_block_removes_stale_output(self):
  self.runcheck();(self.d/'b.csv').write_text('sport,player,team,market,total\nNBA,Nikola Jokic,LAL,POINTS,230\n')
  (self.d/'guarded.csv').write_text('STALE')
  cp=subprocess.run([sys.executable,str(D/'sportsedge_props_guarded_preflight_r3_CANDIDATE.py'),str(self.d/'b.csv'),str(self.d/'p.csv'),'--engine',str(D/'v04.py'),'--rosters',str(self.d/'r.csv'),'--out',str(self.d/'guarded.csv')],capture_output=True)
  self.assertEqual(cp.returncode,2)
  self.assertFalse((self.d/'guarded.csv').exists())
if __name__=='__main__':unittest.main(verbosity=2)
