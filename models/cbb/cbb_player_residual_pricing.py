"""Conditional-on-participation CBB player pricing research; never a production model.

Consume independently generated, frozen out-of-sample player means and observed finals.
Preserve joint residual vectors across counting stats; never infer player identity by name.
No odds enter the distribution. PAPER/0u only. Availability/DNP settlement not modeled.
"""
from dataclasses import dataclass
from datetime import datetime
import math
from statistics import mean

STATS = ("PTS", "REB", "AST", "3PM")
COMBOS = {"PRA": ("PTS", "REB", "AST"), "PR": ("PTS", "REB"),
          "PA": ("PTS", "AST"), "RA": ("REB", "AST")}


def clock(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("CLOCK_NOT_OFFSET_AWARE")
    return d


def vector(values, *, actual=False):
    if set(values) != set(STATS):
        raise ValueError("INCOMPLETE_STAT_VECTOR")
    result = []
    for key in STATS:
        v = values[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError("INVALID_STAT")
        if actual and not float(v).is_integer():
            raise ValueError("NONINTEGER_FINAL")
        result.append(v)
    if result[3] * 3 > result[0] + 1e-9:
        raise ValueError("THREES_EXCEED_POINTS")
    return tuple(result)


@dataclass(frozen=True)
class Forecast:
    event_id: str
    team_id: str
    player_id: str
    tip_utc: str
    frozen_utc: str
    means: dict
    model_version: str


@dataclass(frozen=True)
class Observation:
    forecast: Forecast
    observed_final_utc: str
    actual: dict
    participated: bool


def validate_forecast(f):
    if not all(isinstance(v, str) and v.strip() for v in
               (f.event_id, f.team_id, f.player_id, f.model_version)):
        raise ValueError("MISSING_STABLE_ID_OR_VERSION")
    if clock(f.frozen_utc) >= clock(f.tip_utc):
        raise ValueError("FORECAST_NOT_PREGAME")
    return vector(f.means)


def predictive_draws(target, history, *, as_of_utc, min_samples=20):
    """Empirical joint residual transport from same player/team/model, prior finals only.

    This is an unvalidated candidate: no cross-player pooling or invented variance.
    Historical forecast and final provenance must be verified by the caller.
    """
    mu = validate_forecast(target)
    as_of = clock(as_of_utc)
    if not clock(target.frozen_utc) <= as_of < clock(target.tip_utc):
        raise ValueError("TARGET_NOT_AVAILABLE_PREGAME")
    if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 2:
        raise ValueError("INVALID_MIN_SAMPLES")
    seen, samples = set(), []
    for row in history:
        f = row.forecast
        if (f.player_id, f.team_id, f.model_version) != (target.player_id, target.team_id, target.model_version):
            continue
        if f.event_id == target.event_id:
            raise ValueError("TARGET_IN_HISTORY")
        if clock(row.observed_final_utc) >= as_of:
            continue
        prior = validate_forecast(f)
        if not clock(f.tip_utc) < clock(row.observed_final_utc):
            raise ValueError("FINAL_NOT_AFTER_TIP")
        if f.event_id in seen:
            raise ValueError("DUPLICATE_HISTORICAL_EVENT")
        seen.add(f.event_id)
        if row.participated is not True:
            continue
        actual = vector(row.actual, actual=True)
        draw = [max(0, round(m + a - p)) for m, a, p in zip(mu, actual, prior)]
        # Preserve the hard scoring identity. Track any repair explicitly.
        repaired = 3 * draw[3] > draw[0]
        if repaired:
            draw[3] = draw[0] // 3
        samples.append((tuple(draw), repaired, f.event_id))
    if len(samples) < min_samples:
        raise ValueError("INSUFFICIENT_PRIOR_RESIDUALS")
    return {"draws": tuple(s[0] for s in samples), "samples": len(samples),
            "repaired_draws": sum(s[1] for s in samples),
            "source_event_ids": tuple(s[2] for s in samples),
            "status": "RESEARCH_CONDITIONAL_PARTICIPATION", "approved_stake_u": 0}


def price(distribution, stat, kind, line):
    if stat not in STATS and stat not in COMBOS:
        raise ValueError("UNSUPPORTED_STAT")
    if isinstance(line, bool) or not isinstance(line, (int, float)) or not math.isfinite(line) or line < 0:
        raise ValueError("INVALID_LINE")
    if kind not in ("OU", "AT_LEAST") or (kind == "AT_LEAST" and (line < 1 or not float(line).is_integer())):
        raise ValueError("INVALID_CONTRACT")
    keys = COMBOS.get(stat, (stat,))
    draws = [sum(d[STATS.index(k)] for k in keys) for d in distribution["draws"]]
    if not draws:
        raise ValueError("EMPTY_DISTRIBUTION")
    n = len(draws)
    wins = sum(v >= line if kind == "AT_LEAST" else v > line for v in draws)
    pushes = 0 if kind == "AT_LEAST" else sum(v == line for v in draws)
    return {"p_a": wins / n, "p_push": pushes / n, "p_b": (n - wins - pushes) / n,
            "mean": mean(draws), "samples": n, "status": "PAPER_0U", "counted": "NON_COUNTED",
            "approved_stake_u": 0}


class PlayerBundle:
    """Research-only input bridge. Hash original bundle bytes; exact event/team/player IDs.

    The caller must provide independently verified forecast/final provenance. A local
    JSON file alone cannot establish provider authenticity or actual availability.
    """
    def __init__(self, path, as_of_utc):
        import hashlib
        import json
        from pathlib import Path
        raw = Path(path).read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        doc = json.loads(raw)
        if doc.get("schema") != "CBB_PLAYER_RESIDUAL_BUNDLE_V1":
            raise ValueError("PLAYER_BUNDLE_SCHEMA")
        self.as_of_utc = as_of_utc
        self.evidence_class = doc.get("evidence_class", "UNVERIFIED_EXTERNAL_BUNDLE")
        self.identity_namespace = doc.get("identity_namespace", "UNSPECIFIED")
        if self.identity_namespace not in ("UNSPECIFIED", "ESPN", "CBBD"):
            raise ValueError("PLAYER_BUNDLE_IDENTITY_NAMESPACE")
        self.targets = {}
        for item in doc["targets"]:
            f = Forecast(**item)
            validate_forecast(f)
            key = (f.event_id, f.team_id, f.player_id)
            if key in self.targets:
                raise ValueError("DUPLICATE_TARGET_PLAYER")
            self.targets[key] = f
        self.history = [Observation(Forecast(**item["forecast"]), item["observed_final_utc"],
                                    item["actual"], item["participated"]) for item in doc["history"]]
        self.cache = {}

    def probs(self, game_id, team_id, player_id, tip_utc, market, line):
        key = (game_id, team_id, player_id)
        target = self.targets.get(key)
        if target is None:
            raise ValueError("PLAYER_FORECAST_MISSING")
        if clock(target.tip_utc) != clock(tip_utc):
            raise ValueError("PLAYER_TIP_MISMATCH")
        if key not in self.cache:
            self.cache[key] = predictive_draws(target, self.history, as_of_utc=self.as_of_utc)
        stat, kind = market.removeprefix("PLAYER_").split("_", 1)
        p = price(self.cache[key], stat, kind, line)
        return p["p_a"], p["p_push"], p["p_b"]
