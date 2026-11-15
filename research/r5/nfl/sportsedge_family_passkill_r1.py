#!/usr/bin/env python3
"""SportsEdge per-family forward close PASS/KILL candidate adjudicator.

Implements Isaac's frozen 2026-11-10 standard (PAPER/0u, no engine switch):
- one preregistered opinion per game/market/family, no alt-rung pseudo-replication
- verified DraftKings FINAL-close pair, same line, POWER_V1 devig, stake 1u
- cluster bootstrap by game_id, 10_000 draws, 95% percentile intervals
- PASS: >=300 clusters, CLV CI lower > 0, ROI CI NOT wholly below zero
- KILL-CANDIDATE: >=150 clusters, CLV CI upper < 0
- otherwise no pass/kill label. Always candidate until independently adopted.

Requires the actual raw closing CSV and generated close-pairs CSV, not merely
claimed 'verified' strings. Calls r2's original pair verification gate.

Usage: python sportsedge_family_passkill_r1.py --counted counted.csv \
  --entry-raw raw_entries.csv --close-pairs pairs.csv --close-raw raw_closes.csv --report report.json
"""
import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from sportsedge_close_pair_r2 import key as close_key, pow_devig, time as parse_time

SEED = 20261110
DRAWS = 10_000
PASS_GAMES = 300
KILL_GAMES = 150
REQUIRED_COUNTED = (
    'sport', 'game', 'bet_type', 'price', 'receipt_result', 'receipt_market_key',
    'receipt_close_pair_sha256', 'receipt_closing_price_american',
    'receipt_close_p_devig', 'receipt_close_line_matched', 'receipt_close_book',
    'receipt_start_ct', 'receipt_captured_ct', 'precommit_ct',
    'evidence_label', 'cohort_id'
)


def csv_rows(path, required=()):
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not set(required).issubset(headers):
            raise ValueError('DUPLICATE_OR_MISSING_HEADERS:' + str(set(required)-set(headers)))
        rows = list(reader)
    if any(None in r for r in rows):
        raise ValueError('CSV_FIELD_OVERFLOW')
    return rows


def american_odds(s):
    s = str(s).strip()
    if not s or not ((s[0] in '+-' and s[1:].isdigit()) or s.isdigit()):
        raise ValueError('ODDS_NOT_CANONICAL')
    val = int(s)
    if abs(val) < 100:
        raise ValueError('ODDS_OUT_OF_RANGE')
    return val


def win_profit(american):
    return american / 100 if american > 0 else 100 / -american


def normalize(s):
    return ' '.join(str(s or '').casefold().split())


def quote_identity(pair):
    return (pair['sport'], pair['away'], pair['home'], pair['market'],
            pair['line'], pair['player'], pair['team'], pair['sgp'], pair['side'])


def validate_close_pairs(pairs, raw_rows, raw_path, entry_rows, entry_path):
    digest = hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()
    entry_digest = hashlib.sha256(Path(entry_path).read_bytes()).hexdigest()
    entry_idx = {}
    for r in entry_rows:
        k = close_key(r)
        if k in entry_idx:
            raise ValueError('DUPLICATE_ENTRY_MARKET')
        entry_idx[k] = r
    raw_idx = {}
    for r in raw_rows:
        k = close_key(r)
        if k in raw_idx:
            raise ValueError('DUPLICATE_RAW_MARKET')
        raw_idx[k] = r
    token_idx = {}
    for p in pairs:
        if p.get('close_file_sha256') != digest or p.get('entry_file_sha256') != entry_digest or p.get('verification') != 'PRE_GAME_IDENTICAL_MARKET_AND_LINE':
            raise ValueError('CLOSE_FILE_OR_PAIR_UNVERIFIED')
        k = close_key(p)
        raw = raw_idx.get(k)
        early = entry_idx.get(k)
        if early is None or early.get('line','').strip() != p.get('line','').strip():
            raise ValueError('PAIR_ENTRY_LINE_OR_IDENTITY_MISMATCH')
        if american_odds(early['price_a']) != int(p['entry_price_a']) or american_odds(early['price_b']) != int(p['entry_price_b']):
            raise ValueError('PAIR_RAW_ENTRY_PRICE_MISMATCH')
        if raw is None or raw.get('line','').strip() != p.get('line','').strip():
            raise ValueError('PAIR_LINE_OR_IDENTITY_MISMATCH')
        a = american_odds(raw['price_a']); b = american_odds(raw['price_b'])
        if a != int(p['close_price_a']) or b != int(p['close_price_b']):
            raise ValueError('PAIR_RAW_PRICE_MISMATCH')
        pa,pb = pow_devig(a,b)
        if abs(pa-float(p['p_devig_a'])) > 1e-8 or abs(pb-float(p['p_devig_b'])) > 1e-8:
            raise ValueError('PAIR_DEVIG_MISMATCH')
        c = json.dumps({'close_sha256':digest,'identity':k,'line':p['line'],
                        'quote_a':a,'quote_b':b},sort_keys=True,separators=(',',':'))
        token = hashlib.sha256(c.encode()).hexdigest()
        if token != p.get('close_pair_sha256') or token in token_idx:
            raise ValueError('DUPLICATE_OR_TAMPERED_PAIR_TOKEN')
        close_time = parse_time(p.get('close_asof_utc',''))
        start_time = parse_time(p.get('start_utc',''))
        if not (close_time and start_time and close_time < start_time):
            raise ValueError('CLOSE_NOT_PREGAME')
        token_idx[token] = p
    return token_idx


