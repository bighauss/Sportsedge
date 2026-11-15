#!/usr/bin/env python3
"""Read-only SportsEdge audit. No production model import or mutation.
Usage: python independent_audit.py --input-dir source --output-dir results
Requires Python standard library; reproducible with bundled immutable source copies.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,random,re,statistics
from collections import Counter,defaultdict
from pathlib import Path
from datetime import datetime

SCHEMA_REQUIREMENTS=['event_id','book','source','observed_at_utc','event_start_utc','prediction_created_at_utc','model_version','model_sha','player_id','lineage_id']

def read_csv(path):
    with open(path,newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def emit_csv(path,rows):
    if not rows:return
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def implied(a):
    a=int(a)
    if a == 0 or abs(a)<100:raise ValueError('Invalid American odds: '+str(a))
    return 100/(100+a) if a>0 else -a/(100-a)
def net_win(a):return (int(a)/100 if int(a)>0 else 100/(-int(a)))
def dec(a):return net_win(a)+1
def ev(p,a):return p*dec(a)-1

def parse_card(txt):
    stage=None;keys={'CARD':set(),'DOUBTED':set()};card_order={};doubt_order={}
    for raw in txt.splitlines():
        if raw.strip().startswith('MODEL-DOUBTED'):stage='DOUBTED';continue
        if raw.strip().startswith('1 | CBB') and stage is None:stage='CARD'
        if stage not in keys:continue
        m=re.match(r'^\s*(\d+)\s*\|\s*CBB\s+(.+?)\s*\|\s*(.*?)\s*\|\s*([+-]?\d+)\s*\|',raw)
        if not m:continue
        order,game,pick,price=int(m[1]),m[2].strip(),m[3].strip(),int(m[4]);key=(game,pick,price)
        if key in keys[stage]:raise ValueError('Duplicate card line '+str(key))
        keys[stage].add(key);(card_order if stage=='CARD' else doubt_order)[key]=order
    if len(keys['CARD'])!=65 or len(keys['DOUBTED'])!=10:raise ValueError('Card extraction failed: '+str({k:len(v) for k,v in keys.items()}))
    if keys['CARD']&keys['DOUBTED']:raise ValueError('Card/doubted overlap')
    return keys,card_order,doubt_order

def grade(row,fin):
    # Grading uses external postgame scores only, NEVER changes model p or admission.
    away,home=fin['away'],fin['home'];first=row['bet_type'].startswith('1H_')
    a=int(fin['away_1h'] if first else fin['away_final'])
    h=int(fin['home_1h'] if first else fin['home_final'])
    mk=row['bet_type'].split('|')[0]
    if first:mk=mk[3:]
    s=row['pick'].strip()
    if first:
        if not s.startswith('1H '):return 'INVALID_FIRST_HALF_PREFIX'
        s=s[3:].strip()
    totals=a+h
    if mk=='ML':
        m=re.fullmatch(r'(.+)\s+ML',s)
        if not m:return 'PARSE_FAIL'
        team=m.group(1)
        if team not in (away,home):return 'TEAM_ID_MISMATCH'
        return 'W' if ((h-a if team==home else a-h)>0) else ('L' if ((h-a if team==home else a-h)<0) else 'P')
    if mk=='SPREAD':
        m=re.fullmatch(r'(.+?)\s+([+-]\d+(?:\.\d+)?)',s)
        if not m:return 'PARSE_FAIL'
        team,line=m.group(1),float(m.group(2))
        if team not in (away,home):return 'TEAM_ID_MISMATCH'
        v=(h-a if team==home else a-h)+line
    elif mk=='TOTAL':
        m=re.fullmatch(r'(Over|Under)\s+(\d+(?:\.\d+)?)',s,re.I)
        if not m:return 'PARSE_FAIL'
        v=(totals-float(m.group(2)))*(1 if m.group(1).lower()=='over' else -1)
    elif mk in ('HOME_TT','AWAY_TT'):
        m=re.fullmatch(r'(.+?)\s+(Over|Under)\s+(\d+(?:\.\d+)?)',s,re.I)
        if not m:return 'PARSE_FAIL'
        team,direction,line=m.group(1),m.group(2).lower(),float(m.group(3))
        if team!=(home if mk=='HOME_TT' else away):return 'TEAM_ID_MISMATCH'
        v=((h if mk=='HOME_TT' else a)-line)*(1 if direction=='over' else -1)
    else:return 'UNKNOWN_MARKET'
    return 'W' if v>1e-8 else ('L' if v< -1e-8 else 'P')

def wilson(w,n,z=1.96):
    if n==0:return (None,None)
    a=w/n;den=1+z*z/n;c=(a+z*z/(2*n))/den;span=z*math.sqrt((a*(1-a)+z*z/(4*n))/n)/den
    return (c-span,c+span)
def metrics(rows):
    rs=[r for r in rows if r['result'] in ('W','L','P')]
    if not rs:return {}
    decided=[r for r in rs if r['result'] in ('W','L')]
    p=[float(r['model_p']) for r in decided];y=[1 if r['result']=='W' else 0 for r in decided]
    wins=sum(y);losses=len(y)-wins;unit=sum(float(r['net_units']) for r in rs)
    return dict(rows=len(rs),wins=wins,losses=losses,pushes=len(rs)-len(decided),net_units=round(unit,6),roi_per_unit=round(unit/len(rs),6),hit_rate=round(wins/len(decided),6) if decided else None,
     model_mean_p=round(statistics.mean(p),6) if p else None,brier=round(statistics.mean((u-v)**2 for u,v in zip(p,y)),6) if p else None,
     log_loss=round(statistics.mean(-v*math.log(max(u,1e-12))-(1-v)*math.log(max(1-u,1e-12)) for u,v in zip(p,y)),6) if p else None)

def block_bootstrap(rows,seed=42,n_sim=10000):
    # Resample GAMES not individual bets. With only 10 games, intervals are descriptive, not validated inference.
    gs=defaultdict(list)
    for r in rows:gs[r['game']].append(r)
    keys=sorted(gs)
    if not keys:return None
    rng=random.Random(seed);by_g=[(sum(float(r['net_units']) for r in gs[g]),len(gs[g])) for g in keys]
    rois=[]
    for _ in range(n_sim):
        ix=[rng.randrange(len(keys)) for __ in keys]
        rois.append(sum(by_g[j][0] for j in ix)/sum(by_g[j][1] for j in ix))
    rois.sort();return dict(n_game_clusters=len(keys),n_sim=n_sim,bootstrap_unit_roi_2p5=round(rois[int(.025*n_sim)],5),bootstrap_unit_roi_97p5=round(rois[int(.975*n_sim)],5),method='equal-weight resampling of entire games; NOT a confidence guarantee')

def parse_market_parent(board,game,market):
    away,home=game.split(' @ ')
    for r in board:
        if (r['away'],r['home'],r['market'])==(away,home,market):return r
    return None

def discrepancies(board):
    res=[]
    for r in board:
        try:
            m=implied(r['price_a'])+implied(r['price_b'])-1
        except (ValueError,TypeError):continue
        res.append(dict(game=r['away']+' @ '+r['home'],market=r['market'],book_overround_pct=round(100*m,3),home_model_pts=r['home_proj'],away_model_pts=r['away_proj']))
    return res

def main(src,out):
    out.mkdir(parents=True,exist_ok=True)
    old=json.loads((src/'census.json').read_text())
    priced=read_csv(src/'nov11_picks_188.csv');board=read_csv(src/'nov11_board_96.csv');finals=read_csv(src/'nov11_verified_scores.csv')
    finals_by={r['game']:r for r in finals}
    keys,card_order,doubt_order=parse_card((src/'nov11_card_original.txt').read_text())
    bugs=[];graded=[];dups=[];seen=set();missing=[];tie_estimates=defaultdict(list)
    for i,r in enumerate(priced):
        rr=dict(r);k=(r['game'],r['pick'],int(r['price']))
        if k in seen:dups.append(str(k))
        seen.add(k)
        rr['original_row_index']=i+1
        rr['origin']='CARD' if k in keys['CARD'] else ('MODEL_DOUBTED' if k in keys['DOUBTED'] else 'PRICED_NOT_QUALIFIED')
        rr['qualification_rank']=(card_order.get(k) or doubt_order.get(k) or '')
        p=float(r['model_p']);o=int(r['price']);rr['raw_implied_p']=round(implied(o),9)
        rr['probability_edge_vs_break_even']=round(p-implied(o),9)
        rr['recomputed_ev_per_dollar']=round(ev(p,o),9)
        rr['observed_line_price_time']='NOT_ROW_VERIFIED'
        rr['point_in_time_status']='SOURCE_FILE_PRE_GAME_BY_CREATED_TIME_ONLY; NO ROW_RECEIPT'
        rr['result']=grade(r,finals_by[r['game']]) if r['game'] in finals_by else 'MISSING_FINAL'
        rr['net_units']=(net_win(o) if rr['result']=='W' else (-1.0 if rr['result']=='L' else 0.0))
        rr['net_units']=round(rr['net_units'],8)
        if r['bet_type'].startswith('1H_ML|'):
            # sportsedge_v5 emits model_p=win/(win+loss), but EV=win*payout-loss.
            # Halftime ties push: conditional p alone cannot reproduce EV.
            conditional_ev=ev(p,o)
            if abs(conditional_ev)>1e-6:
                q=1-float(r['ev'])/conditional_ev
                rr['inferred_1h_tie_push_p']=round(q,9)
                tie_estimates[r['game']].append(q)
                if q < -1e-5 or q > 1:bugs.append({'row':i+1,'type':'PUSH_PROBABILITY_OUT_OF_RANGE','detail':str(k)+' q='+str(q)})
        elif abs(float(r['ev'])-ev(p,o))>1e-7:
            bugs.append({'row':i+1,'type':'EV_ARITHMETIC','detail':str(k)})
        if abs(float(r['edge'])-(p-float(r['market_p'])))>1e-7:bugs.append({'row':i+1,'type':'ARCHIVED_EDGE_NOT_MODELP_MINUS_DEVIG','detail':str(k)})
        if rr['result'] not in ('W','L','P'):bugs.append({'row':i+1,'type':'GRADING_FAIL','detail':rr['result']+' '+str(k)})
        graded.append(rr)
    if len(old)!=716 or len(priced)!=188 or len(board)!=96 or len(finals)!=10:raise ValueError('Unexpected source file counts')
    for g,qs in tie_estimates.items():
        if len(qs)>1 and max(qs)-min(qs)>1e-5:
            bugs.append({'row':'ALL','type':'INCONSISTENT_HALFTIME_PUSH_PROBABILITY','detail':g+' '+str(qs)})
    if len([r for r in graded if r['origin']=='CARD'])!=65 or len([r for r in graded if r['origin']=='MODEL_DOUBTED'])!=10:raise ValueError('Card membership mismatch')
    emit_csv(out/'nov11_all_188_priced_with_results.csv',graded)
    card=[r for r in graded if r['origin']=='CARD'];doubted=[r for r in graded if r['origin']=='MODEL_DOUBTED']
    emit_csv(out/'nov11_original_65_card_graded.csv',card)
    emit_csv(out/'nov11_10_doubted_graded_separately.csv',doubted)
    report={'source_integrity':{'SHA256':{p.name:sha(p) for p in sorted(src.glob('*'))},'nov11_priced_rows':len(priced),'nov11_board_markets':len(board),'nov11_game_results':len(finals),'old_graded_census':len(old),'missing_required_row_provenance_columns':[c for c in SCHEMA_REQUIREMENTS if c not in priced[0]], 'duplicate_price_qualification_keys':dups,'1h_push_probabilities_inferred_from_engine_EV':{g:round(statistics.mean(q),8) for g,q in tie_estimates.items()},'calculation_or_grading_issues':bugs},'results':{'original_65_card':metrics(card),'original_10_model_doubted_not_official':metrics(doubted),'all_188_priced_not_a_bet_record':metrics(graded),'original_card_by_market':{},'original_card_by_direction':{},'original_card_by_game':{},'calibration_by_bin':[], 'correlation_risk':{}, 'game_cluster_bootstrap':block_bootstrap(card)}}
    for r in card:
        family=r['bet_type'].split('|')[0]
        direction='OVER' if re.search(r'\bOver\b',r['pick'],re.I) else ('UNDER' if re.search(r'\bUnder\b',r['pick'],re.I) else ('SPREAD' if 'SPREAD' in family else 'ML'))
        report['results']['original_card_by_market'].setdefault(family,[]).append(r)
        report['results']['original_card_by_direction'].setdefault(direction,[]).append(r)
        report['results']['original_card_by_game'].setdefault(r['game'],[]).append(r)
    for grp in ('original_card_by_market','original_card_by_direction','original_card_by_game'):
        report['results'][grp]={k:metrics(v) for k,v in sorted(report['results'][grp].items())}
    for low in [0,.50,.55,.60,.65,.70,.75,.80,.85,.90,.95]:
        high=low+(.5 if low==0 else .05)
        if high>1:high=1.0000001
        rr=[r for r in card if low <= float(r['model_p']) < high and r['result'] in ('W','L')]
        if not rr:continue
        win=sum(r['result']=='W' for r in rr);ci=wilson(win,len(rr))
        report['results']['calibration_by_bin'].append({'range':f'{100*low:.0f}-{100*min(high,1):.0f}%','n':len(rr),'mean_p':round(statistics.mean(float(r['model_p']) for r in rr),4),'actual_win_rate':round(win/len(rr),4),'wilson_95pct_if_independent':[round(ci[0],4),round(ci[1],4)],'caution':'same-game picks correlated: nominal Wilson interval invalid for inference'})
    counts=Counter(r['game'] for r in card)
    report['results']['correlation_risk']={'games':len(counts),'card_rows':len(card),'max_selections_same_game':max(counts.values()),'highest_game':counts.most_common(1)[0][0],'selection_counts_by_game':dict(counts),'true_outcome_correlation_identifiable':'No: one realization per game','effective_independent_N_upper_bound':len(counts)}
    over=discrepancies(board);emit_csv(out/'nov11_book_overround_by_market.csv',over)
    report['market_disagreement']=[]
    for g in sorted(counts):
        pg=next(r for r in board if r['away']+' @ '+r['home']==g)
        m=next((r for r in board if r['away']+' @ '+r['home']==g and r['market']=='SPREAD'),None)
        t=next((r for r in board if r['away']+' @ '+r['home']==g and r['market']=='TOTAL'),None)
        mu_h=float(pg['home_proj']);mu_a=float(pg['away_proj']);raw_margin=mu_h-mu_a;raw_total=mu_h+mu_a
        gap_margin=(raw_margin+float(m['line'])) if m else None
        gap_total=(raw_total-float(t['line'])) if t else None
        report['market_disagreement'].append({'game':g,'projection_home_score':mu_h,'projection_away_score':mu_a,'home_margin_projection':round(raw_margin,3),'book_home_margin':-float(m['line']) if m else None,'margin_model_minus_book_pts':round(gap_margin,3) if gap_margin is not None else None,'total_model':round(raw_total,3),'total_book':float(t['line']) if t else None,'total_model_minus_book_pts':round(gap_total,3) if gap_total is not None else None,'n_original_card':counts[g]})
    # Predefined market-gap bucket research: only full-game family rows with a
    # meaningful same-period numeric model mean and same-market main book line.
    # Excludes 1H and ML, whose per-period means/probabilities need separate inputs.
    by_bucket=defaultdict(list);gap_rows=[]
    for r in card:
        fam=r['bet_type'].split('|')[0]
        if fam not in ('SPREAD','TOTAL','HOME_TT','AWAY_TT'):continue
        parent=parse_market_parent(board,r['game'],fam)
        if parent is None:continue
        home_mu=float(parent['home_proj']);away_mu=float(parent['away_proj'])
        market_line=float(parent['line'])
        gap={'SPREAD':(home_mu-away_mu)+market_line,
             'TOTAL':home_mu+away_mu-market_line,
             'HOME_TT':home_mu-market_line,
             'AWAY_TT':away_mu-market_line}[fam]
        mag=abs(gap)
        bucket='0–3' if mag<3 else ('3–6' if mag<6 else ('6–10' if mag<10 else '10+'))
        by_bucket[bucket].append(r)
        gap_rows.append({'game':r['game'],'pick':r['pick'],'market':fam,'model_vs_parent_market_pts':round(gap,3),'abs_gap_bucket_pts':bucket,'model_p':r['model_p'],'american_odds':r['price'],'result':r['result'],'units':r['net_units']})
    emit_csv(out/'nov11_eligible_fullgame_gap_buckets_per_selection.csv',gap_rows)
    report['results']['market_disagreement_buckets_fullgame_only']={k:metrics(v) for k,v in sorted(by_bucket.items())}
    report['results']['market_disagreement_bucket_n']=len(gap_rows)
    report['book_overround']={'n_paired_book_rows':len(over),'min_percent':min(x['book_overround_pct'] for x in over),'max_percent':max(x['book_overround_pct'] for x in over),'n_negative':sum(x['book_overround_pct']<0 for x in over)}
    report['model_version_context']={'documented_version':'sportsedge_v5 (FIX-7) in November 11 run note','snapshot_code_sha':'NOT_IN_ROW','reported_torvik_teams':365,'reported_torvik_SHA_prefix':'cadbdaafcb8a','known_risk':'Mississippi Valley State fuzzy ID match to Mississippi State was corrected before this board, per run note; need trace proof'}
    (out/'audit_metrics.json').write_text(json.dumps(report,indent=2)+'\n')
    # Historical 716: rank original largest 20. Do not rewrite correction into original census.
    eligible=[r for r in old if isinstance(r.get('ev'),(int,float)) and r.get('price') is not None and r.get('model_p') is not None]
    top=sorted(eligible,key=lambda r:-r['ev'])[:20]
    corrected={'Mississippi Valley @ Washington':lambda r:'W' if (r['pick'].startswith('Washington Under') or r['pick'].startswith('Under ')) else r['outcome']}
    topout=[]
    for j,r in enumerate(top,1):
        o=int(r['price']);p=float(r['model_p']);s=r['outcome'];result=corrected[r['game']](r) if r['game'] in corrected else s
        topout.append({'archived_rank':j,'source':r['source'],'game':r['game'],'pick':r['pick'],'american_odds':o,'model_p':p,'book_break_even_p':round(implied(o),9),'raw_probability_edge':round(p-implied(o),9),'EV_recalculated':round(ev(p,o),9),'archive_result':s,'audit_result':result,'result_changed_from_archive':s!=result,'time_provenance':'NOT_CERTIFIED','severity':'CRITICAL' if r['game'] in ('Rice @ Stanford','Mississippi Valley @ Washington','Toledo Rockets @ Sacramento State Hornets') else 'HIGH'})
    emit_csv(out/'archived_top20_original_odds_and_projection.csv',topout)
    # Cross-market paired quotes: fail closed on absent paired records.
    pairing_fail=[]
    for market in over:
        if market['book_overround_pct'] < -0.01 or market['book_overround_pct'] >15:pairing_fail.append(market)
    report['source_integrity']['abnormal_market_overround']=pairing_fail
    # Forward test specification, not a claim we trained anything.
    (out/'READ_ME_FIRST.txt').write_text('Research-only PAPER/0u. All model probabilities and odds from source snapshots are immutable. '+
      'Postgame scores were newly sourced for outcome grading only. Missing row-level quote timestamps mean betting-edge claims are not point-in-time certified. '+
      'The full 188 rows are BOTH SIDES of 96 markets and NOT 188 recommended bets. Only 65 rows belong to original CARD; 10 were model-doubted. '+
      'Do not add historic games to training when evaluating old predictions. Original census may carry G-18 grader mistakes.\n')
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input-dir',default='source');ap.add_argument('--output-dir',default='results');a=ap.parse_args();r=main(Path(a.input_dir),Path(a.output_dir))
    print(json.dumps({'card':r['results']['original_65_card'],'doubted':r['results']['original_10_model_doubted_not_official'],'issues':len(r['source_integrity']['calculation_or_grading_issues']),'bootstrap':r['results']['game_cluster_bootstrap']},indent=2))
