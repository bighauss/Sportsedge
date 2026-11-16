#!/usr/bin/env python3
"""Research-only RUN IT v2.1 sizing contract. Never places wagers or authorizes stakes."""
import datetime as dt
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

D=Decimal
CT=ZoneInfo("America/Chicago")
RULES='SPORTSEDGE_RISK_2026_11_15_LOCK_V1'
CAP_DAY=D('5');CAP_GAME=D('1');CAP_THEME=D('3')

def dec(value):
    if value is None or isinstance(value,bool):raise ValueError('missing number')
    n=D(str(value))
    if not n.is_finite():raise ValueError('nonfinite number')
    return n

def iso(value):
    t=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if t.utcoffset() is None:raise ValueError('naive date')
    return t

def american_price(s):
    x=int(str(s).replace('−','-').replace('＋','+'))
    if x==0 or -100<x<100:raise ValueError('invalid American odds')
    return D(x)/100 if x>0 else D(100)/D(-x)

def clv_factor(closes,sport):
    # Chronology and external source authenticity must be verified by the caller.
    eligible=[r for r in closes if r.get('eligible') is True and
              r.get('comparable') is True and r.get('sport')==sport]
    last=eligible[-50:]
    if len(last)!=50:return D(1),len(last)
    if sum((dec(r['clv']) for r in last),D(0))<0:return D('.5'),50
    return D(1),50

def prop_gate(x):
    if 'PROP' not in str(x.get('market','')).upper():return []
    sport=str(x.get('sport','')).upper()
    stat=str(x.get('stat','')).upper()
    flags=[]
    try:
        if sport=='NFL':
            if stat in ('RECEIVING','RECEPTIONS','RECEIVING_YARDS'):
                if dec(x.get('projected_targets'))<4:flags.append('NFL_TARGET_MIN_4')
            elif stat in ('RUSHING','RUSH_YARDS','RUSH_ATTEMPTS'):
                if dec(x.get('projected_rush_attempts'))<10:flags.append('NFL_RUSH_MIN_10')
            else:flags.append('UNCLASSIFIED_NFL_PROP')
        elif sport=='NBA':
            if dec(x.get('projected_minutes'))<20:flags.append('NBA_MINUTES_20')
        elif sport=='NHL':
            if dec(x.get('projected_toi'))<14:flags.append('NHL_TOI_14')
        elif sport=='MLB':
            if x.get('confirmed_starting_pitcher') is not True:flags.append('MLB_STARTER_UNCONFIRMED')
            if x.get('lineup_dependent') is True and x.get('confirmed_lineup') is not True:
                flags.append('MLB_LINEUP_UNCONFIRMED')
        else:flags.append('UNSPECIFIED_PROP_MINIMUM')
    except (ValueError,InvalidOperation,TypeError):
        flags.append('PROP_VOLUME_MISSING')
    return flags

