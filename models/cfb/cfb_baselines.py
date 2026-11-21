"""Versioned CFB forecast baselines for the PAPER card. Research only, PAPER / 0u.

Two baselines, both limited to full-game margin / total / moneyline:

* ``FROZEN_RUNIT`` wraps ``models/cfb/sportsedge_cfb_model.py`` EXACTLY as
  committed (untested starting weights). The module file SHA-256 and every
  constant are pinned below; any drift refuses to forecast instead of silently
  running a changed production model. This wrapper never edits a weight.
* ``RATINGS_ONLY_SP`` is a deliberately simple comparator: SP+ offense /
  defense ratings centred on the captured file's FBS means, plus a fixed home
  field constant. It exists to show whether the RUN IT blend beats ratings.

Neither baseline is validated. Passing unit tests is NOT predictive validation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from statistics import NormalDist

from models.cfb import sportsedge_cfb_model as runit

HERE = Path(__file__).resolve().parent
FROZEN_MODEL_FILE = HERE / "sportsedge_cfb_model.py"

# Pinned at registration (origin/main 054c907e, file last changed in 0f38c3cb).
FROZEN_RUNIT = {
    "model_id": "sportsedge-cfb-runit-2026-11-15-untested-v1",
    "module": "models/cfb/sportsedge_cfb_model.py",
    "module_sha256": "1f24cf1a925147a1601d0ba2f04ada30c4cf25173ab6df73bcb16016cff735be",
    "source_commit": "0f38c3cb23be540322cac4936eb2e249a196ba0b",
    # Games kicking off before this instant were available while the model's
    # untested constants were chosen, so they are never "untouched" holdout.
    "registered_utc": "2026-11-22T00:00:00Z",
    "weights_validated": False,
    "markets": ["ML", "SPREAD", "TOTAL"],
}
FROZEN_CONSTANTS = {
    "K_REGRESS": 6.0, "PRIOR_FADE_WEEK": 6, "W_RATINGS": 0.50, "W_MATCHUP": 0.50,
    "LG_PPG": 28.0, "LG_PLAYS": 70.0, "PTS_PER_PPA_PLAY": 1.0,
    "SD_MARGIN": 15.5, "SD_TOTAL": 15.0, "SD_TT": 11.0, "SD_1H": 11.0,
    "H1_SHARE": 0.5, "HFA_DEFAULT": 2.5,
    "INJ": {"QB": -5.5, "STAR_SKILL": -1.5, "OL": -0.75},
    "MULTI_DB_OUT_OPP": 1.5, "TRAVEL_TZ_PEN": -0.5, "SHORT_WEEK_PEN": -0.5,
    "WIND_PEN": -2.0, "PRECIP_PEN": {"heavy_rain": -2.0, "snow": -3.0},
    "ALTITUDE_FT": 5000, "ALTITUDE_HOME": 1.0, "P_BLEND_MODEL": 0.30,
    "PROP_MODEL_W": 0.70,
    "PROP_SD_FRAC": {"rush_yds": 0.45, "rec_yds": 0.50, "pass_yds": 0.28, "receptions": 0.40},
}

RATINGS_ONLY_SP = {
    "model_id": "sportsedge-cfb-sp-ratings-only-v1",
    "description": "points = SP+ offense (centred) + opponent SP+ defense (centred) + league mean; HFA 2.5",
    "registered_utc": "2026-11-22T00:00:00Z",
    "weights_validated": False,
    "markets": ["ML", "SPREAD", "TOTAL"],
}
# Fixed, untuned comparator constants. Same Normal SDs as the frozen model so
# probability differences reflect the mean forecast, not a different spread.
RATINGS_ONLY_CONSTANTS = {"HFA": 2.5, "SD_MARGIN": 15.5, "SD_TOTAL": 15.0, "MIN_TEAM_POINTS": 3.0}

_N = NormalDist()


class ModelRefused(ValueError):
    pass


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def constants_sha256(constants) -> str:
    return sha256(_canon(constants)).hexdigest()


def live_frozen_constants() -> dict:
    return {k: getattr(runit, k) for k in FROZEN_CONSTANTS}


def verify_frozen_model() -> dict:
    """Refuse if the RUN IT module bytes or any constant drifted from the pin."""
    digest = sha256(FROZEN_MODEL_FILE.read_bytes()).hexdigest()
    if digest != FROZEN_RUNIT["module_sha256"]:
        raise ModelRefused("FROZEN_MODEL_FILE_SHA_DRIFT")
    if live_frozen_constants() != FROZEN_CONSTANTS:
        raise ModelRefused("FROZEN_MODEL_CONSTANT_DRIFT")
    return {**FROZEN_RUNIT, "constants_sha256": constants_sha256(FROZEN_CONSTANTS)}


def ratings_only_version() -> dict:
    return {**RATINGS_ONLY_SP, "constants_sha256": constants_sha256(RATINGS_ONLY_CONSTANTS)}


def p_greater(mean, line, sd):
    """P(X > line) under Normal(mean, sd); continuous, so pushes have zero mass."""
    return 1.0 - _N.cdf((line - mean) / sd)


def _summary(model_id, pts_home, pts_away, sd_margin, sd_total, extra=None):
    margin, total = pts_home - pts_away, pts_home + pts_away
    out = {"model_id": model_id, "status": "PROJECTED",
           "pts_home": round(pts_home, 4), "pts_away": round(pts_away, 4),
           "margin_home": round(margin, 4), "total": round(total, 4),
           "sd_margin": sd_margin, "sd_total": sd_total,
           "p_home_win": round(p_greater(margin, 0.0, sd_margin), 6)}
    if extra:
        out.update(extra)
    return out


def frozen_runit_forecast(game_row: dict, ctx: dict) -> dict:
    """Run the untouched RUN IT ``run_game``; returns full-game numbers only."""
    verify_frozen_model()
    proj = runit.run_game(game_row, ctx)
    return _summary(FROZEN_RUNIT["model_id"], proj["pts_home"], proj["pts_away"],
                    runit.SD_MARGIN, runit.SD_TOTAL,
                    {"model_notes": list(proj["notes"]), "weather_note": proj["weather"],
                     "hfa": proj["hfa"]})


def sp_means(sp_rows):
    off = [r["offense"]["rating"] for r in sp_rows]
    dfn = [r["defense"]["rating"] for r in sp_rows]
    if not off or not dfn:
        raise ModelRefused("SP_RATINGS_EMPTY")
    return sum(off) / len(off), sum(dfn) / len(dfn)


def ratings_only_forecast(home_sp: dict, away_sp: dict, *, neutral: bool, means) -> dict:
    mean_off, mean_def = means
    c = RATINGS_ONLY_CONSTANTS
    lg = runit.LG_PPG
    hfa = 0.0 if neutral else c["HFA"]

    def pts(off_row, def_row):
        return lg + (off_row["offense"]["rating"] - mean_off) + (def_row["defense"]["rating"] - mean_def)

    ph = max(c["MIN_TEAM_POINTS"], pts(home_sp, away_sp) + hfa / 2)
    pa = max(c["MIN_TEAM_POINTS"], pts(away_sp, home_sp) - hfa / 2)
    return _summary(RATINGS_ONLY_SP["model_id"], ph, pa, c["SD_MARGIN"], c["SD_TOTAL"], {"hfa": hfa})


def pass_forecast(model_id, reasons) -> dict:
    reasons = sorted(set(reasons))
    if not reasons:
        raise ModelRefused("PASS_REQUIRES_REASON")
    return {"model_id": model_id, "status": "PASS", "pass_reasons": reasons}
