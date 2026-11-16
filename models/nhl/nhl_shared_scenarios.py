"""NHL shared team-shot -> goal -> goalie-save scenarios, RESEARCH ONLY.

Consumes the EXISTING NHL model's projected shots and goals (not sportsbook
quotes). Shots, scored goals and opposing goalie saves reconcile per period.
Overtime/shootouts and player shot allocation are NOT modeled: FULL GAME
settlement, FG goalie saves, skater props, DK DFS and ROI remain BLOCKED.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import random


class Blocked(ValueError):
    pass


def utc(s):
    try:
        x=datetime.fromisoformat(s.replace("Z","+00:00"))
        if x.tzinfo is None:
            raise ValueError("timezone missing")
        return x.astimezone(timezone.utc)
    except (ValueError, AttributeError) as e:
        raise Blocked("timezone-qualified timestamps required") from e


def poisson(rng, lam):
    if not math.isfinite(lam) or not 0 <= lam <= 100:
        raise Blocked("invalid shots-per-period rate")
    if lam==0:
        return 0
    cutoff=math.exp(-lam)
    n=0
    p=1.0
    while True:
        n+=1
        p*=rng.random()
        if p<=cutoff:
            return n-1


@dataclass(frozen=True)
class Params:
    game_id:str
    home:str
    away:str
    home_goalie:str
    away_goalie:str
    shots_home:float
    shots_away:float
    goals_home:float
    goals_away:float
    period_shares:tuple[float,float,float]
    pace_dispersion:float
    confirmed_home_goalie:bool
    confirmed_away_goalie:bool
    model_sha256:str
    input_sha256:str
    frozen_utc:str
    kickoff_utc:str

    def validate(self):
        if not self.game_id or not self.home or not self.away or self.home==self.away:
            raise Blocked("invalid matchup identity")
        if (not self.confirmed_home_goalie or not self.confirmed_away_goalie or
                not self.home_goalie or not self.away_goalie):
            raise Blocked("goalies not separately confirmed")
        for h in (self.model_sha256,self.input_sha256):
            if len(h)!=64 or any(c not in "0123456789abcdef" for c in h):
                raise Blocked("full original model/source SHA256 required")
        if utc(self.frozen_utc)>=utc(self.kickoff_utc):
            raise Blocked("model features frozen at/after kickoff")
        if (len(self.period_shares)!=3 or
            any(not math.isfinite(x) or x<=0 for x in self.period_shares) or
            abs(sum(self.period_shares)-1)>1e-8):
            raise Blocked("three explicitly registered period shares required")
        for shots,goals in ((self.shots_home,self.goals_home),(self.shots_away,self.goals_away)):
            if not math.isfinite(shots) or not math.isfinite(goals) or not 5<=shots<=70 or not 0<=goals<=shots:
                raise Blocked("shots/goals inconsistent or unrealistic")
        if not math.isfinite(self.pace_dispersion) or not 0<=self.pace_dispersion<=2:
            raise Blocked("pace dispersion not valid")


@dataclass(frozen=True)
class Period:
    shots_home:int
    shots_away:int
    goals_home:int
    goals_away:int
    saves_home_goalie:int
    saves_away_goalie:int

    def validate(self):
        if (min(self.__dict__.values())<0 or
                self.goals_home>self.shots_home or self.goals_away>self.shots_away):
            raise Blocked("negative/invalid shot or goal event")
        if (self.saves_home_goalie!=self.shots_away-self.goals_away or
                self.saves_away_goalie!=self.shots_home-self.goals_home):
            raise Blocked("goalie saves inconsistent with same game shots")


@dataclass(frozen=True)
class Scenario:
    periods:tuple[Period,Period,Period]

    def validate(self):
        if len(self.periods)!=3:
            raise Blocked("NHL requires three regulation periods")
        for p in self.periods:
            p.validate()

    def regulation(self):
        return (sum(p.goals_home for p in self.periods),
                sum(p.goals_away for p in self.periods))


def run(params:Params, n:int=20000, seed:int=7):
    params.validate()
    if type(n)!=int or not 2<=n<=50000:
        raise Blocked("invalid simulation count")
    rng=random.Random(seed)
    out=[]
    for _ in range(n):
        if params.pace_dispersion:
            v=params.pace_dispersion
            shared=rng.gammavariate(1/v,v)
        else:
            shared=1.0
        periods=[]
        for fraction in params.period_shares:
            sh=poisson(rng,params.shots_home*fraction*shared)
            sa=poisson(rng,params.shots_away*fraction*shared)
            gh=sum(rng.random()<params.goals_home/params.shots_home for i in range(sh))
            ga=sum(rng.random()<params.goals_away/params.shots_away for i in range(sa))
            periods.append(Period(sh,sa,gh,ga,sa-ga,sh-gh))
        s=Scenario(tuple(periods))
        s.validate()
        out.append(s)
    return out


def price_regulation(params:Params, scenarios):
    if not scenarios:
        raise Blocked("empty scenario batch")
    for s in scenarios:
        s.validate()
    n=len(scenarios)
    output={
        "status":"PAPER_NO_CALIBRATION",
        "source_model_sha256":params.model_sha256,
        "source_input_sha256":params.input_sha256,
        "simulations":n,
        "market_ev":"BLOCKED_NO_AUTHENTICATED_BOOK_PRICE",
        "contest_ev":"BLOCKED_NO_DFS_ROSTER_OWNERSHIP_PAYOUTS",
        "blocked":{
            "FG_ML":"NO_OT_SO_SHOT_SCENARIOS",
            "FG_TOTAL":"NO_OT_SO_SHOT_SCENARIOS",
            "FG_TEAM_TOTAL":"NO_OT_SO_SHOT_SCENARIOS",
            "FG_GOALIE_SAVES":"MISSING_OVERTIME_GOALIE_SHOTS",
            "SKATER_PROPS":"NO_PLAYER_SHOT_OR_GOAL_ALLOCATION",
            "DFS":"NO_PLAYER_STAT_SCENARIOS",
            "P1_ML2":"DRAW_SETTLEMENT_AND_OT_RULES_NOT_MODELED",
            "SGP":"NO_VALIDATED_JOINT_PRICE"
        }
    }
    first=[(s.periods[0].goals_home,s.periods[0].goals_away) for s in scenarios]
    reg=[s.regulation() for s in scenarios]
    for name,arr in (("P1",first),("REG",reg)):
        output[name]={
            "p_home_win":round(sum(h>a for h,a in arr)/n,5),
            "p_draw":round(sum(h==a for h,a in arr)/n,5),
            "p_away_win":round(sum(h<a for h,a in arr)/n,5),
            "mean_total":round(sum(h+a for h,a in arr)/n,5),
            "home_mean_goals":round(sum(h for h,a in arr)/n,5),
            "away_mean_goals":round(sum(a for h,a in arr)/n,5)
        }
    output["P1"]["mean_home_goalie_saves"]=round(sum(s.periods[0].saves_home_goalie for s in scenarios)/n,5)
    output["P1"]["mean_away_goalie_saves"]=round(sum(s.periods[0].saves_away_goalie for s in scenarios)/n,5)
    return output


def from_existing_projection(proj, game, *, sha_model, sha_input,
                             frozen_utc, kickoff_utc, period_shares, pace_dispersion):
    """Explicit bridge from sportsedge_nhl_model.project_game.

    period_shares and pace_dispersion MUST be provided from independently
    recorded/trained source evidence, not silently default to guessed values.
    """
    return Params(game_id=game["game_id"],home=game["home"],away=game["away"],
        home_goalie=game["home_goalie"],away_goalie=game["away_goalie"],
        shots_home=float(proj["shots_h"]),shots_away=float(proj["shots_a"]),
        goals_home=float(proj["lam_h"]),goals_away=float(proj["lam_a"]),
        period_shares=tuple(period_shares),pace_dispersion=float(pace_dispersion),
        confirmed_home_goalie=str(game.get("home_goalie_confirmed","0")).lower() in ("1","true"),
        confirmed_away_goalie=str(game.get("away_goalie_confirmed","0")).lower() in ("1","true"),
        model_sha256=sha_model,input_sha256=sha_input,
        frozen_utc=frozen_utc,kickoff_utc=kickoff_utc)
