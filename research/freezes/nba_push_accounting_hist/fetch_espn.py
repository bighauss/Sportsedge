import json, hashlib, datetime as dt, sys, urllib.request, time
from concurrent.futures import ThreadPoolExecutor
SEASONS={'2023-24':('2023-10-24','2024-06-18'),'2024-25':('2024-10-22','2025-06-23')}
def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:
                b=r.read(); return b
        except Exception as e:
            time.sleep(1+i)
    return None
def day(d):
    u=f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d:%Y%m%d}"
    b=get(u)
    if b is None: return d,None,None
    return d,json.loads(b),hashlib.sha256(b).hexdigest()
games={}
for s,(a,b) in SEASONS.items():
    a=dt.date.fromisoformat(a);b=dt.date.fromisoformat(b)
    days=[a+dt.timedelta(i) for i in range((b-a).days+1)]
    with ThreadPoolExecutor(8) as ex:
        for d,j,h in ex.map(day,days):
            if j is None: print('FAIL',d,file=sys.stderr); continue
            for e in j.get('events',[]):
                c=e['competitions'][0]
                if e['status']['type']['name']!='STATUS_FINAL': continue
                st=e['season'].get('slug')
                hh=[x for x in c['competitors'] if x['homeAway']=='home'][0]
                aa=[x for x in c['competitors'] if x['homeAway']=='away'][0]
                ls=lambda x:[int(p['value']) for p in x.get('linescores',[])]
                games[e['id']]=dict(season=s,date=str(d),stype=st,event=e['id'],home=hh['team']['abbreviation'],away=aa['team']['abbreviation'],
                    hl=ls(hh),al=ls(aa),neutral=c.get('neutralSite'),scoreboard_sha256=h)
    print(s,len(games),flush=True)
def odds(eid):
    u=f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{eid}/competitions/{eid}/odds"
    b=get(u)
    if b is None: return eid,None
    j=json.loads(b)
    out=None
    for it in j.get('items',[]):
        if it.get('spread') is None: continue
        try:
            ho=it['homeTeamOdds'];ao=it['awayTeamOdds']
            fav_home=ho.get('favorite')
            sp=abs(float(it['spread']))
            close=lambda t:(t.get('close') or {})
            out=dict(provider=it['provider']['name'],spread_home=(-sp if fav_home else sp),total=it.get('overUnder'),
                     ml_home=ho.get('moneyLine'),ml_away=ao.get('moneyLine'),sha256=hashlib.sha256(b).hexdigest())
            break
        except Exception: pass
    return eid,out
ids=list(games)
with ThreadPoolExecutor(8) as ex:
    for k,(eid,o) in enumerate(ex.map(odds,ids)):
        games[eid]['odds']=o
        if k%300==0: print('odds',k,len(ids),flush=True)
json.dump(list(games.values()),open('games_raw.json','w'))
print('done',len(games))
