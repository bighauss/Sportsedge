"""Muse relay intake. Research / 0u; no model or primary gate changes.
Only league rows are normalized. Full-board sections are archived, not priced.
Author checks identify a configured GitHub account, not the human Muse.
"""
import csv
from datetime import datetime, timedelta
import hashlib
import io
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

CT=ZoneInfo('America/Chicago')
COLUMNS=('sport','away','home','market','line','price_a','price_b')
PATTERN=re.compile(r'^(\d+)\. (.+?) @ (.+?) — (\d{1,2}:\d{2} [AP]M) CT — Spread: (.+?) ([+-]\d+(?:\.\d+)?) ([+-]\d+) / (.+?) ([+-]\d+(?:\.\d+)?) ([+-]\d+) — ML: (NONE SHOWN|[+-]\d+ / [+-]\d+) — Total (\d+(?:\.\d+)?): O ([+-]\d+) / U ([+-]\d+) — ID (\d+)$')


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=value
    return result


def authenticate(raw, allowed_author_ids, expected_comment_id):
    obj=json.loads(raw,object_pairs_hook=_unique)
    if not allowed_author_ids or any(type(x) is not int for x in allowed_author_ids):
        raise ValueError('explicit integer author allowlist required')
    if type(obj.get('id')) is not int or obj['id']!=expected_comment_id:
        raise ValueError('comment identity mismatch')
    if type(obj.get('user',{}).get('id')) is not int or obj['user']['id'] not in allowed_author_ids:
        raise ValueError('unauthorized GitHub principal')
    if obj.get('html_url')!=f'https://github.com/bighauss/Sportsedge/issues/57#issuecomment-{expected_comment_id}':
        raise ValueError('wrong repository or issue')
    if not isinstance(obj.get('body'),str):raise ValueError('missing body')
    return obj


def capture_interval(body, day_ct):
    day=datetime.strptime(day_ct,'%Y-%m-%d').date()
    if day.isoformat()!=day_ct:raise ValueError('noncanonical date')
    date_match=re.search(r'league scan — (\w+, \w+ \d{1,2}, \d{4})',body)
    if not date_match or datetime.strptime(date_match[1],'%A, %B %d, %Y').date()!=day:
        raise ValueError('body/slate date mismatch')
    matches=list(re.finditer(r'Capture: (\d{1,2}:\d{2})(?: (AM|PM))?[–-](\d{1,2}:\d{2}) (AM|PM) CT',body))
    if len(matches)!=1:raise ValueError('unique body capture interval required')
    a,meridian,b,end_meridian=matches[0].groups()
    def at(clock,half):
        return datetime.combine(day,datetime.strptime(clock+' '+half,'%I:%M %p').time(),CT)
    start=at(a,meridian or end_meridian)
    end=at(b,end_meridian)+timedelta(minutes=1,microseconds=-1)
    if start>end:raise ValueError('invalid capture interval')
    return start,end


def parse_capture(body,day_ct,team_aliases=None):
    aliases=team_aliases or {}
    if not isinstance(aliases,dict) or any(not isinstance(v,list) or any(not isinstance(s,str) for s in v) for v in aliases.values()):
        raise ValueError('aliases must map exact source labels to string lists')
    games=[];rows=[];seen=set();sequences=set()
    def price(text):
        value=int(text)
        if abs(value)<100:raise ValueError('invalid American price')
        return value
    for text in body.splitlines():
        if not re.match(r'^\d+\. ',text):continue
        match=PATTERN.fullmatch(text)
        if not match:raise ValueError('unrecognized numbered row')
        seq,away,home,clock,sa,la,pa,sh,lh,ph,ml,total,po,pu,eid=match.groups()
        if eid in seen or int(seq) in sequences:raise ValueError('duplicate event or sequence')
        if away==home or not away.strip() or not home.strip():raise ValueError('invalid teams')
        if sa not in [away]+aliases.get(away,[]) or sh not in [home]+aliases.get(home,[]):
            raise ValueError('unbound spread label')
        if float(la)+float(lh)!=0:raise ValueError('nonreciprocal spread')
        seen.add(eid);sequences.add(int(seq))
        tip=datetime.combine(datetime.strptime(day_ct,'%Y-%m-%d').date(),datetime.strptime(clock,'%I:%M %p').time(),CT)
        game=dict(dk_event_id=eid,away=away,home=home,tipoff_ct=tip.isoformat(),cbbd_game_id=None,neutral=None)
        games.append(game)
        common=dict(sport='CBB',away=away,home=home)
        rows.extend([dict(**common,market='SPREAD',line=float(lh),price_a=price(ph),price_b=price(pa)),dict(**common,market='TOTAL',line=float(total),price_a=price(po),price_b=price(pu))])
        if ml!='NONE SHOWN':
            ma,mh=ml.split(' / ')
            rows.append(dict(**common,market='ML',line='',price_a=price(mh),price_b=price(ma)))
    if not games or sequences!=set(range(1,len(games)+1)):raise ValueError('empty or incomplete sequence')
    return games,rows


