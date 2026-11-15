#!/usr/bin/env python3
"""Read-only comparison of Claude R2 logit-blend to binding RUN IT v2.1 linear probability blend.

The output is RESEARCH_ONLY_PAPER_0U, not a new model, valid no-vig estimate, calibration,
book authentication, or execution authorization. No historical card is modified.
"""
import argparse,csv,json,math,hashlib
from pathlib import Path

def win_profit(american):
    x=int(str(american).strip().replace('−','-').replace('＋','+'))
    if not (x<=-100 or x>=100):raise ValueError('unsupported American odds')
    return x/100 if x>0 else 100/-x

def diagnostic(rows):
    eligible=[];flagged=[];seen=set()
    for num,raw in enumerate(rows,2):
        r=dict(raw);flags=[]
        key=(r.get('sport','').upper(),r.get('game','').lower(),r.get('bet_type',''),r.get('pick','').lower())
        if key in seen:flags.append('DUPLICATE')
        seen.add(key)
        try:
            p=float(r['model_p']);q=float(r['market_p']);w=.3
            if not (math.isfinite(p) and math.isfinite(q) and 0<p<1 and 0<q<1):raise ValueError('probability')
            payout=win_profit(r['price'])
            linear=.3*p+.7*q  # Binding Nov15 owner's v2.1, no odds-based re-estimation
            linear_ev=linear*payout-(1-linear)
            legacy_prob=float(r['pooled_p']) if r.get('pooled_p') else None
            result=dict(line=num,sport=r.get('sport',''),game=r.get('game',''),market=r.get('bet_type',''),pick=r.get('pick',''),legacy_r2_keep=r.get('r2_keep',''),legacy_logit_probability=legacy_prob,v21_linear_probability=round(linear,8),v21_linear_ev=round(linear_ev,8),gap_pp=round(100*abs(p-q),3),status='PAPER_0U',flags=flags)
            if legacy_prob is not None:
                if legacy_prob<0 or legacy_prob>1:flags.append('BAD_LEGACY_PROBABILITY')
                result['linear_minus_legacy_probability']=round(linear-legacy_prob,8)
            if r.get('r2_keep')=='1':flags.append('PRIOR_R2_KEEP_NOT_VERIFIED')
            if abs(p-q)>.15:flags.append('MODEL_MARKET_GAP_GT15PP_REVIEW')
            # No anonymous evidence can itself authorize any stake; keep all rows.
            eligible.append(result)
        except (KeyError,ValueError,TypeError,OverflowError) as exc:
            flagged.append(dict(line=num,status='HOLD_INVALID_SOURCE_INPUT',reason=type(exc).__name__,game=r.get('game'),pick=r.get('pick')))
    return {'status':'PAPER_0U','total_rows':len(eligible)+len(flagged),'diagnostic_rows':len(eligible),'invalid_rows':len(flagged),'v21_positive_linear_ev_rows':sum(r['v21_linear_ev']>0 for r in eligible),'legacy_r2_kept_rows':sum(r['legacy_r2_keep']=='1' for r in eligible),'approved_stake_u':0,'rows':eligible,'rejected':flagged}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('historical_r2_csv');p.add_argument('--output',help='create-only JSON path');a=p.parse_args(argv)
    b=Path(a.historical_r2_csv).read_bytes();rs=list(csv.DictReader(b.decode('utf-8-sig').splitlines()))
    out=diagnostic(rs);out['source_sha256']=hashlib.sha256(b).hexdigest()
    text=json.dumps(out,indent=2,sort_keys=True)+'\n'
    if a.output:
        with Path(a.output).open('x',encoding='utf-8') as f:f.write(text)
    else:print(text,end='')

if __name__=='__main__':main()