def family(r, pair):
    """Canonical family; period separates full-game, 1H and quarters."""
    text = (r.get('bet_type','').split('|',1)[0] or pair.get('market','')).upper().strip()
    period = next((prefix for prefix in ('1H_','2H_','1Q_','2Q_','3Q_','4Q_')
                   if text.startswith(prefix) or pair.get('market','').upper().startswith(prefix)), '')
    text = text[len(period):] if text.startswith(period) and period else text
    marker=period[:-1]+'|' if period else ''
    if 'TEAM_TOTAL' in text or 'HOME_TT' in text or 'AWAY_TT' in text: return marker+'TEAM_TOTAL'
    if 'FIRST_TD' in text: return marker+'FIRST_TD'
    if 'TD_2PLUS' in text: return marker+'TD_2PLUS'
    if 'ATTD' in text: return marker+'ATTD'
    if 'PLAYER_PROP' in text or 'PLAYER' in text:
        return marker+'PLAYER_PROP:' + normalize(pair.get('market','')).upper()
    if 'SPREAD' in text: return marker+'SPREAD'
    if 'TOTAL' in text: return marker+'TOTAL'
    if text in ('ML','MONEYLINE') or text.endswith('_ML'): return marker+'ML'
    return ''


def percentile(sorted_values, q):
    return sorted_values[max(0,min(len(sorted_values)-1,int(q*(len(sorted_values)-1))))]


def bootstrap(rows, draws=DRAWS, seed=SEED):
    # Each independent game_id is sampled; all selected markets from a game
    # travel together. The observed ROI is flat-stake per bet, not per outcome.
    clusters = defaultdict(list)
    for r in rows:
        clusters[r['game_id']].append(r)
    cluster_values = [(sum(x['clv'] for x in a), sum(x['roi'] for x in a),len(a))
                      for a in clusters.values()]
    n = len(cluster_values)
    if n < 2: return None
    rng = random.Random(seed)
    clv_samples=[];roi_samples=[]
    for _ in range(draws):
        total_clv = total_roi = 0.0;count=0
        for _ in range(n):
            c,r,k = cluster_values[rng.randrange(n)]
            total_clv += c;total_roi += r;count += k
        clv_samples.append(total_clv/count);roi_samples.append(total_roi/count)
    clv_samples.sort();roi_samples.sort()
    return {'clv_95ci':[percentile(clv_samples,0.025),percentile(clv_samples,0.975)],
            'roi_95ci':[percentile(roi_samples,0.025),percentile(roi_samples,0.975)]}


