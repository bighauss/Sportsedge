"""Strict chronological score forecast residual audit (synthetic or real receipts).

Never refit on evaluation outcomes. Produces descriptive MAE/SD/Brier/log loss,
NOT a +EV authorization. Real audit requires independently authenticated,
pre-game model forecast + source publication receipts and actual final scores.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
import statistics

from .allmarkets_research import _hash,_time


@dataclass(frozen=True)
class FrozenGame:
    event_id: str
    sport: str
    start_at_utc: datetime
    features_asof_utc: datetime
    fitted_until_utc: datetime
    projection_home: float
    projection_away: float
    final_home: int
    final_away: int
    forecast_sha256: str

    def __post_init__(self):
        for t in (self.start_at_utc,self.features_asof_utc,self.fitted_until_utc):
            _time(t)
        _hash(self.forecast_sha256)
        if not self.event_id or not self.sport:
            raise ValueError("CHRONOLOGICAL_GAME_IDENTITY_MISSING")
        if not (self.features_asof_utc < self.start_at_utc and
                self.fitted_until_utc < self.features_asof_utc):
            raise ValueError("FUTURE_LEAK_OR_SAME_GAME_TRAINING")
        if any(not math.isfinite(x) or x<0 for x in
               (self.projection_home,self.projection_away)):
            raise ValueError("INVALID_PREDICTIVE_SCORE")
        if any(type(x)!=int or x<0 for x in (self.final_home,self.final_away)):
            raise ValueError("INVALID_FINAL_SCORE")


def _residuals(games:list[FrozenGame]) -> tuple[list[float],list[float]]:
    return (
        [(g.final_home-g.final_away)-(g.projection_home-g.projection_away) for g in games],
        [(g.final_home+g.final_away)-(g.projection_home+g.projection_away) for g in games],
    )


def walk_forward_score_audit(
    games:list[FrozenGame],
    *,
    minimum_training:int=50,
    holdout_per_fold:int=25,
    minimum_folds:int=3,
) -> dict:
    if not games or len(games)<minimum_training+holdout_per_fold*minimum_folds:
        return {"status":"INSUFFICIENT_CHRONOLOGICAL_OBSERVATIONS","official_counted":0,
                "approved_stake_u":0,"folds":[]}
    ordered=sorted(games,key=lambda g:(g.start_at_utc,g.event_id))
    if len({g.event_id for g in ordered})!=len(ordered) or len({g.sport for g in ordered})!=1:
        raise ValueError("DUPLICATE_EVENTS_OR_MIXED_SPORT")
    if minimum_training<30 or holdout_per_fold<10 or minimum_folds<3:
        raise ValueError("WEAK_OR_NONPREREGISTERED_FOLD_POLICY")
    folds=[]
    for offset in range(minimum_training,len(ordered),holdout_per_fold):
        eval_records=ordered[offset:offset+holdout_per_fold]
        if len(eval_records)<holdout_per_fold:break
        cutoff=eval_records[0].start_at_utc
        # Strict less-than cutoff prohibits any game sharing the first holdout start.
        training=[g for g in ordered[:offset] if g.start_at_utc<cutoff]
        if len(training)<minimum_training:
            continue
        if any(g.fitted_until_utc>=cutoff or g.features_asof_utc>=g.start_at_utc
               for g in training+eval_records):
            raise ValueError("FUTURE_LEAKAGE_DETECTED")
        margins,totals=_residuals(training)
        if statistics.pstdev(margins)==0 or statistics.pstdev(totals)==0:
            raise ValueError("DEGENERATE_TRAINING_RESIDUALS")
        sd_m=statistics.stdev(margins)
        sd_t=statistics.stdev(totals)
        errs_m,errs_t=_residuals(eval_records)
        mae_m=statistics.mean(abs(v) for v in errs_m)
        mae_t=statistics.mean(abs(v) for v in errs_t)
        logs=[];briers=[]
        for g in eval_records:
            margin=g.projection_home-g.projection_away
            prob=(1+math.erf(margin/(sd_m*math.sqrt(2))))/2
            outcome=1 if g.final_home>g.final_away else 0 if g.final_home<g.final_away else .5
            prob=min(max(prob,1e-10),1-1e-10)
            briers.append((prob-outcome)**2)
            if outcome in (0,1):
                logs.append(-(outcome*math.log(prob)+(1-outcome)*math.log(1-prob)))
        folds.append({
            "training_n":len(training),"holdout_n":len(eval_records),
            "training_ends_before_utc":cutoff.isoformat(),
            "evaluation_starts_utc":cutoff.isoformat(),
            "train_sd_margin":sd_m,"train_sd_total":sd_t,
            "holdout_mae_margin":mae_m,"holdout_mae_total":mae_t,
            "holdout_brier_ml":statistics.mean(briers),
            "holdout_logloss_ml":statistics.mean(logs) if logs else None,
            "train_data_source_hashes":len({g.forecast_sha256 for g in training}),
        })
    return {
        "status":"RESEARCH_HOLDOUT_REVIEW" if len(folds)>=minimum_folds else "INSUFFICIENT_CHRONOLOGICAL_FOLDS",
        "sport":ordered[0].sport,"folds":folds,
        "completed_folds":len(folds),
        "official_counted":0,"approved_stake_u":0,
        "reasons":[
            "NO_INDEPENDENT_SOURCE_ATTESTATION_FROM_THIS_MODULE",
            "SCORE_FORECAST_ERROR_IS_NOT_BETTING_EDGE",
            "NEED_AUTHENTICATED_DK_TAKE_AND_CLOSE_QUOTES",
            "NO_AUTOMATIC_HYPERPARAMETER_ADOPTION",
        ],
    }
