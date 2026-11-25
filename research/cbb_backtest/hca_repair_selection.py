"""HCA-estimator repair selection on VALIDATION seasons 2022-2024 ONLY (research, PAPER/0u).

Candidates for the home-court term fed to the frozen native projection (ratings fixed
to the repo reconstruction, 8-game shrink). Reports bias/MAE of home-court games.
Run: PYTHONPATH=.:models/cbb python -m research.cbb_backtest.hca_repair_selection
"""
import os
import sys
ROOT = os.environ.get('CBB_DATA_ROOT', '/workspace/cbb_bt_data')
from research.cbb_backtest import data as D, models as M, harness as H
from research.cbb_hca.public_factorial_backtest import context
from statistics import mean
from datetime import timedelta
import cbbd_native_score_model as native
res={k:[] for k in ('shrunk_all','shrunk_q4','raw_all','raw_q4','raw_q8','none')}
for s in (2022,2023,2024):  # VALIDATION seasons only
    g,_=D.load_games(ROOT,s)
    for o in H.origins_for(g):
        prior=[x for x in g if x['day']<o and x['possessions'] is not None]
        tgt=[x for x in g if o<=x['day']<o+timedelta(days=7) and not x['neutral']]
        if len(prior)<150 or not tgt: continue
        ctx=context(prior,8)
        lg,pace=M._league(prior)
        rawr=M._shrunk(prior,0,{},lg,pace)
        h={}
        h['shrunk_all']=M._residual_hca(prior,ctx['ratings'],False)['value']
        h['shrunk_q4']=M._residual_hca(prior,ctx['ratings'],True)['value']
        h['raw_all']=M._residual_hca(prior,rawr,False)['value']
        h['raw_q4']=M._residual_hca(prior,rawr,True)['value']
        M.MIN_QUALIFIED_GAMES=8; h['raw_q8']=M._residual_hca(prior,rawr,True)['value']; M.MIN_QUALIFIED_GAMES=4
        h['none']=0.0
        for k,v in h.items():
            if v is None: continue
            c=dict(ctx); c['hca']={'value':v}
            for x in tgt:
                try: p=native.project(c,x['home'],x['away'],neutral=False,_need_sd=False)
                except native.Pass: continue
                res[k].append((p['margin']-x['margin'], o.month))
for k,v in res.items():
    e=[a for a,_ in v]
    print(k,len(e),'bias',round(mean(e),3),'mae',round(mean(abs(a) for a in e),3), 'bias Nov/Dec',round(mean(a for a,m in v if m in (11,12)),2),'Jan+',round(mean(a for a,m in v if m in (1,2,3,4)),2))
