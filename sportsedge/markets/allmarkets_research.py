"""SportsEdge five-sport all-market *research* scenario pricer, 2026-11-15.

Strictly isolated from frozen v5 and from approved wagers. All scenarios must
be externally generated from independent model projections at a frozen PIT
cutoff; this module NEVER treats sportsbook odds as projection features.

Supported research markets: ML, SPREAD, TOTAL, TEAM_TOTAL, PLAYER_PROP,
ATTD, FIRST_TD, TD_2PLUS, FIRST_BASKET, NRFI, YRFI, SGP (joint evaluation).
Sports: NFL, CFB, CBB, NBA, MLB. Unsupported inputs BLOCK rather than invent.
Every result has card=None, official_counted=0, approved_stake_u=0.

Independent price comparison is only meaningful if BOTH sides' source receipts
and exact canonical market identity match; source identity remains unverified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
import re
from typing import Any

SPORTS = frozenset({"NFL", "CFB", "CBB", "NBA", "MLB"})
BASKETBALL = frozenset({"CBB", "NBA"})
FOOTBALL = frozenset({"NFL", "CFB"})
KINDS = frozenset({"ML", "SPREAD", "TOTAL", "TEAM_TOTAL", "PLAYER_PROP",
                   "ATTD", "FIRST_TD", "TD_2PLUS", "FIRST_BASKET", "NRFI", "YRFI"})
SIDES = frozenset({"HOME", "AWAY", "OVER", "UNDER", "YES", "NO"})
PERIODS = frozenset({"FG", "1H", "2H", "1Q", "2Q", "3Q", "4Q", "F5", "1IN"})
SHA = re.compile(r"^sha256:[a-f0-9]{64}$")
PERIOD_ORDER = {"1Q": ("Q1",), "2Q": ("Q2",), "3Q": ("Q3",),
                "4Q": ("Q4",), "1H": ("Q1", "Q2"), "2H": ("Q3", "Q4"),
                "F5": ("I1", "I2", "I3", "I4", "I5"), "1IN": ("I1",)}
FOOTBALL_STATS = frozenset({"PASS_YDS","PASS_ATT","COMPLETIONS","RUSH_YDS",
    "RUSH_ATT","REC_YDS","RECEPTIONS","TARGETS","PASS_TDS","INTERCEPTIONS",
    "LONGEST_RECEPTION","REC_TDS","RUSH_TDS"})
BASKETBALL_STATS = frozenset({"POINTS","REBOUNDS","ASSISTS","3PM","PRA",
    "STEALS","BLOCKS","TURNOVERS","DOUBLE_DOUBLE","TRIPLE_DOUBLE"})
BASEBALL_STATS = frozenset({"PITCHER_K","PITCHER_OUTS","HITS","TOTAL_BASES",
    "HOME_RUNS","RBI","RUNS","WALKS","STOLEN_BASES"})
STAT_NAMES = {"NFL":FOOTBALL_STATS,"CFB":FOOTBALL_STATS,
              "CBB":BASKETBALL_STATS,"NBA":BASKETBALL_STATS,"MLB":BASEBALL_STATS}


def _time(x: datetime) -> datetime:
    if not isinstance(x, datetime) or x.tzinfo is None or x.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    return x.astimezone(timezone.utc)


def _hash(x: str) -> str:
    if not isinstance(x, str) or not SHA.fullmatch(x):
        raise ValueError("ORIGINAL_PAYLOAD_SHA256_REQUIRED")
    return x


def _decimal(x: Any) -> Decimal:
    if isinstance(x, bool) or x is None:
        raise ValueError("INVALID_DECIMAL")
    try:
        d = Decimal(str(x))
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_DECIMAL") from None
    if not d.is_finite():
        raise ValueError("INVALID_DECIMAL")
    return d


def _american(x: Any) -> int:
    d = _decimal(x)
    if d != d.to_integral_value() or abs(d) < 100 or abs(d) > 1000000:
        raise ValueError("INVALID_AMERICAN_PRICE")
    return int(d)


def _decimal_odds(american: int) -> Decimal:
    x = _american(american)
    return Decimal(1) + (Decimal(x)/100 if x>0 else Decimal(100)/(-x))


def _implied(american: int) -> Decimal:
    return Decimal(1)/_decimal_odds(american)


@dataclass(frozen=True)
class Market:
    sport: str
    event_id: str
    kind: str
    period: str
    selection: str
    line: str = ""
    team_id: str = ""
    player_id: str = ""
    stat: str = ""
    settlement: str = "UNSPECIFIED"

    def __post_init__(self):
        if self.sport not in SPORTS or not self.event_id or self.kind not in KINDS:
            raise ValueError("UNKNOWN_SPORT_EVENT_OR_MARKET")
        if self.period not in PERIODS or self.selection not in SIDES:
            raise ValueError("UNKNOWN_PERIOD_OR_SIDE")
        if self.settlement not in ("INCLUDES_OT", "REGULATION", "POSTED_RULES"):
            raise ValueError("SETTLEMENT_RULE_MUST_BE_EXPLICIT")
        if self.kind in ("NRFI", "YRFI") and (self.sport != "MLB" or self.period != "1IN"):
            raise ValueError("FIRST_INNING_ONLY_MLB")
        if self.kind in ("ATTD", "FIRST_TD", "TD_2PLUS") and self.sport not in FOOTBALL:
            raise ValueError("TOUCHDOWN_MARKET_REQUIRES_FOOTBALL")
        if self.kind == "FIRST_BASKET" and self.sport not in BASKETBALL:
            raise ValueError("FIRST_BASKET_REQUIRES_BASKETBALL")
        if self.sport == "MLB" and self.period in ("1Q","2Q","3Q","4Q","1H","2H"):
            raise ValueError("PERIOD_NOT_SUPPORTED_BY_SPORT")
        if self.sport != "MLB" and self.period in ("F5","1IN"):
            raise ValueError("PERIOD_NOT_SUPPORTED_BY_SPORT")
        if self.kind in ("SPREAD", "ML"):
            if self.selection not in ("HOME", "AWAY"):
                raise ValueError("TEAM_SIDE_REQUIRED")
        elif self.kind in ("TOTAL", "TEAM_TOTAL", "PLAYER_PROP"):
            if self.selection not in ("OVER", "UNDER"):
                raise ValueError("OVER_UNDER_REQUIRED")
        else:
            if self.selection not in ("YES", "NO"):
                raise ValueError("YES_NO_REQUIRED")
        if self.kind in ("TEAM_TOTAL",) and not self.team_id:
            raise ValueError("TEAM_ID_REQUIRED")
        if self.kind in ("PLAYER_PROP","ATTD","FIRST_TD","TD_2PLUS","FIRST_BASKET") and not self.player_id:
            raise ValueError("PLAYER_ID_REQUIRED")
        if self.kind == "PLAYER_PROP" and self.stat not in STAT_NAMES[self.sport]:
            raise ValueError("UNKNOWN_PLAYER_STAT")
        if self.kind in ("ML","ATTD","FIRST_TD","TD_2PLUS","FIRST_BASKET","NRFI","YRFI"):
            if self.line not in ("",):
                raise ValueError("MARKET_CANNOT_HAVE_LINE")
        else:
            object.__setattr__(self, "line", str(_decimal(self.line).normalize()))

    def identity(self) -> tuple[str, ...]:
        return (self.sport, self.event_id, self.kind, self.period, self.selection,
                self.line, self.team_id, self.player_id, self.stat, self.settlement)

    def opposite(self, other: "Market") -> bool:
        x=self.identity(); y=other.identity()
        if x[:4]!=y[:4] or x[6:]!=y[6:]:
            return False
        flips={"HOME":"AWAY","AWAY":"HOME","OVER":"UNDER","UNDER":"OVER",
               "YES":"NO","NO":"YES"}
        if flips.get(self.selection)!=other.selection:
            return False
        return (_decimal(self.line)==-_decimal(other.line)
                if self.kind=="SPREAD" else self.line==other.line)


@dataclass(frozen=True)
class ScoreEvent:
    kind: str
    team_id: str
    player_id: str | None = None
    # For FIRST_TD and FIRST_BASKET, events must be in chronological order.
    def __post_init__(self):
        if self.kind not in ("RUSH_TD","REC_TD","DEF_TD","ST_TD","OTHER_TD","BASKET"):
            raise ValueError("UNKNOWN_SCORE_EVENT_KIND")
        if self.kind in ("RUSH_TD","REC_TD","BASKET") and not self.player_id:
            raise ValueError("PLAYER_EVENT_REQUIRES_ID")
        if self.kind in ("DEF_TD","ST_TD","OTHER_TD") and self.player_id:
            raise ValueError("NON_PLAYER_TD_CANNOT_CREDIT_OFFENSE")


@dataclass(frozen=True)
class Outcome:
    # Key: Q1..Q4, OT for football/basketball; I1..I9, EXTRA for MLB.
    periods: dict[str, tuple[int, int]]    # always home, away
    player_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    events: tuple[ScoreEvent, ...] = ()
    events_complete: bool = False
    # Period props must be separately projected. NEVER reuse full-game stats.
    player_period_stats: dict[str,dict[str,dict[str,int]]] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.periods, dict):
            raise ValueError("PERIOD_SCORES_MISSING")
        for x in self.periods.values():
            if not isinstance(x, (tuple,list)) or len(x)!=2 or any(type(n)!=int or n<0 for n in x):
                raise ValueError("INVALID_PERIOD_SCORE")
        for player, stats in self.player_stats.items():
            if not player or not isinstance(stats,dict):
                raise ValueError("INVALID_PLAYER_STATS")
            if any(type(v)!=int or v<0 for v in stats.values()):
                raise ValueError("INVALID_PLAYER_STAT_VALUE")
        for period, players in self.player_period_stats.items():
            if period not in PERIODS or period=="FG" or not isinstance(players,dict):
                raise ValueError("INVALID_PLAYER_PROP_PERIOD")
            for player,stats in players.items():
                if not player or not isinstance(stats,dict):
                    raise ValueError("INVALID_PLAYER_PERIOD_STATS")
                if any(type(v)!=int or v<0 for v in stats.values()):
                    raise ValueError("INVALID_PLAYER_PERIOD_STAT_VALUE")


@dataclass(frozen=True)
class SimulationBatch:
    sport: str
    event_id: str
    home_id: str
    away_id: str
    roster_ids: frozenset[str]
    model_sha256: str
    feature_sha256: str
    asof_utc: datetime
    generated_at_utc: datetime
    outcomes: tuple[Outcome, ...]
    calibration_status: str = "UNVERIFIED"

    def __post_init__(self):
        if self.sport not in SPORTS or not self.event_id or not self.home_id or not self.away_id or self.home_id==self.away_id:
            raise ValueError("INVALID_EVENT_OR_SPORT")
        _hash(self.model_sha256);_hash(self.feature_sha256)
        if _time(self.asof_utc)>_time(self.generated_at_utc):
            raise ValueError("MODEL_ASOF_AFTER_GENERATION")
        if not self.outcomes:
            raise ValueError("EMPTY_SCENARIO_SET")
        if self.calibration_status not in ("UNVERIFIED","HOLDOUT_RESEARCH"):
            raise ValueError("UNSUPPORTED_MODEL_PROMOTION_STATE")
        for o in self.outcomes:
            if not set(o.player_stats).issubset(self.roster_ids):
                raise ValueError("PLAYER_STATS_ROSTER_MISMATCH")
            for period_player_stats in o.player_period_stats.values():
                if not set(period_player_stats).issubset(self.roster_ids):
                    raise ValueError("PERIOD_PLAYER_STATS_ROSTER_MISMATCH")
            for e in o.events:
                if e.team_id not in (self.home_id,self.away_id) or (e.player_id and e.player_id not in self.roster_ids):
                    raise ValueError("SCORING_EVENT_ROSTER_MISMATCH")


@dataclass(frozen=True)
class PriceReceipt:
    market: Market
    odds_american: int
    book: str
    provider_id: str
    provider_event_id: str
    provider_market_id: str
    quote_id: str
    receipt_id: str
    raw_payload_sha256: str
    observed_at_utc: datetime
    received_at_utc: datetime
    event_start_utc: datetime

    def __post_init__(self):
        _hash(self.raw_payload_sha256)
        _american(self.odds_american)
        for x in (self.book,self.provider_id,self.provider_event_id,self.provider_market_id,
                  self.quote_id,self.receipt_id):
            if not isinstance(x,str) or not x.strip():
                raise ValueError("RECEIPT_IDENTIFIERS_MISSING")
        if not (_time(self.observed_at_utc)<=_time(self.received_at_utc)<_time(self.event_start_utc)):
            raise ValueError("RECEIPT_TIME_ORDER_INVALID")


def _period_score(o: Outcome, sport: str, period: str, settlement: str) -> tuple[int,int]:
    """Fail closed on unresolved full-game overtime and extra innings.

    Period-only and explicitly regulation-only markets do not inherit
    unmodeled overtime. This is a model-scenario completeness check,
    NOT an attestation of a sportsbook's posted settlement rules.
    """
    if period == "FG":
        keys=(tuple("I"+str(i) for i in range(1,10)) if sport=="MLB"
              else ("Q1","Q2","Q3","Q4"))
    else:
        keys=PERIOD_ORDER[period]
    if any(k not in o.periods for k in keys):
        raise ValueError("MISSING_PERIOD_SPLIT")
    home=sum(o.periods[k][0] for k in keys)
    away=sum(o.periods[k][1] for k in keys)
    if period!="FG" or settlement=="REGULATION":
        return home,away
    if sport=="MLB":
        if home!=away:
            if "EXTRA" in o.periods:
                raise ValueError("EXTRA_INNINGS_WITHOUT_NINE_INNING_TIE")
            return home,away
        if "EXTRA" not in o.periods:
            raise ValueError("MLB_EXTRA_INNINGS_OUTCOME_MISSING")
        home+=o.periods["EXTRA"][0]
        away+=o.periods["EXTRA"][1]
        if home==away:
            raise ValueError("MLB_FINAL_TIE_UNRESOLVED")
        return home,away
    if settlement=="POSTED_RULES":
        # This generic flag does not identify whether the book includes OT.
        # For a regulation tie, the absent rule can change any FG market.
        if home==away:
            raise ValueError("POSTED_SETTLEMENT_RULE_UNVERIFIED")
        if "OT" in o.periods:
            raise ValueError("POSTED_SETTLEMENT_RULE_UNVERIFIED")
        return home,away
    if settlement=="INCLUDES_OT":
        if home!=away:
            if "OT" in o.periods:
                raise ValueError("OVERTIME_WITHOUT_REGULATION_TIE")
            return home,away
        if "OT" not in o.periods:
            raise ValueError("OVERTIME_OUTCOME_MISSING")
        home+=o.periods["OT"][0]
        away+=o.periods["OT"][1]
        if (sport in BASKETBALL or sport=="CFB") and home==away:
            raise ValueError("OVERTIME_FINAL_TIE_UNRESOLVED")
    return home,away


def settle(batch: SimulationBatch, o: Outcome, market: Market) -> str:
    if batch.event_id!=market.event_id or batch.sport!=market.sport:
        raise ValueError("EVENT_IDENTITY_MISMATCH")
    if market.team_id and market.team_id not in (batch.home_id,batch.away_id):
        raise ValueError("TEAM_IDENTITY_MISMATCH")
    if market.player_id and market.player_id not in batch.roster_ids:
        raise ValueError("PLAYER_ROSTER_MISMATCH")
    if market.kind in ("ATTD","FIRST_TD","TD_2PLUS","FIRST_BASKET"):
        if market.period!="FG" or not o.events_complete:
            raise ValueError("FULL_EVENT_SEQUENCE_MISSING")
        if market.kind=="FIRST_BASKET":
            first=next((e for e in o.events if e.kind=="BASKET"),None)
            hit=bool(first and first.player_id==market.player_id)
        elif market.kind=="FIRST_TD":
            first=next((e for e in o.events if e.kind.endswith("_TD")),None)
            hit=bool(first and first.kind in ("RUSH_TD","REC_TD") and first.player_id==market.player_id)
        else:
            count=sum(1 for e in o.events if e.kind in ("RUSH_TD","REC_TD") and e.player_id==market.player_id)
            hit=count >= (2 if market.kind=="TD_2PLUS" else 1)
        return "W" if (hit==(market.selection=="YES")) else "L"
    if market.kind in ("NRFI","YRFI"):
        home,away=_period_score(o,batch.sport,"1IN",market.settlement)
        hit=(home+away==0) if market.kind=="NRFI" else (home+away>0)
        return "W" if (hit==(market.selection=="YES")) else "L"
    if market.kind=="PLAYER_PROP":
        if market.period=="FG":
            stats=o.player_stats
        else:
            stats=o.player_period_stats.get(market.period,{})
        if market.player_id not in stats or market.stat not in stats[market.player_id]:
            raise ValueError("PERIOD_PLAYER_STAT_PROJECTION_MISSING" if market.period!="FG"
                             else "PLAYER_STAT_PROJECTION_MISSING")
        val=Decimal(stats[market.player_id][market.stat])
        line=_decimal(market.line)
        diff=val-line if market.selection=="OVER" else line-val
    else:
        home,away=_period_score(o,batch.sport,market.period,market.settlement)
        if market.kind=="ML":
            diff=Decimal(home-away if market.selection=="HOME" else away-home)
            if batch.sport=="MLB" and diff==0:
                raise ValueError("MLB_FULL_GAME_TIE_NOT_SETTLEABLE")
        elif market.kind=="SPREAD":
            diff=Decimal(home-away if market.selection=="HOME" else away-home)+_decimal(market.line)
        elif market.kind=="TOTAL":
            diff=Decimal(home+away)-_decimal(market.line)
            if market.selection=="UNDER":diff=-diff
        elif market.kind=="TEAM_TOTAL":
            pts=home if market.team_id==batch.home_id else away
            diff=Decimal(pts)-_decimal(market.line)
            if market.selection=="UNDER":diff=-diff
        else:
            raise ValueError("MARKET_NOT_SUPPORTED")
    return "W" if diff>0 else ("L" if diff<0 else "P")


def validate_pair(
    primary: PriceReceipt | None, opponent: PriceReceipt | None,
    market: Market, decision_at_utc: datetime,
    *, max_age_seconds: int = 300, max_pair_skew_seconds: int = 30,
) -> tuple[Decimal,Decimal]:
    """No-vig requires two truly captured complementary prices on exact definition."""
    now=_time(decision_at_utc)
    if primary is None or opponent is None:
        raise ValueError("MISSING_TWO_SIDED_PRICE")
    if primary.market.identity()!=market.identity() or not market.opposite(opponent.market):
        raise ValueError("TWO_SIDED_MARKET_LINE_MISMATCH")
    if primary.book.casefold()!="draftkings" or opponent.book.casefold()!="draftkings":
        raise ValueError("NON_DK_PRICE_USED_AS_DK_TAKEN_QUOTE")
    if (primary.provider_id!=opponent.provider_id or
        primary.provider_event_id!=opponent.provider_event_id or
        primary.provider_market_id!=opponent.provider_market_id):
        raise ValueError("DIFFERENT_QUOTE_SOURCE_EVENT_OR_MARKET")
    if primary.event_start_utc!=opponent.event_start_utc:
        raise ValueError("EVENT_START_MISMATCH")
    if primary.receipt_id==opponent.receipt_id or primary.quote_id==opponent.quote_id:
        raise ValueError("DUPLICATE_QUOTE_RECEIPT")
    if type(max_age_seconds)!=int or not 0<max_age_seconds<=300:
        raise ValueError("UNSAFE_PREGAME_QUOTE_AGE")
    if (type(max_pair_skew_seconds)!=int or
            not 0<max_pair_skew_seconds<=max_age_seconds):
        raise ValueError("UNSAFE_TWO_SIDED_QUOTE_SKEW_LIMIT")
    for q in (primary,opponent):
        if not (q.observed_at_utc <= q.received_at_utc <= now < q.event_start_utc):
            raise ValueError("QUOTE_AFTER_DECISION_OR_START")
        if (now-q.observed_at_utc).total_seconds()>max_age_seconds:
            raise ValueError("STALE_QUOTE")
    # Only compare quote synchronicity after both inputs pass their own
    # freshness and temporal validity checks. A stale receipt is always
    # reported as stale even when the pair is also asynchronous.
    if abs((primary.observed_at_utc-opponent.observed_at_utc).total_seconds())>max_pair_skew_seconds:
        raise ValueError("TWO_SIDED_QUOTE_SNAPSHOT_SKEW")
    p=_implied(primary.odds_american); opp=_implied(opponent.odds_american)
    return p/(p+opp), _decimal_odds(primary.odds_american)


def result_record(market: Market, status: str, reasons: list[str], **kwargs) -> dict:
    """Explicit non-promotable output. There is no callable bypass."""
    return {"market":market.identity(),"status":status,"reasons":sorted(set(reasons)),
            "card":None,"approved_stake_u":0,"official_counted":0,
            "externally_authenticated":False, **kwargs}


def price_market(
    batch: SimulationBatch, market: Market,
    primary: PriceReceipt | None, opponent: PriceReceipt | None,
    decision_at_utc: datetime,
    *, min_simulations: int = 1000, min_tail_count: int = 25,
) -> dict:
    """Return unverified candidate EV (not actionable), or a reasoned BLOCK."""
    try:
        now=_time(decision_at_utc)
        if market.sport!=batch.sport or market.event_id!=batch.event_id:
            raise ValueError("MARKET_EVENT_MISMATCH")
        if now < batch.generated_at_utc or now < batch.asof_utc:
            raise ValueError("SIMULATION_GENERATED_AFTER_DECISION")
        if len(batch.outcomes)<max(1000,min_simulations):
            raise ValueError("INSUFFICIENT_SIMULATION_COUNT")
        market_cond,decimal_odds=validate_pair(primary,opponent,market,now)
        outcomes=[settle(batch,o,market) for o in batch.outcomes]
        w=outcomes.count("W");p=outcomes.count("P");l=outcomes.count("L")
        if w<min_tail_count or l<min_tail_count or w+l==0:
            raise ValueError("INSUFFICIENT_WIN_LOSS_TAIL")
        n=len(outcomes);nonpush=w+l
        model_cond=Decimal(w)/Decimal(nonpush)
        blended_cond=Decimal("0.30")*model_cond+Decimal("0.70")*market_cond
        nonpush_frac=Decimal(nonpush)/Decimal(n)
        model_win=Decimal(w)/Decimal(n)
        blended_win=blended_cond*nonpush_frac
        stakeprofit=decimal_odds-1
        model_loss=Decimal(l)/Decimal(n)
        blended_loss=(1-blended_cond)*nonpush_frac
        return result_record(market,"PAPER_0U",
                ["MODEL_AND_SOURCE_CALIBRATION_UNVERIFIED","NO_OFFICIAL_PRICE_ATTESTATION",
                 "ALL_FIVE_GATES_NOT_PASSED"],
                simulations=n,wins=w,losses=l,pushes=p,model_p_win=float(model_win),
                model_p_push=p/n,model_p_loss=float(model_loss),
                no_vig_market_p_conditional=float(market_cond),
                blend_p_win=float(blended_win),
                raw_ev_unverified=float(model_win*stakeprofit-model_loss),
                blended_ev_unverified=float(blended_win*stakeprofit-blended_loss),
                model_sha256=batch.model_sha256, feature_sha256=batch.feature_sha256,
                primary_receipt_id=primary.receipt_id,opponent_receipt_id=opponent.receipt_id)
    except (ValueError, ArithmeticError, OverflowError, KeyError) as exc:
        return result_record(market,"BLOCK",[str(exc)])


def price_sgp(
    batch: SimulationBatch, legs: tuple[Market, ...],
    quoted_american: int | None, quote_payload_sha256: str | None,
    quote_legs_sha256: str | None, quote_received_at_utc: datetime | None,
    decision_at_utc: datetime, *,
    quote_book: str | None = None, event_start_at_utc: datetime | None = None,
    min_scenarios: int=1000, min_joint_wins: int=25,
) -> dict:
    """Joint-play scenario pricing. No parlay independence multiplication, ever.

    A valid DK SGP receipt MUST bind the exact set of selection identities.
    Pushes are blocked until documented SGP-specific recalculation rules exist.
    """
    result={"status":"BLOCK","card":None,"approved_stake_u":0,"official_counted":0,
            "market":"SGP","reasons":[],"joint_probability_unverified":None,
            "raw_ev_unverified":None}
    try:
        now=_time(decision_at_utc)
        if not legs or len(legs)<2 or len({m.identity() for m in legs})!=len(legs):
            raise ValueError("SGP_MISSING_OR_DUPLICATE_LEGS")
        if len(batch.outcomes)<max(min_scenarios,1000):
            raise ValueError("SGP_SIMULATIONS_INSUFFICIENT")
        if now<batch.generated_at_utc:
            raise ValueError("SGP_SIMULATION_GENERATED_AFTER_DECISION")
        for m in legs:
            if m.event_id!=batch.event_id or m.sport!=batch.sport:
                raise ValueError("SGP_LEG_DIFFERENT_EVENT")
        if (quoted_american is None or not quote_payload_sha256 or not quote_legs_sha256
                or quote_received_at_utc is None or event_start_at_utc is None
                or quote_book is None or quote_book.casefold()!="draftkings"):
            raise ValueError("EXACT_DK_SGP_PRICE_RECEIPT_REQUIRED")
        if not (now < _time(event_start_at_utc)):
            raise ValueError("SGP_ALREADY_STARTED")
        _hash(quote_payload_sha256);_hash(quote_legs_sha256)
        fingerprint=sha256(json.dumps([m.identity() for m in legs],sort_keys=True,
            separators=(",",":")).encode()).hexdigest()
        if quote_legs_sha256!="sha256:"+fingerprint:
            raise ValueError("SGP_LEG_FINGERPRINT_MISMATCH")
        if not (_time(quote_received_at_utc)<=now):
            raise ValueError("SGP_QUOTE_FUTURE_DATED")
        if (now-quote_received_at_utc).total_seconds()>300:
            raise ValueError("SGP_QUOTE_STALE")
        win=0
        for o in batch.outcomes:
            states=[settle(batch,o,m) for m in legs]
            if "P" in states:
                raise ValueError("SGP_PUSH_REPRICING_RULE_UNKNOWN")
            if all(x=="W" for x in states):
                win+=1
        if win<min_joint_wins or len(batch.outcomes)-win<min_joint_wins:
            raise ValueError("INSUFFICIENT_JOINT_TAIL_SUPPORT")
        p=Decimal(win)/Decimal(len(batch.outcomes))
        dec=_decimal_odds(_american(quoted_american))
        result.update(status="PAPER_0U",reasons=["SGP_ODDS_PROVIDER_AUTH_UNVERIFIED",
                "JOINT_MODEL_CALIBRATION_NOT_PROVEN","NO_INDEPENDENT_NO_VIG_PARLAY_BASELINE"],
            joint_probability_unverified=float(p),raw_ev_unverified=float(p*dec-1),
            jointly_winning_scenarios=win,simulations=len(batch.outcomes),
            leg_fingerprint=quote_legs_sha256)
        return result
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        result["reasons"]=[str(exc)]
        return result
