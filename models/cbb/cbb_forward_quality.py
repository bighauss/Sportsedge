"""CBB complete-board forward diagnostics, never an official wagering gate.

Preserve every attempted side, require exact opposite offers, and score each
mirrored pair ONCE for model/market Brier. Closes are same-line comparisons.
Historical/prospective inputs are original private receipts, not reconstructed.
Self-reported SHA/timestamps do not independently authenticate any provider.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
SIDES = {"HOME":"AWAY", "AWAY":"HOME", "OVER":"UNDER", "UNDER":"OVER"}


class Blocked(ValueError):
    pass


def _time(value):
    if not isinstance(value,str) or not value.endswith("Z") or len(value)<20:
        raise Blocked("UTC_Z_REQUIRED")
    try:
        d=datetime.fromisoformat(value[:-1]+"+00:00")
    except ValueError as exc:
        raise Blocked("INVALID_UTC_TIMESTAMP") from exc
    if d.utcoffset().total_seconds()!=0:
        raise Blocked("INVALID_UTC_OFFSET")
    return d


def _hash(value):
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise Blocked("SHA256_REQUIRED_NOT_AUTHENTICATED")


def _price(x):
    if type(x) is not int or abs(x)<100:
        raise Blocked("INVALID_AMERICAN_PRICE")
    return x


def _decimal_odds(x):
    a=_price(x)
    return 1 + (a/100 if a>0 else 100/-a)


def _implied(x):
    return 1/_decimal_odds(x)


def _prob(x):
    if type(x) not in (int,float) or not math.isfinite(x) or not 0<x<1:
        raise Blocked("INVALID_MODEL_PROBABILITY")
    return float(x)


def _market(value):
    if not isinstance(value,(tuple,list)) or len(value)!=10 or value[0]!="CBB":
        raise Blocked("CBB_EXACT_MARKET_ID_REQUIRED")
    sport,event,kind,period,side,line,team,player,stat,settlement=value
    if not all(isinstance(v,str) for v in value) or not event or \
       kind not in ("ML","SPREAD","TOTAL","TEAM_TOTAL","PLAYER_PROP") or \
       period not in ("FG","1H","2H") or side not in SIDES or \
       settlement not in ("INCLUDES_OT","REGULATION","POSTED_RULES"):
        raise Blocked("INVALID_MARKET_ID")
    if ((kind in ("ML","SPREAD") and side not in ("HOME","AWAY")) or
        (kind not in ("ML","SPREAD") and side not in ("OVER","UNDER"))):
        raise Blocked("INVALID_MARKET_SIDE")
    if (kind=="TEAM_TOTAL" and not team) or (kind=="PLAYER_PROP" and (not player or not stat)):
        raise Blocked("UNBOUND_PLAYER_OR_TEAM_MARKET")
    if kind=="ML":
        if line:
            raise Blocked("ML_CANNOT_HAVE_LINE")
        pair_line=""
    else:
        try:
            d=Decimal(line)
        except (InvalidOperation,TypeError) as exc:
            raise Blocked("INVALID_LINE") from exc
        if not d.is_finite() or abs(d)%1!=Decimal("0.5"):
            raise Blocked("PUSH_DISTRIBUTION_NOT_PROVIDED")
        pair_line=format((abs(d) if kind=="SPREAD" else d).normalize(),"f")
    return (sport,event,kind,period,pair_line,team,player,stat,settlement),side


def _validate(row):
    if not isinstance(row,dict) or row.get("capture_state")!="OFFERED":
        raise Blocked("NOT_A_PRICED_OFFER")
    pair,side=_market(row.get("market"))
    book=row.get("book")
    if not isinstance(book,str) or not book.strip():
        raise Blocked("BOOK_REQUIRED")
    pair=(*pair,book.casefold())
    for field in ("model_sha256","feature_sha256","take_source_sha256"):
        _hash(row.get(field))
    p=_prob(row.get("model_p"))
    take=_price(row.get("take_american"))
    opposite=_price(row.get("take_opposite_american"))
    feature_pub=_time(row.get("feature_published_utc"))
    feature_obs=_time(row.get("feature_captured_utc"))
    freeze=_time(row.get("forecast_frozen_utc"))
    taken=_time(row.get("take_observed_utc"))
    start=_time(row.get("event_start_utc"))
    if not feature_pub<=feature_obs<=freeze<=taken<start:
        raise Blocked("LOOKAHEAD_OR_LATE_TAKE")
    if type(row.get("selected")) is not bool:
        raise Blocked("ORIGINAL_SELECTION_BOOLEAN_REQUIRED")
    y=row.get("outcome")
    if y is not None:
        if type(y) is not int or y not in (0,1):
            raise Blocked("PUSH_OR_INVALID_SETTLEMENT")
        _hash(row.get("final_source_sha256"))
        pub=_time(row.get("final_published_utc"))
        obs=_time(row.get("final_captured_utc"))
        if not start<pub<=obs:
            raise Blocked("PREMATURE_FINAL_OR_MISSING_RECEIPT")
    close=None
    fields=("close_american","close_opposite_american","close_observed_utc","close_source_sha256")
    if any(row.get(k) is not None for k in fields):
        if not all(row.get(k) is not None for k in fields):
            raise Blocked("PARTIAL_CLOSE_NOT_REPAIRED")
        _hash(row["close_source_sha256"])
        close=(_price(row["close_american"]),_price(row["close_opposite_american"]),
               _time(row["close_observed_utc"]))
        if not taken<=close[2]<start or (start-close[2]).total_seconds()>3600:
            raise Blocked("STALE_OR_LATE_CLOSE")
    return dict(pair=pair,side=side,model_p=p,take=take,opposite=opposite,
                taken=taken,close=close,outcome=y,selected=row["selected"],
                forecast_sig=(row["model_sha256"],row["feature_sha256"],freeze,
                              feature_pub,feature_obs,start),
                take_sig=row["take_source_sha256"],raw_ev=p*_decimal_odds(take)-1)


def audit_full_cbb_board(rows, *, expected_attempted_rows):
    if (not isinstance(rows,list) or type(expected_attempted_rows) is not int or
            expected_attempted_rows!=len(rows)):
        raise Blocked("FULL_BOARD_CENSUS_MISMATCH")
    ledger=[];groups=defaultdict(list);exact=Counter()
    for i,row in enumerate(rows):
        entry={"index":i,"state":"BLOCK"}
        try:
            if not isinstance(row,dict):
                raise Blocked("ROW_NOT_OBJECT")
            if row.get("capture_state")!="OFFERED":
                if row.get("capture_state") not in ("NOT_OFFERED","NOT_CAPTURED","NO_MODEL","NO_PRICE"):
                    raise Blocked("UNKNOWN_CENSUS_STATE")
                entry.update(state=row["capture_state"],reason="NO_AUTHENTICATED_COMPLETE_OFFER")
                ledger.append(entry)
                continue
            parsed=_validate(row)
            parsed["index"]=i
            groups[parsed["pair"]].append(parsed)
            exact[(parsed["pair"],parsed["side"])]+=1
            entry.update(state="STRUCTURE_PENDING_MIRROR",event_id=parsed["pair"][1])
        except (Blocked,AttributeError,TypeError,KeyError,ValueError) as exc:
            entry["reason"]=str(exc)
        ledger.append(entry)
    scored=[];chosen=[];selected_returns=[];moves=[];extremes=[];direction=Counter()
    for pair,items in groups.items():
        def block_all(reason):
            for item in items:
                ledger[item["index"]].update(state="BLOCK",reason=reason)
        if (len(items)!=2 or
            any(exact[(pair,x["side"])]!=1 for x in items) or
            items[0]["side"]!=SIDES.get(items[1]["side"])):
            block_all("MISSING_OR_DUPLICATE_MIRRORED_SIDE_ALL_COPIES")
            continue
        a,b=items
        if pair[2]=="SPREAD":
            la=Decimal(rows[a["index"]]["market"][5])
            lb=Decimal(rows[b["index"]]["market"][5])
            if la != -lb:
                block_all("SPREAD_MIRROR_LINE_NOT_OPPOSITE")
                continue
        if (a["take"]!=b["opposite"] or b["take"]!=a["opposite"] or
            a["taken"]!=b["taken"] or a["forecast_sig"]!=b["forecast_sig"] or
            a["take_sig"]!=b["take_sig"] or
            abs(a["model_p"]+b["model_p"]-1)>1e-6 or
            (a["outcome"] is None)!=(b["outcome"] is None) or
            (a["outcome"] is not None and a["outcome"]+b["outcome"]!=1)):
            block_all("MIRROR_PRICE_PROBABILITY_OR_GRADE_CONFLICT")
            continue
        if ((a["close"] is None)!=(b["close"] is None) or
            (a["close"] is not None and (
             a["close"][0]!=b["close"][1] or a["close"][1]!=b["close"][0] or
             a["close"][2]!=b["close"][2]))):
            block_all("MIRRORED_CLOSE_CONFLICT")
            continue
        for x in items:
            ledger[x["index"]]["state"]="MIRRORED_PAPER_RESEARCH_ONLY"
        canonical=next(x for x in items if x["side"] in ("HOME","OVER"))
        p=canonical["model_p"]
        m=_implied(canonical["take"])/(_implied(canonical["take"])+_implied(canonical["opposite"]))
        if canonical["outcome"] is not None:
            y=canonical["outcome"]
            scored.append((pair[1],(p-y)**2,(m-y)**2))
        best=max(items,key=lambda x:x["raw_ev"])
        if pair[2] in ("ML","SPREAD"):
            if pair[2]=="SPREAD":
                number=float(rows[best["index"]]["market"][5])
                label="UNDERDOG" if number>0 else "FAVORITE" if number<0 else "PICKEM"
            else:
                label="UNDERDOG" if best["take"]>0 else "FAVORITE"
            direction[label]+=1
        elif pair[2] in ("TOTAL","TEAM_TOTAL"):
            direction[best["side"]]+=1
        best_m=m if best is canonical else 1-m
        if best["raw_ev"]>=.25 or abs(best["model_p"]-best_m)>=.15:
            extremes.append({"event_id":pair[1],"market_kind":pair[2],"side":best["side"],
                             "reason":"MODEL_DOUBTED_EXTREME_DISAGREEMENT"})
        if canonical["outcome"] is not None:
            chosen.append((_decimal_odds(best["take"])-1 if best["outcome"] else -1))
        selected=[x for x in items if x["selected"]]
        if len(selected)>1:
            for x in selected:
                ledger[x["index"]]["selection_warning"]="BOTH_MIRRORED_SIDES_SELECTED_NO_ROI_COUNT"
        elif selected and selected[0]["outcome"] is not None:
            x=selected[0]
            selected_returns.append(_decimal_odds(x["take"])-1 if x["outcome"] else -1)
        if best["close"] is not None:
            p_close=_implied(best["close"][0])/(
                _implied(best["close"][0])+_implied(best["close"][1]))
            moves.append((p_close-best_m)*100)
    model=mean(x[1] for x in scored) if scored else None
    market=mean(x[2] for x in scored) if scored else None
    return {
        "state":"PAPER_0U_RESEARCH_UNAUTHENTICATED","input_rows":len(rows),
        "output_rows":len(ledger),
        "row_states":dict(sorted(Counter(x["state"] for x in ledger).items())),
        "paired_unique_market_rows":sum(x["state"]=="MIRRORED_PAPER_RESEARCH_ONLY" for x in ledger)//2,
        "paired_graded_markets":len(scored),
        "graded_unique_events":len({x[0] for x in scored}),
        "model_brier":model,"no_vig_market_brier":market,
        "market_minus_model_brier":(market-model if scored else None),
        "market_beaten_on_brier_observed_only":(model<market if scored else None),
        "one_best_model_side_flat_units_research":sum(chosen),
        "originally_selected_side_flat_units_research":sum(selected_returns),
        "selected_scored_count":len(selected_returns),
        "best_side_close_no_vig_shift_pp_mean_research":mean(moves) if moves else None,
        "matched_close_pairs":len(moves),
        "best_side_direction_counts":dict(sorted(direction.items())),
        "extreme_model_doubted":extremes,"rows":ledger,
        "counted_forward_rows":0,"official_counted":0,"approved_stake_u":0,
        "warnings":[
            "HASHES_AND_TIMESTAMP_CLAIMS_NOT_PROVIDER_AUTHENTICATION",
            "DESCRIPTIVE_BRIER_AND_RETURNS_NOT_FORWARD_CERTIFICATION",
            "EVENT_DEPENDENT_MARKETS_NOT_INDEPENDENT_TRIALS",
            "NO_FITTED_PLAYER_AVAILABILITY_COEFFICIENTS",
            "NO_AUTO_CALIBRATION_OR_PROMOTION",
        ],
    }


def _private(path):
    p=Path(os.path.abspath(path));resolved=p.resolve()
    if any(x==ROOT or ROOT in x.parents for x in (p,resolved)) or p.is_symlink():
        raise Blocked("CBB_PRIVATE_EVIDENCE_IN_PUBLIC_REPO")
    return p


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--report",required=True)
    parser.add_argument("--expected-attempted-rows",type=int,required=True)
    a=parser.parse_args(argv)
    raw=_private(a.input).read_bytes()
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result: raise Blocked("DUPLICATE_JSON_KEY")
            result[k]=v
        return result
    def constant(v):
        raise Blocked("NONFINITE_JSON_CONSTANT")
    rows=json.loads(raw,object_pairs_hook=unique,parse_constant=constant)
    audit=audit_full_cbb_board(rows,expected_attempted_rows=a.expected_attempted_rows)
    fd=os.open(_private(a.report),os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        json.dump(audit,stream,sort_keys=True,indent=2,allow_nan=False)
        stream.write("\n")
        stream.flush();os.fsync(stream.fileno())
    print("CBB PAPER/0u private diagnostic written; counted forward rows: 0")


if __name__=="__main__":
    main()
