"""Market-implied count survival ladder, research only.

Uses existing two-sided consensus; does not identify a full PMF, a point mean,
or authenticated source clocks. Half-integer lines only, nonnegative counts.
"""
from collections import defaultdict
from math import fsum
from .devig import book_key, consensus, utc


def _external_rows(quotes):
    return [q for q in quotes if book_key(q.book)!="draftkings" and q.copies is None]

def infer_count_ladder(quotes, *, as_of, max_age_seconds, max_snapshot_skew_seconds=60, method="power"):
    if type(max_snapshot_skew_seconds) is not int or max_snapshot_skew_seconds<0:
        raise ValueError("INVALID_SNAPSHOT_SKEW")
    # Never allow a DK alias or a declared copied book to enter the ladder.
    rows=_external_rows(quotes)
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


# Narrow research contract: integer-valued is not enough (yards can be negative).
# Providers must map their own identifiers and settlement terms upstream.
_COUNT_MARKETS = {
    "NBA": {"prop_points", "prop_rebounds", "prop_assists"},
    "CBB": {"prop_points", "prop_rebounds", "prop_assists"},
    "NFL": {"prop_receptions"}, "CFB": {"prop_receptions"},
    "MLB": {"prop_hits", "prop_total_bases", "prop_pitcher_strikeouts"},
    "NHL": {"prop_shots_on_goal", "prop_goals", "prop_assists"},
    "PGA": {"prop_birdies"},
}


def integer_count_bounds(quotes, line, *, as_of, max_age_seconds,
                         max_snapshot_skew_seconds=60, method="power"):
    """Sharp marginal over/push/under bounds conditional on non-void settlement.

    Each interval may put its mass at any integer in its support. An outcome
    gets all the mass in its lower bound iff forced, and in its upper bound iff
    possible. Endpoints of different marginals need not be jointly attainable.
    This is identification uncertainty, not a sampling confidence interval.
    """
    if type(line) is not int or line < 0:
        raise ValueError("NONNEGATIVE_INTEGER_TARGET_REQUIRED")
    rows = _external_rows(quotes)
    ladder = infer_count_ladder(rows, as_of=as_of, max_age_seconds=max_age_seconds,
                                max_snapshot_skew_seconds=max_snapshot_skew_seconds, method=method)
    first = rows[0]
    if first.market not in _COUNT_MARKETS.get(first.sport, ()):
        raise ValueError("UNSUPPORTED_NONNEGATIVE_COUNT_MARKET")
    weights = {}
    for q in rows:
        book, weight = book_key(q.book), float(q.weight)
        if weights.setdefault(book, weight) != weight:
            raise ValueError("CHANGING_BOOK_WEIGHT")
    masses = {"over": ([], []), "push": ([], []), "under": ([], [])}
    for interval in ladder["interval_masses"]:
        lo, hi, mass = interval["min_count"], interval["max_count"], interval["mass"]
        possible = {"under": lo < line, "push": lo <= line and (hi is None or line <= hi),
                    "over": hi is None or hi > line}
        forced = sum(possible.values()) == 1
        for outcome, allowed in possible.items():
            if allowed:
                masses[outcome][1].append(mass)
                if forced:
                    masses[outcome][0].append(mass)
    return {"status": "PAPER_0U_INTEGER_BOUNDS", "line": line,
            "contract": {k: getattr(first, k) for k in
                         ("sport", "event_id", "player_id", "market", "period", "rules")},
            "start_utc": utc(first.start_utc).isoformat(), "as_of": utc(as_of).isoformat(),
            "books": ladder["books"], "method": method,
            "bounds": {k: [fsum(lower), fsum(upper)] for k, (lower, upper) in masses.items()},
            "semantics": "SHARP_MARGINAL_BOUNDS_CONDITIONAL_ON_NONVOID",
            "source_authentication": ladder["source_authentication"], "approved_stake_u": 0}
