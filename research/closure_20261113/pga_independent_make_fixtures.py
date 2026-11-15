"""Independent MINIMAL synthetic fixture generator. Not the original PGA fixture module."""
import json
from pathlib import Path

def make_row(pid, fin='1', owgr_rank=10, close=5., sgs=None, scores=None, dg_pts=0):
    sgs = [0.0]*4 if sgs is None else sgs
    scores = [70]*len(sgs) if scores is None else scores
    return dict(dg_id=pid,player_name=f'P{pid}',fin=fin,owgr_rank=owgr_rank,close=close,
                rounds=[dict(r=i+1,score=scores[i],sg=sgs[i],par=70) for i in range(len(sgs))],
                excluded=dict(dg_pts=dg_pts,dg_rank=0))

def make_event(event_id, date, rows, name='Synthetic Event'):
    year=int(date[:4]);return dict(event_id=str(event_id),calendar_year=year,season=year,date=date,name=name,
                                num_rounds=4,rows=rows)

def write_corpus(path, events):
    p=Path(path);p.mkdir(parents=True,exist_ok=True)
    for ev in events:
        (p/f"{ev['event_id']}_{ev['date']}.json").write_text(json.dumps(ev))
