"""Fail-closed NFL main-line, prop and TD quote gate. PAPER / 0u only.

Independent of frozen sportsedge_v5.py. Preserves every supplied quote,
does not price from sportsbook-derived means, does not infer player IDs from
truncated names, and refuses to turn X+ ladders into two-sided no-vig prices.
The source SHA protects local bytes, NOT publisher authenticity.
"""
from __future__ import annotations

from collections import defaultdict, Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

SHA = re.compile(r"^sha256:[a-f0-9]{64}$")
KINDS = frozenset({"ML","SPREAD","TOTAL","TEAM_TOTAL","PLAYER_PROP",
                   "PLAYER_PROP_XPLUS","ATTD","FIRST_TD","TD_2PLUS","SGP"})
PERIODS = frozenset({"FG","1H","2H","1Q","2Q","3Q","4Q"})
PLAYER = frozenset({"PLAYER_PROP","PLAYER_PROP_XPLUS","ATTD","FIRST_TD","TD_2PLUS"})
TD = frozenset({"ATTD","FIRST_TD","TD_2PLUS"})
RECEIVING = frozenset({"REC_YDS","RECEPTIONS","TARGETS","LONGEST_RECEPTION"})
RUSHING = frozenset({"RUSH_YDS","RUSH_ATT"})
OPPOSITE = {"HOME":"AWAY","AWAY":"HOME","OVER":"UNDER","UNDER":"OVER",
            "YES":"NO","NO":"YES"}
REQUIRED = frozenset({"event_id","market_id","kind","period","side","line",
                      "odds_american","observed_at_utc","event_start_utc",
                      "source_sha256","quote_id"})
OPTIONAL = frozenset({"team_id","player_id","player_display","stat","book"})


def utc(value):
    if not isinstance(value,str) or not value:
        raise ValueError("TIMESTAMP_MISSING")
    try:
        result=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if result.tzinfo is None or result.utcoffset().total_seconds()!=0:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    return result.astimezone(timezone.utc)


def dec(value):
    if isinstance(value,bool) or value is None:
        raise ValueError("INVALID_NUMBER")
    try:
        result=Decimal(str(value))
    except (InvalidOperation,ValueError) as exc:
        raise ValueError("INVALID_NUMBER") from exc
    if not result.is_finite():
        raise ValueError("INVALID_NUMBER")
    return result


def odds(value):
    result=dec(value)
    if result!=result.to_integral_value() or not 100<=abs(result)<=100000:
        raise ValueError("INVALID_AMERICAN_PRICE")
    return int(result)


def key(row):
    value=dec(row["line"]) if row["line"] not in ("",None) else None
    if row["kind"]=="SPREAD" and row["side"]=="AWAY":
        value=-value
    return (row["event_id"],row["market_id"],row["kind"],row["period"],
            row.get("team_id",""),row.get("player_id",""),row.get("stat",""),
            str(value) if value is not None else "")


