import csv, json, math, sys, statistics as st, hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import nba_push_accounting_equivalence as eq

# Required on every output of this analysis (owner ruling, #536 review): the projections used
# here are the closing market (margin = -closing spread, total = closing total), NOT the SportsEdge model.
STAND_IN_FLAG = {
    'projection_basis': 'MARKET_DERIVED_STAND_IN',
    'independent_model_evidence': False,
    'flag': 'MARKET_STAND_IN_NOT_INDEPENDENT_MODEL_EVIDENCE',
    'meaning': ('Projections are market-derived stand-ins (closing full-game spread/total), not SportsEdge projections. '
                'Results describe the frozen pricer applied to market-implied inputs; they are not independent-model, '
                'forecast-quality, ROI or CLV evidence.'),
}


def _f(v):
    return float(v) if v != '' else None


def load_games():
    out = []
    for r in csv.DictReader(open(HERE / 'games.csv', newline='', encoding='utf-8')):
        ls = lambda s: [int(v) for v in s.split('|')] if s else []
        odds = None
        if r['odds_provider']:
            odds = dict(provider=r['odds_provider'], spread_home=_f(r['spread_home']), total=_f(r['total']),
                        ml_home=_f(r['ml_home']), ml_away=_f(r['ml_away']))
        out.append(dict(season=r['season'], date=r['date'], stype=r['season_type'], event=r['event_id'],
                        hl=ls(r['home_linescore']), al=ls(r['away_linescore']), odds=odds))
    return out


