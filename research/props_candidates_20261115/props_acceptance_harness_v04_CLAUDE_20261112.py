import csv,subprocess,sys,tempfile,pathlib,hashlib
A=pathlib.Path(sys.argv[1]); V=A/'v02.py'; C=A/'v04.py'
DEN="""DEN,Jamal Murray,36.9,25.8,5.1,5.7,4.0
DEN,Nikola Jokic,36.2,23.1,10.8,9.1,1.0
DEN,Christian Braun,34.1,12.4,4.0,2.2,1.6
DEN,Aaron Gordon,29.3,11.2,5.2,2.1,1.1
DEN,Cameron Johnson,28.0,10.3,3.8,1.7,2.0
DEN,DeMar DeRozan,23.9,10.3,2.1,2.9,0.3
DEN,Trevon Brazile,20.3,7.1,5.7,0.6,0.8
DEN,Spencer Jones,17.5,6.5,3.0,0.5,1.5
DEN,Bryce Hopkins,14.3,5.4,2.0,0.4,0.3
DEN,Marvin Bagley III,12.3,6.0,3.4,0.6,0.0
DEN,Tyus Jones,10.6,2.8,0.6,1.8,0.3
DEN,Alpha Diallo,8.0,1.0,0.8,0.5,0.0
DEN,Cam Whitmore,7.5,4.0,1.0,0.5,0.0
DEN,Zeke Nnaji,3.5,3.5,0.5,0.0,0.5
DEN,Ryan Nembhard,3.3,3.0,0.3,0.7,0.3
DEN,DaRon Holmes,2.5,0.8,0.3,0.5,0.3
MEM,Zach Edey,20.8,8.2,8.0,1.0,0.1
MEM,Ty Jerome,30.6,26.7,3.7,4.9,2.8
MEM,Kris Murray,12.1,1.3,1.7,0.7,0.1
MEM,Carson Cooper,3.0,1.0,2.0,1.0,0.0
LAL,Luka Doncic,36.3,39.3,7.8,7.9,5.5
LAL,Austin Reaves,36.2,25.3,3.4,4.6,2.4"""
ROS=[dict(zip("team player minutes pts reb ast threes".split(),l.split(','))) for l in DEN.splitlines()]
PF=['sport','player','team','games','minutes','pts','reb','ast','threes']
def W(p,f,rows):
 with open(p,'w',newline='') as fh:
  w=csv.DictWriter(fh,fieldnames=f,extrasaction='ignore');w.writeheader();w.writerows(rows)
def pl(rows,games=20): return [dict(sport='NBA',games=games,**r) for r in rows]
def brd(names,mk=('POINTS','REBOUNDS','ASSISTS','THREES','PRA'),tot=''):
 return [dict(sport='NBA',player=n,team=t,market=m,total=tot) for n,t in names for m in mk]
def run(script,board,players,rosters=None,outs=None,teams=None):
 p=pathlib.Path(tempfile.mkdtemp(dir=A)); W(p/'b.csv',['sport','player','team','market','total','home_proj','away_proj'],board); W(p/'p.csv',PF,players)
 cmd=[sys.executable,'-I',str(script),str(p/'b.csv'),str(p/'p.csv'),'--out',str(p/'o.csv')]
 if rosters is not None: W(p/'r.csv',['team','player','minutes','pts','reb','ast','threes'],rosters);cmd+=['--rosters',str(p/'r.csv')]
 if outs is not None: W(p/'x.csv',['player'],[{'player':o} for o in outs]);cmd+=['--outlist',str(p/'x.csv')]
 if teams: W(p/'t.csv',['team','avg_total'],[{'team':k,'avg_total':v} for k,v in teams.items()]);cmd+=['--teams',str(p/'t.csv')]
 r=subprocess.run(cmd,capture_output=True,text=True); o=(p/'o.csv').read_bytes() if (p/'o.csv').exists() else None
 return r,o
def proj(o,name):
 return {r['market']:r['proj'] for r in csv.DictReader(o.decode().splitlines()) if r['player']==name}
den=[r for r in ROS if r['team']=='DEN']
B=brd([('Nikola Jokic','DEN'),('Jamal Murray','DEN'),('Christian Braun','DEN')])
res={}
print("== REQ1 Denver replay (Murray OUT)")
oo={}
ok1=True
for n,s in(('v0.2',V),('v0.4',C)):
 r,o=run(s,B,pl(den),den,['Jamal Murray']); oo[n]=o; j=proj(o,'Nikola Jokic')
 print(n,'rc',r.returncode,'Jokic PTS/REB/AST',j['POINTS'],j['REBOUNDS'],j['ASSISTS'],'stderr',r.stderr.strip()[:80] or '-')
 ok1&=(j['POINTS'],j['REBOUNDS'],j['ASSISTS'])==('25.7','11.31','9.67')
ok1&=oo['v0.2']==oo['v0.4']
print('byte-identical',oo['v0.2']==oo['v0.4'],hashlib.sha256(oo['v0.4']).hexdigest()[:16]); res['REQ1']=ok1
print("== REQ2 crash regression (zero-minute)")
ok2=True
for z in('DaRon Holmes','Nikola Jokic'):
 d0=[dict(r,minutes='0',pts='0',reb='0',ast='0',threes='0') if r['player']==z else r for r in den]
 for n,s in(('v0.2',V),('v0.4',C)):
  r,o=run(s,brd([('Nikola Jokic','DEN'),(z,'DEN')],('POINTS',)),pl(d0),d0,['Jamal Murray'])
  print(z,n,'rc',r.returncode,(r.stderr.strip().splitlines() or [''])[-1][:90])
  if n=='v0.4': ok2&=(r.returncode==0)
