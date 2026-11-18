"""Projection-only adapters to the recovered Claude and NFL ridge modules.

This bridge never invokes the older card writers, market no-vig estimate or
suggested stakes. It takes independent score forecasts and returns their mean,
with the model input byte hash. All source timestamps and calibration remain
UNVERIFIED until their actual upstream evidence is independently audited.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path

from .allmarkets_research import _hash,_time,SPORTS


@dataclass(frozen=True)
class TeamProjection:
    sport: str
    event_id: str
    home_id: str
    away_id: str
    expected_home: float
    expected_away: float
    model_sha256: str
    feature_sha256: str
    asof_utc: datetime
    warnings: tuple[str,...] = ("NOT_CHRONOLOGICALLY_CALIBRATED",)

    def __post_init__(self):
        if self.sport not in SPORTS or not self.event_id or not self.home_id or not self.away_id or self.home_id==self.away_id:
            raise ValueError("INVALID_GAME_PROJECTION_IDENTITY")
        if any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) or x<0
               for x in (self.expected_home,self.expected_away)):
            raise ValueError("INVALID_GAME_SCORE_MEANS")
        _hash(self.model_sha256);_hash(self.feature_sha256);_time(self.asof_utc)


def sha_inputs(paths: dict[str,str], *, forbidden: tuple[str,...] = (
    "odds","lines","lines_extra","props","prop_odds","bestbook","dk",
)) -> str:
    """Hash only model feature bytes, never card prices."""
    hasher=sha256()
    seen=0
    for role,p in sorted(paths.items()):
        if role.lower() in forbidden:
            continue
        if not isinstance(p,str):
            raise ValueError("MODEL_FEATURE_FILE_PATH_REQUIRED:"+role)
        path=Path(p)
        if path.is_dir() and role in ("folder","data_dir"):
            # MLB loader accepts a directory; hash each independent CSV input.
            # Neither odds nor prop odds may enter the independent-feature hash.
            inputs=sorted(x for x in path.glob("*.csv") if x.name not in
                          ("odds.csv","prop_odds.csv","bets.csv"))
        else:
            inputs=[path]
        if not inputs or not all(x.is_file() for x in inputs):
            raise ValueError("MODEL_FEATURE_FILE_MISSING:"+role)
        for input_path in inputs:
            raw=input_path.read_bytes()
            if not raw:
                raise ValueError("MODEL_FEATURE_FILE_EMPTY:"+role)
            hasher.update((role+"/"+input_path.name).encode()+b"\0"+sha256(raw).digest())
            seen+=1
    if not seen:
        raise ValueError("NO_INDEPENDENT_MODEL_FEATURE_FILES")
    return "sha256:"+hasher.hexdigest()


def _code_hash(module_file: str) -> str:
    return "sha256:"+sha256(Path(module_file).read_bytes()).hexdigest()


def from_claude_sport(
    sport: str,
    feature_paths: dict[str,str],
    game_id: str,
    *,
    asof_utc: datetime,
) -> TeamProjection:
    """Run recovered projection functions, not their EV/capture/card paths.

    The original model's source-time, injury status, and lineup claims remain
    unverified; avoid passing a current/future data file as historical evidence.
    """
    if sport not in ("CBB","CFB","NBA","MLB"):
        raise ValueError("SPORT_ADAPTER_NOT_AVAILABLE")
    _time(asof_utc)
    # A missing injury file is not evidence of zero injuries. Refuse CBB
    # projections until a captured injury source (including a header-only
    # verified no-injuries export) is supplied and included in the feature hash.
    if sport=="CBB" and not feature_paths.get("injuries"):
        raise ValueError("CBB_CRITICAL_INJURY_SOURCE_REQUIRED")
    features=sha_inputs(feature_paths)
    if sport=="CBB":
        from models.cbb import sportsedge_cbb_model as m
        games=m.read_csv(feature_paths.get("games"))
        g=next((g for g in games if g.get("game_id")==game_id),None)
        if g is None:raise ValueError("GAME_NOT_FOUND_IN_FROZEN_FEATURE_SET")
        teams=m.load_teams(feature_paths["teams"])
        players=m.load_players(feature_paths.get("players"))
        injuries={}
        for i in m.read_csv(feature_paths.get("injuries")):
            injuries.setdefault(i["team"],[]).append(i)
        result=m.project_game(g,teams,injuries,players)
        home,away=g["home"],g["away"]
        home_pts,away_pts=result["home_pts"],result["away_pts"]
    elif sport=="CFB":
        from models.cfb import sportsedge_cfb_model as m
        game_rows=m.load(feature_paths.get("games"))
        g=next((g for g in game_rows if str(g.get("id"))==game_id),None)
        if g is None:raise ValueError("GAME_NOT_FOUND_IN_FROZEN_FEATURE_SET")
        result=m.run_game(g,m.build_ctx(feature_paths))
        home,away=result["home"],result["away"]
        home_pts,away_pts=result["pts_home"],result["pts_away"]
    elif sport=="NBA":
        from models.nba import sportsedge_nba_model as m
        data=m.load_inputs(feature_paths)
        g=next((g for g in data["games"] if g.get("game_id")==game_id),None)
        if g is None:raise ValueError("GAME_NOT_FOUND_IN_FROZEN_FEATURE_SET")
        result=m.project_game(g,data)
        home,away=g["home"],g["away"]
        home_pts,away_pts=result["home_pts"],result["away_pts"]
    else:
        from models.mlb import sportsedge_mlb_model as m
        data=m.load_inputs(feature_paths.get("folder") or feature_paths.get("data_dir"))
        g=next((g for g in data["games"] if g.get("game_id")==game_id),None)
        if g is None:raise ValueError("GAME_NOT_FOUND_IN_FROZEN_FEATURE_SET")
        result=m.project_game(data,g)
        home,away=g["home"],g["away"]
        home_pts,away_pts=result["home"]["runs"],result["away"]["runs"]
    return TeamProjection(sport,game_id,home,away,float(home_pts),float(away_pts),
        _code_hash(m.__file__),features,asof_utc)


def from_nfl_ridge(
    ratings_csv: str,
    forecast: dict,
    *,
    event_id: str,
    frozen_asof_utc: datetime,
) -> TeamProjection:
    """Use recovered NFL ridge forecast recomputation gate, not unverified picks."""
    from research.r5.nfl import sportsedge_nfl_projection_recompute_r1 as m
    if m.gate(ratings_csv,[forecast])["status"]!="PASS":
        raise ValueError("NFL_FORECAST_FAILS_RECOMPUTATION_GATE")
    source=Path(ratings_csv)
    feature_sha="sha256:"+sha256(source.read_bytes()).hexdigest()
    return TeamProjection(
        "NFL",event_id,forecast["home"],forecast["away"],
        float(forecast["home_proj"]),float(forecast["away_proj"]),
        _code_hash(m.__file__),feature_sha,_time(frozen_asof_utc),
        warnings=("NFL_RIDGE_FORMULA_REPRODUCED","HISTORICAL_DATA_AND_PIT_NOT_EXTERNALLY_AUTHENTICATED",
                  "PROP_TD_SHARE_SGP_NOT_INCLUDED"))
