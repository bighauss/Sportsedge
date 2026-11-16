"""CBB per-possession SAME-SIM first-half/regulation scoreboard — PAPER only.

Requires original source-frozen empirical scoring PMFs (0..6 pts per
possession), historical pace/half split, and a game mean from the existing
CBB model. No guessed possession probabilities or player points. NCAA OT,
official FG settlement, player props, first basket, DFS and SGP BLOCK until
their event/roster/odds requirements exist.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import random


class Blocked(ValueError):
    pass


def utc(v):
    try:
        d=datetime.fromisoformat(v.replace("Z","+00:00"))
        if d.tzinfo is None:
            raise ValueError("missing offset")
        return d.astimezone(timezone.utc)
    except (ValueError,AttributeError) as e:
        raise Blocked("UTC capture/tipoff timestamp required") from e


@dataclass(frozen=True)
class Params:
    game_id:str
    home:str
    away:str
    pace_mean:float
    pace_sd:float
    half1_share:float
    home_ppp:tuple[float,...]
    away_ppp:tuple[float,...]
    expected_home_pts:float
    expected_away_pts:float
    model_sha256:str
    source_sha256:str
    frozen_utc:str
    tipoff_utc:str

    def validate(self):
        if not self.game_id or not self.home or not self.away or self.home==self.away:
            raise Blocked("invalid CBB game identity")
        for h in (self.model_sha256,self.source_sha256):
            if len(h)!=64 or any(c not in "0123456789abcdef" for c in h):
                raise Blocked("model and PBP source SHA256 required")
        if utc(self.frozen_utc)>=utc(self.tipoff_utc):
            raise Blocked("source frozen at/after tipoff")
        if not (35<=self.pace_mean<=95 and 0<=self.pace_sd<=20 and
                .25<self.half1_share<.75):
            raise Blocked("missing/invalid historical pace or half split")
        for pmf,expected in ((self.home_ppp,self.expected_home_pts),
                             (self.away_ppp,self.expected_away_pts)):
            if (len(pmf)!=7 or
                any(not math.isfinite(x) or x<0 or x>1 for x in pmf) or
                abs(sum(pmf)-1)>1e-7):
                raise Blocked("empirical score-per-possession PMF 0..6 missing")
            if not math.isfinite(expected) or not 30<=expected<=140:
                raise Blocked("invalid expected team score")
            ppp=sum(i*v for i,v in enumerate(pmf))
            if abs(ppp*self.pace_mean-expected)>max(3.,.05*expected):
                raise Blocked("team projection disagrees with supplied scoring PMF")


@dataclass(frozen=True)
class Half:
    home_possessions:int
    away_possessions:int
    home_score:int
    away_score:int

    def validate(self):
        if min(self.__dict__.values())<0 or abs(self.home_possessions-self.away_possessions)>1:
            raise Blocked("impossible period possession/score")


@dataclass(frozen=True)
class Scenario:
    first:Half
    second:Half

    def validate(self):
        self.first.validate()
        self.second.validate()

    def regulation(self):
        return (self.first.home_score+self.second.home_score,
                self.first.away_score+self.second.away_score)


def scored_points(rng,pmf):
    u=rng.random()
    acc=0.0
    for n,p in enumerate(pmf):
        acc+=p
        if u<acc:
            return n
    return len(pmf)-1


def simulate(p:Params,n=20000,seed=7):
    p.validate()
    if type(n)!=int or not 2<=n<=50000:
        raise Blocked("bad simulation count")
    rng=random.Random(seed)
    scenarios=[]
    for _ in range(n):
        possessions=round(rng.gauss(p.pace_mean,p.pace_sd))
        possessions=max(35,min(95,possessions))
        first=round(possessions*p.half1_share)
        halves=[]
        for count in (first,possessions-first):
            # Team opportunities paired; no invented late-half asymmetry.
            h=sum(scored_points(rng,p.home_ppp) for _ in range(count))
            a=sum(scored_points(rng,p.away_ppp) for _ in range(count))
            halves.append(Half(count,count,h,a))
        g=Scenario(*halves)
        g.validate()
        scenarios.append(g)
    return scenarios


def research_summary(p,scenarios):
    if not scenarios:
        raise Blocked("no simulated outcomes")
    for g in scenarios:
        g.validate()
    n=len(scenarios)
    r={
        "status":"PAPER_NON_COUNTED_UNCALIBRATED",
        "source_model_sha256":p.model_sha256,
        "source_pbp_sha256":p.source_sha256,
        "simulations":n,
        "market_ev":"BLOCKED_NO_AUTHENTICATED_BOOK_PRICE_OR_PROSPECTIVE_CALIBRATION",
        "blocked":{
            "FG_ML":"OT_NOT_MODELED",
            "FG_SPREAD":"OT_NOT_MODELED",
            "FG_TOTAL":"OT_NOT_MODELED",
            "FG_TEAM_TOTAL":"OT_NOT_MODELED",
            "PLAYER_PROPS":"NO_PLAYER_STAT_EVENTS",
            "DFS":"NO_PLAYER_STAT_EVENTS_OR_DK_SALARIES",
            "FIRST_BASKET":"NO_ORDERED_PLAYER_SCORE_IDENTITY",
            "SGP":"NO_VALIDATED_JOINT_AND_ORIGINAL_BOOK_PRICE",
        },
    }
    for label,rows in (
        ("H1",[(g.first.home_score,g.first.away_score) for g in scenarios]),
        ("REGULATION",[g.regulation() for g in scenarios]),
    ):
        r[label]={
            "home_mean":round(sum(h for h,a in rows)/n,4),
            "away_mean":round(sum(a for h,a in rows)/n,4),
            "p_home_leads":round(sum(h>a for h,a in rows)/n,5),
            "p_tied":round(sum(h==a for h,a in rows)/n,5),
            "p_away_leads":round(sum(h<a for h,a in rows)/n,5),
            "mean_total":round(sum(h+a for h,a in rows)/n,4),
        }
    return r


def from_existing_projection(projected,game,*,home_outcome_pmf,
                             away_outcome_pmf,observed_pace_sd,
                             observed_first_half_share,model_sha256,
                             source_sha256,frozen_utc,tipoff_utc):
    """Bridge from existing CBB project_game output, no default distribution."""
    return Params(
        game_id=game["game_id"],home=game["home"],away=game["away"],
        pace_mean=float(projected["poss"]),
        pace_sd=float(observed_pace_sd),
        half1_share=float(observed_first_half_share),
        home_ppp=tuple(home_outcome_pmf),
        away_ppp=tuple(away_outcome_pmf),
        expected_home_pts=float(projected["home_pts"]),
        expected_away_pts=float(projected["away_pts"]),
        model_sha256=model_sha256,source_sha256=source_sha256,
        frozen_utc=frozen_utc,tipoff_utc=tipoff_utc)
