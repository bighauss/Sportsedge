"""As-of release-aware prequential BASELINE for binary SportsEdge markets.

A fixed Beta(1,1) smoothed historical win-rate is the ONLY fitted predictor.
Uses outcomes only after they were actually published; separates props/lines.
This does not retrain SportsEdge v5 or authenticate historic provider releases.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

from quant_foundation import SPORTS, when
from quant_evidence import _cluster_ci, digest_ok, _canonical_line


def _parse(rows: list[dict]) -> tuple[list[dict], list[dict], int]:
    clean, rejected, pushes = [], [], 0
    keys = set()
    for n, r in enumerate(rows, 2):
        try:
            required = ('sport','event_id','market','period','side','game_start_utc',
                        'forecast_asof_utc','features_published_utc',
                        'fitted_until_utc','final_published_utc',
                        'model_sha256','result_source','outcome')
            missing = [k for k in required if not str(r.get(k,'')).strip()]
            if missing:
                raise ValueError('MISSING_FIELD:' + ','.join(missing))
            if r['sport'] not in SPORTS or not digest_ok(r['model_sha256']):
                raise ValueError('INVALID_SPORT_OR_MODEL_HASH')
            freeze, kickoff, published, fitted, final = [when(r[k]) for k in (
                'forecast_asof_utc','game_start_utc','features_published_utc',
                'fitted_until_utc','final_published_utc')]
            if not (published <= freeze < kickoff < final and fitted < freeze):
                raise ValueError('FUTURE_INFORMATION_OR_INVALID_RELEASE_CLOCK')
            if r['outcome'] not in ('W','L','P'):
                raise ValueError('UNSETTLED_OUTCOME')
            group=(r['sport'],r['market'].casefold().strip(),r['period'].casefold().strip(),
                   r['side'].casefold().strip(),_canonical_line(r.get('line')),
                   str(r.get('player_id','')).strip())
            unique=(group,r['event_id'])
            if unique in keys:
                raise ValueError('DUPLICATE_EVENT_MARKET_LINE')
            keys.add(unique)
            if r['outcome']=='P':
                pushes += 1
                continue
            p = None
            if r.get('p_model') not in (None,''):
                p = float(r['p_model'])
                if not math.isfinite(p) or not 0 < p < 1:
                    raise ValueError('INVALID_FROZEN_PROBABILITY')
            clean.append({'row':n,'event_id':r['event_id'],'group':group,
                          'asof':freeze,'final_published':final,
                          'y':int(r['outcome']=='W'),'model_p':p})
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({'row':n,'reason':str(exc)})
    return clean, rejected, pushes


def run_walkforward_baseline(rows: list[dict], *, min_prior: int = 30) -> dict:
    """Score only future rows with >= min_prior earlier published outcomes.

    Groups include the exact betting line, so alt lines are NOT pooled.
    Training is a fixed statistical baseline only; no tuning or calibration.
    """
    if min_prior < 1:
        raise ValueError('MIN_PRIOR_MUST_BE_POSITIVE')
    clean, rejected, pushes = _parse(rows)
    per_group: dict[tuple,list[dict]] = defaultdict(list)
    for r in clean:
        per_group[r['group']].append(r)
    qualified = []
    insufficient = 0
    for group, items in per_group.items():
        chronological = sorted(items,key=lambda x:(x['asof'],x['event_id']))
        by_release = sorted(items,key=lambda x:(x['final_published'],x['event_id']))
        prior = wins = idx = 0
        for test in chronological:
            # Only results *published earlier* than this prediction are trainable.
            while idx < len(by_release) and by_release[idx]['final_published'] < test['asof']:
                earlier = by_release[idx]
                prior += 1
                wins += earlier['y']
                idx += 1
            if prior < min_prior:
                insufficient += 1
                continue
            p_baseline=(wins+1)/(prior+2)
            qualified.append({'event_id':test['event_id'],'group':group,
                              'asof':test['asof'].isoformat(),'train_n':prior,
                              'baseline_p':p_baseline,'model_p':test['model_p'],
                              'outcome':test['y'],
                              'baseline_brier':(p_baseline-test['y'])**2,
                              'model_brier':((test['model_p']-test['y'])**2 if test['model_p'] is not None else None)})
    paired=[x for x in qualified if x['model_brier'] is not None]
    diffs=[(x['event_id'],x['baseline_brier']-x['model_brier']) for x in paired]
    groups_out=[]
    grouped: dict[tuple,list[dict]] = defaultdict(list)
    for x in qualified:
        grouped[x['group']].append(x)
    for group, items in sorted(grouped.items()):
        m=[x for x in items if x['model_brier'] is not None]
        groups_out.append({'sport':group[0], 'market':group[1], 'period':group[2],
                           'side':group[3], 'line':group[4], 'player_id':group[5],
                           'n':len(items),'unique_events':len({x['event_id'] for x in items}),
                           'baseline_brier':round(mean(x['baseline_brier'] for x in items),6),
                           'frozen_model_matched_n':len(m),
                           'frozen_model_brier':round(mean(x['model_brier'] for x in m),6) if m else None})
    return {'status':'RELEASE_AWARE_BASELINE_RESEARCH_ONLY_PAPER_0U',
            'raw_rows':len(rows), 'valid_decided_rows':len(clean), 'push_rows_excluded_from_binary_scoring':pushes,
            'invalid_rows':rejected, 'insufficient_training_rows':insufficient,
            'evaluated_n':len(qualified), 'unique_eval_events':len({x['event_id'] for x in qualified}),
            'baseline_brier':round(mean(x['baseline_brier'] for x in qualified),6) if qualified else None,
            'model_matched_n':len(paired),
            'model_brier_on_matched':round(mean(x['model_brier'] for x in paired),6) if paired else None,
            'paired_brier_improvement_positive_model_better':round(mean(v for _,v in diffs),6) if diffs else None,
            'paired_brier_improvement_event_cluster95':_cluster_ci(diffs),
            'by_market_line':groups_out,
            'warning':'Release times are user supplied, not independently attested. A smoothed binary win-rate is only a naive baseline; no v5 retraining, odds authentication, or positive-EV certification.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv_file');p.add_argument('--report',required=True)
    p.add_argument('--min-prior',type=int,default=30)
    args=p.parse_args(argv)
    raw=Path(args.csv_file).read_bytes()
    rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    result=run_walkforward_baseline(rows,min_prior=args.min_prior)
    result['source_sha256']=hashlib.sha256(raw).hexdigest()
    with Path(args.report).open('x',encoding='utf-8') as out:
        json.dump(result,out,sort_keys=True,indent=2,allow_nan=False);out.write('\n')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
