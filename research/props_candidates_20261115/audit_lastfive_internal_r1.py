#!/usr/bin/env python3
"""Internal structural checks for SportsEdge last-five CSV; NEVER authenticates ESPN."""
import csv,collections,datetime as dt,hashlib,json,math,pathlib,re,sys,unicodedata
ALIAS={'NOP':'NO','BRK':'BKN','UTA':'UTAH','SAS':'SA','GSW':'GS'}
def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower() if c.isalnum())
def team(s):return ALIAS.get(s,s)
def audit(log,roster):
    rows=list(csv.DictReader(log.open(encoding='utf-8-sig',newline='')))
    rr=list(csv.DictReader(roster.open(encoding='utf-8-sig',newline='')))
    issues=[];ids=collections.defaultdict(list);keys=collections.Counter();mapid={}
    for rowno,r in enumerate(rows,2):
        aid=r['athlete_id'];ids[aid].append(r);keys[(aid,r['event_id'])]+=1
        if not (r['source_url'].startswith('https://') and '/athletes/'+aid+'/gamelog' in r['source_url']): issues.append(('SOURCE_URL_ID_MISMATCH',rowno))
        if not re.fullmatch('[0-9a-f]{64}',r['gamelog_sha256']): issues.append(('SOURCE_HASH_FORMAT',rowno))
        for col in ['minutes','pts','reb','ast','tpm']:
            try:v=float(r[col]);assert math.isfinite(v) and v>=0
            except (ValueError,AssertionError): issues.append(('BAD_STAT',rowno,col))
        try:
            started=dt.datetime.fromisoformat(r['game_date_utc']);retrieved=dt.datetime.fromisoformat(r['retrieved_utc'])
            assert started.tzinfo and retrieved.tzinfo and started<=retrieved
        except (ValueError,AssertionError,TypeError):issues.append(('BAD_CHRONOLOGY',rowno))
        ident=(r['player'],r['team'],r['source_url'],r['gamelog_sha256'])
        if aid in mapid and ident!=mapid[aid]:issues.append(('ATHLETE_ID_CHANGED',rowno))
        mapid.setdefault(aid,ident)
    for k,n in keys.items():
        if n!=1:issues.append(('DUPLICATE_PLAYER_EVENT',k,n))
    byname={norm(rs[0]['player']):rs[0] for rs in ids.values()}
    suffix_fixes={'DaRon Holmes':'DaRon Holmes II','GG Jackson II':'GG Jackson','Robert Williams':'Robert Williams III'}
    missing=[];team_conflicts=[];alias_teams=[];suffix=[]
    for x in rr:
        logname=suffix_fixes.get(x['player'],x['player']);l=byname.get(norm(logname))
        if l is None:
            missing.append(x['player']);continue
        if logname!=x['player']:suffix.append((x['player'],logname))
        if team(x['team']) != team(l['team']): team_conflicts.append((x['player'],x['team'],l['team']))
        elif x['team']!=l['team']:alias_teams.append((x['team'],l['team']))
    count=collections.Counter(len(v) for v in ids.values())
    eventdates=collections.defaultdict(set)
    for x in rows:eventdates[x['event_id']].add(x['game_date_ct'])
    res={
      'disposition':'PAPER_ONLY__NO_SOURCE_AUTHENTICATION__NO_PRICING',
      'file_name':log.name,'file_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),
      'file_bytes':log.stat().st_size,'roster_sha256':hashlib.sha256(roster.read_bytes()).hexdigest(),
      'data_rows':len(rows),'distinct_athlete_ids':len(ids),'roster_rows':len(rr),
      'distinct_game_ids':len(eventdates),'full_five_players':count[5],
      'fewer_than_five_players':sum(v for n,v in count.items() if n<5),
      'five_game_count_distribution':dict(sorted(count.items())),
      'duplicate_athlete_event_keys':sum(n-1 for n in keys.values() if n>1),
      'event_id_multiple_dates':sum(len(v)!=1 for v in eventdates.values()),
      'missing_roster_names_after_known_suffix':missing,
      'known_suffix_aliases':suffix,'non_alias_team_conflicts':team_conflicts,
      'known_team_alias_matches':len(alias_teams),
      'issue_count':len(issues),'first_issues':issues[:20],
      'source_urls_present':sum(bool(x['source_url']) for x in rows),
      'sha256_strings_present':sum(bool(x['gamelog_sha256']) for x in rows),
      'retrieved_timestamps_present':sum(bool(x['retrieved_utc']) for x in rows),
      'source_payloads_retrieved_and_rehashed':False,
      'event_completion_independently_authenticated':False,
      'source_roster_manifest_verified':False,
      'valid_for_live_pricing':False,
      'warning':'CSV consistency and recorded claims are NOT independent validation of upstream ESPN payloads or event-time manifest.'
    }
    return res
if __name__=='__main__':
    a,b,c=map(pathlib.Path,sys.argv[1:4]); c.write_text(json.dumps(audit(a,b),indent=2)+'\n')
    print(c.read_text())