res['REQ2']=ok2
print("== REQ3 parity (normal cases)")
allp=pl(ROS); names=[(r['player'],r['team']) for r in ROS]; Ba=brd(names)
Bpace=[dict(r,home_proj='115',away_proj='112') if r['team'] in('DEN','MEM') else r for r in Ba]
cases={'no_out_no_roster':(Ba,allp,None,None,None),'no_out_roster':(Ba,allp,ROS,None,None),
'murray_out_roster':(Ba,allp,ROS,['Jamal Murray'],None),
'multi_out_teams':(Ba,allp,ROS,['Jamal Murray','Ty Jerome'],{'DEN':226.4,'MEM':228.7,'LAL':236.5}),
'out_no_roster':(Ba,allp,None,['Nikola Jokic'],{'DEN':226.4}),
'pace_cols':(Bpace,allp,ROS,['Jamal Murray'],{'DEN':226.4,'MEM':228.7}),
'out_not_on_board':(Ba[:40],allp,ROS,['Kris Murray'],None)}
ok=0
for k,a in cases.items():
 r1,o1=run(V,*a); r2,o2=run(C,*a); same=o1==o2 and r1.stdout.split(':',1)[1]==r2.stdout.split(':',1)[1] and r1.returncode==r2.returncode==0 and r2.stderr==''; ok+=same
 print(k,'rc',r1.returncode,r2.returncode,'csv_identical',o1==o2,'stdout_identical(path-normalized)',r1.stdout.split(':',1)[1]==r2.stdout.split(':',1)[1],'cand_stderr',r2.stderr.strip()[:50] or '-')
print('parity',ok,'/',len(cases)); res['REQ3']=(ok==len(cases))
print("== REQ4 identity safety (v0.4 must WARN; numbers unchanged vs v0.2)")
w4=[]
def probe(label,b,p,r,o,must=None):
 r1,o1=run(V,b,p,r,o); r2,o2=run(C,b,p,r,o)
 warned='WARNING' in r2.stderr and (must is None or must in r2.stderr)
 w4.append(warned and r2.returncode==0 and o1==o2)
 print(label,'| v02 rc',r1.returncode,'WARN' if 'WARNING' in r1.stderr else 'silent','| v04 rc',r2.returncode,'WARN' if warned else 'SILENT','| csv identical to v02',o1==o2,'|',r2.stderr.strip().replace('\n',' // ')[:150])
 return o2
Bj=brd([('Nikola Jokic','DEN')],('POINTS',))
probe('4a unmatched OUT (Jamal Murrey)',Bj,pl(den),den,['Jamal Murrey'],'unmatched OUT')
probe('4b OUT surname only (Murray)',Bj,pl(den),den,['Murray'],'unmatched OUT')
dup=pl(den)+[dict(sport='NBA',player='Jamal Murray',team='XXX',games=20,minutes='20',pts='8',reb='2',ast='2',threes='1')]
probe('4c duplicate name across teams',Bj,dup,den,['Jamal Murray'],'duplicate')
tr=[dict(r,team='MEM') if r['player']=='Jamal Murray' else r for r in pl(den)]
probe('4d traded/team mismatch players MEM vs roster DEN',Bj,tr,den,['Jamal Murray'],'team mismatch')
col=pl([dict(team='DEN',player='Nikola Jokic',minutes='30',pts='20',reb='10',ast='8',threes='1'),dict(team='MEM',player='Nikola Jokić',minutes='30',pts='12',reb='4',ast='2',threes='2')])
probe('4e normalized-name collision (Jokic vs Jokić)',brd([('Nikola Jokic','DEN')],('POINTS',)),col,None,None,'collision')
probe('4j board name suffix miss (Marcus Morris vs Marcus Morris Sr. in files)',brd([('Marcus Morris','DEN')],('POINTS',)),pl([dict(team='DEN',player='Marcus Morris Sr.',minutes='20',pts='8',reb='2',ast='2',threes='1')]),None,None,'not found in players')
Bc=brd([('Carson Cooper','LAL')],('POINTS',))
cc=[r for r in ROS if r['team'] in('MEM','LAL')]
probe('4f board team LAL vs files MEM (Cooper)',Bc,pl(cc),cc,['Zach Edey'],'board team')
for lab,val in(('nan','nan'),('neg','-5')):
 bad=[dict(r,minutes=val) if r['player']=='Christian Braun' else r for r in den]
 probe('4g '+lab+' minutes',Bj,pl(bad),bad,['Jamal Murray'],'minutes')
# matched OUT must stay silent
r2,_=run(C,Bj,pl(den),den,['Jamal Murray']); print('4h matched OUT silent:',r2.stderr=='' ); w4.append(r2.stderr=='')
# OUT player only in roster (not in players) is matched, silent
r2,_=run(C,Bj,pl([r for r in den if r['player']!='Jamal Murray']),den,['Jamal Murray']); print('4i OUT only in roster silent:',r2.stderr=='',r2.stderr.strip()[:80]); w4.append(r2.stderr=='')
print('REQ4 checks passed',sum(w4),'/',len(w4)); res['REQ4']=all(w4)
print('SUMMARY',res)