def run(comment=None, *, raw, allowed_author_ids, expected_comment_id, day_ct,
        expected_games, output_dir, team_aliases=None, capture_start_ct=None,capture_end_ct=None):
    obj=authenticate(raw,allowed_author_ids,expected_comment_id)
    if comment is not None and obj!=comment:raise ValueError('raw JSON/parsed comment mismatch')
    if 'FULL DRAFTKINGS BOARD —' in obj['body']:
        raise ValueError('full boards require explicit section adapter; archive separately')
    start,end=capture_interval(obj['body'],day_ct)
    for supplied,derived in [(capture_start_ct,start),(capture_end_ct,end)]:
        if supplied is not None and datetime.fromisoformat(supplied)!=derived:
            raise ValueError('supplied interval not bound to body')
    updated=datetime.fromisoformat(obj['updated_at'].replace('Z','+00:00'))
    if updated.utcoffset() is None or end>updated:raise ValueError('capture chronology mismatch')
    games,rows=parse_capture(obj['body'],day_ct,team_aliases)
    if type(expected_games) is not int or expected_games<1 or len(games)!=expected_games:
        raise ValueError('game denominator mismatch')
    if any(end>=datetime.fromisoformat(g['tipoff_ct']) for g in games):raise ValueError('not pregame')
    stream=io.StringIO();writer=csv.DictWriter(stream,COLUMNS,lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    by_team={(g['away'],g['home']):g for g in games}
    contracts=[]
    for index,row in enumerate(rows):
        g=by_team[row['away'],row['home']]
        contracts.append(dict(board_row=index+1,**row,dk_event_id=g['dk_event_id'],tipoff_ct=g['tipoff_ct'],
            period='FULL_GAME',settlement_rules_verified=False,source_comment_id=obj['id'],
            capture_start_ct=start.isoformat(),capture_end_ct=end.isoformat(),eligible_for_pricing=False))
    files={'comment.raw.json':raw,'board.csv':stream.getvalue().encode(),'events.json':json.dumps(games,sort_keys=True).encode(),
           'contracts.json':json.dumps(contracts,sort_keys=True).encode()}
    manifest=dict(source_url=obj['html_url'],source_kind='GITHUB_RELAY_NOT_BOOK_RECEIPT',
        github_author_id=obj['user']['id'],human_author_authenticated=False,
        capture_start_ct=start.isoformat(),capture_end_ct=end.isoformat(),timestamp_precision='minute',
        output_sha256={name:hashlib.sha256(data).hexdigest() for name,data in files.items()},
        games=len(games),paired_markets=len(rows),offered_sides=2*len(rows),
        totals_text_labels_checked=True,primary_totals_gate_changed=False,
        forecast_execution_complete=False,approved_stake_u=0)
    destination=Path(output_dir);destination.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():(destination/name).write_bytes(data)
    (destination/'COMPLETE.json').write_text(json.dumps(manifest,indent=2))
    return manifest


def archive_full_board(*, raw,allowed_author_ids,expected_comment_id,day_ct,expected_games,output_dir):
    obj=authenticate(raw,allowed_author_ids,expected_comment_id)
    matches=list(re.finditer(r'^FULL DRAFTKINGS BOARD — (.+?) @ (.+?) \(NCAAB\), DK event ID (\d+)\s*$',obj['body'],re.M))
    if type(expected_games) is not int or expected_games<1 or len(matches)!=expected_games:
        raise ValueError('full-board denominator mismatch')
    sections=[];ids=set()
    for index,match in enumerate(matches):
        text=obj['body'][match.start():matches[index+1].start() if index+1<len(matches) else len(obj['body'])]
        away,home,eid=match.groups()
        if eid in ids:raise ValueError('duplicate full-board event')
        ids.add(eid)
        tip=re.search(r'Tip-off: (\w+ \w+ \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M) CT',text)
        if not tip:raise ValueError('missing exact full-board tip')
        start_game=datetime.strptime(tip[1],'%a %b %d, %Y, %I:%M %p').replace(tzinfo=CT)
        if start_game.date().isoformat()!=day_ct:raise ValueError('full-board day mismatch')
        capture=re.search(r'Capture(?: window)?: (\d{1,2}:\d{2}(?: [AP]M)?[–-]\d{1,2}:\d{2} [AP]M CT)',text)
        if not capture:raise ValueError('missing full-board capture interval')
        prefix='DraftKings NCAAB league scan — '+start_game.strftime('%A, %B %d, %Y')+'\nCapture: '+capture[1]
        lo,hi=capture_interval(prefix,day_ct)
        updated=datetime.fromisoformat(obj['updated_at'].replace('Z','+00:00'))
        if updated.utcoffset() is None or hi>updated or hi>=start_game:
            raise ValueError('full-board chronology mismatch')
        sections.append(dict(dk_event_id=eid,away=away,home=home,tipoff_ct=start_game.isoformat(),
            capture_start_ct=lo.isoformat(),capture_end_ct=hi.isoformat(),source_comment_id=obj['id'],
            raw_section=text,structured_market_normalization_complete=False,eligible_for_pricing=False,
            status='ARCHIVED_UNPRICED_REQUIRES_MARKET_AND_MOVEMENT_ADAPTER'))
    files={'comment.raw.json':raw,'sections.json':json.dumps(sections,ensure_ascii=False).encode()}
    manifest=dict(source_url=obj['html_url'],github_author_id=obj['user']['id'],human_author_authenticated=False,
        games=len(sections),normalized_market_count=0,approved_stake_u=0,
        output_sha256={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
    destination=Path(output_dir);destination.mkdir(parents=True,exist_ok=False)
    for name,data in files.items():(destination/name).write_bytes(data)
    (destination/'COMPLETE.json').write_text(json.dumps(manifest,indent=2))
    return manifest


def main():
    import argparse
    import os
    import urllib.request
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--comment-id',type=int);source.add_argument('--comment-json')
    parser.add_argument('--allowed-author-id',type=int,action='append',required=True)
    parser.add_argument('--expected-comment-id',type=int,required=True)
    parser.add_argument('--day',required=True);parser.add_argument('--expected-games',type=int,required=True)
    parser.add_argument('--team-aliases-json');parser.add_argument('--out',required=True)
    parser.add_argument('--full-board-archive',action='store_true')
    args=parser.parse_args()
    if args.comment_id is not None:
        if args.comment_id!=args.expected_comment_id:raise ValueError('fetch/expected comment ID mismatch')
        headers={'Accept':'application/vnd.github+json','User-Agent':'SportsEdge-Muse-Intake'}
        token=os.environ.get('GITHUB_TOKEN')
        if token:headers['Authorization']='Bearer '+token
        url=f'https://api.github.com/repos/bighauss/Sportsedge/issues/comments/{args.comment_id}'
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=30) as response:
            raw=response.read(2_000_001)
    else:raw=Path(args.comment_json).read_bytes()
    if len(raw)>2_000_000:raise ValueError('source size limit')
    common=dict(raw=raw,allowed_author_ids=set(args.allowed_author_id),expected_comment_id=args.expected_comment_id,
                day_ct=args.day,expected_games=args.expected_games,output_dir=args.out)
    if args.full_board_archive:archive_full_board(**common)
    else:
        aliases=json.loads(Path(args.team_aliases_json).read_text(),object_pairs_hook=_unique) if args.team_aliases_json else {}
        run(**common,team_aliases=aliases)


if __name__=='__main__':main()