def audit(rows,forecasts,*,decision_utc,max_quote_age_s=300,
          max_pair_skew_s=30,max_score_gap=3):
    """One visible 0u row per observation; diagnostics never confer acceptance.

    forecasts[event] optionally includes asof_utc, source_sha256, total,
    margin_home, and players[player_id][stat] with mean, sd, asof_utc,
    source_sha256, confirmed_active and independent projected volume.
    """
    now=utc(decision_utc)
    if not isinstance(rows,list) or not isinstance(forecasts,dict):
        raise ValueError("INVALID_AUDIT_INPUT")
    if type(max_quote_age_s)!=int or not 0<max_quote_age_s<=300:
        raise ValueError("UNSAFE_QUOTE_AGE_LIMIT")
    if type(max_pair_skew_s)!=int or not 0<max_pair_skew_s<=max_quote_age_s:
        raise ValueError("UNSAFE_PAIR_SKEW_LIMIT")
    gap=dec(max_score_gap)
    if not 0<gap<=10:
        raise ValueError("UNSAFE_GAP_THRESHOLD")
    # A contradictory first copy is just as unreliable as the later copy.
    # Count every claimed original quote ID before processing any market row.
    quote_counts=Counter((r.get("event_id"),r.get("quote_id"))
                         for r in rows if isinstance(r,dict))
    output=[]; groups=defaultdict(list)
    for index,row in enumerate(rows):
        if not isinstance(row,dict) or not REQUIRED.issubset(row) or set(row)-REQUIRED-OPTIONAL:
            raise ValueError("UNEXPECTED_OR_MISSING_QUOTE_FIELDS")
        event=row["event_id"]; kind=row["kind"]; side=row["side"]
        if not isinstance(event,str) or not event or not isinstance(row["market_id"],str) or not row["market_id"]:
            raise ValueError("EVENT_OR_MARKET_ID_MISSING")
        if kind not in KINDS or row["period"] not in PERIODS or side not in OPPOSITE:
            raise ValueError("UNSUPPORTED_MARKET_PERIOD_OR_SIDE")
        price=odds(row["odds_american"])
        observed=utc(row["observed_at_utc"])
        start=utc(row["event_start_utc"])
        if not isinstance(row["source_sha256"],str) or not SHA.fullmatch(row["source_sha256"]):
            raise ValueError("SOURCE_BYTES_HASH_REQUIRED")
        if not isinstance(row["quote_id"],str) or not row["quote_id"]:
            raise ValueError("QUOTE_ID_MISSING")
        if not isinstance(row.get("book","DraftKings"),str) or row.get("book","DraftKings").casefold()!="draftkings":
            raise ValueError("NOT_DRAFTKINGS")
        line=row["line"]
        if kind in ("ML","ATTD","FIRST_TD","TD_2PLUS","SGP"):
            if line not in ("",None): raise ValueError("LINE_NOT_ALLOWED")
        elif kind=="PLAYER_PROP_XPLUS":
            if side!="YES" or dec(line)!=dec(line).to_integral_value() or dec(line)<1:
                raise ValueError("INVALID_XPLUS_THRESHOLD")
        elif line in ("",None): raise ValueError("LINE_REQUIRED")
        else: dec(line)
        if kind in ("SPREAD","ML") and side not in ("HOME","AWAY"):
            raise ValueError("TEAM_SIDE_INVALID")
        if kind in ("TOTAL","TEAM_TOTAL","PLAYER_PROP") and side not in ("OVER","UNDER"):
            raise ValueError("OVER_UNDER_REQUIRED")
        if kind in TD and side!="YES":
            raise ValueError("TOUCHDOWN_SELECTION_UNSUPPORTED")
        reasons=set()
        if observed>now: reasons.add("QUOTE_FROM_FUTURE")
        if now>=start or observed>=start: reasons.add("EVENT_STARTED_OR_LIVE_PRICE")
        if (now-observed).total_seconds()>max_quote_age_s:
            reasons.add("STALE_PRICE_RECAPTURE")
        qkey=(event,row["quote_id"])
        if quote_counts[qkey]>1: reasons.add("DUPLICATE_QUOTE_ID")
        canonical=key(row)
        if kind!="PLAYER_PROP_XPLUS": groups[canonical].append((index,side,observed))
        if kind in PLAYER:
            label=row.get("player_display","")
            if not row.get("player_id"): reasons.add("PLAYER_ID_UNBOUND")
            if "…" in label or "..." in label: reasons.add("PLAYER_DISPLAY_TRUNCATED")
        f=forecasts.get(event)
        if not isinstance(f,dict):
            reasons.add("NO_INDEPENDENT_EVENT_PROJECTION")
        else:
            try:
                f_time=utc(f["asof_utc"])
                if not isinstance(f["source_sha256"],str) or not SHA.fullmatch(f["source_sha256"]):
                    raise ValueError("INVALID_SOURCE_SHA")
                if f_time>observed: reasons.add("FORECAST_AFTER_QUOTE")
                if f_time>=start: reasons.add("FORECAST_AFTER_KICKOFF")
            except (KeyError,ValueError): reasons.add("FORECAST_PROVENANCE_INVALID")
            if kind in ("TOTAL","SPREAD","ML"):
                # A full-game mean MUST NOT be applied to a half/quarter line.
                period_forecast=(f if row["period"]=="FG" else
                                 f.get("periods",{}).get(row["period"]))
                if not isinstance(period_forecast,dict):
                    reasons.add("NO_INDEPENDENT_PERIOD_PROJECTION")
                else:
                    try:
                        if kind=="TOTAL" and abs(dec(period_forecast["total"])-dec(line))>gap:
                            reasons.add("UNEXPLAINED_TOTAL_MODEL_MARKET_GAP")
                        if kind=="SPREAD" and abs(dec(period_forecast["margin_home"])+(
                            dec(line) if side=="HOME" else -dec(line)))>gap:
                            reasons.add("UNEXPLAINED_MARGIN_MODEL_MARKET_GAP")
                        if kind=="ML": dec(period_forecast["margin_home"])
                    except (KeyError,ValueError):
                        reasons.add("NO_INDEPENDENT_SCORE_PROJECTION")
            if kind=="TEAM_TOTAL":
                # Team totals must have their own team/period-specific estimate.
                if not row.get("team_id"):
                    reasons.add("TEAM_TOTAL_TEAM_ID_UNBOUND")
                team_forecast=(f.get("team_totals",{}).get(row["period"],{})
                               .get(row.get("team_id")))
                if not isinstance(team_forecast,dict):
                    reasons.add("NO_INDEPENDENT_TEAM_TOTAL_PROJECTION")
                else:
                    try:
                        if abs(dec(team_forecast["mean"])-dec(line))>gap:
                            reasons.add("UNEXPLAINED_TEAM_TOTAL_MODEL_MARKET_GAP")
                    except (KeyError,ValueError):
                        reasons.add("NO_INDEPENDENT_TEAM_TOTAL_PROJECTION")
            if kind in PLAYER and kind not in TD:
                try:
                    p=f["players"][row.get("player_id")][row.get("stat")]
                    if row["period"]!="FG":
                        # No full-game stat distribution can price 1H/1Q props.
                        if not isinstance(p,dict) or not isinstance(
                            p.get("periods",{}).get(row["period"]),dict):
                            reasons.add("NO_INDEPENDENT_PERIOD_PLAYER_PROJECTION")
                            raise ValueError("PERIOD_PLAYER_FORECAST_MISSING")
                        p=p["periods"][row["period"]]
                    if not isinstance(p,dict): raise ValueError("INVALID_PLAYER")
                    if utc(p["asof_utc"])>observed or utc(p["asof_utc"])>=start:
                        reasons.add("PLAYER_MODEL_LOOKAHEAD")
                    if not isinstance(p["source_sha256"],str) or not SHA.fullmatch(p["source_sha256"]):
                        raise ValueError("PLAYER_SOURCE_HASH_REQUIRED")
                    if dec(p["mean"])<0 or dec(p["sd"])<=0:
                        raise ValueError("INVALID_PLAYER_MOMENTS")
                    if p.get("confirmed_active") is not True:
                        reasons.add("ACTIVE_STATUS_UNVERIFIED")
                    if row.get("stat") in RECEIVING and dec(p.get("projected_targets",0))<4:
                        reasons.add("RECEIVING_TARGET_VOLUME_BELOW_4")
                    if row.get("stat") in RUSHING and dec(p.get("projected_rush_attempts",0))<10:
                        reasons.add("RUSH_ATTEMPT_VOLUME_BELOW_10")
                except (KeyError,TypeError,ValueError):
                    reasons.add("INDEPENDENT_PLAYER_FORECAST_MISSING_OR_INVALID")
        if kind=="PLAYER_PROP_XPLUS": reasons.add("ONE_SIDED_XPLUS_NO_VIG_PAIR")
        if kind in TD: reasons.add("NO_VALIDATED_ORDERED_TD_EVENT_MODEL")
        if kind=="SGP": reasons.add("SGP_NEEDS_JOINT_EVENT_PROBABILITY_AND_POSTED_PRICE")
        output.append({"index":index,"event_id":event,"market_id":row["market_id"],
                       "kind":kind,"period":row["period"],"side":side,
                       "line":str(line) if line is not None else "",
                       "odds_american":price,"quote_id":row["quote_id"],
                       "canonical_key":list(canonical),"reasons":reasons})
    for group in groups.values():
        for i,side,time in group:
            if "DUPLICATE_QUOTE_ID" in output[i]["reasons"]:
                output[i]["reasons"].add("DUPLICATE_QUOTE_CANNOT_ESTABLISH_TWO_SIDED_PAIR")
                continue
            opposite=[t for j,s,t in group
                      if j!=i and s==OPPOSITE[side]
                      and "DUPLICATE_QUOTE_ID" not in output[j]["reasons"]]
            if not opposite: output[i]["reasons"].add("NO_MATCHED_TWO_SIDED_QUOTE")
            elif all(abs((time-t).total_seconds())>max_pair_skew_s for t in opposite):
                output[i]["reasons"].add("OPPOSITE_QUOTE_SNAPSHOT_TOO_FAR_APART")
    for row in output:
        row["reasons"].add("SOURCE_AND_MODEL_NOT_EXTERNALLY_AUTHENTICATED")
        row["reasons"]=sorted(row["reasons"])
        row.update(status="PAPER_HOLD_0U",approved_stake_u=0,official_counted=0,
                   raw_ev=None,blended_ev=None,stars=None)
    digest=sha256(json.dumps(rows,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    return {"version":"NFL_FULL_MARKET_GATE_R1","status":"PAPER_HOLD_0U",
            "decision_utc":now.isoformat(),"count":len(output),"rows":output,
            "no_verified_bets":True,"approved_stake_u":0,
            "original_snapshot_sha256":"sha256:"+digest}
