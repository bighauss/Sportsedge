"""NHL regulation-only skater attribution from existing shared period scenarios.

Research challenger ONLY. No odds or production card inputs. Every simulated
team shot and goal is attributed to exactly one uniquely identified skater;
opposing goalie saves are inherited from the identical original game scenario.
Unmodeled OT/shootouts, assists, points, blocks, DFS and full-game props are
explicitly unsupported. Never interpret this as authenticated source capture
or calibrated player predictions. PAPER / 0u.
"""
from __future__ import annotations

import hashlib
import json
import math
import random


class Blocked(ValueError):
    pass


_PERIODS = ("P1", "P2", "P3")
_SKATER_KEYS = tuple(f"{p}_{stat}" for p in _PERIODS for stat in ("SOG", "GOALS"))
_GOALIE_KEYS = tuple(f"{p}_SAVES" for p in _PERIODS)
_SCOPE = "REGULATION_ONLY"


def _profile_rows(profiles):
    if not isinstance(profiles, (list, tuple)) or len(profiles) != 36:
        raise Blocked("NO_FORECAST_EXACT_18_SKATERS_EACH_SIDE_REQUIRED")
    by_side = {"home": [], "away": []}
    ids = set()
    for r in profiles:
        if not isinstance(r, dict):
            raise Blocked("INVALID_SKATER_PROFILE")
        pid, side = r.get("player_id"), r.get("side")
        if (not isinstance(pid, str) or not pid.strip() or pid in ids
                or side not in by_side):
            raise Blocked("MISSING_DUPLICATE_OR_AMBIGUOUS_PLAYER_ID")
        ids.add(pid)
        for key in ("projected_toi_minutes", "shots_per_60", "goals_per_shot"):
            x = r.get(key)
            if (isinstance(x, bool) or not isinstance(x, (int, float))
                    or not math.isfinite(x)):
                raise Blocked("NONFINITE_OR_MISSING_" + key.upper())
        if (not 0 < r["projected_toi_minutes"] <= 60
                or not 0 < r["shots_per_60"] <= 30
                or not 0 < r["goals_per_shot"] <= 1):
            raise Blocked("INVALID_TOI_SHOT_OR_CONVERSION_RATE")
        by_side[side].append({
            "player_id": pid,
            "side": side,
            "projected_toi_minutes": float(r["projected_toi_minutes"]),
            "shots_per_60": float(r["shots_per_60"]),
            "goals_per_shot": float(r["goals_per_shot"]),
        })
    if any(len(by_side[side]) != 18 for side in ("home", "away")):
        raise Blocked("NO_FORECAST_EXACT_18_SKATERS_EACH_SIDE_REQUIRED")
    for side in by_side:
        by_side[side].sort(key=lambda r: r["player_id"])
    return by_side, ids


def _choose(rng, weights):
    total = sum(weights)
    if total <= 0 or not math.isfinite(total):
        raise Blocked("SHOT_GOAL_ALLOCATION_IMPOSSIBLE")
    u = rng.random() * total
    cumulative = 0.0
    for j, w in enumerate(weights):
        cumulative += w
        if u < cumulative:
            return j
    return len(weights) - 1


