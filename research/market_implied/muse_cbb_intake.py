"""Muse #57 league capture -> existing CBB RUN IT board CSV. Research / 0u.

No odds scraping, ratings substitution, model changes or automatic scheduling.
price_a is HOME for spread/ML and OVER for totals. This proves text labels only;
CBBD IDs, venue agreement and primary totals-order gates remain upstream.
"""
import argparse
import csv
from datetime import date, datetime
import hashlib
import io
import json
import re
from pathlib import Path
import os
import urllib.request
from zoneinfo import ZoneInfo

COLUMNS=('sport','away','home','market','line','price_a','price_b')
REPO='bighauss/Sportsedge'
PATTERN=re.compile(r'^(\d+)\. (.+?) @ (.+?) — (\d{1,2}:\d{2} [AP]M) CT — Spread: (.+?) ([+-]\d+(?:\.\d+)?) ([+-]\d+) / (.+?) ([+-]\d+(?:\.\d+)?) ([+-]\d+) — ML: (NONE SHOWN|[+-]\d+ / [+-]\d+) — Total (\d+(?:\.\d+)?): O ([+-]\d+) / U ([+-]\d+) — ID (\d+)$')


def _price(s):
    n=int(s)
    if abs(n)<100:raise ValueError('invalid American price')
    return n


def parse_capture(body, day_ct):
    day=date.fromisoformat(day_ct)
    if day.isoformat()!=day_ct:raise ValueError('canonical ISO date required')
    games=[];board=[];seen=set();sequences=set()
    for line in body.splitlines():
        if not re.match(r'^\d+\. ',line):continue
        match=PATTERN.fullmatch(line)
        if not match:raise ValueError('unrecognized numbered capture row')
        seq,away,home,clock,sa,la,pa,sh,lh,ph,ml,total,po,pu,eid=match.groups()
        if eid in seen or int(seq) in sequences:raise ValueError('duplicate capture event or sequence')
        if not away.strip() or not home.strip() or away==home:raise ValueError('invalid teams')
        # Muse's spread leg sometimes uses an explicit abbreviation.
        # Never accept an unbound label; permit only the known NMSU alias.
        aliases={'New Mexico State':'NMSU'}
        if sa not in (away,aliases.get(away)) or sh not in (home,aliases.get(home)):
            raise ValueError('spread team-label mismatch')
        if float(la)+float(lh)!=0:raise ValueError('nonreciprocal spread')
        seen.add(eid);sequences.add(int(seq))
        tip=datetime.combine(day,datetime.strptime(clock,'%I:%M %p').time(),ZoneInfo('America/Chicago'))
        common=dict(sport='CBB',away=away,home=home)
        board.append(dict(**common,market='SPREAD',line=float(lh),price_a=_price(ph),price_b=_price(pa)))
        board.append(dict(**common,market='TOTAL',line=float(total),price_a=_price(po),price_b=_price(pu)))
        if ml!='NONE SHOWN':
            ma,mh=ml.split(' / ')
            board.append(dict(**common,market='ML',line='',price_a=_price(mh),price_b=_price(ma)))
        games.append(dict(dk_event_id=eid,away=away,home=home,tipoff_ct=tip.isoformat(),
                          neutral=None,cbbd_game_id=None,moneyline_displayed=ml!='NONE SHOWN'))
    if not games:raise ValueError('no recognized games')
    if sequences!=set(range(1,len(games)+1)):raise ValueError('noncontiguous source sequence')
    return games,board


def board_csv(rows):
    stream=io.StringIO();writer=csv.DictWriter(stream,COLUMNS,lineterminator='\n')
    writer.writeheader();writer.writerows(rows);return stream.getvalue()


def fetch_comment(comment_id):
    if not str(comment_id).isdigit():raise ValueError('numeric comment ID required')
    headers={'Accept':'application/vnd.github+json','User-Agent':'SportsEdge-Muse-Intake'}
    token=os.environ.get('GITHUB_TOKEN')
    if token:headers['Authorization']='Bearer '+token
    url=f'https://api.github.com/repos/{REPO}/issues/comments/{comment_id}'
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=30) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('comment size limit')
    return json.loads(raw),raw


def run(comment, *, day_ct, expected_games, output_dir, capture_start_ct, capture_end_ct, raw=None):
    if type(expected_games) is not int or expected_games<1:raise ValueError('positive expected count required')
    cid=str(comment['id']);url=f'https://github.com/{REPO}/issues/57#issuecomment-{cid}'
    if not cid.isdigit() or comment['html_url']!=url:raise ValueError('comment identity mismatch')
    start,end=datetime.fromisoformat(capture_start_ct),datetime.fromisoformat(capture_end_ct)
    if start.utcoffset() is None or end.utcoffset() is None or not start<=end:
        raise ValueError('timezone-aware ordered capture interval required')
    if start.astimezone(ZoneInfo('America/Chicago')).date().isoformat()!=day_ct or end.astimezone(ZoneInfo('America/Chicago')).date().isoformat()!=day_ct:
        raise ValueError('capture/slate date mismatch')
    if comment.get('updated_at'):
        updated=datetime.fromisoformat(comment['updated_at'].replace('Z','+00:00'))
        if updated.utcoffset() is None or end>updated:raise ValueError('capture after comment update')
    games,board=parse_capture(comment['body'],day_ct)
    if len(games)!=expected_games:raise ValueError('expected game count mismatch')
    if any(end>=datetime.fromisoformat(g['tipoff_ct']) for g in games):raise ValueError('capture is not pregame')
    destination=Path(output_dir);destination.mkdir(parents=True,exist_ok=False)
    payload=raw if raw is not None else json.dumps(comment,sort_keys=True).encode()
    (destination/'comment.raw.json').write_bytes(payload)
    (destination/'board.csv').write_text(board_csv(board))
    (destination/'events.json').write_text(json.dumps(games,indent=2))
    manifest=dict(source_url=url,source_kind='MUSE_GITHUB_RELAY_NOT_BOOK_RECEIPT',
        source_sha256=hashlib.sha256(payload).hexdigest(),capture_start_ct=capture_start_ct,
        capture_end_ct=capture_end_ct,game_count=len(games),paired_markets=len(board),
        offered_sides=2*len(board),price_a={'SPREAD':'home','ML':'home','TOTAL':'over'},
        totals_text_labels_checked=True,primary_totals_gate_changed=False,
        cbbd_identity_join_complete=False,forecast_execution_complete=False,approved_stake_u=0)
    # Completion manifest is written last; consumers must ignore partial directories.
    (destination/'COMPLETE.json').write_text(json.dumps(manifest,indent=2))
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--comment-id');source.add_argument('--comment-json')
    parser.add_argument('--day',required=True);parser.add_argument('--expected-games',required=True,type=int)
    parser.add_argument('--capture-start-ct',required=True);parser.add_argument('--capture-end-ct',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.comment_id:comment,raw=fetch_comment(args.comment_id)
    else:raw=Path(args.comment_json).read_bytes();comment=json.loads(raw)
    run(comment,raw=raw,day_ct=args.day,expected_games=args.expected_games,output_dir=args.out,
        capture_start_ct=args.capture_start_ct,capture_end_ct=args.capture_end_ct)


if __name__=='__main__':main()
