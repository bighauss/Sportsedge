"""CBBD-native pregame CBB score model (research only, PAPER / 0u).

SEPARATE from frozen v5 (``sportsedge_cbb_model.py``) and the Torvik
baselines; it never imports, edits or substitutes into them.

Inputs, all point-in-time at ``freeze_utc``:
* CBBD ``/ratings/adjusted`` bytes captured by
  ``sportsedge.validation.daily_ratings_capture`` (camelCase ``teamId``,
  ``team``, ``season``, ``offensiveRating``, ``defensiveRating``,
  ``netRating``; season 2027 = 2026-27). Exact positive CBBD team IDs only.
* Prior completed games whose final was captured STRICTLY before the freeze
  (exact CBBD game/team IDs, explicit neutral flag, possessions). Later rows
  are counted and rejected, never used.

Formula (additive efficiency, no narrative terms):
  eff_home = ORtg_home + DRtg_away - league_mean_ORtg
  eff_away = ORtg_away + DRtg_home - league_mean_ORtg
  possessions = pace_home * pace_away / league_pace   (prior games only)
  points = eff * possessions / 100 +/- HCA/2 (non-neutral only)
HCA has NO default constant: it is the mean residual of prior non-neutral
games and is recorded with its sample size and standard error. Predictive SDs
come from prior released results only (prospective card residuals when
enough exist, otherwise retro residuals of prior finals, explicitly labelled
as likely understated). Nothing here is validated predictive skill.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean, stdev

MODEL_VERSION = "cbbd-native-additive-v0.1-research"
MODEL_CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
ZULU = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
DEFAULTS = {"min_pace_games": 3, "min_league_games": 30,
            "min_hca_games": 50, "min_sd_games": 30}


class Pass(ValueError):
    """A fail-closed reason code; the caller records it as an explicit PASS."""


def utc(value, name):
    if not isinstance(value, str) or not ZULU.fullmatch(value):
        raise Pass(name + ":UTC_Z_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise Pass(name + ":INVALID_UTC") from exc


def stamp(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def season_of(tip):
    """CBBD season end-year: Aug 2026 - Jul 2027 is season 2027."""
    return tip.year + int(tip.month >= 8)


def canonical_id(value):
    """Exact positive decimal ID string (ints are accepted and stringified)."""
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and value.isascii() and value.isdecimal() and \
            value[0] != "0":
        return value
    return None


def _strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Pass("DUPLICATE_JSON_KEY")
            out[k] = v
        return out

    def bad(_):
        raise Pass("NONFINITE_JSON")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                          parse_constant=bad)
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, Pass):
            raise
        raise Pass("INVALID_JSON") from exc


def parse_ratings(body, season):
    """Map exact CBBD teamId -> ratings. Any malformed row fails the payload."""
    if type(season) is not int:
        raise Pass("RATINGS_SEASON_INVALID")
    doc = _strict_json(body)
    if not isinstance(doc, list) or not doc:
        raise Pass("RATINGS_NOT_A_LIST")
    out = {}
    for row in doc:
        if not isinstance(row, dict) or type(row.get("season")) is not int:
            raise Pass("RATINGS_ROW_SCHEMA")
        if row["season"] != season:
            raise Pass("RATINGS_WRONG_SEASON")
        tid = row.get("teamId")
        if type(tid) is not int or tid <= 0:
            raise Pass("RATINGS_TEAM_ID_INVALID")
        if str(tid) in out:
            raise Pass("RATINGS_DUPLICATE_TEAM_ID")
        vals = [row.get(k) for k in ("offensiveRating", "defensiveRating", "netRating")]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in vals):
            raise Pass("RATINGS_VALUE_INVALID")
        o, d, net = (float(v) for v in vals)
        if not (60 <= o <= 160 and 60 <= d <= 160) or abs((o - d) - net) > 0.5:
            raise Pass("RATINGS_VALUE_OUT_OF_RANGE_OR_NET_INCONSISTENT")
        out[str(tid)] = {"off": o, "def": d, "team": row.get("team")}
    return out


def eligible_prior_games(rows, *, season, freeze):
    """Keep only exact-ID finals captured strictly before ``freeze``.

    Returns (games, census). Duplicated game IDs quarantine EVERY copy.
    """
    census = Counter()
    if not isinstance(rows, list):
        raise Pass("PRIOR_GAMES_NOT_A_LIST")
    ids = Counter(canonical_id(r.get("game_id")) if isinstance(r, dict) else None
                  for r in rows)
    games = []
    for r in rows:
        try:
            if not isinstance(r, dict):
                raise Pass("ROW_NOT_OBJECT")
            gid = canonical_id(r.get("game_id"))
            if gid is None:
                raise Pass("GAME_ID_NONCANONICAL")
            if ids[gid] > 1:
                raise Pass("DUPLICATE_GAME_ID_ALL_COPIES")
            if r.get("season") != season or type(r.get("season")) is not int:
                raise Pass("WRONG_SEASON")
            tip = utc(r.get("tipoff_utc"), "tipoff_utc")
            cap = utc(r.get("final_captured_utc"), "final_captured_utc")
            if season_of(tip) != season:
                raise Pass("TIP_DATE_SEASON_MISMATCH")
            if not tip < cap:
                raise Pass("FINAL_CAPTURED_BEFORE_TIP")
            if cap >= freeze:
                raise Pass("FUTURE_FINAL_AFTER_FREEZE")
            h, a = canonical_id(r.get("home_team_id")), canonical_id(r.get("away_team_id"))
            if h is None or a is None or h == a:
                raise Pass("TEAM_IDS_INVALID")
            hp, ap = r.get("home_points"), r.get("away_points")
            if type(hp) is not int or type(ap) is not int or not (0 <= hp <= 250 and
                                                                   0 <= ap <= 250) or hp == ap:
                raise Pass("FINAL_SCORE_INVALID")
            poss = r.get("possessions")
            if type(poss) not in (int, float) or not math.isfinite(poss) or not 40 <= poss <= 110:
                raise Pass("POSSESSIONS_INVALID")
            if r.get("neutral") not in (True, False, None):
                raise Pass("NEUTRAL_FLAG_INVALID")
        except Pass as exc:
            census["rejected:" + str(exc)] += 1
            continue
        census["eligible"] += 1
        games.append({"game_id": gid, "tip": tip, "captured": cap, "home": h,
                      "away": a, "home_points": hp, "away_points": ap,
                      "possessions": float(poss), "neutral": r["neutral"]})
    games.sort(key=lambda g: (g["captured"], g["game_id"]))
    return games, dict(sorted(census.items()))


def _summary(values):
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "se": None}
    sd = stdev(values) if n >= 2 else None
    return {"n": n, "mean": mean(values), "sd": sd,
            "se": sd / math.sqrt(n) if sd is not None else None}


def fit_context(ratings_body, prior_rows, *, season, freeze_utc,
                prior_residuals=None, settings=None):
    """Build every freeze-time quantity once; record provenance and n."""
    cfg = {**DEFAULTS, **(settings or {})}
    freeze = utc(freeze_utc, "freeze_utc")
    ratings = parse_ratings(ratings_body, season)
    games, census = eligible_prior_games(prior_rows, season=season, freeze=freeze)
    league_off = mean(r["off"] for r in ratings.values())
    poss_by_team = defaultdict(list)
    for g in games:
        poss_by_team[g["home"]].append(g["possessions"])
        poss_by_team[g["away"]].append(g["possessions"])
    ctx = {
        "model_version": MODEL_VERSION, "model_code_sha256": MODEL_CODE_SHA256,
        "season": season, "freeze_utc": stamp(freeze), "settings": cfg,
        "ratings": ratings, "league_mean_ortg": league_off,
        "prior_game_census": census, "prior_games_used": len(games),
        "team_pace": {t: (mean(v), len(v)) for t, v in poss_by_team.items()},
        "league_pace": mean(g["possessions"] for g in games)
        if len(games) >= cfg["min_league_games"] else None,
        "hca": None, "sd": None,
    }
    # HCA: mean residual of prior non-neutral games given each game's actual
    # possessions. Ratings are the freeze-time snapshot (may include those
    # games: in-sample, but no information later than the freeze).
    resid = []
    for g in games:
        if g["neutral"] is not False or g["home"] not in ratings or g["away"] not in ratings:
            continue
        eh, ea = _effs(ctx, g["home"], g["away"])
        resid.append((g["home_points"] - g["away_points"]) - (eh - ea) * g["possessions"] / 100)
    s = _summary(resid)
    ctx["hca"] = {**s, "value": s["mean"] if s["n"] >= cfg["min_hca_games"] else None,
                  "basis": "MEAN_RESIDUAL_PRIOR_NON_NEUTRAL_FINALS",
                  "min_n": cfg["min_hca_games"]}
    ctx["sd"] = _fit_sd(ctx, games, prior_residuals, freeze, cfg)
    return ctx


def _fit_sd(ctx, games, prior_residuals, freeze, cfg):
    prospective = []
    for r in prior_residuals or ():
        if not isinstance(r, dict):
            continue
        try:
            cap = utc(r.get("final_captured_utc"), "residual.final_captured_utc")
        except Pass:
            continue
        m, t = r.get("margin_residual"), r.get("total_residual")
        if cap < freeze and all(type(x) in (int, float) and math.isfinite(x) for x in (m, t)):
            prospective.append((float(m), float(t)))
    if len(prospective) >= cfg["min_sd_games"]:
        pairs, basis = prospective, "PROSPECTIVE_PRIOR_CARD_RESIDUALS"
    else:
        pairs, basis = [], "RETRO_PRIOR_FINALS_IN_SAMPLE_LIKELY_UNDERSTATED"
        for g in games:
            try:
                p = project(ctx, g["home"], g["away"], neutral=g["neutral"],
                            _need_sd=False)
            except Pass:
                continue
            pairs.append(((g["home_points"] - g["away_points"]) - p["margin"],
                          (g["home_points"] + g["away_points"]) - p["total"]))
    n = len(pairs)
    ok = n >= cfg["min_sd_games"]
    return {"n": n, "basis": basis, "min_n": cfg["min_sd_games"],
            "margin": stdev(x[0] for x in pairs) if ok else None,
            "total": stdev(x[1] for x in pairs) if ok else None,
            "prospective_available": len(prospective)}


def _effs(ctx, home, away):
    r = ctx["ratings"]
    lg = ctx["league_mean_ortg"]
    return (r[home]["off"] + r[away]["def"] - lg, r[away]["off"] + r[home]["def"] - lg)


def project(ctx, home, away, *, neutral, _need_sd=True):
    """Expected points, margin, total and predictive SDs, or raise Pass."""
    if neutral not in (True, False):
        raise Pass("NEUTRAL_SITE_UNKNOWN")
    for t in (home, away):
        if t not in ctx["ratings"]:
            raise Pass("UNMAPPED_CBBD_TEAM_ID")
    cfg = ctx["settings"]
    if ctx["league_pace"] is None:
        raise Pass("MISSING_LEAGUE_PACE_HISTORY")
    paces = []
    for t in (home, away):
        pace, n = ctx["team_pace"].get(t, (None, 0))
        if n < cfg["min_pace_games"]:
            raise Pass("MISSING_PACE_HISTORY")
        paces.append(pace)
    hca = 0.0
    if neutral is False:
        if ctx["hca"]["value"] is None:
            raise Pass("HCA_UNMEASURED_INSUFFICIENT_PRIOR_GAMES")
        hca = ctx["hca"]["value"]
    poss = paces[0] * paces[1] / ctx["league_pace"]
    eh, ea = _effs(ctx, home, away)
    hp = eh * poss / 100 + hca / 2
    ap = ea * poss / 100 - hca / 2
    out = {"home_points": hp, "away_points": ap, "margin": hp - ap,
           "total": hp + ap, "possessions": poss, "hca_applied": hca}
    if _need_sd:
        if ctx["sd"]["margin"] is None or ctx["sd"]["total"] is None:
            raise Pass("PREDICTIVE_SD_UNMEASURED")
        out.update(sd_margin=ctx["sd"]["margin"], sd_total=ctx["sd"]["total"],
                   sd_basis=ctx["sd"]["basis"], sd_n=ctx["sd"]["n"])
    return out


def _cdf(z):
    return (1 + math.erf(z / math.sqrt(2))) / 2


def _line_probs(mu, sd, threshold):
    """P(X > threshold), P(push), P(X < threshold); integer lines push."""
    if sd is None or sd <= 0:
        raise Pass("PREDICTIVE_SD_INVALID")
    if float(threshold).is_integer():
        lo, hi = _cdf((threshold - 0.5 - mu) / sd), _cdf((threshold + 0.5 - mu) / sd)
        return 1 - hi, hi - lo, lo
    below = _cdf((threshold - mu) / sd)
    return 1 - below, 0.0, below


def market_probs(proj, market, line=None):
    """Model probabilities for (side_a, push, side_b).

    moneyline: (home, 0, away); spread: home line L, home covers if
    margin + L > 0; total: (over, push, under).
    """
    if market == "moneyline":
        p = _cdf(proj["margin"] / proj["sd_margin"])
        return p, 0.0, 1 - p
    if market == "spread":
        return _line_probs(proj["margin"], proj["sd_margin"], -line)
    if market == "total":
        return _line_probs(proj["total"], proj["sd_total"], line)
    raise Pass("MARKET_UNSUPPORTED")


def decimal_odds(american):
    if type(american) is not int or abs(american) < 100 or abs(american) > 100000:
        raise Pass("INVALID_AMERICAN_PRICE")
    return 1 + (american / 100 if american > 0 else 100 / -american)


def no_vig(price_a, price_b):
    a, b = 1 / decimal_odds(price_a), 1 / decimal_odds(price_b)
    return a / (a + b), b / (a + b), a + b - 1


def ev_per_unit(p_win, p_push, price):
    """Paper expected return per 1u at the ACTUAL price (push refunds)."""
    p_loss = 1 - p_win - p_push
    return p_win * (decimal_odds(price) - 1) - p_loss
