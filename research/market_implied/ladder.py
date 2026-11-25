"""Market-implied count survival ladder, research only.

Uses existing two-sided consensus; does not identify a full PMF, a point mean,
or authenticated source clocks. Half-integer lines only, nonnegative counts.
"""
from collections import defaultdict
from .devig import book_key, consensus, utc

def infer_count_ladder(quotes, *, as_of, max_age_seconds, max_snapshot_skew_seconds=60, method="power"):
    if type(max_snapshot_skew_seconds) is not int or max_snapshot_skew_seconds<0:
        raise ValueError("INVALID_SNAPSHOT_SKEW")
    # Never allow a DK alias or a declared copied book to enter the ladder.
    rows=[q for q in quotes if book_key(q.book)!="draftkings" and q.copies is None]
    if not rows:raise ValueError("NO_EXTERNAL_BOOKS")
    groups=defaultdict(list)
    common=None
    for q in rows:
        if type(q.line) not in (int,float) or not 0<=q.line<=750 or q.line%1!=.5:
            raise ValueError("NONNEGATIVE_HALF_LINE_REQUIRED")
        if tuple(q.outcomes)!=("over","under") or len(q.prices)!=2:
            raise ValueError("TWO_SIDED_ORDERED_OVER_UNDER_REQUIRED")
        if q.market.startswith(("prop","player_prop")) and (not isinstance(q.player_id,str) or not q.player_id.strip()):
            raise ValueError("PLAYER_ID_REQUIRED")
        key=(q.sport,q.event_id,q.player_id,q.market,q.period,q.rules,utc(q.start_utc))
        if common is not None and key!=common:raise ValueError("MIXED_LADDER_CONTRACT")
        common=key
        groups[q.line].append(q)
    if len(groups)<2:raise ValueError("AT_LEAST_TWO_DISTINCT_RUNGS_REQUIRED")
    books=None
    for _,rs in groups.items():
        keys={book_key(q.book) for q in rs}
        if len(keys)!=len(rs):raise ValueError("DUPLICATE_BOOK_RUNG")
        if books is not None and keys!=books:raise ValueError("CHANGING_BOOK_COMPOSITION")
        books=keys
    clocks=[utc(q.capture_utc) for q in rows]
    if (max(clocks)-min(clocks)).total_seconds()>max_snapshot_skew_seconds:
        raise ValueError("LADDER_SNAPSHOT_SKEW")
    rungs=[]
    for line,rs in sorted(groups.items()):
        fair=consensus(rs,method=method,as_of=as_of,max_age_seconds=max_age_seconds)
        if fair.status!="OK":raise ValueError("RUNG_CONSENSUS_"+fair.status+":"+fair.reason)
        rungs.append({"line":line,"p_over":fair.fair[0],"p_under":fair.fair[1]})
    if any(b["p_over"]>a["p_over"] for a,b in zip(rungs,rungs[1:])):
        raise ValueError("NONMONOTONIC_LADDER")
    # Adjacent survival differences identify interval mass, not the within-
    # interval distribution. Open upper tail makes the mean non-identifiable.
    intervals=[{"min_count":0,"max_count":int(rungs[0]["line"]),"mass":1-rungs[0]["p_over"]}]
    for a,b in zip(rungs,rungs[1:]):
        intervals.append({"min_count":int(a["line"])+1,"max_count":int(b["line"]),"mass":a["p_over"]-b["p_over"]})
    intervals.append({"min_count":int(rungs[-1]["line"])+1,"max_count":None,"mass":rungs[-1]["p_over"]})
    median_min=next(x["min_count"] for i,x in enumerate(intervals) if sum(v["mass"] for v in intervals[:i+1])>=.5)
    median_max=next(x["max_count"] for i,x in enumerate(intervals) if sum(v["mass"] for v in intervals[:i+1])>=.5)
    return {"status":"PAPER_0U_LADDER_RESEARCH","method":method,"books":sorted(books),"rungs":rungs,
        "interval_masses":intervals,"lower_median_bounds":[median_min,median_max],
        "mean_lower_bound":sum(v["min_count"]*v["mass"] for v in intervals),"mean_estimate":None,
        "mean_upper_bound":None,"full_pmf_identified":False,"source_authentication":"NOT_VERIFIED_HERE",
        "assumption":"De-vigged half-line odds approximate survival conditional on decisive settlement; player availability and void rules not inferred.",
        "approved_stake_u":0}