def evaluate(counted_csv, close_pairs_csv, close_raw_csv, entry_raw_csv, report_json, draws=DRAWS, seed=SEED):
    counted=csv_rows(counted_csv, REQUIRED_COUNTED)
    pairs=csv_rows(close_pairs_csv)
    raw=csv_rows(close_raw_csv)
    entries=csv_rows(entry_raw_csv)
    tokens=validate_close_pairs(pairs,raw,close_raw_csv,entries,entry_raw_csv)
    rejected=Counter();admitted=[]
    for row in counted:
        reasons=[]
        if row['evidence_label'] != 'COUNTED_PRECOMMITTED_CANDIDATE': reasons.append('NOT_PREREGISTERED')
        if row['receipt_result'] not in ('W','L'): reasons.append('NOT_BINARY_SETTLED')
        if row['receipt_close_book'] != 'DK' or row['receipt_close_line_matched'] != 'YES':
            reasons.append('CLOSE_NOT_IDENTICAL_DK')
        pair=tokens.get(row['receipt_close_pair_sha256'])
        if pair is None: reasons.append('PAIR_NOT_BOUND_TO_RAW')
        if pair is not None:
            chunks=row['bet_type'].split('|')
            if len(chunks)<2 or chunks[1] not in ('0','1'):reasons.append('SIDE_UNVERIFIABLE')
            else:
                side=int(chunks[1]);which='a' if side==0 else 'b'
                pclose=float(pair['p_devig_'+which])
                close_odds=int(pair['close_price_'+which])
                if normalize(row['sport'])!=normalize(pair['sport']) or normalize(row['game'])!=normalize(pair['away']+' @ '+pair['home']):
                    reasons.append('GAME_MISMATCH')
                if normalize(row['receipt_market_key'])!=normalize(pair['market_key']):
                    reasons.append('MARKET_MISMATCH')
                if int(row['receipt_closing_price_american'])!=close_odds or abs(float(row['receipt_close_p_devig'])-pclose)>1e-8:
                    reasons.append('CLOSE_PRICE_OR_PROB_MISMATCH')
                captured=parse_time(row['receipt_captured_ct']);committed=parse_time(row['precommit_ct'])
                start=parse_time(row['receipt_start_ct']);closed=parse_time(pair['close_asof_utc'])
                if not (captured and committed and start and closed and captured<=committed<closed<start):
                    reasons.append('POINT_IN_TIME_ORDER_INVALID')
        fam=family(row,pair or {})
        if not fam:reasons.append('FAMILY_UNCLASSIFIED')
        try:entry=american_odds(row['price'])
        except ValueError:entry=None;reasons.append('ENTRY_PRICE_INVALID')
        if pair is not None and entry is not None and len(row['bet_type'].split('|'))>=2 and row['bet_type'].split('|')[1] in ('0','1'):
            entry_side='a' if row['bet_type'].split('|')[1]=='0' else 'b'
            if entry != int(pair['entry_price_'+entry_side]):
                reasons.append('ENTRY_PRICE_NOT_BOUND_TO_RAW')
        if reasons:
            rejected.update(set(reasons));continue
        game=normalize(row['sport'])+'|'+normalize(row['game'])
        roi=win_profit(entry) if row['receipt_result']=='W' else -1.0
        clv=pclose*win_profit(entry)-(1-pclose)
        admitted.append({'game_id':game,'family':row['sport'].upper()+'|'+fam,
                         'market':normalize(pair['market']), 'player':normalize(pair.get('player','')),
                         'team':normalize(pair.get('team','')), 'side':chunks[1],
                         'roi':roi,'clv':clv})
    # Drop ALL ambiguous overlapping rungs/picks within same game+family+underlying market.
    # This prevents an apparent sample of 10 bets from one game's alt ladder.
    identity_counts=Counter((r['game_id'],r['family'],r['player'],r['team']) for r in admitted)
    dedup=[]
    for r in admitted:
        identity=(r['game_id'],r['family'],r['player'],r['team'])
        if identity_counts[identity]>1:
            rejected['MULTIPLE_RUNG_OR_OPINIONS_SAME_GAME_MARKET']+=1
        else:dedup.append(r)
    grouped=defaultdict(list)
    for r in dedup:grouped[r['family']].append(r)
    results={}
    for f, rows in sorted(grouped.items()):
        interval=bootstrap(rows,draws,seed)
        ngames=len(set(r['game_id'] for r in rows))
        label=None
        if interval:
            cl,cu=interval['clv_95ci']; rl,ru=interval['roi_95ci']
            if ngames>=PASS_GAMES and cl>0 and ru>=0: label='PASS'
            elif ngames>=KILL_GAMES and cu<0: label='KILL-CANDIDATE'
        results[f]={'independent_game_clusters':ngames,'bets':len(rows),
                    'mean_clv':sum(r['clv'] for r in rows)/len(rows),
                    'flat_1u_roi':sum(r['roi'] for r in rows)/len(rows),
                    'uncertainty':interval,'label':label}
    result={'inputs':{'counted_sha256':hashlib.sha256(Path(counted_csv).read_bytes()).hexdigest(),
                      'close_pairs_sha256':hashlib.sha256(Path(close_pairs_csv).read_bytes()).hexdigest(),
                      'close_raw_sha256':hashlib.sha256(Path(close_raw_csv).read_bytes()).hexdigest(),
                      'entry_raw_sha256':hashlib.sha256(Path(entry_raw_csv).read_bytes()).hexdigest()},
            'input_counted':len(counted),'admitted_after_dedupe':len(dedup),
            'rejected_reasons':dict(rejected),'families':results,
            'policy':{'pass_clusters':PASS_GAMES,'kill_clusters':KILL_GAMES,'bootstrap_draws':draws,
                      'bootstrap_seed':seed,'interval':'95% game-cluster percentile',
                      'clv':'one unit EV at devigged DK FINAL close, at captured entry odds',
                      'roi':'one flat hypothetical unit per preregistered bet'},
            'production_engine_unchanged':True,'status':'CANDIDATE_PAPER_0U_NOT_RELEASE_APPROVAL'}
    Path(report_json).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for arg in ('counted','entry-raw','close-pairs','close-raw','report'):
        ap.add_argument('--'+arg,required=True)
    a=ap.parse_args()
    result=evaluate(a.counted,a.close_pairs,a.close_raw,a.entry_raw,a.report)
    print(json.dumps({'admitted':result['admitted_after_dedupe'],
                      'families':len(result['families']),
                      'labels':{k:v['label'] for k,v in result['families'].items()}}))
