"""Research walk-forward evaluation of frozen probabilities, never production routing.

Source authentication is an upstream acceptance gate, not established by this
module. Probabilities must share conditional-no-push semantics. Pushes are
excluded from binary scores; dead heats require a future book-rules adapter.
"""
import math
import random
from collections import defaultdict
from datetime import datetime, timezone

INDEPENDENT_WEIGHTS = (0., .25, .50, .60, .75, .80, .90, .95, 1.)
# Public blend API uses market weight. Complement the owner-approved independent grid.
MARKET_WEIGHTS = tuple(sorted(round(1-w, 2) for w in INDEPENDENT_WEIGHTS))
SPORTS = frozenset(("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA"))


def utc(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)


def checked_p(value):
    if isinstance(value, bool):
        raise ValueError("boolean probability")
    p = float(value)
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("invalid probability")
    return p


def blend(market_p, independent_p, market_weight):
    w = checked_p(market_weight)
    return w*checked_p(market_p)+(1-w)*checked_p(independent_p)


def validate(rows):
    seen, events = set(), {}
    for r in rows:
        if r["sport"] not in SPORTS or not r["event_id"] or not r["quote_id"]:
            raise ValueError("sport/event/quote identity required")
        key = (r["sport"],r["event_id"],r["quote_id"],r["horizon"])
        if key in seen:
            raise ValueError("duplicate evaluation quote/capture")
        seen.add(key)
        cap,start,available = map(utc,(r["capture_utc"],r["start_utc"],r["result_available_utc"]))
        if not cap < start <= available:
            raise ValueError("invalid temporal ordering")
        ek=(r["sport"],r["event_id"])
        if ek in events and events[ek] != start:
            raise ValueError("conflicting event starts")
        events[ek]=start
        if r["prob_definition"] != "conditional_no_push":
            raise ValueError("unsupported probability semantics")
        if r["result"] not in ("W","L","P","NG","DH"):
            raise ValueError("invalid result")
        for f in ("market_p","independent_p","current_p"):
            if r.get(f) is not None:
                checked_p(r[f])


def _score(p,y):
    clipped=min(1-1e-6,max(1e-6,p))
    return ((p-y)**2, -(y*math.log(clipped)+(1-y)*math.log(1-clipped)))


def _select(rows, min_events):
    groups=defaultdict(list)
    for r in rows:
        if r["result"] in ("W","L") and all(r.get(f) is not None for f in ("market_p","independent_p","current_p")):
            groups[r["event_id"]].append(r)
    if len(groups)<min_events:
        return None,len(groups)
    losses={w:sum(sum(_score(blend(r["market_p"],r["independent_p"],w),int(r["result"]=="W"))[0]
                             for r in rs)/len(rs) for rs in groups.values())/len(groups) for w in MARKET_WEIGHTS}
    return min(losses,key=lambda w:(losses[w],-w)),len(groups)


def _summary(records, n_boot, seed):
    by_event=defaultdict(list)
    for event,brier,ll,delta in records:
        by_event[event].append((brier,ll,delta))
    means=[tuple(sum(x[i] for x in rs)/len(rs) for i in range(3)) for rs in by_event.values()]
    n=len(means)
    if not n:
        return {"n":0,"n_events":0,"brier":None,"log_loss":None,"paired_delta_brier":None,"ci95":None,"small_sample":True}
    ci=None
    if n>=2:
        rng=random.Random(seed)
        boots=sorted(sum(means[rng.randrange(n)][2] for _ in range(n))/n for _ in range(n_boot))
        ci=[boots[int(.025*n_boot)],boots[int(.975*n_boot)]]
    return dict(n=len(records),n_events=n,brier=sum(x[0] for x in means)/n,
                log_loss=sum(x[1] for x in means)/n,paired_delta_brier=sum(x[2] for x in means)/n,
                ci95=ci,small_sample=n<30,weighting="equal_event",promotion_authorized=False)