def diagnostic(candidate,ledger=(),closing_observations=()):
    """Return proposed *diagnostic* units. Approved stake always stays zero."""
    flags=[]
    report={'rules':RULES,'research_only':True,'approved_stake_u':0,
            'diagnostic_u':0,'status':'PAPER_0U','flags':flags}
    mandatory=('bet_id','event_id','theme','risk_date_ct','market','sport',
               'price_american','p_model','p_market_novig','bankroll',
               'dollars_per_u','confidence','captured_utc','game_start_utc')
    missing=[k for k in mandatory if candidate.get(k) is None or str(candidate.get(k)).strip()=='']
    if missing:flags.append('MISSING:'+','.join(missing));return report
    if candidate.get('book')!='DK':flags.append('BOOK_NOT_DK')
    if candidate.get('source_receipt_verified') is not True:flags.append('SOURCE_RECEIPT_NOT_VERIFIED')
    if candidate.get('independent_model_verified') is not True:flags.append('MODEL_SOURCE_UNVERIFIED')
    if candidate.get('quote_is_fresh') is not True:flags.append('QUOTE_FRESHNESS_UNVERIFIED')
    if candidate.get('line_crossed_projection') is True:flags.append('LINE_CROSSED_PROJECTION')
    if candidate.get('requires_lineup_confirmation') is True and candidate.get('confirmed_lineup') is not True:
        flags.append('LINEUP_UNCONFIRMED')
    if str(candidate.get('sport','')).upper()=='NHL' and candidate.get('goalie_confirmed') is not True:
        flags.append('GOALIE_UNCONFIRMED')
    if candidate.get('material_news_changed') is True and candidate.get('repriced_after_change') is not True:
        flags.append('MATERIAL_NEWS_REPRICE_REQUIRED')
    if candidate.get('confidence') not in ('HIGH','MEDIUM','LOW'):flags.append('INVALID_CONFIDENCE')
    flags.extend(prop_gate(candidate))
    try:
        quote=iso(candidate['captured_utc']);start=iso(candidate['game_start_utc'])
        if quote>=start:flags.append('POST_START_QUOTE')
        if D(str((start-quote).total_seconds()))<=D(90*60) and candidate.get('injury_snapshot_locked') is not True:
            flags.append('T90_INJURY_LOCK_MISSING')
        # Daily staking/exposure caps are assessed on the Central Time
        # calendar day of the candidate quote/decision, not the future game's
        # kickoff date. An early bet on Monday's game placed Sunday consumes
        # Sunday's 5u budget. Caller claims still require independent receipts.
        if quote.astimezone(CT).date().isoformat()!=str(candidate['risk_date_ct']):
            flags.append('CT_DATE_NEEDS_INDEPENDENT_VERIFICATION')
        p_model=dec(candidate['p_model']);p_market=dec(candidate['p_market_novig'])
        if not (0<p_model<1 and 0<p_market<1):raise ValueError('probability out of range')
        bankroll=dec(candidate['bankroll']);unit=dec(candidate['dollars_per_u'])
        if bankroll<=0 or unit<=0:raise ValueError('invalid bankroll/unit')
        b=american_price(candidate['price_american'])
        if candidate.get('push_capable') is True:
            mp=dec(candidate.get('p_model_push'));vp=dec(candidate.get('p_market_push'))
            if not (0<=mp<1-p_model and 0<=vp<1-p_market):
                raise ValueError('invalid push probability')
            push=D('.3')*mp+D('.7')*vp
        else:push=D(0)
        win=D('.3')*p_model+D('.7')*p_market
        loss=1-win-push
        ev=b*win-loss
        report.update(blended_ev_per_dollar=str(ev),
                      blended_win_probability=str(win),
                      blended_push_probability=str(push))
        if ev<=0:flags.append('NON_POSITIVE_BLENDED_EV')
        if not flags:
            full_kelly=ev/(b*(win+loss))
            init=D('.25')*max(D(0),full_kelly)*bankroll/unit
            init=min(D('1.5'),max(D('.25'),init))
            if candidate.get('sport')=='NHL' and candidate.get('goalie_morning_only') is True and candidate['confidence']=='HIGH':
                flags.append('NHL_GOALIE_MORNING_MAX_MEDIUM')
            if not flags:
                if candidate['confidence']=='LOW':init*=D('.5')
                factor,n=clv_factor(closing_observations,candidate['sport'])
                init*=factor
                report['clv_matched_recent_count']=n
                day=game=theme=D(0);seen=set()
                for record in ledger:
                    ident=str(record['bet_id'])
                    if ident in seen:flags.append('LEDGER_DUPLICATE_BET_ID')
                    seen.add(ident)
                    if ident==str(candidate['bet_id']):flags.append('DUPLICATE_BET_ALREADY_RECORDED')
                    qty=dec(record['stake_u'])
                    if qty<0:flags.append('NEGATIVE_LEDGER_EXPOSURE')
                    if record.get('risk_date_ct')==candidate['risk_date_ct']:day+=qty
                    if record.get('event_id')==candidate['event_id']:game+=qty
                    if record.get('theme')==candidate['theme']:theme+=qty
                room=min(CAP_DAY-day,CAP_GAME-game,CAP_THEME-theme)
                if room<=0:flags.append('RISK_CAP_EXHAUSTED')
                if not flags:report['diagnostic_u']=str(min(room,init))
    except (ValueError,TypeError,KeyError,InvalidOperation,OverflowError) as exc:
        flags.append('UNVERIFIED_NUMERIC_OR_LEDGER:'+type(exc).__name__)
    return report
