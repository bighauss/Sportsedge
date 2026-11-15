#!/usr/bin/env python3
"""SportsEdge NFL RIDGE_R1 deterministic forecast recomputation gate.

Does NOT authenticate NFL result histories, sportsbook captures, roster news,
QB changes or evidence for betting EV. It only checks that a forecast is a
numerical consequence of an independently supplied, hash-checked ratings CSV.
Research/PAPER 0u; no model/engine mutations.
"""
import csv
import datetime as dt
import math
from pathlib import Path

SUPPORTED = 'SPORTSEDGE_NFL_RIDGE_R1'
RATINGS_REQUIRED=('team','off','def','gp','lg','hfa','asof','half_life','ridge')

def norm(s):return ' '.join(s.casefold().split())

def gate(source, forecasts):
    problems=[]
    try:
        with open(source,'r',newline='',encoding='utf-8-sig') as f:
            reader=csv.DictReader(f,restkey=None,restval=None)
            cols=reader.fieldnames or []
            if len(cols)!=len(set(cols)) or not set(RATINGS_REQUIRED).issubset(cols):
                return {'status':'BLOCK','reasons':['RATINGS_SOURCE_SCHEMA_INVALID'],'verified_games':0}
            rows=list(reader)
        if not rows:
            return {'status':'BLOCK','reasons':['RATINGS_SOURCE_EMPTY'],'verified_games':0}
        teams={};meta=None
        for row in rows:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('RATINGS_SOURCE_RAGGED')
            team=row['team'].strip();k=norm(team)
            if not k or k in teams:
                raise ValueError('RATINGS_SOURCE_BLANK_OR_DUPLICATE_TEAM')
            off=float(row['off']);dff=float(row['def']);lg=float(row['lg']);hfa=float(row['hfa'])
            ridge=float(row['ridge']);half_life=float(row['half_life']);gp=int(row['gp'])
            asof=dt.date.fromisoformat(row['asof'])
            if not all(map(math.isfinite,(off,dff,lg,hfa,ridge,half_life))):
                raise ValueError('RATINGS_SOURCE_NONFINITE')
            if gp < 1 or lg<=0 or not (0<=hfa<=12) or ridge<=0 or half_life<=0:
                raise ValueError('RATINGS_SOURCE_IMPLAUSIBLE_PARAMS')
            common=(lg,hfa,ridge,half_life,asof)
            if meta is None:meta=common
            elif common!=meta:raise ValueError('RATINGS_SOURCE_INCONSISTENT_METADATA')
            teams[k]=(off,dff)
    except (OSError,UnicodeError,csv.Error,KeyError,ValueError,TypeError,OverflowError) as exc:
        return {'status':'BLOCK','reasons':['RATINGS_SOURCE_INVALID:'+str(exc)],'verified_games':0}
    n=0
    for forecast in forecasts:
        try:
            if forecast['model_version']!=SUPPORTED:
                problems.append('FORECAST_MODEL_VERSION_UNVERIFIED');continue
            h=teams.get(norm(forecast['home']));a=teams.get(norm(forecast['away']))
            if h is None or a is None or norm(forecast['home'])==norm(forecast['away']):
                problems.append('FORECAST_TEAM_NOT_IN_SOURCE');continue
            asof_ct=dt.datetime.fromisoformat(forecast['asof_ct'])
            if asof_ct.tzinfo is None or asof_ct.utcoffset() is None or asof_ct.date()!=meta[4]:
                problems.append('FORECAST_ASOF_NOT_SOURCE_ASOF');continue
            lg,hfa,_,_,_=meta
            eh=max(lg+h[0]-a[1]+hfa/2,3.0)
            ea=max(lg+a[0]-h[1]-hfa/2,3.0)
            observed=(float(forecast['home_proj']),float(forecast['away_proj']))
            if not all(math.isfinite(x) for x in observed):
                problems.append('FORECAST_SCORE_NOT_FINITE');continue
            # Ratings source uses 4dp and projection uses 3dp; at most
            # 0.00065 rounded-point discrepancy per side.
            if abs(observed[0]-eh)>0.0015 or abs(observed[1]-ea)>0.0015:
                problems.append('FORECAST_DOES_NOT_RECOMPUTE_FROM_SOURCE');continue
            n+=1
        except (KeyError,ValueError,TypeError,OverflowError):
            problems.append('FORECAST_RECOMPUTE_INPUT_INVALID')
    return {'status':'PASS' if not problems else 'BLOCK','reasons':sorted(set(problems)),
            'verified_games':n,'source_teams':len(teams),'supported_model_version':SUPPORTED,
            'source_asof':meta[4].isoformat(),'source_ridge':meta[2],'source_half_life':meta[3]}
