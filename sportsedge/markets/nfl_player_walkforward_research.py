"""NFL player-stat historical reconstruction, with strict prior-week feature windows.

Research only. Reads separately original-SHA-checked nflverse weekly and NGS
raw release bytes, never bookmaker odds or live projected lines.

A Nov 15 release filtered to weeks <=9 is NOT a historically frozen Nov 9
snapshot. Prior-week *row* partition proves only no same/future-week feature
use IN THIS computation, not provider point-in-time availability.

No starter/inactive schedule or game-start data => predictions are conditional
on previously active players; missing current-week rows are counted as
ungraded, NEVER silently settled as 0. NGS comparison is a fixed unvalidated
candidate; adoption requires independent prospective PIT capture and holdouts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite, sqrt
from statistics import mean
from typing import Any
import json

from .source_ingestion import parse_snapshot_bytes
from .ngs_public_research_smoke import (
    NGS_ASSETS, CORE_STATS, NFL_TEAMS, EXACT_NGS_ALIASES,
    audit_ngs_weekly_rows,
)

# source weekly stat | opportunity volume stat | minimum *historical* average
# The historical role gate is NOT a confirmed active/start status.
STATS = {
    "PASS_YDS": ("passing_yards", "attempts", 10.0, "NFL_NGS_PASS", "pass_yards"),
    "PASS_ATT": ("attempts", "attempts", 10.0, "NFL_NGS_PASS", "attempts"),
    "RUSH_YDS": ("rushing_yards", "carries", 10.0, "NFL_NGS_RUSH", "rush_yards"),
    "RUSH_ATT": ("carries", "carries", 10.0, "NFL_NGS_RUSH", "rush_attempts"),
    "REC_YDS": ("receiving_yards", "targets", 4.0, "NFL_NGS_RECEIVE", "yards"),
    "RECEPTIONS": ("receptions", "targets", 4.0, "NFL_NGS_RECEIVE", "receptions"),
    "TARGETS": ("targets", "targets", 4.0, "NFL_NGS_RECEIVE", "targets"),
}

COUNT_STATS = frozenset({"PASS_ATT", "RUSH_ATT", "RECEPTIONS", "TARGETS"})
YARD_STATS = frozenset({"PASS_YDS", "RUSH_YDS", "REC_YDS"})
ZERO_STATS = frozenset({"attempts", "carries", "targets", "receptions"})
RELEASE_SOURCES = {
    "weekly": "NFLVERSE_WEEKLY",
    "NFL_NGS_PASS": "NFLVERSE_NGS",
    "NFL_NGS_RUSH": "NFLVERSE_NGS",
    "NFL_NGS_RECEIVE": "NFLVERSE_NGS",
}


def numeric(value: Any, *, allow_negative: bool=False) -> float | None:
    """Missing stays missing; NaN/inf/malformed never become zero."""
    if value is None or isinstance(value, bool):
        return None
    s=str(value).strip()
    if s in ("", "NA", "NaN", "nan", "null", "None"):
        return None
    try:
        n=float(s)
    except (TypeError, ValueError):
        return None
    if not isfinite(n) or (n<0 and not allow_negative):
        return None
    return n


def canonical_team(value: str) -> str:
    if not isinstance(value,str):
        raise ValueError("WEEKLY_TEAM_ID_MISSING")
    t=EXACT_NGS_ALIASES.get(value.strip().upper(),
                           value.strip().upper())
    if t not in NFL_TEAMS:
        raise ValueError("WEEKLY_UNKNOWN_TEAM:"+t)
    return t


def parse_source_archive(raw: bytes, *, source_id: str, expected_sha256: str,
                         observed_at_utc: datetime,
                         captured_at_utc: datetime) -> tuple[tuple[dict,...],str]:
    if not isinstance(expected_sha256,str) or not expected_sha256.startswith("sha256:"):
        raise ValueError("PROVIDER_ORIGINAL_DIGEST_REQUIRED")
    digest="sha256:"+sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("SOURCE_ORIGINAL_SHA256_MISMATCH")
    receipt,rows=parse_snapshot_bytes(
        source_id,raw,observed_at_utc,captured_at_utc)
    return tuple(rows),receipt.sha256_raw


def _weighted_3(values: list[float]) -> float:
    v=values[-3:]
    if len(v)!=3:
        raise ValueError("AT_LEAST_THREE_PAST_OBSERVATIONS_REQUIRED")
    return 0.2*v[0]+0.3*v[1]+0.5*v[2]


def _observations_weekly(rows: tuple[dict,...],season:int,through_week:int):
    data:dict[tuple[str,str,int],dict]={}
    excluded_after=0
    unbound=0
    for r in rows:
        if r.get("season")!=str(season) or r.get("season_type")!="REG":
            continue
        try:
            week=int(r["week"])
        except (TypeError,ValueError) as exc:
            raise ValueError("WEEKLY_WEEK_INVALID") from exc
        if week<1:
            # Explicitly exclude season aggregate or invalid week-0.
            if week!=0:
                raise ValueError("WEEKLY_NEGATIVE_WEEK")
            continue
        if week>through_week:
            excluded_after+=1
            continue
        t=canonical_team(r.get("team") or r.get("recent_team"))
        player=(r.get("player_id") or "").strip()
        if not player:
            # A missing stable ID cannot be imputed from name or jersey.
            if (numeric(r.get("rushing_tds")) or 0)+(numeric(r.get("receiving_tds")) or 0)>0:
                raise ValueError("UNATTRIBUTED_OFFENSIVE_TD_MISSING_GSIS_ID")
            unbound+=1
            continue
        k=(player,t,week)
        if k in data:
            raise ValueError("WEEKLY_DUPLICATE_PLAYER_TEAM_WEEK")
        data[k]=r
    return data,excluded_after,unbound


def _observations_ngs(asset:str, rows:tuple[dict,...], season:int, through_week:int):
    stats=CORE_STATS[asset]
    required={"season","season_type","week","player_gsis_id","team_abbr"}
    required.update(stats)
    if not rows or not required.issubset(rows[0].keys()):
        raise ValueError("NGS_REQUIRED_SOURCE_COLUMNS_MISSING")
    # Provider-specific record and 32-team checks already exist; reuse them.
    census=audit_ngs_weekly_rows(asset,tuple(rows[0].keys()),list(rows),
                                 season=season,through_week=through_week)
    idx={}
    for r in rows:
        if r.get("season")!=str(season) or r.get("season_type")!="REG":
            continue
        week=int(r["week"])
        if not 1<=week<=through_week:
            continue
        team=canonical_team(r["team_abbr"])
        player=(r.get("player_gsis_id") or "").strip()
        key=(player,team,week)
        if key in idx:
            raise ValueError("NGS_DUPLICATE_PLAYER_TEAM_WEEK")
        idx[key]=r
    return idx,census


def _ngs_candidate(prior_ngs:list[dict],stat:str, prior_volume:float) -> float|None:
    _,_,_,asset,ngs_field=STATS[stat]
    if len(prior_ngs)<2:
        return None
    latest=prior_ngs[-3:]
    values=[numeric(row.get(ngs_field),
                    allow_negative=(stat in YARD_STATS)) for row in latest]
    if any(v is None for v in values):
        return None
    if stat in COUNT_STATS:
        return max(0.0,mean(values))
    # Price-free lagged efficiency × independently predicted historical volume.
    volume_field={"PASS_YDS":"attempts","RUSH_YDS":"rush_attempts",
                  "REC_YDS":"targets"}[stat]
    volumes=[numeric(r.get(volume_field)) for r in latest]
    if any(v is None for v in volumes) or sum(volumes)<=0:
        return None
    efficiency=sum(values)/sum(volumes)
    return max(0.0,prior_volume*efficiency)


@dataclass(frozen=True)
class ResearchForecast:
    player_id: str
    team_id: str
    eval_week: int
    stat: str
    last_training_week: int
    baseline_mean: float
    ngs_candidate_mean: float|None
    observed_actual: float|None
    model_uncertainty_sd_unfitted: float
    candidate_has_verified_active_status: bool=False
    def __post_init__(self):
        if self.last_training_week>=self.eval_week:
            raise ValueError("LOOKAHEAD_LAST_TRAINING_WEEK")
        if self.baseline_mean<0 or not isfinite(self.baseline_mean):
            raise ValueError("INVALID_BASELINE_MEAN")
        if self.model_uncertainty_sd_unfitted<=0:
            raise ValueError("INVALID_UNCALIBRATED_PLAYER_WIDTH")
        if self.candidate_has_verified_active_status:
            raise ValueError("STARTER_STATUS_CANNOT_BE_INFERRED_FROM_GAME_LOGS")


def _metrics(errs:list[float])->dict|None:
    if not errs:
        return None
    return {"n":len(errs),"mae":round(mean(abs(e) for e in errs),4),
            "rmse":round(sqrt(mean(e*e for e in errs)),4),
            "signed_bias_actual_minus_pred":round(mean(errs),4)}


def historical_player_walkforward(
    weekly_rows:tuple[dict,...],
    ngs_rows:dict[str,tuple[dict,...]],
    *,
    season:int=2026,
    first_test_week:int=5,
    through_week:int=9,
    min_prior_games:int=3,
) -> dict:
    if type(season)!=int or type(through_week)!=int or not 4<=first_test_week<=through_week<=18:
        raise ValueError("INVALID_RESEARCH_WEEK_RANGE")
    if type(min_prior_games)!=int or min_prior_games<3 or min_prior_games>6:
        raise ValueError("UNSAFE_PRIOR_GAMES_POLICY")
    if set(ngs_rows)!=set(NGS_ASSETS):
        raise ValueError("THREE_NGS_SOURCE_ASSETS_REQUIRED")
    weekly,excluded_after,excluded_unbound=_observations_weekly(
        weekly_rows,season,through_week)
    ngs={};ngs_census={}
    for asset in NGS_ASSETS:
        ngs[asset],ngs_census[asset]=_observations_ngs(
            asset,ngs_rows[asset],season,through_week)
    players:dict[tuple[str,str],list[tuple[int,dict]]]={}
    for (pid,team,w),r in weekly.items():
        players.setdefault((pid,team),[]).append((w,r))
    for k in players:players[k].sort(key=lambda x:x[0])
    forecasts:list[ResearchForecast]=[]
    counts={"conditional_roster_candidates":0,"not_observed_in_holdout":0,
            "missing_actual_stat":0,"graded":0,
            "paired_ngs_grades":0}
    folds=[]
    for week in range(first_test_week,through_week+1):
        baseline_errors={stat:[] for stat in STATS}
        paired_base={stat:[] for stat in STATS}
        paired_ngs={stat:[] for stat in STATS}
        present=0;absent=0;total=0
        for (pid,team),history in players.items():
            prior=[(w,row) for w,row in history if w<week]
            if len(prior)<min_prior_games or week-prior[-1][0]>2:
                continue
            actual_row=weekly.get((pid,team,week))
            for stat,(field,vol_field,minimum,asset,ngs_field) in STATS.items():
                valid_prior=[]
                for w,row in prior:
                    value=numeric(row.get(field),
                                  allow_negative=stat in YARD_STATS)
                    volume=numeric(row.get(vol_field))
                    if value is not None and volume is not None and volume>0:
                        valid_prior.append((w,value,volume))
                if len(valid_prior)<min_prior_games:
                    continue
                recent=valid_prior[-3:]
                vol_pred=_weighted_3([v for _,_,v in recent])
                if vol_pred<minimum:
                    continue
                baseline=max(0.0,_weighted_3([v for _,v,_ in recent]))
                nindex=ngs[asset]
                # Align NGS only to prior observed weeks for SAME player/team.
                hist_ngs=[nindex[(pid,team,w)] for w,_,_ in recent
                          if (pid,team,w) in nindex]
                ngs_value=_ngs_candidate(hist_ngs,stat,vol_pred)
                candidate=(.65*baseline+.35*ngs_value
                           if ngs_value is not None else None)
                observed=(numeric(actual_row.get(field),
                          allow_negative=stat in YARD_STATS)
                          if actual_row is not None else None)
                # Descriptive within-player SD from training only. Never treated
                # as a fitted/validated next-game conditional prop distribution.
                mu=mean(v for _,v,_ in recent)
                width=sqrt(sum((v-mu)**2 for _,v,_ in recent)/2)
                width=max(1.0,width)
                rec=ResearchForecast(pid,team,week,stat,recent[-1][0],
                     round(baseline,4),
                     round(candidate,4) if candidate is not None else None,
                     observed,round(width,4))
                forecasts.append(rec);total+=1
                counts["conditional_roster_candidates"]+=1
                if observed is None:
                    counts["not_observed_in_holdout"]+=1;absent+=1
                    continue
                counts["graded"]+=1;present+=1
                e=observed-baseline
                baseline_errors[stat].append(e)
                if candidate is not None:
                    paired_base[stat].append(e)
                    paired_ngs[stat].append(observed-candidate)
                    counts["paired_ngs_grades"]+=1
        folds.append({
            "holdout_week":week,"training_cutoff_exclusive_week":week,
            "candidates":total,"matched_observed_player_stats":present,
            "ungraded_absent_or_missing_stat":absent,
            "stats":{
                stat:{"baseline":_metrics(baseline_errors[stat]),
                      "paired_baseline":_metrics(paired_base[stat]),
                      "paired_ngs":_metrics(paired_ngs[stat]),
                      "paired_delta_mae_ngs_minus_baseline":(
                        round(mean(abs(v) for v in paired_ngs[stat])-
                              mean(abs(v) for v in paired_base[stat]),4)
                        if paired_base[stat] else None)}
                for stat in STATS},
        })
    if not folds:
        raise ValueError("NO_CHRONOLOGICAL_FOLDS")
    totals={}
    for stat in STATS:
        base=[];paired_b=[];paired_n=[]
        for f in forecasts:
            if f.stat!=stat or f.observed_actual is None:
                continue
            base.append(f.observed_actual-f.baseline_mean)
            if f.ngs_candidate_mean is not None:
                paired_b.append(f.observed_actual-f.baseline_mean)
                paired_n.append(f.observed_actual-f.ngs_candidate_mean)
        totals[stat]={
            "baseline":_metrics(base),
            "paired_baseline":_metrics(paired_b),
            "paired_ngs":_metrics(paired_n),
            "paired_delta_mae_ngs_minus_baseline":(
                round(mean(abs(v) for v in paired_n)-
                      mean(abs(v) for v in paired_b),4)
                if paired_b else None),
        }
    return {
        "status":"RETROSPECTIVE_PUBLIC_RELEASE_RECONSTRUCTION_RESEARCH_ONLY",
        "season":season,"first_test_week":first_test_week,
        "last_test_week":through_week,
        "model":"LAG3_EWMA_0.2_0.3_0.5",
        "ngs_candidate":"0.65_X_LAG3_BASELINE_0.35_X_PRIOR_NGS_EFFICIENCY",
        "baseline_and_ngs_pair_on_same_actual_player_weeks":True,
        "trained_only_on_strictly_lower_week_numbers":True,
        "historical_publisher_snapshots_at_original_decision":False,
        "confirmed_lineups_or_rosters_available":False,
        "missing_player_actuals_not_assumed_zero":True,
        "bookmaker_derived_model_features":False,
        "post_cutoff_weekly_rows_excluded":excluded_after,
        "unbound_non_scoring_weekly_rows_excluded":excluded_unbound,
        "counts":counts,
        "ngs_census":ngs_census,
        "folds":folds,
        "totals":totals,
        "no_automatic_model_adoption":True,
        "no_stake_or_issued_player_forecasts":True,
        "official_counted":0,"approved_stake_u":0,"card":None,
        "reasons":[
            "CURRENT_PUBLISHER_RELEASE_IS_NOT_HISTORIC_PREGAME_PIT_SNAPSHOT",
            "ACTIVITY_SELECTION_BIAS_AND_UNVERIFIED_GAME_STARTER_STATUS",
            "HISTORICAL_VARIANCE_NOT_PROSPECTIVELY_CALIBRATED",
            "NO_INDEPENDENT_BOOKMAKER_QUOTES_OR_MATCHED_CLOSING_LINES",
            "NO_AUTOMATIC_BETTING_EDGE_OR_PROP_PROMOTION",
        ],
    }