def walk_forward(rows, *, min_events, n_boot=1000, seed=42):
    """Retrospective replay; freeze each event's selection at its earliest capture.

    Input rows are one preselected capture per quote/horizon. This module rejects
    duplicates, rather than choosing captures using settlement availability.
    """
    if type(min_events) is not int or min_events<2 or type(n_boot) is not int or n_boot<100:
        raise ValueError("explicit minimum >=2 and n_boot>=100 required")
    rows=list(rows)
    validate(rows)
    events=defaultdict(list)
    for r in rows:
        events[(r["sport"],r["event_id"])].append(r)
    forecasts=[]
    coverage=defaultdict(int)
    metrics=defaultdict(list)
    for event, target in sorted(events.items(),key=lambda item:min(utc(r["capture_utc"]) for r in item[1])):
        cutoff=min(utc(r["capture_utc"]) for r in target)
        for r in target:
            stratum=(r["sport"],r["market"],r["horizon"])
            training=[h for h in rows if (h["sport"],h["event_id"]) != event
                      and (h["sport"],h["market"],h["horizon"])==stratum
                      and utc(h["result_available_utc"])<cutoff]
            w,n_train=_select(training,min_events)
            missing=[f for f in ("market_p","independent_p","current_p") if r.get(f) is None]
            status="MISSING_PROBABILITY" if missing else "INSUFFICIENT_TRAINING" if w is None else "EXPERIMENTAL"
            coverage[(stratum,status,r["result"])]+=1
            preds={}
            if not missing:
                preds={"market_only":r["market_p"],"independent":r["independent_p"],"current":r["current_p"]}
                preds.update({f"market_weight_{weight:g}":blend(r["market_p"],r["independent_p"],weight) for weight in MARKET_WEIGHTS})
                if w is not None:
                    preds["selected_hybrid"]=blend(r["market_p"],r["independent_p"],w)
            forecasts.append(dict(sport=r["sport"],event_id=r["event_id"],quote_id=r["quote_id"],
                market=r["market"],horizon=r["horizon"],cutoff=cutoff.isoformat(),market_weight=w,
                n_training_events=n_train,status=status,predictions=preds,source_authentication="NOT_VERIFIED_HERE"))
            # All candidates share the selected hybrid's eligible sample.
            if status=="EXPERIMENTAL" and r["result"] in ("W","L"):
                y=int(r["result"]=="W")
                baseline=_score(r["market_p"],y)[0]
                for candidate,p in preds.items():
                    b,ll=_score(p,y)
                    metrics[(stratum,candidate)].append((r["event_id"],b,ll,b-baseline))
    return dict(forecasts=forecasts,coverage=[dict(sport=k[0][0],market=k[0][1],horizon=k[0][2],status=k[1],result=k[2],n=v) for k,v in coverage.items()],
                metrics=[dict(sport=k[0][0],market=k[0][1],horizon=k[0][2],candidate=k[1],**_summary(v,n_boot,seed)) for k,v in metrics.items()],
                roi_status="NOT_IMPLEMENTED_NO_SETTLEMENT_ADAPTER",clv_status="NOT_AVAILABLE_NO_AUTHENTICATED_CLOSING_QUOTES")


def research_output(forecast, *, independent_projection=None, vegas_projection=None, dk_decimal=None):
    """Render the required research schema; never infer score means from probabilities."""
    from .devig import ev_per_unit, fair_win_given_push
    p=forecast["predictions"].get("selected_hybrid")
    return dict(independent_sportsedge_projection=independent_projection,
                vegas_projection=vegas_projection,external_market_consensus=forecast["predictions"].get("market_only"),
                hybrid_projection=None,hybrid_probability=p,market_weight=forecast["market_weight"],
                fair_decimal_odds=fair_win_given_push(p,0) if p is not None and p>0 else None,
                draftkings_decimal_odds=dk_decimal,
                projected_ev=ev_per_unit(p,dk_decimal,0) if p is not None and dk_decimal is not None else None,
                probability_semantics="conditional_no_push",ev_semantics="conditional_on_decisive_settlement",
                confidence=None,uncertainty=None,data_quality=forecast["source_authentication"],
                validation_status=forecast["status"],approved_stake_u=0,promotion_authorized=False)
