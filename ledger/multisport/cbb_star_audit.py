"""Frozen-card confidence diagnostics, not a new rating system or betting approval.
Use explicitly selected original runs only, never substitute a later replay.
Caller authenticates bytes and final evidence separately.
"""
from collections import Counter
from statistics import mean
from .comparison import _reconcile_run, _cond_prob, _profit_1u, _parse_utc, IntegrityError

def audit_stars(runs, pick_set, *, authenticated_finals=None, star_field="stars"):
    runs=list(runs);events=set();groups={i:[] for i in range(1,6)};holds=Counter()
    for run in runs:
        m=run["manifest"];key=(m["sport"],m["event_id"])
        if key in events:raise IntegrityError("duplicate explicitly selected event run")
        events.add(key)
        if m["sport"].upper()!="CBB":raise IntegrityError("CBB only")
        if _parse_utc(m["capture_utc"])>=_parse_utc(m["start_utc"]):raise IntegrityError("nonpregame capture")
        if run.get("quarantined") or not run.get("settlement") or run["settlement"].get("quarantined") or run["settlement"].get("run_integrity_ok") is not True:
            holds["RUN_UNSETTLED_OR_QUARANTINED"]+=1;continue
        rows=_reconcile_run(run,pick_set,authenticated_finals=authenticated_finals)
        seen=set()
        for r in rows:
            fr=run["frozen_picks"][pick_set][r["row"]]
            q=fr.get("quote_id")
            if not isinstance(q,str) or not q or q in seen:raise IntegrityError("invalid or duplicate original quote ID")
            seen.add(q)
            if fr.get("on_card") is not True:
                holds["NOT_EXPLICITLY_ON_CARD"]+=1;continue
            s=fr.get(star_field)
            if type(s) is not int or not 1<=s<=5:
                holds["ORIGINAL_STAR_LABEL_MISSING_OR_INVALID"]+=1;continue
            if r["result"] not in ("W","L","P"):
                holds["OUTCOME_UNSETTLED"]+=1;continue
            p=_cond_prob("CBB",r,"blend_p") if r["result"]!="P" else None
            groups[s].append(dict(event=key,result=r["result"],p=p,units=_profit_1u(r["price"],r["result"])))
    result={}
    for s,rows in groups.items():
        decided=[r for r in rows if r["result"]!="P"]
        paired=[r for r in decided if r["p"] is not None]
        result[str(s)]=dict(settled=len(rows),events=len({r["event"] for r in rows}),
            wins=sum(r["result"]=="W" for r in rows),losses=sum(r["result"]=="L" for r in rows),
            pushes=sum(r["result"]=="P" for r in rows),win_rate=mean(r["result"]=="W" for r in decided) if decided else None,
            paired_n=len(paired),conditional_mean_probability=mean(r["p"] for r in paired) if paired else None,
            paired_win_rate=mean(r["result"]=="W" for r in paired) if paired else None,
            conditional_brier=mean((r["p"]-int(r["result"]=="W"))**2 for r in paired) if paired else None,
            paper_roi_per_1u_risked=mean(r["units"] for r in rows) if rows else None,
            small_sample=len({r["event"] for r in rows})<30)
    return dict(status="ORIGINAL_STAR_LABEL_DIAGNOSTIC_PAPER_ONLY",runs=len(runs),holds=dict(holds),stars=result,
        approved_stake_u=0,official_counted=0,limitations=["Original explicit selection and star fields required; no inferred rating.",
        "Conditional Brier excludes pushes; paper ROI includes push zero. No authenticated entry/close claim or star promotion."])