def analyze():
    old = eq.load(eq.OLD_PATH, eq.OLD_BLOB, 'v1'); new = eq.load(eq.NEW_PATH, eq.NEW_BLOB, 'v2')
    g = load_games()
    def wilson(k,n,z=1.96):
        p=k/n; d=1+z*z/n; c=p+z*z/(2*n); r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)); return ((c-r)/d,(c+r)/d)
    out={**STAND_IN_FLAG, 'source':'ESPN public scoreboard (linescores) + ESPN core odds (closing full-game spread/total/ML); NOT in repo; fetched 2026-11-25 via fetch_espn.py',
         'games_fetched':len(g)}
    use=[x for x in g if len(x['hl'])>=4 and len(x['al'])>=4 and x.get('odds') and x['odds'].get('total') is not None and x['odds'].get('spread_home') is not None]
    # spread sign sanity vs ML
    def sane(x):
        o=x['odds']
        if o['ml_home'] is None or o['ml_away'] is None: return True
        if o['spread_home']==0: return True
        return (o['spread_home']<0)==(o['ml_home']<o['ml_away'])
    bad=[x for x in use if not sane(x)]
    use=[x for x in use if sane(x)]
    out['excluded']={'short_or_missing_linescore':sum(1 for x in g if len(x['hl'])<4 or len(x['al'])<4),
                     'missing_odds_or_total':sum(1 for x in g if len(x['hl'])>=4 and not (x.get('odds') and x['odds'].get('total') is not None)),
                     'spread_sign_vs_ml_inconsistent':len(bad)}
    out['games_used']=len(use)
    # ties (all fetched games with 4 linescores)
    allg=[x for x in g if len(x['hl'])>=4 and len(x['al'])>=4]
    def tie(x,n): return sum(x['hl'][:n])==sum(x['al'][:n])
    tr={}
    for label,n,pers in (('1H',2,None),('Q1',1,None),('Q2',None,1),('Q3',None,2),('Q4',None,3)):
        def t(x):
            if n: return tie(x,n)
            return x['hl'][pers]==x['al'][pers]
        k=sum(t(x) for x in allg); lo,hi=wilson(k,len(allg))
        per={}
        for s in ('2023-24','2024-25'):
            sub=[x for x in allg if x['season']==s]; kk=sum(t(x) for x in sub); per[s]={'ties':kk,'games':len(sub),'rate':kk/len(sub)}
        tr[label]={'ties':k,'games':len(allg),'rate':k/len(allg),'wilson95':[lo,hi],'by_season':per}
    out['tie_frequency_all_fetched_games']=tr
    # model replay on market-implied margin
    SD1H=12.5*0.71; SD1Q=12.5*0.5
    rows=[]
    for x in use:
        mu=-x['odds']['spread_home']; tot=x['odds']['total']
        proj={'margin':mu,'total':tot,'home':'H','away':'A','home_pts':(tot+mu)/2,'away_pts':(tot-mu)/2}
        for seg,n in (('1H',2),('1Q',1)):
            h=sum(x['hl'][:n]); a=sum(x['al'][:n]); d=h-a
            r=lambda sel:{'market':seg+'_ML','selection':sel,'line':''}
            oh=old.price_game_market(r('H'),proj); oa=old.price_game_market(r('A'),proj)
            nh=new.price_game_market(r('H'),proj); na=new.price_game_market(r('A'),proj)
            rows.append(dict(seg=seg,d=d,mu=mu,old_h=oh[0],old_a=oa[0],new_h=nh[0],new_a=na[0],push=nh[1],season=x['season']))
    res={}
    for seg in ('1H','1Q'):
        R=[r for r in rows if r['seg']==seg]; n=len(R)
        d=[r['d'] for r in R]; mu=[r['mu'] for r in R]
        mf=0.49 if seg=='1H' else 0.245; sdm=SD1H if seg=='1H' else SD1Q
        resid=[r['d']-r['mu']*mf for r in R]
        ties=sum(1 for r in R if r['d']==0)
        pred_push=[r['push'] for r in R]
        # conditional win prob for home, non-tie games
        nt=[r for r in R if r['d']!=0]
        yh=[1.0 if r['d']>0 else 0.0 for r in nt]
        po=[r['old_h'] for r in nt]
        pn=[r['new_h']/(r['new_h']+r['new_a']) for r in nt]
        br=lambda p,y: sum((a-b)**2 for a,b in zip(p,y))/len(y)
        ll=lambda p,y: -sum(math.log(min(max(a,1e-12),1-1e-12)) if b else math.log(min(max(1-a,1e-12),1-1e-12)) for a,b in zip(p,y))/len(y)
        # three-outcome score of NEW model incl ties; OLD model scored with half-credit tie (its implied accounting)
        def brier3(r):
            o=(1.0 if r['d']>0 else 0.0, 1.0 if r['d']<0 else 0.0, 1.0 if r['d']==0 else 0.0)
            return (r['new_h']-o[0])**2+(r['new_a']-o[1])**2+(r['push']-o[2])**2
        def brier3_old(r):  # old model: P(tie)=0
            o=(1.0 if r['d']>0 else 0.0, 1.0 if r['d']<0 else 0.0, 1.0 if r['d']==0 else 0.0)
            return (r['old_h']-o[0])**2+(r['old_a']-o[1])**2+(0-o[2])**2
        ll3=-sum(math.log(max(r['new_h'] if r['d']>0 else r['new_a'] if r['d']<0 else r['push'],1e-12)) for r in R)/n
        # tie calibration by predicted-push tercile
        srt=sorted(R,key=lambda r:r['push']); ter=[srt[:n//3],srt[n//3:2*n//3],srt[2*n//3:]]
        cal=[{'n':len(t),'mean_pred_push':st.mean(r['push'] for r in t),'obs_tie_rate':sum(r['d']==0 for r in t)/len(t)} for t in ter]
        # accounting error: old model's credited win prob vs refund-aware: expected win probability bias on actual outcomes
        res[seg]={'games':n,'ties':ties,'tie_rate':ties/n,'tie_rate_wilson95':wilson(ties,n),
          'mean_predicted_push_new':st.mean(pred_push),'mean_predicted_push_old':0.0,
          'sd_model_assumed':sdm,'sd_observed_resid_margin_vs_mf_x_market':st.pstdev(resid),'mean_resid_margin':st.mean(resid),
          'tie_calibration_by_predicted_push_tercile':cal,
          'nontie_games':len(nt),'brier_cond_home_old':br(po,yh),'brier_cond_home_new':br(pn,yh),
          'logloss_cond_home_old':ll(po,yh),'logloss_cond_home_new':ll(pn,yh),
          'brier3_new_incl_ties':st.mean(brier3(r) for r in R),'brier3_old_pushless_incl_ties':st.mean(brier3_old(r) for r in R),
          'logloss3_new_incl_ties':ll3,'logloss3_old':'infinite on tie games (P(tie)=0): %d tie games'%ties,
          'mean_home_win_prob_shift_new_minus_old':st.mean(r['new_h']-r['old_h'] for r in R),
          'abs_shift_p_max':max(abs(r['new_h']-r['old_h']) for r in R)}
    out['model_replay_on_market_implied_margin']={**STAND_IN_FLAG, 'method':'projection margin := -closing full-game spread, total := closing total (market-implied stand-in; NOT the SportsEdge projection); price_game_market of both blobs on 1H_ML/1Q_ML','segments':res}
    # EV shift at hypothetical fair-vig prices (-110/-110 two-way) over the real mu distribution (home side), raw EV per 1u
    def ev(p,dec,push): return p*(dec-1)-(1-p-push)
    dec=1+100/110
    evs={}
    for seg in ('1H','1Q'):
        R=[r for r in rows if r['seg']==seg]
        # best side for each game under old model at -110: use both sides
        d_old=[]; d_new=[]
        for r in R:
            for po_,pn_ in ((r['old_h'],r['new_h']),(r['old_a'],r['new_a'])):
                d_old.append(ev(po_,dec,0)); d_new.append(ev(pn_,dec,r['push']))
        shift=[b-a for a,b in zip(d_old,d_new)]
        evs[seg]={'sides':len(shift),'mean_raw_ev_shift_at_-110':st.mean(shift),'min':min(shift),'max':max(shift),
                  'sides_old_ev_gt0':sum(e>0 for e in d_old),'sides_new_ev_gt0':sum(e>0 for e in d_new),
                  'sides_ev_sign_flipped_pos_to_nonpos':sum(1 for a,b in zip(d_old,d_new) if a>0 and b<=0)}
    out['ev_shift_hypothetical_minus110']={**STAND_IN_FLAG, 'note':'HYPOTHETICAL price -110 both sides; no 1H/1Q ML prices exist in the repo or ESPN odds, so real EV/ROI/CLV cannot be computed','segments':evs}
    grid = {}
    for seg in ('1H', '1Q'):
        R = [r for r in rows if r['seg'] == seg]
        grid[seg] = {}
        for am in (-300, -150, -110, 100, 150, 300):
            dc = 1 + (am / 100 if am > 0 else 100 / -am)
            sh = []
            for r in R:
                for po_, pn_ in ((r['old_h'], r['new_h']), (r['old_a'], r['new_a'])):
                    sh.append(ev(pn_, dc, r['push']) - ev(po_, dc, 0))
            grid[seg][str(am)] = {'mean_raw_ev_shift': st.mean(sh), 'min': min(sh), 'max': max(sh)}
    out['ev_shift_hypothetical_minus110']['by_hypothetical_price_same_price_both_sides'] = grid
    out['ev_shift_hypothetical_minus110']['identity'] = ('EV = p*dec - 1 + push, so raw_ev_new - raw_ev_old = (p_new - p_old)*dec + push exactly; '
                                                          'old p = P(margin>0), new p = P(margin>=0.5), so p_new - p_old = -P(0<margin<0.5), about -push/2 for near-even '
                                                          'matchups => shift about push*(1 - dec/2): positive below +100 (favorites), negative above +100 (underdogs), about zero at +100')
    out['games_csv_sha256']=hashlib.sha256((HERE / 'games.csv').read_bytes()).hexdigest()
    return out


if __name__ == '__main__':
    res = analyze()
    (HERE / 'analysis.json').write_text(json.dumps(res, indent=1, sort_keys=True) + '\n')
    print(json.dumps(res, indent=1, sort_keys=True))
