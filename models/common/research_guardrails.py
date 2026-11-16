"""Fail-closed research-to-card guards. No production model is modified.

NFL pace correction is disabled pending its own pre-registered forward win.
Combination markets require the *same identified simulation draws*; never add
independent marginal projections/distributions as though uncorrelated.
"""
import math
class Blocked(ValueError):pass

COMBOS={"PRA","RUSH_PLUS_RECEIVE","PASS_PLUS_RUSH","COMBO"}

def forbid_unvalidated_nfl_pace(*,sport,pace_adjustment):
    if str(sport).upper()=="NFL" and pace_adjustment:
        raise Blocked("NFL_PACE_ADJUSTMENT_DISABLED_UNTIL_PROSPECTIVE_VALIDATION")
    return True

def shared_joint_draws(by_stat):
    if not isinstance(by_stat,dict) or len(by_stat)<2:
        raise Blocked("COMBO_REQUIRES_MULTIPLE_SHARED_STAT_STREAMS")
    canonical=None;values=[]
    for stat,rows in sorted(by_stat.items()):
        if not isinstance(rows,(list,tuple)) or len(rows)<2:
            raise Blocked("COMBO_REQUIRES_FULL_SHARED_DRAWS")
        ids=[];number=[]
        for item in rows:
            if not isinstance(item,(list,tuple)) or len(item)!=2:
                raise Blocked("DRAW_ID_REQUIRED")
            drawid,x=item
            if not isinstance(drawid,(str,int)) or not str(drawid) or not isinstance(x,(int,float)) or not math.isfinite(x):
                raise Blocked("BAD_COMBO_DRAW")
            ids.append(str(drawid));number.append(float(x))
        if len(set(ids))!=len(ids):raise Blocked("REUSED_DRAW_ID")
        if canonical is None:canonical=ids
        elif ids!=canonical:raise Blocked("INDEPENDENT_OR_MISALIGNED_DRAW_STREAMS")
        values.append(number)
    # Alignment is asserted by IDs; provenance still requires external validation.
    return [{"draw_id":ident,"sum":sum(series[i] for series in values)}
            for i,ident in enumerate(canonical)]

def card_gate(record):
    """Never certify an official bet; show why a proposal remains 0u."""
    reasons=[]
    if str(record.get("sport","")).upper()=="NFL" and record.get("pace_adjustment"):
        reasons.append("UNVALIDATED_PACE")
    if str(record.get("market","")).split(":")[-1].upper() in COMBOS and not record.get("shared_draw_provenance"):
        reasons.append("COMBO_NOT_JOINTLY_SIMULATED")
    if not record.get("pregame_source_verified"):reasons.append("PREGAME_SOURCE_UNVERIFIED")
    def safe_number(v):
        return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) else None
    books=safe_number(record.get("independent_books"))
    forward=safe_number(record.get("historical_walkforward_n"))
    model=safe_number(record.get("model_nll"))
    baseline=safe_number(record.get("baseline_nll"))
    hit=safe_number(record.get("advertised_hit_rate"))
    roi=safe_number(record.get("advertised_roi"))
    if books is None or books<2:reasons.append("INDEPENDENT_FAIR_BASELINE_MISSING")
    if not record.get("original_close_saved"):reasons.append("CLOSING_PRICE_MISSING")
    if forward is None or forward<30:reasons.append("INSUFFICIENT_FORWARD_SAMPLE")
    if model is None or baseline is None or model>=baseline:
        reasons.append("MODEL_NOT_BETTER_THAN_BASELINE")
    if hit is None or roi is None:
        reasons.append("UNVERIFIED_MARKETING_METRICS")
    elif hit>.65 or roi>1:
        reasons.append("EXTRAORDINARY_PERFORMANCE_CLAIM_AUDIT")
    return {"status":"PAPER_0U","reasons":reasons or ["FINAL_INDEPENDENT_ADMISSION_NOT_IMPLEMENTED"],
            "official":False,"stake_u":0}

def assert_can_publish_as_official(record):
    raise Blocked("OFFICIAL_PUBLICATION_DISABLED_UNTIL_INDEPENDENT_REVIEW_AND_ADMISSION")
