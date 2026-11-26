"""Walk-forward usage-based props backtest (nflverse weekly player stats).
mean = team volume (EWMA of prior team weeks) x player share (EWMA, regressed) x efficiency (regressed).
Only prior weeks of the same season are used for each prediction. Baseline = player's prior-week season average."""
import sys, pandas as pd, numpy as np
HL=3.0; K_SHARE=2.0; K_EFF={'ypt':40,'catch':40,'ypc':60,'ypa':150}
def load(paths):
    out=[]
    for p in paths:
        d=pd.read_csv(p,low_memory=False)
        if 'recent_team' in d: d=d.rename(columns={'recent_team':'team'})
        out.append(d[['player_id','player_display_name','position','team','season','week','season_type',
                      'attempts','passing_yards','carries','rushing_yards','targets','receptions','receiving_yards']])
    d=pd.concat(out); d=d[d.season_type=='REG'].fillna(0); return d
def ewm(vals):
    n=len(vals); w=0.5**(np.arange(n)[::-1]/HL); return float((w*vals).sum()/w.sum())
def run(d):
    rows=[]
    team=d.groupby(['season','team','week'])[['attempts','targets','carries']].sum().reset_index()
    for s in sorted(d.season.unique()):
        ds=d[d.season==s]; ts=team[team.season==s]
        for wk in sorted(ds.week.unique()):
            prior=ds[ds.week<wk]
            if prior.empty: continue
            pt=ts[ts.week<wk]
            pos=prior.groupby('position')[['targets','receptions','receiving_yards','carries','rushing_yards','attempts','passing_yards']].sum()
            cur=ds[ds.week==wk]
            for _,r in cur.iterrows():
                hist=prior[(prior.player_id==r.player_id)&(prior.team==r.team)].sort_values('week')
                if len(hist)<3: continue
                th=pt[pt.team==r.team].set_index('week')
                hist=hist[hist.week.isin(th.index)]
                if len(hist)<3: continue
                tv={c:ewm(th[c].values) for c in ['attempts','targets','carries']}
                n=len(hist); P=pos.loc[r.position] if r.position in pos.index else None
                def share(stat):
                    sh=hist[stat].values/np.maximum(th.loc[hist.week,stat].values,1)
                    return (n*ewm(sh)+K_SHARE*sh.mean())/(n+K_SHARE)
                def eff(num,den,key):
                    pm=P[num]/max(P[den],1) if P is not None else 0
                    return (hist[num].sum()+K_EFF[key]*pm)/(hist[den].sum()+K_EFF[key])
                for stat,vol,shs,effv,base in [
                    ('receiving_yards','targets','targets',('receiving_yards','targets','ypt'),'receiving_yards'),
                    ('receptions','targets','targets',('receptions','targets','catch'),'receptions'),
                    ('rushing_yards','carries','carries',('rushing_yards','carries','ypc'),'rushing_yards'),
                    ('passing_yards','attempts','attempts',('passing_yards','attempts','ypa'),'passing_yards')]:
                    if stat=='passing_yards' and r.position!='QB': continue
                    if stat in('receiving_yards','receptions') and r.position not in('WR','TE','RB'): continue
                    if stat=='rushing_yards' and r.position not in('RB','QB'): continue
                    if hist[shs].sum()==0: continue
                    a=tv[vol]*share(shs)*eff(*effv); b=hist[base].mean()
                    rows.append((s,wk,r.position,stat,r[stat],a,b))
    return pd.DataFrame(rows,columns=['season','week','pos','stat','actual','usage','baseline'])
if __name__=='__main__':
    res=run(load(sys.argv[1:-1])); res.to_csv(sys.argv[-1],index=False)
    res['ae_u']=(res.actual-res.usage).abs(); res['ae_b']=(res.actual-res.baseline).abs()
    g=res.groupby(['stat','season']).agg(n=('ae_u','size'),mae_usage=('ae_u','mean'),mae_baseline=('ae_b','mean')).round(2)
    print(g.to_string()); a=res.groupby('stat').agg(n=('ae_u','size'),mae_usage=('ae_u','mean'),mae_baseline=('ae_b','mean')).round(2)
    a['improve_pct']=((1-a.mae_usage/a.mae_baseline)*100).round(1); print(a.to_string())
