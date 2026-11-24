"""Research-only normalized ladder replay, not a sportsbook/slate parser.
Caller must obtain manifest_sha256 independently of the untrusted input bundle.
Hashes do not authenticate book origin. No pricing or consensus admission.
"""
import argparse,csv,hashlib,io,json,math,re
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
    anchors=list(anchors);discrete_bins(anchors);s={engine.finite(t):engine.finite(p) for t,p in anchors}
    if k-.5 not in s or k+.5 not in s:raise ValueError('push mass unidentified: neighboring anchors required')
    return dict(win=s[k+.5],push=s[k-.5]-s[k+.5],loss=1-s[k-.5])


def research_ev_bounds(price,win_bounds,*,p_push):
    low,high=map(engine.finite,win_bounds);push=engine.finite(p_push)
    if not 0<=low<=high<=1 or not 0<=push<=1 or high+push>1:raise ValueError('invalid win/push bounds')
    decimal=engine.american_to_decimal(price)
    return dict(lower=engine.ev_per_unit(low,decimal,push),upper=engine.ev_per_unit(high,decimal,push),eligible_for_pricing=False)


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


def _json(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def replay(fixture,receipt,*,manifest,manifest_sha256):
    if not isinstance(manifest_sha256,str) or not re.fullmatch('[0-9a-f]{64}',manifest_sha256):raise ValueError('independently trusted manifest digest required')
    manifest_raw=Path(manifest).read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest()!=manifest_sha256:raise ValueError('manifest digest mismatch')
    pin=_json(manifest_raw);receipt_raw=Path(receipt).read_bytes()
    if type(pin.get('version')) is not int or pin['version']!=1 or hashlib.sha256(receipt_raw).hexdigest()!=pin.get('receipt_sha256'):raise ValueError('receipt binding mismatch')
    meta=_json(receipt_raw);raw=Path(fixture).read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest!=meta['csv_sha256'] or digest!=pin.get('fixture_sha256'):raise ValueError('fixture digest mismatch')
    source=Path(engine.__file__).read_bytes();blob=hashlib.sha1(b'blob '+str(len(source)).encode()+b'\0'+source).hexdigest()
    if blob!=meta['engine_git_blob'] or blob!=pin.get('engine_git_blob'):raise ValueError('engine pin mismatch')
    if meta['event_id']!=pin.get('event_id'):raise ValueError('event binding mismatch')
    try:start,end,tip=(engine.utc(meta[k]) for k in ('capture_start_ct','capture_end_ct','tipoff_ct'))
    except (ValueError,TypeError,AttributeError,KeyError) as exc:raise ValueError('invalid capture chronology') from exc
    if not start<=end<tip:raise ValueError('capture must end before tipoff')
    expected=pin.get('expected_ladders')
    if not isinstance(expected,list) or not expected or any(not isinstance(x,list) or len(x)!=2 or any(not isinstance(v,str) or not v for v in x) for x in expected):raise ValueError('expected ladder manifest required')
    expected=[tuple(x) for x in expected]
    if len(set(expected))!=len(expected):raise ValueError('duplicate expected ladder')
    if any(meta.get(k) is not False for k in ('eligible_for_pricing','settlement_rules_verified','external_consensus_eligible')):raise ValueError('unsupported authorization')
    if type(meta.get('approved_stake_u')) is not int or meta['approved_stake_u']!=0:raise ValueError('stake guard')
    reader=csv.DictReader(io.StringIO(raw.decode()))
    if reader.fieldnames!=['market','subject','line','price_a','price_b','market_role']:raise ValueError('fixture schema')
    rows=list(reader)
    if type(meta['paired_quotes']) is not int or len(rows)!=meta['paired_quotes'] or not rows:raise ValueError('quote denominator')
    groups=defaultdict(lambda:defaultdict(list));main_counts=defaultdict(int);seen=set();differences=[];ev_intervals=[];max_error=0
    pairwise={a+'|'+b:0 for i,a in enumerate(engine.METHODS) for b in engine.METHODS[i+1:]}
    for row in rows:
        market,subject=row['market'],row['subject'];line=engine.finite(row['line'])
        if market not in ('SPREAD','TOTAL','TEAM_TOTAL') or not subject or row['market_role'] not in ('MAIN','ALTERNATE'):raise ValueError('unsupported ladder contract')
        if market=='SPREAD' and subject!=meta['away']:raise ValueError('away-side handicap required')
        if market=='TOTAL' and subject!='GAME':raise ValueError('game total subject required')
        if market=='TEAM_TOTAL' and subject not in (meta['away'],meta['home']):raise ValueError('unknown team total subject')
        identity=(market,subject,line)
        if identity in seen:raise ValueError('duplicate or conflicting quote')
        main_counts[(market,subject)]+=row['market_role']=='MAIN'
        seen.add(identity);prices=[int(row['price_a']),int(row['price_b'])];fair={}
        for method in engine.METHODS:
            r=engine.devig(prices,method)
            if r.status!='OK':raise ValueError('inconsistent prices: '+r.reason)
            error=max(abs(a-b) for a,b in zip(r.fair,reference_two_way(prices,method)));max_error=max(max_error,error)
            if error>1e-9:raise ValueError('reference disagreement')
            fair[method]=r.fair[0];groups[(market,subject)][method].append((-line if market=='SPREAD' else line,r.fair[0]))
        low,high=min(fair.values()),max(fair.values())
        differences.append(dict(market=market,subject=subject,line=line,range=high-low))
        if 2*line%2!=1:raise ValueError('half-point anchors required; integer pushes unresolved')
        for side,price,bounds in [('a',prices[0],(low,high)),('b',prices[1],(1-high,1-low))]:
            ev_intervals.append(dict(market=market,subject=subject,line=line,side=side,price=price,**research_ev_bounds(price,bounds,p_push=0)))
        for key in pairwise:
            a,b=key.split('|');pairwise[key]=max(pairwise[key],abs(fair[a]-fair[b]))
    if set(groups)!=set(expected) or any(main_counts[k]!=1 for k in expected):raise ValueError('exactly one main anchor per expected ladder required')
    distributions=[];uncertainty=[]
    for (market,subject),methods in sorted(groups.items()):
        computed=[discrete_bins(methods[m]) for m in engine.METHODS]
        bins=[[row[0],row[1],[round(c[0][i][2],12) for c in computed]] for i,row in enumerate(computed[0][0])]
        distributions.append(dict(market=market,subject=subject,bins=bins))
        for i,gap in enumerate(computed[0][1]):
            uncertainty.append(dict(market=market,subject=subject,threshold_interval_exclusive=gap[:2],survival_bounds=[[round(c[1][i][2],12),round(c[1][i][3],12)] for c in computed]))
    audit=dict(manifest_sha256=manifest_sha256,receipt_sha256=pin['receipt_sha256'],fixture_sha256=digest,engine_git_blob=blob,event_id=meta['event_id'],source_url=meta['source_url'],input_origin=meta['input_origin'],evaluations=len(rows)*len(engine.METHODS),reference_max_abs_error=max_error,paired_quotes=len(rows),methods=list(engine.METHODS),mass_bin_count=sum(len(x['bins']) for x in distributions)*len(engine.METHODS),max_method_disagreement=max(differences,key=lambda x:x['range']),max_pairwise_disagreement=pairwise,research_ev_intervals=ev_intervals,ev_basis='Single-book method envelope at execution prices; not independent EV or calibrated confidence. Half-point integer-outcome assumption gives zero push.',stored_decimal_places=12,monotonicity_violations=0,capture_before_tipoff=True,main_anchor_coverage_verified=True,eligible_for_pricing=False,settlement_rules_verified=False,external_consensus_eligible=False,approved_stake_u=0,independent_forecasts=0,hybrid_forecasts=0,limitations=['Manifest digest must come from a separately trusted source; a self-computed digest is not authentication.','Selected relay fixture, not all-slate ingestion or book-origin authentication.','Common settlement definitions remain unverified; no current-price freshness claim.','Open tails and missing-rung bins remain unallocated; no joint score distribution.','Same-assistant reproduction, not independent external validation.'])
    return dict(methods=list(engine.METHODS),bin_columns=['lower_integer_inclusive','upper_integer_inclusive','mass_by_method'],null_endpoint='open tail',series=distributions),dict(methods=list(engine.METHODS),bounds_columns=['lower','upper'],interval='strictly between observed half-point thresholds',gaps=uncertainty),audit


def write_evidence(directory,distributions,bounds,audit):
    directory=Path(directory);directory.parent.mkdir(parents=True,exist_ok=True);directory.mkdir()
    hashes={}
    for name,value in [('distribution_bins.json',distributions),('missing_rung_bounds.json',bounds),('replay_audit.json',audit)]:
        raw=(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n').encode()
        with (directory/name).open('xb') as stream:stream.write(raw)
        hashes[name]=hashlib.sha256(raw).hexdigest()
    complete=dict(output_sha256=hashes,manifest_sha256=audit['manifest_sha256'])
    with (directory/'COMPLETE.json').open('x') as stream:stream.write(json.dumps(complete,separators=(',',':'))+'\n')
    return complete


def main():
    p=argparse.ArgumentParser()
    for name in ('fixture','receipt','manifest','manifest-sha256','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();result=replay(a.fixture,a.receipt,manifest=a.manifest,manifest_sha256=a.manifest_sha256);write_evidence(a.output,*result)

if __name__=='__main__':main()
