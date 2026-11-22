"""P2 + P5 — independent projection helpers and the evidence-gated adjustment registry
(Theo 1-7, 14-19, 26, 29, 47-48). These are CHALLENGER / reference calculators that
sit outside the frozen engine (engine/sportsedge_v5.py is never imported or changed).
"""
from __future__ import annotations

import math
from typing import Sequence

# ------------------------------------------------------------ power ratings / fair spread

def power_rating(off_eff: float, def_eff: float, lg_avg: float) -> float:
    """Net points per 100 possessions above average (higher = better)."""
    return (off_eff - lg_avg) - (def_eff - lg_avg)


def fair_spread(rating_home: float, rating_away: float, poss: float, hfa: float) -> float:
    """Home spread (negative = home favoured). hfa must be the sport's MEASURED value."""
    return -((rating_home - rating_away) * poss / 100 + hfa)


def pace_total(pace_a: float, pace_b: float, lg_pace: float, ortg_a: float, drtg_a: float,
               ortg_b: float, drtg_b: float, lg_rtg: float) -> dict:
    """Theo 3 — show the math. Multiplicative pace & efficiency matchup model."""
    poss = pace_a * pace_b / lg_pace
    pts_a = poss * (ortg_a * drtg_b / lg_rtg) / 100
    pts_b = poss * (ortg_b * drtg_a / lg_rtg) / 100
    return {"possessions": poss, "team_a": pts_a, "team_b": pts_b, "total": pts_a + pts_b,
            "margin_a": pts_a - pts_b,
            "math": f"poss={pace_a}*{pace_b}/{lg_pace}={poss:.1f}; A={poss:.1f}*{ortg_a}*{drtg_b}/{lg_rtg}/100"}


def cover_prob(proj_margin: float, spread: float, sd: float) -> float:
    """P(team covers spread) given projected margin and historical margin SD."""
    return 0.5 * (1 + math.erf((proj_margin + spread) / (sd * math.sqrt(2))))


def total_prob_over(proj_total: float, line: float, sd: float) -> float:
    return 1 - 0.5 * (1 + math.erf((line - proj_total) / (sd * math.sqrt(2))))


# ------------------------------------------------------------ Elo (Theo 29)

class Elo:
    def __init__(self, k: float = 20, hfa: float = 55, pts_per_elo: float = 1 / 25, mov: bool = True):
        self.k, self.hfa, self.ppe, self.mov, self.r = k, hfa, pts_per_elo, mov, {}

    def get(self, t):
        return self.r.setdefault(t, 1500.0)

    def win_prob(self, home, away, neutral=False):
        d = self.get(home) - self.get(away) + (0 if neutral else self.hfa)
        return 1 / (1 + 10 ** (-d / 400))

    def spread(self, home, away, neutral=False):
        return -(self.get(home) - self.get(away) + (0 if neutral else self.hfa)) * self.ppe

    def update(self, home, away, home_pts, away_pts, neutral=False):
        p = self.win_prob(home, away, neutral)
        s = 1.0 if home_pts > away_pts else 0.0 if home_pts < away_pts else 0.5
        mult = 1.0
        if self.mov:
            diff = abs(home_pts - away_pts)
            elo_d = (self.get(home) - self.get(away)) * (1 if s == 1 else -1)
            mult = math.log(diff + 1) * 2.2 / (elo_d * 0.001 + 2.2)
        delta = self.k * mult * (s - p)
        self.r[home] += delta
        self.r[away] -= delta
        return delta


# ------------------------------------------------------------ P5 evidence-gated adjustments

BLOCKED_BY_DEFAULT = {"motivation", "revenge", "narrative", "sharp_money", "trap_line",
                      "momentum", "public_fade", "rivalry", "look_ahead", "must_win"}


