"""Research-only CBB efficiency baseline with strict pregame source chronology.

Consumes externally supplied *frozen* Torvik-shaped ratings and documented HCA.
Does not fetch providers, estimate variance, price wagers, or alter v5.
Never authenticate user-asserted timestamps merely by checking their order.
"""
from datetime import datetime, timezone, timedelta
import math
import re

UTC_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
SHA_RE = re.compile(r"^[a-fA-F0-9]{64}$")


class Blocked(ValueError):
    """A record is ineligible even for the research projection."""


def _utc(value, label):
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise Blocked(f"{label}: UTC_Z_TIMESTAMP_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise Blocked(f"{label}: INVALID_TIMESTAMP") from exc


def _num(value, label, low, high):
    if isinstance(value, bool):
        raise Blocked(f"{label}: BAD_NUMBER")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise Blocked(f"{label}: BAD_NUMBER") from exc
    if not math.isfinite(number) or not low <= number <= high:
        raise Blocked(f"{label}: OUT_OF_RANGE")
    return number


def _evidence(record, label, freeze, max_age_hours):
    """Clock consistency only, never proof of external source authenticity."""
    if not isinstance(record, dict):
        raise Blocked(f"{label}: SOURCE_RECORD_REQUIRED")
    sha = record.get("source_sha256")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise Blocked(f"{label}: SOURCE_SHA256_REQUIRED")
    published = _utc(record.get("published_utc"), f"{label}.published_utc")
    captured = _utc(record.get("captured_utc"), f"{label}.captured_utc")
    through = _utc(record.get("data_through_utc"), f"{label}.data_through_utc")
    if not (through <= published <= captured <= freeze):
        raise Blocked(f"{label}: FUTURE_OR_OUT_OF_ORDER_SOURCE")
    age = (freeze - captured).total_seconds() / 3600
    if max_age_hours is not None and age > max_age_hours:
        raise Blocked(f"{label}: STALE_CAPTURE")
    return {"sha256": sha.lower(), "captured_utc": record["captured_utc"],
            "age_hours": round(age, 3)}


def project(game, home, away, league, hca=None, *, max_age_hours=None):
    """Return only *uncalibrated* research expected scores (never a wager).

    The source manifests are caller-supplied assertions. A hash-format check
    does not verify original bytes, provider identity, or a real as-of time.
    """
    if not isinstance(game, dict) or not game.get("game_id"):
        raise Blocked("GAME_ID_REQUIRED")
    season = game.get("season")
    if not isinstance(season, int) or isinstance(season, bool) or season < 2000:
        raise Blocked("SEASON_END_YEAR_REQUIRED")
    home_id, away_id = game.get("home_team_id"), game.get("away_team_id")
    if not all(isinstance(x, str) and x.strip() for x in (home_id, away_id)):
        raise Blocked("EXACT_TEAM_IDS_REQUIRED")
    if home_id == away_id:
        raise Blocked("SAME_TEAM_BOTH_SIDES")
    tip = _utc(game.get("tipoff_utc"), "tipoff_utc")
    freeze = _utc(game.get("freeze_utc"), "freeze_utc")
    if freeze >= tip:
        raise Blocked("MODEL_NOT_FROZEN_BEFORE_TIP")
    model_sha = game.get("model_sha256")
    if not isinstance(model_sha, str) or not SHA_RE.fullmatch(model_sha):
        raise Blocked("MODEL_SHA256_REQUIRED")
    if type(game.get("neutral")) is not bool:
        raise Blocked("EXPLICIT_NEUTRAL_BOOL_REQUIRED")
    if max_age_hours is not None:
        _num(max_age_hours, "max_age_hours", 0.001, 24 * 366)
    manifests = {}
    for key, record, expected_id in (("home", home, home_id),
                                     ("away", away, away_id),
                                     ("league", league, "LEAGUE")):
        if not isinstance(record, dict):
            raise Blocked(f"{key}: RECORD_REQUIRED")
        if record.get("team_id") != expected_id or record.get("season") != season:
            raise Blocked(f"{key}: WRONG_TEAM_OR_SEASON")
        manifests[key] = _evidence(record, key, freeze, max_age_hours)

    hca_pts = 0.0
    if game["neutral"]:
        if hca is not None:
            raise Blocked("NEUTRAL_GAME_MUST_NOT_APPLY_HCA")
    else:
        if hca is None:
            raise Blocked("NONNEUTRAL_HCA_EVIDENCE_REQUIRED")
        if hca.get("team_id") != home_id or hca.get("season") != season:
            raise Blocked("HCA_WRONG_TEAM_OR_SEASON")
        manifests["hca"] = _evidence(hca, "hca", freeze, max_age_hours)
        hca_pts = _num(hca.get("home_court_points"), "hca_points", -20, 20)

    h_o = _num(home.get("adj_o"), "home.adj_o", 1, 250)
    h_d = _num(home.get("adj_d"), "home.adj_d", 1, 250)
    h_t = _num(home.get("adj_tempo"), "home.adj_tempo", 20, 120)
    a_o = _num(away.get("adj_o"), "away.adj_o", 1, 250)
    a_d = _num(away.get("adj_d"), "away.adj_d", 1, 250)
    a_t = _num(away.get("adj_tempo"), "away.adj_tempo", 20, 120)
    lg_o = _num(league.get("league_adj_o"), "league.league_adj_o", 1, 250)
    # League tempo is part of the evidence manifest for future baselines.
    _num(league.get("league_tempo"), "league.league_tempo", 20, 120)

    possessions = (h_t + a_t) / 2  # pre-registered simple baseline, not a fitted formula
    home_points = possessions * h_o * a_d / lg_o / 100 + hca_pts / 2
    away_points = possessions * a_o * h_d / lg_o / 100 - hca_pts / 2
    if min(home_points, away_points) < 0:
        raise Blocked("NEGATIVE_EXPECTED_SCORE")
    return {
        "game_id": game["game_id"],
        "season": season,
        "status": "PAPER_NON_COUNTED_UNCALIBRATED",
        "official": False,
        "stake_u": 0,
        "model_sha256": model_sha.lower(),
        "freeze_utc": game["freeze_utc"],
        "tipoff_utc": game["tipoff_utc"],
        "source_clock_consistent_not_authenticated": manifests,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "possessions": round(possessions, 6),
        "home_points": round(home_points, 6),
        "away_points": round(away_points, 6),
        "margin_home": round(home_points - away_points, 6),
        "total": round(home_points + away_points, 6),
        "ml_probability": None,
        "spread_cover_probability": None,
        "total_over_probability": None,
        "expected_value": None,
        "unmodeled": ["roster_continuity", "injuries", "rest",
                      "travel", "four_factors", "player_props"],
        "blockers_to_bet": ["PROVIDER_ASOF_UNAUTHENTICATED",
                            "MODEL_NOT_WALKFORWARD_CALIBRATED",
                            "NO_VERIFIED_TWO_SIDED_ODDS"],
    }


def research_board(items, *, max_age_hours=None):
    """Retain one explicit result for EVERY attempted game; no silent deletes."""
    results = []
    seen = set()
    for index, item in enumerate(items):
        game = item.get("game") if isinstance(item, dict) else None
        gid = game.get("game_id") if isinstance(game, dict) else None
        try:
            if not isinstance(gid, str) or not gid.strip():
                raise Blocked("GAME_ID_REQUIRED")
            if gid in seen:
                raise Blocked("DUPLICATE_GAME_ID")
            seen.add(gid)
            outcome = project(game, item.get("home"), item.get("away"),
                              item.get("league"), item.get("hca"),
                              max_age_hours=max_age_hours)
        except (Blocked, TypeError, AttributeError, KeyError) as exc:
            outcome = {"game_id": gid, "status": "BLOCKED", "official": False,
                       "stake_u": 0, "reason": str(exc)}
        results.append({"input_index": index, **outcome})
    return results
