#!/usr/bin/env python3
"""Paired DraftKings entry/FINAL-close verifier; exact market+line identity.

No grading/CLV inferred. Emits verified quote deltas and a SHA-pinned POWER_V1
no-vig probability on BOTH directions only when close is proven pregame and
market identity is exactly matched. Reflags line jumps rather than backfilling.
"""
import argparse,csv,datetime as dt,hashlib,json,math,re
from collections import Counter
from pathlib import Path

QUOTE_FIELDS=('sport','home','away','player','team','market','line','sgp','side')
PRICE=re.compile(r'^[+-]?[1-9][0-9]{2,}$')

def quote(s):
    if s is None or not PRICE.fullmatch(str(s).strip()):return None
    n=int(s);return n if abs(n)>=100 else None

def prob(a):return 100/(a+100) if a>0 else (-a)/(-a+100)
def pow_devig(oa,ob):
    a,b=prob(oa),prob(ob);low,high=0.2,10.0
    for _ in range(70):
        mid=(low+high)/2
        if a**mid+b**mid>1:low=mid
        else:high=mid
    return a**high,b**high

def read(file):
    with open(file,encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f);rows=list(rd)
        if None in (rd.fieldnames or []) or any(None in r for r in rows):raise ValueError('BROKEN_CSV_STRUCTURE')
        return rows

def key(r):return tuple((r.get(k) or '').strip().casefold() for k in QUOTE_FIELDS[:6]+QUOTE_FIELDS[7:])
def time(s):
    try:
        x=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
        return x.astimezone(dt.timezone.utc) if x.tzinfo and x.utcoffset() is not None else None
    except ValueError:return None

def verify(early,close,asof_close,start_utc,output,report):
    t1,t2=time(asof_close),time(start_utc)
    if not (t1 and t2 and t1<t2):raise ValueError('CLOSE_NOT_PROVEN_PREGAME')
    pre,post=read(early),read(close)
    dc=hashlib.sha256(Path(close).read_bytes()).hexdigest();de=hashlib.sha256(Path(early).read_bytes()).hexdigest()
    qpre={};qpost={};dups=[]
    for rows,target,kind in [(pre,qpre,'ENTRY'),(post,qpost,'CLOSE')]:
        for r in rows:
            k=key(r)
            if k in target:dups.append((kind,k))
            target[k]=r
    if dups:raise ValueError('DUPLICATE_MARKET_IDENTITIES')
    valid=[];bad=[]
    for k,r in qpre.items():
        z=qpost.get(k)
        if not z:bad.append({'market_key':k,'reason':'CLOSE_MARKET_MISSING'});continue
        if (r['line'] or '').strip()!=(z['line'] or '').strip():
            bad.append({'market_key':k,'reason':'ENTRY_CLOSE_LINE_MOVED','old_line':r['line'],'close_line':z['line']});continue
        o1,o2,p1,p2=quote(r['price_a']),quote(r['price_b']),quote(z['price_a']),quote(z['price_b'])
        if None in (o1,o2,p1,p2):bad.append({'market_key':k,'reason':'TWO_SIDED_QUOTE_MISSING_OR_INVALID'});continue
        pa,pb=pow_devig(p1,p2)
        data={field:r.get(field,'') for field in QUOTE_FIELDS}
        pair_token=json.dumps({'close_sha256':dc,'identity':k,'line':r['line'],
                               'quote_a':p1,'quote_b':p2},sort_keys=True,separators=(',',':'))
        market_key='|'.join(str(v).casefold() for v in (r['sport'],r['away'],r['home'],r['market'],r['line'],r['player'],r['team'],r['sgp'],r['side']))
        valid.append({**data,'market_key':market_key,'entry_price_a':o1,'entry_price_b':o2,'close_price_a':p1,'close_price_b':p2,
                      'p_devig_a':round(pa,12),'p_devig_b':round(pb,12),
                      'quote_movement_a':p1!=o1,'quote_movement_b':p2!=o2,
                      'close_pair_sha256':hashlib.sha256(pair_token.encode()).hexdigest(),
                      'entry_file_sha256':de,'close_file_sha256':dc,'close_asof_utc':t1.isoformat(),
                      'start_utc':t2.isoformat(),'verification':'PRE_GAME_IDENTICAL_MARKET_AND_LINE'})
    for k in set(qpost)-set(qpre):bad.append({'market_key':k,'reason':'UNMATCHED_CLOSE_MARKET'})
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    if valid:
        with open(output,'w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(valid[0]));w.writeheader();w.writerows(valid)
    else:Path(output).write_text('verification\n')
    result={'entry_markets':len(pre),'close_markets':len(post),'paired_identical_line':len(valid),
            'refused':len(bad),'refusals':bad,'entry_sha256':de,'close_sha256':dc,
            'pair_quote_directions':2*len(valid),'research_only':True,'result_data_present':False,
            'counted_model_edges':0,'close_verified_pregame':True}
    Path(report).write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--entry',required=True);ap.add_argument('--close',required=True)
    ap.add_argument('--close-asof',required=True);ap.add_argument('--start-utc',required=True)
    ap.add_argument('--output',required=True);ap.add_argument('--report',required=True)
    a=ap.parse_args();print(json.dumps(verify(a.entry,a.close,a.close_asof,a.start_utc,a.output,a.report),indent=2))
