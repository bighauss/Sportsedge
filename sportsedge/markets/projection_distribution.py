"""Projection-to-joint-score simulator with explicit, unvalidated dispersion.

No fitted widths/period shares are silently assumed. This is a research-only
scenario generator, not a calibrated scoring model or SGP correlation engine.
Player-stat moments must be sourced independently, never reverse-engineered
from DK odds. TD events are NEVER manufactured from historical TD shares.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import random

from .allmarkets_research import Outcome, SimulationBatch, STAT_NAMES, _hash, _time
from .projection_bridge import TeamProjection


GENERATOR_VERSION = "SPORTSEDGE_GAUSSIAN_RESEARCH_GENERATOR_R1"


def scenario_spec_digest(projection: TeamProjection, dispersion: "DistributionInput",
                         roster_ids: frozenset[str],
                         player_moments: tuple["PlayerMoment",...],
                         count: int, seed: int) -> str:
    """Full input/code fingerprint, NOT a statement of predictive calibration.

    Preserve supplied player-moment order because RNG advances in that order.
    Exclude wall-clock execution timestamp: identical frozen specs with the
    same seed/count should yield the same fingerprint and simulated outcomes.
    """
    def moment_map(value):
        return {name: (item.isoformat() if isinstance(item, datetime) else item)
                for name, item in vars(value).items()}

    definition = {
        "generator_version": GENERATOR_VERSION,
        "generator_file_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "projection": moment_map(projection),
        "dispersion": moment_map(dispersion),
        "roster_ids": sorted(roster_ids),
        "player_moments_in_draw_order": [moment_map(x) for x in player_moments],
        "scenario_count": count, "seed": seed,
    }
    raw = json.dumps(definition, sort_keys=True, separators=(",",":"),
                     allow_nan=False).encode("utf-8")
    return "sha256:"+sha256(raw).hexdigest()


@dataclass(frozen=True)
class DistributionInput:
    sport: str
    sd_margin: float
    sd_total: float
    period_shares: tuple[float, ...]
    model_sha256: str
    training_end_utc: datetime
    status: str = "UNCALIBRATED_RESEARCH"
    # Optional empirical period-share data/code fingerprint. The separate
    # score-width fit/model identity remains in model_sha256.
    period_fit_model_sha256: str | None = None
    # Zero exactly preserves the old research Gaussian sampling path.
    # Nonzero is accepted only via an independently frozen fit ledger in
    # RUN IT; it is NOT calibrated tail dependence or a validated SGP copula.
    margin_total_correlation: float = 0.0

    def __post_init__(self):
        _hash(self.model_sha256)
        if self.period_fit_model_sha256 is not None:
            _hash(self.period_fit_model_sha256)
        _time(self.training_end_utc)
        if self.status != "UNCALIBRATED_RESEARCH":
            raise ValueError("CALIBRATION_STATUS_UNSUPPORTED")
        if not (0.1<=self.sd_margin<=150 and 0.1<=self.sd_total<=150):
            raise ValueError("DISPERSION_WIDTH_OUT_OF_BOUNDS")
        if (type(self.margin_total_correlation) not in (int, float)
                or not math.isfinite(self.margin_total_correlation)
                or abs(self.margin_total_correlation) >= .999):
            raise ValueError("MARGIN_TOTAL_CORRELATION_INVALID")
        expected_lengths=((9,) if self.sport=="MLB" else
                          (2,4) if self.sport=="CBB" else (4,))
        if len(self.period_shares) not in expected_lengths:
            raise ValueError("PERIOD_SPLITS_MISSING")
        if any(not math.isfinite(x) or not 0<x<1 for x in self.period_shares):
            raise ValueError("INVALID_PERIOD_SHARES")
        if abs(sum(self.period_shares)-1)>1e-8:
            raise ValueError("PERIOD_SHARES_MUST_SUM_TO_1")


@dataclass(frozen=True)
class PlayerMoment:
    player_id: str
    team_id: str
    stat: str
    projected_mean: float
    standard_deviation: float
    raw_features_sha256: str
    trained_until_utc: datetime
    projection_asof_utc: datetime
    confirmed_active: bool
    projected_targets: float | None = None
    projected_rush_attempts: float | None = None
    projected_minutes: float | None = None
    confirmed_pitcher: bool = False
    confirmed_batting_lineup: bool = False

    def validate(self,sport:str,freeze:datetime)->None:
        if not self.player_id or not self.team_id or self.stat not in STAT_NAMES[sport]:
            raise ValueError("UNSUPPORTED_PLAYER_STAT_OR_ID")
        _hash(self.raw_features_sha256)
        if _time(self.projection_asof_utc)>freeze or _time(self.trained_until_utc)>=freeze:
            raise ValueError("PLAYER_MOMENT_USES_FUTURE_DATA")
        if not (math.isfinite(self.projected_mean) and math.isfinite(self.standard_deviation)
                and self.projected_mean>=0 and self.standard_deviation>0):
            raise ValueError("INVALID_PLAYER_MOMENTS")
        if not self.confirmed_active:
            raise ValueError("PLAYER_NOT_CONFIRMED_ACTIVE")
        if sport in ("NFL","CFB"):
            if self.stat in ("REC_YDS","RECEPTIONS","TARGETS","LONGEST_RECEPTION") and (
                self.projected_targets is None or self.projected_targets<4):
                raise ValueError("RECEIVING_PROP_TARGET_VOLUME_BELOW_FLOOR")
            if self.stat in ("RUSH_YDS","RUSH_ATT") and (
                self.projected_rush_attempts is None or self.projected_rush_attempts<10):
                raise ValueError("RUSHING_PROP_ATTEMPT_VOLUME_BELOW_FLOOR")
        if sport=="NBA" and (self.projected_minutes is None or self.projected_minutes<20):
            raise ValueError("NBA_PROP_MINUTES_BELOW_FLOOR")
        if sport=="MLB":
            if self.stat in ("PITCHER_K","PITCHER_OUTS") and not self.confirmed_pitcher:
                raise ValueError("STARTING_PITCHER_NOT_CONFIRMED")
            if self.stat not in ("PITCHER_K","PITCHER_OUTS") and not self.confirmed_batting_lineup:
                raise ValueError("BATTING_LINEUP_NOT_CONFIRMED")


def split_int(rng:random.Random,total:int,weights:tuple[float,...])->tuple[int,...]:
    """A score-preserving multinomial split (noncalibrated time profile)."""
    if total<0:
        raise ValueError("NEGATIVE_SCORE")
    out=[0]*len(weights)
    for _ in range(total):
        u=rng.random()
        accum=0.0
        for i,w in enumerate(weights):
            accum+=w
            if u<accum or i==len(weights)-1:
                out[i]+=1
                break
    return tuple(out)


def generate_score_scenarios(
    projection: TeamProjection,
    dispersion: DistributionInput,
    *,
    roster_ids: frozenset[str] = frozenset(),
    player_moments: tuple[PlayerMoment,...]=(),
    count: int=2000,
    seed: int=10,
    generated_at_utc: datetime,
) -> SimulationBatch:
    """Build coherent SCORE/PLAYER-STAT examples; NOT validated SGP/TD events.

    Marginal player distributions are Gaussian sketches with NO validated joint
    team/player covariance. Even 100k simulations would not prove calibration.
    """
    if type(count)!=int or not 1000<=count<=100_000:
        raise ValueError("SCENARIO_SAMPLE_SIZE_OUT_OF_BOUNDS")
    if type(seed)!=int:
        raise ValueError("SEED_MUST_BE_INT")
    if projection.sport!=dispersion.sport:
        raise ValueError("SPORT_DISTRIBUTION_MISMATCH")
    if dispersion.training_end_utc>=projection.asof_utc:
        raise ValueError("DISPERSION_FIT_NOT_CHRONOLOGICAL")
    if generated_at_utc<projection.asof_utc:
        raise ValueError("SCENARIOS_BEFORE_FEATURE_FREEZE")
    for p in player_moments:
        p.validate(projection.sport,projection.asof_utc)
        if p.player_id not in roster_ids or p.team_id not in (projection.home_id,projection.away_id):
            raise ValueError("PLAYER_NOT_ON_FROZEN_EVENT_ROSTER")
    if len({(p.player_id,p.stat) for p in player_moments})!=len(player_moments):
        raise ValueError("DUPLICATE_PLAYER_STAT_MOMENT")
    spec_digest=scenario_spec_digest(
        projection,dispersion,roster_ids,player_moments,count,seed)
    rng=random.Random(seed)
    # The nonzero fitted branch samples the same TOTAL latent Gaussian and
    # a correlated MARGIN latent Gaussian, not independent uncertainty.
    # Use the UNCLIPPED total draw for z1, to avoid introducing artificial
    # dependence when scores are clamped at zero.
    rho=dispersion.margin_total_correlation
    retained=math.sqrt(1-rho*rho)
    outcomes=[]
    for _ in range(count):
        # Only independently fitted dispersion could make these win chances reliable.
        expected_total=projection.expected_home+projection.expected_away
        expected_margin=projection.expected_home-projection.expected_away
        total_latent=rng.gauss(expected_total,dispersion.sd_total)
        total=max(0,round(total_latent))
        if rho == 0:
            # Exact legacy draw path: avoids an accidental probability
            # regression for all unchanged, uncalibrated research studies.
            margin=rng.gauss(expected_margin,dispersion.sd_margin)
        else:
            total_z=(total_latent-expected_total)/dispersion.sd_total
            independent_z=rng.gauss(0.0,1.0)
            margin=expected_margin+dispersion.sd_margin*(
                rho*total_z+retained*independent_z)
        home=max(0,min(total,round((total+margin)/2)))
        away=total-home
        h_parts=split_int(rng,home,dispersion.period_shares)
        a_parts=split_int(rng,away,dispersion.period_shares)
        prefix=("I" if projection.sport=="MLB" else
                "H" if projection.sport=="CBB" and len(h_parts)==2 else "Q")
        keys=[prefix+str(i+1) for i in range(len(h_parts))]
        periods={k:(h,a) for k,h,a in zip(keys,h_parts,a_parts)}
        props={}
        for mom in player_moments:
            draw=round(rng.gauss(mom.projected_mean,mom.standard_deviation))
            props.setdefault(mom.player_id,{})[mom.stat]=max(0,draw)
        outcomes.append(Outcome(periods=periods,player_stats=props,
                                events=(),events_complete=False))
    return SimulationBatch(
        projection.sport,projection.event_id,projection.home_id,projection.away_id,
        roster_ids,projection.model_sha256,projection.feature_sha256,
        projection.asof_utc,generated_at_utc,tuple(outcomes),
        calibration_status="UNVERIFIED",
        scenario_spec_sha256=spec_digest,
        scenario_generator_version=GENERATOR_VERSION)


def generator_limitations() -> tuple[str,...]:
    return (
        "UNTESTED_TEAM_SCORE_VARIANCE_UNTIL_WALK_FORWARD_FIT",
        "PERIOD_SHARE_SIMULATION_NOT_FIRST_HALF_CALIBRATION",
        "PLAYER_MOMENTS_INDEPENDENT_NOT_JOINTLY_CORRELATED",
        "NO_TOUCHDOWN_SCORING_EVENT_SIMULATION_FROM_HISTORICAL_SHARES",
        "NO_POSTED_SGP_PRICE_OR_CORRELATION_VALIDATION",
        "NO_RECORDED_AUTHENTICATED_LIVE_BOOK_QUOTES",
        "NO_OFFICIAL_CARD_OR_STAKE_AUTHORIZED",
    )
