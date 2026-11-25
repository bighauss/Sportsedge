"""Research fetcher: ESPN core-API odds per completed event -> compact JSON cache (no credentials). RESEARCH ONLY."""
import json, os, sys, urllib.request, concurrent.futures as cf, pandas as pd, time
B='https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/events/{0}/competitions/{0}/odds?lang=en&region=us'
OUT='/workspace/fg_data/odds'
def get(gid):
    p=f'{OUT}/{gid}.json'
    if os.path.exists(p): return 0
    for k in range(3):
        try:
            d=json.load(urllib.request.urlopen(B.format(gid),timeout=30))
            items=[]
            for it in d.get('items',[]):
                def side(t):
                    t=t or {}
                    o={'ml':t.get('moneyLine'),'spread_odds':t.get('spreadOdds')}
                    for w in ('open','close'):
                        x=t.get(w) or {}
                        o[w]={'ps':(x.get('pointSpread') or {}).get('american'),'sp':(x.get('spread') or {}).get('american'),'ml':(x.get('moneyLine') or {}).get('american')}
                    return o
                tot={}
                for w in ('open','close'):
                    x=it.get(w) or {}
                    tot[w]={'total':(x.get('total') or {}).get('american'),'over':(x.get('over') or {}).get('american'),'under':(x.get('under') or {}).get('american')}
                items.append({'provider':it.get('provider',{}).get('name'),'pid':it.get('provider',{}).get('id'),'details':it.get('details'),
                  'overUnder':it.get('overUnder'),'spread':it.get('spread'),'overOdds':it.get('overOdds'),'underOdds':it.get('underOdds'),
                  'home':side(it.get('homeTeamOdds')),'away':side(it.get('awayTeamOdds')),'tot':tot})
            json.dump(items,open(p,'w')); return 0
        except Exception as e:
            time.sleep(1+k)
    return 1
ids=[]
for s in sys.argv[1:]:
    d=pd.read_parquet(f'/workspace/fg_data/mbb_schedule_{s}.parquet',columns=['game_id','status_type_completed'])
    ids+= [int(x) for x in d[d.status_type_completed==True].game_id]
print('n',len(ids),flush=True)
with cf.ThreadPoolExecutor(24) as ex: print('errors',sum(ex.map(get,ids)),flush=True)