def allocate(params, scenarios, skaters, goalie_ids, *, seed=7):
    """Allocate *existing* regulation draws, never resimulate team outcomes.

    params: nhl_shared_scenarios.Params with checked as-of fields.
    scenarios: list from nhl_shared_scenarios.run(params).
    skaters: exactly 18 per side, stable player_id and independent pregame
       projected_toi_minutes, shots_per_60, goals_per_shot.
    goalie_ids: side->stable ID, separate from display names.
    The parameter validation is structural, NOT source authentication.
    """
    params.validate()
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise Blocked("INVALID_SEED")
    if not isinstance(scenarios, (list, tuple)) or not 1 <= len(scenarios) <= 50000:
        raise Blocked("INVALID_SCENARIO_COUNT")
    sides, skater_ids = _profile_rows(skaters)
    if (not isinstance(goalie_ids, dict) or set(goalie_ids) != {"home", "away"}
            or any(not isinstance(g, str) or not g.strip() for g in goalie_ids.values())
            or goalie_ids["home"] == goalie_ids["away"]
            or any(g in skater_ids for g in goalie_ids.values())):
        raise Blocked("MISSING_DUPLICATE_OR_AMBIGUOUS_GOALIE_ID")
    rng = random.Random(seed)
    data = {pid: {k: [] for k in _SKATER_KEYS + ("REG_SOG", "REG_GOALS")}
            for pid in skater_ids}
    goalie_data = {gid: {k: [] for k in _GOALIE_KEYS + ("REG_SAVES",)}
                   for gid in goalie_ids.values()}
    head = {
        "schema": "NHL_REG_PLAYER_SCENARIOS_V1", "seed": seed,
        "model_sha256": params.model_sha256, "input_sha256": params.input_sha256,
        "game_id": params.game_id, "frozen_utc": params.frozen_utc,
        "kickoff_utc": params.kickoff_utc, "goalie_ids": goalie_ids,
        "skaters": sides, "n": len(scenarios),
    }
    digest = hashlib.sha256(json.dumps(head, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode())
    for scenario in scenarios:
        scenario.validate()
        local = {pid: {k: 0 for k in _SKATER_KEYS} for pid in skater_ids}
        local_goalie = {gid: {} for gid in goalie_ids.values()}
        for i, period in enumerate(scenario.periods):
            pk = _PERIODS[i]
            for side in ("home", "away"):
                ps = sides[side]
                shots = period.shots_home if side == "home" else period.shots_away
                goals = period.goals_home if side == "home" else period.goals_away
                shot_weights = [r["projected_toi_minutes"] * r["shots_per_60"] / 60
                                for r in ps]
                counts = [0] * len(ps)
                for _ in range(shots):
                    counts[_choose(rng, shot_weights)] += 1
                remaining = counts.copy()
                scorer_goals = [0] * len(ps)
                # Condition goals on the SAME team goals and each shooter's
                # actual allocated shot count: no goal without a shot.
                for _ in range(goals):
                    w = [remaining[j] * ps[j]["goals_per_shot"]
                         for j in range(len(ps))]
                    j = _choose(rng, w)
                    remaining[j] -= 1
                    scorer_goals[j] += 1
                for j, r in enumerate(ps):
                    local[r["player_id"]][pk + "_SOG"] = counts[j]
                    local[r["player_id"]][pk + "_GOALS"] = scorer_goals[j]
            local_goalie[goalie_ids["home"]][pk + "_SAVES"] = period.saves_home_goalie
            local_goalie[goalie_ids["away"]][pk + "_SAVES"] = period.saves_away_goalie
        for pid, stats in local.items():
            for k in _SKATER_KEYS:
                data[pid][k].append(stats[k])
            data[pid]["REG_SOG"].append(sum(stats[p + "_SOG"] for p in _PERIODS))
            data[pid]["REG_GOALS"].append(sum(stats[p + "_GOALS"] for p in _PERIODS))
        for gid, stats in local_goalie.items():
            for k in _GOALIE_KEYS:
                goalie_data[gid][k].append(stats[k])
            goalie_data[gid]["REG_SAVES"].append(sum(stats[k] for k in _GOALIE_KEYS))
        record = {"players": local, "goalies": local_goalie,
                  "team_periods": [
                      [p.shots_home, p.shots_away, p.goals_home, p.goals_away,
                       p.saves_home_goalie, p.saves_away_goalie]
                      for p in scenario.periods]}
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
    return {
        "status": "PAPER_UNCALIBRATED_REGULATION_RESEARCH",
        "n": len(scenarios), "scenario_sha256": digest.hexdigest(),
        "input_sha256": params.input_sha256,
        "model_sha256": params.model_sha256,
        "skaters": data, "goalies": goalie_data,
        "source_authenticated": False,
        "player_minutes_verified": False,
        "no_vig_verified": False, "official_counted": 0, "approved_stake_u": 0,
        "unsupported": ("FG_INCLUDING_OT", "OT", "SO", "POINTS", "ASSISTS",
                        "BLOCKS", "DFS", "SGP", "FIRST_GOAL", "2PLUS_GOALS"),
    }


def price(batch, market, side, line, *, player_id, settlement_scope=None):
    """Regulation-only Over/Under W/P/L. No assumed sportsbook contract."""
    if settlement_scope != _SCOPE:
        return {"status": "UNRESOLVED_MARKET",
                "reason": "ORIGINAL_SETTLEMENT_SCOPE_NOT_CONFIRMED"}
    if side not in ("over", "under"):
        return {"status": "UNRESOLVED_MARKET", "reason": "INVALID_SELECTION"}
    if (isinstance(line, bool) or not isinstance(line, (int, float))
            or not math.isfinite(line) or line < 0 or line > 100):
        return {"status": "UNRESOLVED_MARKET", "reason": "INVALID_PROP_LINE"}
    if not isinstance(player_id, str) or not player_id:
        return {"status": "NO_FORECAST", "reason": "MISSING_STABLE_PLAYER_ID"}
    if market.endswith("_SAVES") and market in _GOALIE_KEYS + ("REG_SAVES",):
        values = batch["goalies"].get(player_id, {}).get(market)
    elif market in _SKATER_KEYS + ("REG_SOG", "REG_GOALS"):
        values = batch["skaters"].get(player_id, {}).get(market)
    else:
        return {"status": "NO_FORECAST", "reason": "UNSUPPORTED_MARKET"}
    if values is None:
        return {"status": "NO_FORECAST", "reason": "PLAYER_ID_NOT_IN_FROZEN_ROSTER"}
    n = len(values)
    w = sum((v > line) if side == "over" else (v < line) for v in values)
    p = sum(v == line for v in values)
    return {"status": "SIMULATED_REGULATION_RESEARCH_ONLY",
            "n": n, "p_win": w / n, "p_push": p / n,
            "p_loss": (n - w - p) / n,
            "wins": w, "pushes": p, "losses": n - w - p,
            "scenario_sha256": batch["scenario_sha256"],
            "official_counted": 0, "approved_stake_u": 0}
