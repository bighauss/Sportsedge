"""As-of release-aware PREQUENTIAL binary benchmark, research-only / PAPER 0u.

A Beta(1,1) empirical prior uses only results published before each forecast.
All copies of an ambiguous event/selection decision are quarantined, rather
than retaining an arbitrary first occurrence. Book/settlement/participant
identities keep unrelated markets out of a training stratum. Supplied source
clocks are not independently authenticated, and no SportsEdge v5 fit occurs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from quant_foundation import SPORTS, when
from quant_evidence import (_cluster_ci, _book_id, _canonical_line,
                            _market_id, digest_ok)

# Strict source fields prevent a missing book/settlement from merging unlike bets.
REQUIRED = (
    'sport', 'event_id', 'market', 'period', 'side', 'book', 'settlement',
    'game_start_utc', 'forecast_asof_utc', 'features_published_utc',
    'fitted_until_utc', 'final_published_utc', 'model_sha256',
    'result_source', 'outcome',
)
PLAYER_MARKETS = frozenset(('atd', 'attd', 'firsttd', 'td2plus', 'firstbasket',
                            'homerun', 'anytimegoal', 'firstgoal'))


def _event_group(r: dict) -> tuple[tuple, tuple]:
    """Construct exact outcome and evaluation identity, not quote timestamp.

    Returns group for cohort training, and (group,event) as duplicate identity.
    Different alt lines and different books stay distinct reference cohorts.
    """
    sport = r['sport'].strip()
    event = r['event_id'].strip()
    market = _market_id(r['market'].strip())
    period = r['period'].strip().casefold()
    side = r['side'].strip().casefold()
    book = _book_id(r['book'].strip())
    settlement = r['settlement'].strip().casefold()
    line = _canonical_line(r.get('line'))
    if not all((sport,event,market,period,side,book,settlement)):
        raise ValueError('INCOMPLETE_EVENT_OR_MARKET_IDENTITY')
    if market == 'ml' and line in ('', '0'):
        line = ''
    if (market in ('spread','total','teamtotal') or 'prop' in market) and not line:
        raise ValueError('NUMERIC_MARKET_LINE_REQUIRED')
    is_player = 'prop' in market or market in PLAYER_MARKETS
    is_team = market == 'teamtotal'
    player = str(r.get('player_id') or '').strip().casefold() if is_player else ''
    team = str(r.get('team_id') or '').strip().casefold() if is_team else ''
    stat = str(r.get('stat') or '').strip().casefold() if is_player else ''
    if is_player and (not player or not stat):
        raise ValueError('PLAYER_AND_STAT_ID_REQUIRED')
    if is_team and not team:
        raise ValueError('TEAM_TOTAL_TEAM_ID_REQUIRED')
    group = (sport,market,period,side,line,player,team,stat,book,settlement)
    return group, (group,event)


def _parse(rows: list[dict]) -> tuple[list[dict], list[dict], int, int]:
    """Keep every raw row: valid decided, unambiguous push, or rejected.

    Compute candidate duplicates before as-of checks so a malformed first copy
    cannot silently let another copy qualify. Conflicting W/L or model versions
    are *all* blocked rather than choosing the input-order winner.
    """
    duplicate_counts: Counter = Counter()
    for r in rows:
        key = None
        if isinstance(r, dict):
            try:
                if all(isinstance(r.get(f),str) and r[f].strip() for f in
                       ('sport','event_id','market','period','side','book','settlement')):
                    _, key = _event_group(r)
            except (ValueError, TypeError, KeyError, AttributeError):
                pass
        if key is not None:
            duplicate_counts[key] += 1

    clean, rejected, pushes, duplicate_rows = [], [], 0, 0
    for n, r in enumerate(rows, 2):
        try:
            if not isinstance(r,dict):
                raise ValueError('INVALID_SOURCE_ROW')
            if None in r:
                raise ValueError('EXTRA_UNNAMED_CSV_FIELDS')
            missing = [k for k in REQUIRED if not isinstance(r.get(k),str)
                       or not r[k].strip()]
            if missing:
                raise ValueError('MISSING_FIELD:' + ','.join(missing))
            if r['sport'] not in SPORTS or not digest_ok(r['model_sha256']):
                raise ValueError('INVALID_SPORT_OR_MODEL_HASH')
            group, key = _event_group(r)
            # Refuse ALL copies, not only second and later rows.
            if duplicate_counts[key] > 1:
                duplicate_rows += 1
                raise ValueError('DUPLICATE_EVENT_MARKET_ALL_COPIES_QUARANTINED')
            freeze, kickoff, published, fitted, final = [when(r[k]) for k in (
                'forecast_asof_utc','game_start_utc','features_published_utc',
                'fitted_until_utc','final_published_utc')]
            if not (published <= freeze < kickoff < final and fitted < freeze):
                raise ValueError('FUTURE_INFORMATION_OR_INVALID_RELEASE_CLOCK')
            if r['outcome'] not in ('W','L','P'):
                raise ValueError('UNSETTLED_OUTCOME')
            # Validate full-precision frozen model probability even for pushes.
            p = None
            if r.get('p_model') not in (None,''):
                p = float(r['p_model'])
                if not math.isfinite(p) or not 0 < p < 1:
                    raise ValueError('INVALID_FROZEN_PROBABILITY')
            if r['outcome'] == 'P':
                pushes += 1
                continue
            clean.append({'row':n,'event_id':r['event_id'].strip(),'group':group,
                          'asof':freeze,'final_published':final,
                          'y':int(r['outcome']=='W'),'model_p':p})
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            rejected.append({'row':n,'reason':str(exc)})
    return clean, rejected, pushes, duplicate_rows


def run_walkforward_baseline(rows: list[dict], *, min_prior: int = 30) -> dict:
    """Evaluate fixed smoothing only with strictly prior released outcomes."""
    if type(min_prior) is not int or min_prior < 1:
        raise ValueError('MIN_PRIOR_MUST_BE_POSITIVE_INTEGER')
    clean, rejected, pushes, duplicate_rows = _parse(rows)
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
            while (idx < len(by_release) and
                   by_release[idx]['final_published'] < test['asof']):
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
                              'model_brier':((test['model_p']-test['y'])**2
                                             if test['model_p'] is not None else None)})
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
                           'team_id':group[6], 'stat':group[7], 'book':group[8],
                           'settlement':group[9],
                           'n':len(items),'unique_events':len({x['event_id'] for x in items}),
                           'baseline_brier':round(mean(x['baseline_brier'] for x in items),6),
                           'frozen_model_matched_n':len(m),
                           'frozen_model_brier':round(mean(x['model_brier'] for x in m),6) if m else None})
    return {'status':'RELEASE_AWARE_BASELINE_RESEARCH_ONLY_PAPER_0U',
            'raw_rows':len(rows), 'valid_decided_rows':len(clean),
            'push_rows_excluded_from_binary_scoring':pushes,
            'duplicate_rows_quarantined':duplicate_rows,
            'invalid_rows':rejected, 'insufficient_training_rows':insufficient,
            'evaluated_n':len(qualified),'unique_eval_events':len({x['event_id'] for x in qualified}),
            'baseline_brier':round(mean(x['baseline_brier'] for x in qualified),6) if qualified else None,
            'model_matched_n':len(paired),
            'model_brier_on_matched':round(mean(x['model_brier'] for x in paired),6) if paired else None,
            'paired_brier_improvement_positive_model_better':round(mean(v for _,v in diffs),6) if diffs else None,
            'paired_brier_improvement_event_cluster95':_cluster_ci(diffs),
            'by_market_line':groups_out,
            'warning':'All duplicates quarantined. Release times and book labels are user-supplied, not independently attested. Fixed smoothed win-rate is only a naive comparator; no v5 retraining, true provider quote, or positive-EV certification.'}


REPO_ROOT = Path(__file__).resolve().parents[2]


def _private_path(value: str) -> Path:
    """Refuse original historical evidence and generated reports in public Git."""
    lexical = Path(os.path.abspath(os.fspath(value)))
    resolved = lexical.resolve()
    for path in (lexical, resolved):
        if path == REPO_ROOT or REPO_ROOT in path.parents:
            raise ValueError('HISTORICAL_INPUT_OR_REPORT_INSIDE_PUBLIC_CHECKOUT')
    if lexical.is_symlink() or any(parent.is_symlink() for parent in lexical.parents):
        raise ValueError('UNTRUSTED_SYMLINK_PATH')
    return lexical


def _write_private_create_only(path: Path, report: dict):
    body = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb') as file:
            fd = -1
            file.write(body)
            file.flush()
            os.fsync(file.fileno())
    except Exception:
        # A partial create must never masquerade as a finished audit report.
        path.unlink(missing_ok=True)
        raise
    finally:
        if fd >= 0:
            os.close(fd)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv_file');p.add_argument('--report',required=True)
    p.add_argument('--min-prior',type=int,default=30)
    args=p.parse_args(argv)
    source=_private_path(args.csv_file)
    target=_private_path(args.report)
    raw=source.read_bytes()
    if not raw or len(raw)>20_000_000:
        raise ValueError('EMPTY_OR_OVERSIZE_SOURCE_BYTES')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''), strict=True)
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):
            raise ValueError('MISSING_OR_DUPLICATE_CSV_HEADERS')
        if not set(REQUIRED).issubset(reader.fieldnames):
            raise ValueError('MISSING_CSV_COLUMNS')
        rows=list(reader)
    except UnicodeError as exc:
        raise ValueError('INVALID_CSV_ENCODING') from exc
    except csv.Error as exc:
        raise ValueError('MALFORMED_CSV') from exc
    result=run_walkforward_baseline(rows,min_prior=args.min_prior)
    result['source_sha256']=hashlib.sha256(raw).hexdigest()
    _write_private_create_only(target, result)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
