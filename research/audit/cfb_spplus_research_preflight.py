#!/usr/bin/env python3
"""Point-in-time SP+ ratings-only RESEARCH preflight. NEVER prices wagers.

Consumes a frozen manually captured 138-team SP+ CSV (no ESPN scraping), an
explicit game census, and a SHA-bound capture manifest. Fails closed on
missing data and source chronology. Does not import or modify the engine.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


class Rejected(ValueError):
    pass


def utc_clock(raw, label):
    if not raw:
        raise Rejected(f'{label}:MISSING_TIMESTAMP')
    try:
        d = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except (ValueError, TypeError) as e:
        raise Rejected(f'{label}:INVALID_TIMESTAMP') from e
    if d.tzinfo is None or d.utcoffset() is None:
        raise Rejected(f'{label}:OFFSET_REQUIRED')
    return d.astimezone(timezone.utc)


def source_csv(path, required):
    raw = Path(path).read_bytes()
    try:
        reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        head = [x.strip().lower() for x in next(reader)]
        if len(head) != len(set(head)) or not all(head):
            raise Rejected('DUPLICATE_OR_BLANK_HEADER')
        missing = set(required).difference(head)
        if missing:
            raise Rejected('MISSING_COLS:' + ','.join(sorted(missing)))
        rows = []
        for idx, line in enumerate(reader, 2):
            if len(line) != len(head) or not any(str(x).strip() for x in line):
                raise Rejected(f'MALFORMED_ROW:{idx}')
            rows.append({k: v.strip() for k, v in zip(head, line)})
    except (UnicodeError, StopIteration, csv.Error) as e:
        raise Rejected('MALFORMED_CSV') from e
    return rows, hashlib.sha256(raw).hexdigest()


def valid_num(raw, label, lo, hi):
    try:
        v = float(raw)
    except (ValueError, TypeError) as e:
        raise Rejected(f'{label}:NOT_NUMERIC') from e
    if not math.isfinite(v) or not lo <= v <= hi:
        raise Rejected(f'{label}:OUT_OF_RANGE')
    return v


def run(ratings_file, games_file, manifest_file):
    ratings, rating_sha = source_csv(ratings_file, ('team', 'offense', 'defense', 'special_teams'))
    games, game_sha = source_csv(games_file, ('game_id', 'home', 'away', 'kickoff_utc', 'neutral'))
    m = json.loads(Path(manifest_file).read_text(encoding='utf-8'))
    if m.get('source_kind') != 'ESPN_SPPLUS_2026':
        raise Rejected('SOURCE_KIND_UNVERIFIED')
    u = urlsplit(m.get('source_url', ''))
    if u.scheme != 'https' or u.hostname not in ('espn.com', 'www.espn.com', 'abc7chicago.com'):
        raise Rejected('SOURCE_URL_NOT_ESPN')
    if m.get('ratings_sha256') != rating_sha or m.get('games_sha256') != game_sha:
        raise Rejected('SOURCE_SHA_MISMATCH')
    published = utc_clock(m.get('published_utc'), 'PUBLISHED')
    captured = utc_clock(m.get('captured_utc'), 'CAPTURED')
    through = utc_clock(m.get('data_through_utc'), 'DATA_THROUGH')
    asof = utc_clock(m.get('model_asof_utc'), 'MODEL_ASOF')
    if not through <= published <= captured <= asof:
        raise Rejected('SOURCE_CLOCKS_OUT_OF_ORDER')
    if len(ratings) != 138 or len(games) != m.get('expected_games'):
        raise Rejected('CENSUS_INCOMPLETE')
    by_team = {}
    for x in ratings:
        name = x['team']
        if not name or name in by_team:
            raise Rejected('DUPLICATE_OR_BLANK_TEAM')
        by_team[name] = {
            'offense': valid_num(x['offense'], 'OFFENSE_PPG', 0, 85),
            'defense': valid_num(x['defense'], 'DEFENSE_ALLOWED_PPG', 0, 85),
            'special_teams': valid_num(x['special_teams'], 'SPECIAL_TEAMS_PPG', -20, 20)
        }
    # Raw SP+ offense is points scored against average defense; defense is
    # points allowed against average offense. NEVER add raw values to 28 points.
    # This mean is a diagnostic normalization; NOT a validated scoring model.
    baseline = sum((x['offense'] + x['defense']) / 2 for x in by_team.values()) / len(by_team)
    results, seen = [], set()
    for g in games:
        gid = g['game_id']
        if not gid or gid in seen:
            raise Rejected('DUPLICATE_OR_BLANK_GAME_ID')
        seen.add(gid)
        ko = utc_clock(g['kickoff_utc'], f'{gid}:KICKOFF')
        if g['neutral'] not in ('0', '1'):
            raise Rejected('NEUTRAL_FLAG_UNVERIFIED')
        codes = ['NO_VALIDATED_SPPLUS_TO_SCORE_CALIBRATION',
                 'SOURCE_PUBLICATION_NOT_INDEPENDENTLY_AUTHENTICATED',
                 'NO_GAME_SPECIFIC_PACE_OR_ADVANCED_STATS',
                 'NO_VALIDATED_HOME_ADVANTAGE_OR_SPECIAL_TEAMS_BLEND']
        if g['home'] == g['away']:
            codes.append('SAME_TEAM_BOTH_SIDES')
        if ko <= asof:
            codes.append('ASOF_AFTER_KICKOFF')
        if ko <= through:
            codes.append('RATINGS_INCLUDE_GAME_OR_FUTURE')
        missing = [name for name in (g['home'], g['away']) if name not in by_team]
        if missing:
            codes.append('TEAM_NOT_IN_FBS_SPPLUS_CENSUS')
        projection = None
        if not missing and ko > asof and ko > through and g['home'] != g['away']:
            home = by_team[g['home']]
            away = by_team[g['away']]
            # Neutral-field *diagnostic*: no home, pace or special teams adjustment.
            # Output only scoring means, never win probabilities or EV.
            ph = home['offense'] + away['defense'] - baseline
            pa = away['offense'] + home['defense'] - baseline
            projection = {'home_neutral_points': round(ph, 3),
                          'away_neutral_points': round(pa, 3),
                          'full_game_total_neutral': round(ph + pa, 3),
                          'league_mean_scoring_baseline': round(baseline, 5)}
        results.append({'game_id': gid, 'home': g['home'], 'away': g['away'],
                        'neutral': g['neutral'] == '1', 'kickoff_utc': ko.isoformat(),
                        'research_projection': projection,
                        'source_mode': 'ESPN_SPPLUS_RATINGS_ONLY_UNCALIBRATED',
                        'status': 'RESEARCH_PAPER' if projection else 'BLOCKED',
                        'reason_codes': sorted(set(codes)), 'stake_u': 0,
                        'wager_eligible': False, 'model_win_prob': None, 'ev': None})
    return {'source_kind': m['source_kind'], 'source_url': m['source_url'],
            'ratings_sha256': rating_sha, 'games_sha256': game_sha,
            'ratings_teams': len(ratings), 'games': len(games),
            'asof_utc': asof.isoformat(), 'data_through_utc': through.isoformat(),
            'league_mean_scoring_baseline': round(baseline, 5),
            'research_paper': sum(r['status'] == 'RESEARCH_PAPER' for r in results),
            'blocked': sum(r['status'] == 'BLOCKED' for r in results),
            'wagers': 0, 'rows': results}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ('ratings', 'games', 'manifest', 'out'):
        ap.add_argument('--' + arg, required=True)
    a = ap.parse_args()
    result = run(a.ratings, a.games, a.manifest)
    with open(a.out, 'x', encoding='utf-8') as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write('\n')
    print(f"RESEARCH {result['research_paper']} BLOCKED {result['blocked']} OFFICIAL 0u")


if __name__ == '__main__':
    main()
