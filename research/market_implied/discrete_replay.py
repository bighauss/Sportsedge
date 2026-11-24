"""Replay normalized two-way ladders. Research only, not a sportsbook parser.
Half-point anchors assume integer outcomes and common settlement definitions.
No joint distribution, tail allocation, consensus admission or pricing grant.
"""
import argparse,csv,hashlib,io,json,math
from collections import defaultdict
from pathlib import Path
from . import devig as engine


def discrete_bins(anchors):
    points=sorted((engine.finite(t),engine.finite(s)) for t,s in anchors)
    if len(points)<2:raise ValueError('at least two anchors required')
    if any(2*t%2!=1 for t,s in points):raise ValueError('half-point anchors required; integer pushes unresolved')
    if any(not 0<=s<=1 for t,s in points):raise ValueError('invalid probability')
    if len({t for t,s in points})!=len(points):raise ValueError('duplicate threshold')
    if any(b[1]>a[1] for a,b in zip(points,points[1:])):raise ValueError('inconsistent increasing survival')
    bins=[[None,math.floor(points[0][0]),1-points[0][1]]];gaps=[]
    for (t,s),(u,v) in zip(points,points[1:]):
        bins.append([math.ceil(t),math.floor(u),s-v])
        if u-t>1:gaps.append([t,u,v,s])
    bins.append([math.ceil(points[-1][0]),None,points[-1][1]])
    if abs(sum(b[2] for b in bins)-1)>1e-9:raise ValueError('mass conservation failure')
    return bins,gaps


def integer_outcomes(line,anchors):
    k=engine.finite(line)
    if not k.is_integer():raise ValueError('integer settlement line required')
    anchors=list(anchors);discrete_bins(anchors);s=dict(anchors)
    if k-.5 not in s or k+.5 not in s:raise ValueError('push mass unidentified: neighboring anchors required')
    return dict(win=s[k+.5],push=s[k-.5]-s[k+.5],loss=1-s[k-.5])


def reference_two_way(prices,method):
    q=[100/(a+100) if a>0 else -a/(100-a) for a in prices];total=sum(q)
    if method=='multiplicative' or (method=='shin' and total<=1):return [x/total for x in q]
    if method in ('additive','shin'):return [x-(total-1)/2 for x in q]
    if method!='power':raise ValueError('unknown reference method')
    lo,hi=1e-6,50
    for _ in range(110):
        k=(lo+hi)/2
        if sum(x**k for x in q)>1:lo=k
        else:hi=k
    return [x**((lo+hi)/2) for x in q]


def replay(fixture,receipt):
    raw=Path(fixture).read_bytes();meta=json.loads(Path(receipt).read_bytes())
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=meta['csv_sha256']:raise ValueError('fixture digest mismatch')
    source=Path(engine.__file__).read_bytes()
    blob=hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest()
    if blob!=meta['engine_git_blob']:raise ValueError('engine pin mismatch')
    if any(meta.get(k) is not False for k in ('eligible_for_pricing','settlement_rules_verified','external_consensus_eligible')):raise ValueError('unsupported authorization')
    if type(meta.get('approved_stake_u')) is not int or meta['approved_stake_u']!=0:raise ValueError('stake guard')
    reader=csv.DictReader(io.StringIO(raw.decode()))
    if reader.fieldnames!=['market','subject','line','price_a','price_b','market_role']:raise ValueError('fixture schema')
    rows=list(reader)
    if len(rows)!=meta['paired_quotes'] or not rows:raise ValueError('quote denominator')
    groups=defaultdict(lambda:defaultdict(list));seen=set();differences=[];max_error=0
    pairwise={a+'|'+b:0 for i,a in enumerate(engine.METHODS) for b in engine.METHODS[i+1:]}
    for row in rows:
        market,subject=row['market'],row['subject'];line=engine.finite(row['line'])
        if market not in ('SPREAD','TOTAL','TEAM_TOTAL') or not subject or row['market_role'] not in ('MAIN','ALTERNATE'):raise ValueError('unsupported ladder contract')
        if market=='SPREAD' and subject!=meta['away']:raise ValueError('away-side handicap required')
        if market=='TOTAL' and subject!='GAME':raise ValueError('game total subject required')
        if market=='TEAM_TOTAL' and subject not in (meta['away'],meta['home']):raise ValueError('unknown team total subject')
        identity=(market,subject,line)
        if identity in seen:raise ValueError('duplicate or conflicting quote')
        seen.add(identity);prices=[int(row['price_a']),int(row['price_b'])];fair={}
        for method in engine.METHODS:
            r=engine.devig(prices,method)
            if r.status!='OK':raise ValueError('inconsistent prices: '+r.reason)
            ref=reference_two_way(prices,method)
            error=max(abs(a-b) for a,b in zip(r.fair,ref));max_error=max(max_error,error)
            if error>1e-9:raise ValueError('reference disagreement')
            fair[method]=r.fair[0]
            groups[(market,subject)][method].append((-line if market=='SPREAD' else line,r.fair[0]))
        differences.append(dict(market=market,subject=subject,line=line,range=max(fair.values())-min(fair.values())))
        for key in pairwise:
            a,b=key.split('|');pairwise[key]=max(pairwise[key],abs(fair[a]-fair[b]))
    distributions=[];uncertainty=[]
    for (market,subject),methods in sorted(groups.items()):
        computed=[discrete_bins(methods[m]) for m in engine.METHODS]
        bins=[[row[0],row[1],[round(c[0][i][2],12) for c in computed]] for i,row in enumerate(computed[0][0])]
        distributions.append(dict(market=market,subject=subject,bins=bins))
        for i,gap in enumerate(computed[0][1]):
            uncertainty.append(dict(market=market,subject=subject,threshold_interval_exclusive=gap[:2],survival_bounds=[[round(c[1][i][2],12),round(c[1][i][3],12)] for c in computed]))
    audit=dict(fixture_sha256=digest,engine_git_blob=blob,event_id=meta['event_id'],source_url=meta['source_url'],input_origin=meta['input_origin'],evaluations=len(rows)*len(engine.METHODS),reference_max_abs_error=max_error,paired_quotes=len(rows),methods=list(engine.METHODS),mass_bin_count=sum(len(x['bins']) for x in distributions)*len(engine.METHODS),max_method_disagreement=max(differences,key=lambda x:x['range']),max_pairwise_disagreement=pairwise,stored_decimal_places=12,monotonicity_violations=0,eligible_for_pricing=False,settlement_rules_verified=False,external_consensus_eligible=False,approved_stake_u=0,independent_forecasts=0,hybrid_forecasts=0,limitations=['Selected relay fixture, not all-slate automated ingestion or original book receipts.','Integer outcomes and common settlement definitions are assumptions, not verified rules.','Open tails and missing-rung bins remain unallocated.','No joint score distribution or calibrated confidence intervals.','Same-assistant reproduction; not independent external validation.'])
    return dict(methods=list(engine.METHODS),bin_columns=['lower_integer_inclusive','upper_integer_inclusive','mass_by_method'],null_endpoint='open tail',series=distributions),dict(methods=list(engine.METHODS),bounds_columns=['lower','upper'],interval='strictly between observed half-point thresholds',gaps=uncertainty),audit


def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture',required=True);p.add_argument('--receipt',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    distributions,bounds,audit=replay(a.fixture,a.receipt);directory=Path(a.output);directory.mkdir(parents=True,exist_ok=True)
    for name,value in [('distribution_bins.json',distributions),('missing_rung_bounds.json',bounds),('replay_audit.json',audit)]:
        (directory/name).write_text(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n')

if __name__=='__main__':main()
