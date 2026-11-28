"""Shared, market-specific settlement for CBB / CFB / NFL (PAPER research grading).

One pure function, settle(selection, event, players=None), returns an immutable
GradeRecord. It never guesses:
  * results come only from final scores / period scores and player box scores;
  * props are NEVER graded from team totals;
  * integer lines push; two-way period moneylines push on a tied period;
  * cancelled / postponed / abandoned events -> VOID; not-final -> UNGRADED;
  * player did not participate (DNP / inactive) -> VOID, never a loss;
  * a player missing from the box score -> UNGRADED (unknown is not zero).

Period conventions (DraftKings US football/basketball):
  FG includes overtime; H2 includes overtime; Q4 and H1/Q1-Q3 exclude it.
  Quarters exist only for football (CBB plays halves).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from types import MappingProxyType

SPORT_PERIODS = {"NFL": ("Q1", "Q2", "Q3", "Q4"), "CFB": ("Q1", "Q2", "Q3", "Q4"),
                 "CBB": ("H1", "H2")}
PERIODS = ("FG", "H1", "H2", "Q1", "Q2", "Q3", "Q4")
PLAYER_OU = {"pass_yds": ("passing_yards",), "pass_tds": ("passing_tds",),
             "pass_att": ("attempts",), "completions": ("completions",),
             "rush_yds": ("rushing_yards",), "rush_att": ("carries",),
             "rec_yds": ("receiving_yards",), "receptions": ("receptions",),
             "rush_rec_yds": ("rushing_yards", "receiving_yards"),
             "pts": ("points",), "reb": ("rebounds",), "ast": ("assists",),
             "tpm": ("threes",), "pra": ("points", "rebounds", "assists")}
TD_MARKETS = {"anytime_td": 1, "td_2plus": 2, "td_3plus": 3}
# TDs that count for scorer markets: rushing, receiving and return TDs; never passing TDs.
TD_FIELDS = ("rushing_tds", "receiving_tds", "special_teams_tds")
VOID_STATUSES = {"cancelled", "canceled", "postponed", "abandoned", "forfeit", "no_contest"}
RESULTS = ("W", "L", "P", "VOID", "UNGRADED")


class SettlementInputError(ValueError):
    pass


@dataclass(frozen=True)
class GradeRecord:
    result: str
    reason: str | None
    profit_units: float
    graded_value: float | None
    selection_sha256: str
    selection: MappingProxyType = field(repr=False)
    state: str = "PAPER_0U_NON_COUNTED"
    official_counted: int = 0
    approved_stake_u: int = 0


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False, default=str).encode()).hexdigest()


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _american(v):
    x = _num(v)
    if x is None or not x.is_integer() or abs(x) < 100:
        raise SettlementInputError("INVALID_AMERICAN_PRICE")
    return x


def _profit(result, price):
    if result == "W":
        return price / 100.0 if price > 0 else 100.0 / -price
    return -1.0 if result == "L" else 0.0


def _ou(side, value, line):
    if side not in ("over", "under"):
        raise SettlementInputError("SIDE_MUST_BE_OVER_OR_UNDER")
    if value == line:
        return "P"
    return "W" if (value > line) == (side == "over") else "L"


def period_points(event, team_key, period):
    """Points for one team in a period, or None if the period scores are unavailable."""
    sport = event["sport"]
    regs = SPORT_PERIODS[sport]
    scores = event.get(team_key + "_periods")
    final = _num(event.get(team_key + "_score"))
    if period == "FG":
        return final
    if not isinstance(scores, (list, tuple)) or len(scores) < len(regs):
        return None
    vals = [_num(x) for x in scores]
    if any(v is None for v in vals):
        return None
    reg, ot = vals[:len(regs)], vals[len(regs):]
    if final is not None and sum(vals) != final:
        raise SettlementInputError("PERIOD_SCORES_DO_NOT_SUM_TO_FINAL")
    if period not in regs and period not in ("H1", "H2"):
        raise SettlementInputError("PERIOD_NOT_PLAYED_IN_SPORT")
    if period in regs and period.startswith("Q"):
        return reg[int(period[1]) - 1]
    if sport == "CBB":
        return reg[0] if period == "H1" else reg[1] + sum(ot)
    return (reg[0] + reg[1]) if period == "H1" else (reg[2] + reg[3] + sum(ot))


def _game_result(sel, ev):
    m, period, side = sel["market"], sel.get("period", "FG"), sel.get("side")
    if period not in PERIODS:
        raise SettlementInputError("UNKNOWN_PERIOD")
    hp, ap = period_points(ev, "home", period), period_points(ev, "away", period)
    if hp is None or ap is None:
        return None, "PERIOD_SCORES_UNAVAILABLE", None
    if m == "moneyline":
        if side not in ("home", "away"):
            raise SettlementInputError("SIDE_MUST_BE_HOME_OR_AWAY")
        if hp == ap:
            # FG football/basketball ties after OT and tied periods refund a two-way ML.
            return "P", "TIED", 0.0
        return ("W" if (hp > ap) == (side == "home") else "L"), None, hp - ap
    line = _num(sel.get("line"))
    if line is None:
        raise SettlementInputError("LINE_REQUIRED")
    if m == "spread":
        if side not in ("home", "away"):
            raise SettlementInputError("SIDE_MUST_BE_HOME_OR_AWAY")
        mg = (hp - ap) if side == "home" else (ap - hp)
        v = mg + line
        return ("P" if v == 0 else "W" if v > 0 else "L"), None, mg
    if m == "total":
        return _ou(side, hp + ap, line), None, hp + ap
    if m == "team_total":
        team = sel.get("team")
        if team not in ("home", "away"):
            raise SettlementInputError("TEAM_MUST_BE_HOME_OR_AWAY")
        pts = hp if team == "home" else ap
        return _ou(side, pts, line), None, pts
    raise SettlementInputError("UNSUPPORTED_MARKET")


def _player_result(sel, ev, players):
    m, side = sel["market"], sel.get("side")
    if sel.get("period", "FG") != "FG":
        return None, "PLAYER_PERIOD_PROPS_UNSUPPORTED", None
    pid = sel.get("player_id")
    if not isinstance(pid, str) or not pid.strip():
        raise SettlementInputError("PLAYER_ID_REQUIRED")
    if not isinstance(players, dict):
        return None, "NO_PLAYER_BOX_SCORE", None
    rec = players.get(pid)
    if rec is None:
        return None, "PLAYER_NOT_IN_BOX_SCORE", None
    if rec.get("participated") is False:
        return "VOID", "PLAYER_DID_NOT_PARTICIPATE", None
    if rec.get("participated") is not True:
        return None, "PARTICIPATION_UNKNOWN", None
    team = sel.get("team")
    if team is not None and rec.get("team") is not None and team != rec.get("team"):
        raise SettlementInputError("PLAYER_TEAM_MISMATCH")
    if m in TD_MARKETS:
        vals = [_num(rec.get(k)) for k in TD_FIELDS if k in rec]
        if not vals or any(v is None for v in vals):
            return None, "TD_FIELDS_MISSING", None
        tds = sum(vals)
        hit = tds >= TD_MARKETS[m]
        if side not in ("yes", "no"):
            raise SettlementInputError("SIDE_MUST_BE_YES_OR_NO")
        return ("W" if hit == (side == "yes") else "L"), None, tds
    cols = PLAYER_OU.get(m)
    if cols is None:
        raise SettlementInputError("UNSUPPORTED_MARKET")
    vals = [_num(rec.get(c)) for c in cols]
    if any(v is None for v in vals):
        return None, "PLAYER_STAT_MISSING", None
    line = _num(sel.get("line"))
    if line is None:
        raise SettlementInputError("LINE_REQUIRED")
    v = sum(vals)
    return _ou(side, v, line), None, v


def settle(selection, event, players=None):
    """Grade one selection. Returns a frozen GradeRecord; never mutates inputs."""
    if not isinstance(selection, dict) or not isinstance(event, dict):
        raise SettlementInputError("SELECTION_AND_EVENT_MUST_BE_OBJECTS")
    snap = json.loads(json.dumps(selection, default=str))
    sha = _digest(snap)
    if event.get("sport") not in SPORT_PERIODS:
        raise SettlementInputError("UNSUPPORTED_SPORT")
    if selection.get("event_id") is not None and event.get("event_id") is not None \
            and str(selection["event_id"]) != str(event["event_id"]):
        raise SettlementInputError("EVENT_ID_MISMATCH")
    price = _american(selection.get("price"))
    status = str(event.get("status") or "").lower()
    if status in VOID_STATUSES:
        res, why, val = "VOID", "EVENT_" + status.upper(), None
    elif status != "final":
        res, why, val = "UNGRADED", "EVENT_NOT_FINAL", None
    else:
        m = selection.get("market")
        if m in PLAYER_OU or m in TD_MARKETS:
            res, why, val = _player_result(selection, event, players)
        else:
            res, why, val = _game_result(selection, event)
        if res is None:
            res = "UNGRADED"
    return GradeRecord(result=res, reason=why, profit_units=_profit(res, price),
                       graded_value=val, selection_sha256=sha,
                       selection=MappingProxyType(snap))


def nflverse_players(rows, season, week, team=None):
    """nflverse weekly rows -> {player_id: box record}. Players present in the weekly file
    recorded a stat; absence means UNKNOWN (not DNP), so they are simply not included."""
    out = {}
    for r in rows:
        if str(r.get("season")) != str(season) or str(r.get("week")) != str(week):
            continue
        if team is not None and r.get("recent_team", r.get("team")) not in team:
            continue
        pid = r.get("player_id")
        if not pid:
            continue
        if pid in out:
            raise SettlementInputError("DUPLICATE_PLAYER_ROW")
        rec = {"participated": True, "team": r.get("recent_team", r.get("team"))}
        for k in ("passing_yards", "passing_tds", "attempts", "completions", "rushing_yards",
                  "carries", "receiving_yards", "receptions", "rushing_tds", "receiving_tds",
                  "special_teams_tds"):
            if k in r:
                rec[k] = r[k]
        out[pid] = rec
    return out