class AdjustmentRegistry:
    """Rule 1: no invented advantages. An adjustment only applies if registered with
    historical evidence: n, effect (points), standard error, out-of-sample confirmed."""

    def __init__(self, min_n: int = 200, z: float = 1.96):
        self.min_n, self.z, self.items = min_n, z, {}

    def register(self, name, effect, se, n, oos_confirmed=False, source=""):
        self.items[name] = {"effect": effect, "se": se, "n": n, "oos": oos_confirmed, "source": source}

    def status(self, name) -> tuple[str, str]:
        e = self.items.get(name)
        if e is None:
            return ("BLOCKED", "NARRATIVE_UNQUANTIFIED" if name in BLOCKED_BY_DEFAULT else "NO_EVIDENCE")
        if e["n"] < self.min_n:
            return ("BLOCKED", f"SAMPLE_{e['n']}_LT_{self.min_n}")
        if abs(e["effect"]) < self.z * e["se"]:
            return ("BLOCKED", "NOT_SIGNIFICANT")
        if not e["oos"]:
            return ("BLOCKED", "NO_OUT_OF_SAMPLE_CONFIRMATION")
        return ("ALLOWED", "EVIDENCED")

    def apply(self, base: float, requested: dict[str, float]) -> dict:
        """requested: {name: multiplier (e.g. 1 for 'applies', 2 for B2B count)}."""
        total, log = base, []
        for name, mult in requested.items():
            st, why = self.status(name)
            amt = self.items[name]["effect"] * mult if st == "ALLOWED" else 0.0
            total += amt
            log.append({"adjustment": name, "status": st, "reason": why, "points": amt})
        return {"value": total, "log": log}


def schedule_factors(rest_a: int, rest_b: int, tz_crossed_a: int = 0, tz_crossed_b: int = 0,
                     b2b_a: bool = False, b2b_b: bool = False, miles_a: float = 0, miles_b: float = 0) -> dict:
    """Theo 14 — emits factor flags only; points come from AdjustmentRegistry evidence."""
    req = {}
    if rest_a != rest_b:
        req["rest_diff_per_day"] = rest_a - rest_b
    if b2b_a or b2b_b:
        req["back_to_back"] = int(b2b_b) - int(b2b_a)
    if tz_crossed_a or tz_crossed_b:
        req["timezone_per_zone"] = tz_crossed_b - tz_crossed_a
    if miles_a or miles_b:
        req["travel_per_1000mi"] = (miles_b - miles_a) / 1000
    return req


def weather_factors(wind_mph: float | None, temp_f: float | None, precip: bool, roof_closed: bool) -> dict:
    if roof_closed:
        return {}
    req = {}
    if wind_mph is not None and wind_mph >= 15:
        req["wind_ge_15_total"] = 1
    if temp_f is not None and temp_f <= 25:
        req["cold_le_25_total"] = 1
    if precip:
        req["precip_total"] = 1
    return req


def injury_impact(player_value_per_game: float, replacement_value: float, minutes_share: float) -> float:
    """Theo 4 — points lost = (player - replacement) × share of minutes. Values from on/off data."""
    return (player_value_per_game - replacement_value) * minutes_share


def fip(hr: int, bb: int, hbp: int, k: int, ip: float, cfip: float = 3.10) -> float:
    """Theo 47 — FIP; cfip should be the season constant from FanGraphs."""
    return (13 * hr + 3 * (bb + hbp) - 2 * k) / ip + cfip


def red_zone_margin(drives_a, rz_trips_rate_a, td_pct_a, drives_b, rz_trips_rate_b, td_pct_b) -> float:
    """Theo 48 — expected points from red-zone trips (TD=7 incl. PAT approx, else FG=3)."""
    ev = lambda d, r, t: d * r * (t * 6.95 + (1 - t) * 3 * 0.9)
    return ev(drives_a, rz_trips_rate_a, td_pct_a) - ev(drives_b, rz_trips_rate_b, td_pct_b)


def blend(model_p: float, market_p: float, w_model: float) -> float:
    """Blended model/market probability (used for 'blended EV' on cards)."""
    return w_model * model_p + (1 - w_model) * market_p


def drop_contradictions(candidates: Sequence[dict]) -> list[dict]:
    """Owner rule: drop overs/unders that contradict the projection."""
    keep = []
    for c in candidates:
        side, proj, line = c.get("side", "").lower(), c.get("projection"), c.get("line")
        if proj is not None and line is not None and (
                (side == "over" and proj <= line) or (side == "under" and proj >= line)):
            continue
        keep.append(c)
    return keep
