import tempfile,unicodedata
from pathlib import Path
from sportsedge_cross_id_preflight_r5 import audit
H='sport,event_id,home,away,start_at,captured_at\n'
def run(board,al):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d);(p/'b.csv').write_text(board,encoding='utf-8');(p/'a.csv').write_text(al,encoding='utf-8')
        try:
            r=audit(p/'b.csv',p/'a.csv');return len(r['invalid']),[c['reason'] for c in r['conflicts']]
        except ValueError as e: return 'ERR',str(e)
nfc=unicodedata.normalize('NFC','San José State');nfd=unicodedata.normalize('NFD','San José State')
A=f'sport,team_name,team_id\nCBB,{nfc},sjsu\nCBB,Boston,bst\n'
row=lambda h,e='e1':f'CBB,{e},Boston,{h},2026-11-15T20:00:00Z,2026-11-14T12:00:00Z\n'
print('P1 NFC alias vs NFD board name:',run(H+row(nfd),A))
print('P2 NFC vs NFC control:',run(H+row(nfc),A))
print('P3 tid typo splits identity (sjsu vs sjsu_):',run(H+row(nfc,'e1')+row('San Jose St','e2'),A+'CBB,San Jose St,sjsu_\n'))
print('P4 tid case merge (SJSU vs sjsu) same game 2 ids:',run(H+row(nfc,'e1')+row('SJ State','e2'),A+'CBB,SJ State,SJSU\n'))
print('P5 no source column accepted? (extra col):',run(H+row(nfc),'sport,team_name,team_id,source\nCBB,Boston,bst,x\n'))
print('P6 name with leading/trailing space on board:',run(H+row(' '+nfc+' '),A))
