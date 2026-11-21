"""Pre-kickoff CFB game-record assembler. Research only, PAPER / 0u.

Turns a private capture directory (CFBD games / advanced stats / talent /
returning production + operator QB and injury files), the daily SP+ ratings
capture (``sportsedge.validation.daily_ratings_capture``) and Open-Meteo
FORECAST captures (``sportsedge.data.open_meteo_pit``) into one normalized
record per game, audited through ``models.cfb.cfb_source_pit_contract``.

Point-in-time rules enforced here:
* only captures with ``captured_utc <= frozen_utc < kickoff`` are eligible;
  a later capture is ignored, never merged;
* a games file that already contains a completed result for a target game, or
  claims a completion before its own capture clock, is refused as
  post-game / historical evidence;
* every file must match the capture season exactly; team identity is the
  exact CFBD team ID from the games file, joined to name-keyed CFBD files by
  that game's exact school string (no fuzzy matching);
* starting-QB status unknown or missing => explicit HOLD; injuries come only
  from an operator file that lists the game as reviewed (an empty list is
  recorded as NOT proof of no injuries);
* weather is an Open-Meteo forecast captured before the freeze for that
  exact event and kickoff; never a retrospective actual.

Every game yields READY, HOLD (reasons) or PASS (reasons). Nothing here is
predictive validation or a wager signal.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from models.cfb import cfb_capture_store as store
from models.cfb import cfb_source_pit_contract as contract
from models.cfb import sportsedge_cfb_model as runit
from models.cfb.cfb_capture_store import CaptureRefused, utc, stamp
from sportsedge.data import open_meteo_pit
from sportsedge.validation import daily_ratings_capture as ratings_capture

QB_SCHEMA = "sportsedge-cfb-operator-qb-v1"
INJURY_SCHEMA = "sportsedge-cfb-operator-injuries-v1"
QB_STATUSES = ("CONFIRMED", "QUESTIONABLE", "OUT", "UNKNOWN")
INJURY_STATUSES = ("OUT", "QUESTIONABLE", "PROBABLE", "AVAILABLE", "UNKNOWN")
INJURY_ROLES = ("QB", "STAR_SKILL", "DB", "OL", "OTHER")
SP_MAX_AGE_SECONDS = 8 * 86400
NONBLOCKING_CONTRACT_REASONS = ("ORIGINAL_ALL_MARKET_QUOTES_INCOMPLETE",)
OUT_OF_SCOPE_FAMILIES = ("TEAM_TOTAL", "PLAYER_PROP", "PERIOD", "SPECIAL", "ALTERNATE", "SGP")


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def event_id(season, gid):
    return f"cfbd:{season}:{gid}"


def team_id(tid):
    return f"cfbd-team:{tid}"


def weather_event_id(season, gid):
    # open_meteo_pit event ids may not contain ':'.
    return f"cfbd-{season}-{gid}"


def _list(doc, code):
    if not isinstance(doc, list) or any(not isinstance(r, dict) for r in doc):
        raise CaptureRefused(code)
    return doc


def _num(v):
    return type(v) in (int, float)


# ------------------------------------------------------------------ CFBD files
def parse_games(body, receipt, season, week, season_type):
    rows = _list(store.strict_json(body), "GAMES_SCHEMA")
    captured = utc(receipt["captured_utc"])
    games, seen, names = {}, set(), {}
    for r in rows:
        gid = r.get("id")
        if type(gid) is not int or gid <= 0 or gid in seen:
            raise CaptureRefused("GAMES_ID_INVALID_OR_DUPLICATE")
        seen.add(gid)
        if r.get("season") != season or type(r.get("season")) is not int:
            raise CaptureRefused("GAMES_WRONG_SEASON")
        for side in ("home", "away"):
            tid, name = r.get(side + "Id"), r.get(side + "Team")
            if type(tid) is not int or tid <= 0 or not isinstance(name, str) or not name.strip():
                raise CaptureRefused("GAMES_TEAM_IDENTITY_INVALID")
            if names.setdefault(name, tid) != tid:
                raise CaptureRefused("GAMES_TEAM_NAME_ID_CONFLICT")
        if r["homeId"] == r["awayId"]:
            raise CaptureRefused("GAMES_IDENTICAL_HOME_AWAY")
        start = utc(_z(r.get("startDate")), "startDate")
        done = r.get("completed") is True or r.get("homePoints") is not None or r.get("awayPoints") is not None
        if done and start > captured:
            # A result for a game that had not started when the file was
            # captured is impossible: the clock or the file is not pregame.
            raise CaptureRefused("GAMES_FILE_CLOCK_INCONSISTENT")
        if r.get("week") != week or r.get("seasonType", season_type) != season_type:
            continue
        games[gid] = {**r, "_kickoff": start, "_completed_in_file": done}
    if len(set(names.values())) != len(names):
        raise CaptureRefused("GAMES_TEAM_ID_SHARED_BY_TWO_NAMES")
    return games


def _z(value):
    """CFBD startDate such as 2026-11-21T20:30:00.000Z -> strict Z string."""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CaptureRefused("GAME_START_NOT_UTC")
    t = utc(value, "startDate")
    return stamp(t.replace(microsecond=0)) if t.microsecond == 0 else stamp(t)


def _by_team(rows, season_key, season, code):
    out = {}
    for r in rows:
        if r.get(season_key) != season or type(r.get(season_key)) is not int:
            raise CaptureRefused(code + "_WRONG_SEASON")
        name = r.get("team")
        if not isinstance(name, str) or not name.strip() or name in out:
            raise CaptureRefused(code + "_TEAM_INVALID_OR_DUPLICATE")
        out[name] = r
    return out


def parse_advanced(body, season):
    rows = _list(store.strict_json(body), "ADVANCED_SCHEMA")
    out = _by_team(rows, "season", season, "ADVANCED")
    for r in out.values():
        for side in ("offense", "defense"):
            s = r.get(side)
            if not isinstance(s, dict) or not _num(s.get("ppa")):
                raise CaptureRefused("ADVANCED_PPA_MISSING")
        if not _num(r["offense"].get("plays")) or not _num(r["offense"].get("drives")):
            raise CaptureRefused("ADVANCED_VOLUME_MISSING")
    return out


def parse_talent(body, season):
    out = _by_team(_list(store.strict_json(body), "TALENT_SCHEMA"), "year", season, "TALENT")
    for r in out.values():
        if not _num(r.get("talent")):
            raise CaptureRefused("TALENT_VALUE_INVALID")
    return out


def parse_returning(body, season):
    out = _by_team(_list(store.strict_json(body), "RETURNING_SCHEMA"), "season", season, "RETURNING")
    for r in out.values():
        if not _num(r.get("percentPPA")) or not 0 <= r["percentPPA"] <= 1.5:
            raise CaptureRefused("RETURNING_VALUE_INVALID")
    return out


# ------------------------------------------------------------------ SP+ (daily ratings capture)
def select_sp(ratings_dirs, season, frozen, kickoff):
    """Newest daily-ratings capture of cfbd_ratings_sp eligible at the freeze."""
    best = None
    for d in ratings_dirs or ():
        d = Path(d)
        try:
            doc = store.strict_json(store.read_private(d / "receipt.json"))
        except (OSError, CaptureRefused):
            continue
        for rec in doc.get("receipts", []) if isinstance(doc, dict) else []:
            if not isinstance(rec, dict) or rec.get("source") != "cfbd_ratings_sp" or rec.get("state") != "CAPTURED":
                continue
            try:
                body = store.read_private(d / rec["file"])
                ratings_capture.eligible_bytes(body, rec, source="cfbd_ratings_sp", season=season,
                                               decision=frozen, kickoff=kickoff,
                                               max_age_seconds=SP_MAX_AGE_SECONDS)
            except (OSError, KeyError, TypeError, ValueError):
                continue
            try:
                observed = utc(_zs(rec["observed_utc"]))
            except (CaptureRefused, AttributeError):
                continue
            if best is None or observed > best[0]:
                best = (observed, rec, body)
    if best is None:
        return None
    rows = json.loads(best[2])
    return {"receipt": best[1], "rows": {r["team"]: r for r in rows}, "observed": best[0]}


# ------------------------------------------------------------------ weather (Open-Meteo forecast)
def select_weather(weather_dir, season, gid, kickoff, frozen):
    if weather_dir is None:
        return None, "WEATHER_FORECAST_MISSING"
    d = store.private_dir(weather_dir)
    target = weather_event_id(season, gid)
    best = None
    for rp in sorted(d.glob(target + "_*.openmeteo.report.json")):
        rep = store.strict_json(store.read_private(rp))
        if not isinstance(rep, dict) or rep.get("event_id") != target:
            continue
        cap = utc(rep.get("source_local_capture_utc"), "weather_capture")
        if cap > frozen:
            continue
        if best is None or cap > best[0]:
            best = (cap, rep, rp)
    if best is None:
        return None, "WEATHER_FORECAST_MISSING"
    cap, rep, rp = best
    if rep.get("sport") != "CFB":
        return None, "WEATHER_FORECAST_WRONG_SPORT"
    if utc(rep.get("event_start_utc")) != kickoff:
        return None, "WEATHER_FORECAST_FOR_DIFFERENT_KICKOFF"
    raw = store.read_private(d / rep.get("original_file_basename", ""))
    if "sha256:" + sha256(raw).hexdigest() != rep.get("source_raw_sha256"):
        return None, "WEATHER_ORIGINAL_SHA_MISMATCH"
    request = {"schema": open_meteo_pit.SCHEMA, "sport": "CFB", "event_id": target,
               "event_start_utc": rep["event_start_utc"], "venue_id": rep.get("venue_id"),
               "latitude": rep.get("latitude_requested"), "longitude": rep.get("longitude_requested"),
               "coordinate_source": rep.get("coordinate_source_claim"),
               "roof_status": rep.get("roof_status_owner_claim"),
               "purpose": "PERSONAL_NONCOMMERCIAL_RESEARCH"}
    try:
        parsed = open_meteo_pit.parse_hourly(raw, request, now=cap)
    except (open_meteo_pit.ForecastSourceError, TypeError):
        return None, "WEATHER_FORECAST_REPARSE_FAILED"
    if parsed["event_hour_forecast"] != rep.get("event_hour_forecast"):
        return None, "WEATHER_REPORT_DISAGREES_WITH_ORIGINAL"
    return {"report": rep, "captured": cap, "raw_sha256": rep["source_raw_sha256"],
            "forecast": parsed["event_hour_forecast"], "roof": request["roof_status"]}, None


# ------------------------------------------------------------------ operator files
def parse_qb(body, season):
    doc = store.strict_json(body)
    if not isinstance(doc, dict) or doc.get("schema") != QB_SCHEMA or doc.get("season") != season:
        raise CaptureRefused("OPERATOR_QB_SCHEMA_OR_SEASON")
    return _list(doc.get("rows"), "OPERATOR_QB_ROWS")


def parse_injuries(body, season):
    doc = store.strict_json(body)
    if not isinstance(doc, dict) or doc.get("schema") != INJURY_SCHEMA or doc.get("season") != season:
        raise CaptureRefused("OPERATOR_INJURY_SCHEMA_OR_SEASON")
    reviewed = doc.get("games_reviewed")
    if not isinstance(reviewed, list) or any(type(g) is not int for g in reviewed):
        raise CaptureRefused("OPERATOR_INJURY_REVIEW_CENSUS_REQUIRED")
    return set(reviewed), _list(doc.get("rows"), "OPERATOR_INJURY_ROWS")


def _side_rows(rows, gid, teams_by_id, label, reasons):
    """Rows for one game; borrowed team IDs or names disagreeing with the ID are refused."""
    out = []
    for r in rows:
        if r.get("cfbd_game_id") != gid:
            continue
        tid = r.get("team_id")
        if tid not in teams_by_id:
            reasons.append(label + "_BORROWED_TEAM_ID")
            continue
        if "team" in r and r["team"] != teams_by_id[tid]:
            reasons.append(label + "_TEAM_NAME_ID_MISMATCH")
            continue
        out.append(r)
    return out


# ------------------------------------------------------------------ assembly
def _clock(rec):
    published = rec.get("published_utc") or rec["observed_utc"]
    return {"provider": rec["provider"], "published_utc": published,
            "observed_utc": rec["observed_utc"], "captured_utc": rec["captured_utc"]}


def _derived_clock(clocks, provider):
    return {"provider": provider,
            "published_utc": max(clocks, key=lambda c: utc(c["published_utc"]))["published_utc"],
            "observed_utc": max(clocks, key=lambda c: utc(c["observed_utc"]))["observed_utc"],
            "captured_utc": max(clocks, key=lambda c: utc(c["captured_utc"]))["captured_utc"]}


def _lineage(rec):
    return {"source": rec.get("source"), "provider": rec["provider"], "sha256": rec["sha256"],
            "observed_utc": rec["observed_utc"], "captured_utc": rec["captured_utc"]}


def assemble_slate(capture_dir, *, frozen_utc, ratings_dirs=(), weather_dir=None,
                   quote_receipts=None) -> dict:
    """Return {meta, games: [record]}; raises CaptureRefused on slate-level integrity faults.

    ``quote_receipts`` maps cfbd_game_id -> {"ML"|"SPREAD"|"TOTAL": sha256 hex}
    for the contract's market-family census (other families NOT_CAPTURED).
    """
    frozen = utc(frozen_utc, "frozen_utc")
    meta = store.load_capture(capture_dir)
    season, week, stype = meta["season"], meta["week"], meta["season_type"]
    sel = {s: store.select_source(capture_dir, s, frozen) for s in store.SOURCES}
    games_rec, games_body = sel["cfbd_games"]
    if games_rec is None:
        raise CaptureRefused("NO_GAMES_FILE_CAPTURED_BEFORE_FREEZE")
    games = parse_games(games_body, games_rec, season, week, stype)
    adv = parse_advanced(sel["cfbd_advanced"][1], season) if sel["cfbd_advanced"][0] else None
    talent = parse_talent(sel["cfbd_talent"][1], season) if sel["cfbd_talent"][0] else None
    ret = parse_returning(sel["cfbd_returning"][1], season) if sel["cfbd_returning"][0] else None
    qb_rows = parse_qb(sel["operator_qb"][1], season) if sel["operator_qb"][0] else None
    inj = parse_injuries(sel["operator_injuries"][1], season) if sel["operator_injuries"][0] else None
    lm = runit.league_means(list(adv.values())) if adv else None
    records = []
    for gid in sorted(games, key=lambda g: (games[g]["_kickoff"], g)):
        records.append(_assemble_game(
            games[gid], meta=meta, frozen=frozen, sel=sel, adv=adv, lm=lm, talent=talent, ret=ret,
            qb_rows=qb_rows, inj=inj, ratings_dirs=ratings_dirs, weather_dir=weather_dir,
            quote_receipts=(quote_receipts or {}).get(gid, {})))
    return {"schema": "sportsedge-cfb-pregame-slate-v1", "season": season, "week": week,
            "season_type": stype, "frozen_utc": stamp(frozen),
            "source_receipts": {s: (_lineage(r) if r else None) for s, (r, _) in sel.items()},
            "games": records, "official_counted": 0, "approved_stake_u": 0}


def _assemble_game(g, *, meta, frozen, sel, adv, lm, talent, ret, qb_rows, inj, ratings_dirs,
                   weather_dir, quote_receipts):
    season, week = meta["season"], meta["week"]
    gid, kickoff = g["id"], g["_kickoff"]
    H, A = g["homeTeam"], g["awayTeam"]
    hid, aid = g["homeId"], g["awayId"]
    teams_by_id = {hid: H, aid: A}
    rec = {"cfbd_game_id": gid, "event_id": event_id(season, gid), "season": season, "week": week,
           "kickoff_utc": stamp(kickoff), "home_team": H, "away_team": A,
           "home_team_id": hid, "away_team_id": aid, "neutral_site": bool(g.get("neutralSite")),
           "status": None, "reasons": [], "notes": [], "lineage": {}, "contract": None}
    passes, holds = [], []
    if g.get("startTimeTBD") is True:
        passes.append("KICKOFF_TIME_TBD")
    if kickoff <= frozen:
        passes.append("KICKOFF_NOT_AFTER_FREEZE")
    if g["_completed_in_file"]:
        passes.append("GAME_ALREADY_COMPLETED_IN_SOURCE_FILE_NOT_PREGAME")
    rec["lineage"]["cfbd_games"] = _lineage(sel["cfbd_games"][0])
    for src in ("cfbd_advanced", "cfbd_talent", "cfbd_returning"):
        r = sel[src][0]
        if r is None:
            continue
        rec["lineage"][src] = _lineage(r)
        if utc(r["captured_utc"]) >= kickoff:
            passes.append("SEASON_FILE_CAPTURED_AFTER_KICKOFF:" + src)
    if adv is None:
        passes.append("ADVANCED_STATS_FILE_MISSING")
    else:
        for name in (H, A):
            if name not in adv:
                passes.append("ADVANCED_STATS_MISSING:" + name)
    early = week < runit.PRIOR_FADE_WEEK
    for label, table in (("TALENT", talent), ("RETURNING", ret)):
        if table is None or any(n not in table for n in (H, A)):
            (passes if early else rec["notes"]).append(
                ("PRESEASON_PRIOR_MISSING:" if early else "PRIOR_MISSING_NO_EFFECT_AFTER_FADE:") + label)
    sp = select_sp(ratings_dirs, season, frozen, kickoff) if kickoff > frozen else None
    if sp is None:
        passes.append("SP_RATINGS_NOT_ELIGIBLE_AT_FREEZE")
    else:
        rec["lineage"]["cfbd_ratings_sp"] = {
            "source": "cfbd_ratings_sp", "provider": "collegefootballdata.com",
            "sha256": sp["receipt"]["sha256"], "observed_utc": sp["receipt"]["observed_utc"],
            "captured_utc": sp["receipt"]["observed_utc"]}
        for name in (H, A):
            if name not in sp["rows"]:
                passes.append("SP_RATING_MISSING:" + name)
    weather, wx_reason = (None, None)
    if kickoff > frozen:
        weather, wx_reason = select_weather(weather_dir, season, gid, kickoff, frozen)
    if wx_reason:
        passes.append(wx_reason)
    elif weather:
        rec["lineage"]["open_meteo_forecast"] = {
            "source": "open_meteo_forecast", "provider": "OPEN_METEO_FREE",
            "sha256": weather["raw_sha256"], "observed_utc": stamp(weather["captured"]),
            "captured_utc": stamp(weather["captured"])}
    # Starting QB: unknown or missing => HOLD, never a guess.
    qb_norm = []
    if qb_rows is None:
        holds.append("QB_STATUS_FILE_MISSING")
    else:
        rec["lineage"]["operator_qb"] = _lineage(sel["operator_qb"][0])
        rows = _side_rows(qb_rows, gid, teams_by_id, "QB", passes)
        for tid in (hid, aid):
            mine = [r for r in rows if r["team_id"] == tid]
            if len(mine) > 1:
                passes.append("QB_DUPLICATE_TEAM_ROW")
                continue
            if not mine:
                holds.append(f"QB_STATUS_UNKNOWN:{tid}")
                qb_norm.append({"team_id": team_id(tid), "qb_id": "UNKNOWN", "starter_status": "UNKNOWN"})
                continue
            r = mine[0]
            status = r.get("starter_status") if r.get("starter_status") in QB_STATUSES else "UNKNOWN"
            qb_norm.append({"team_id": team_id(tid), "qb_id": str(r.get("qb_id") or "UNKNOWN"),
                            "starter_status": status})
    inj_norm, inj_model = [], []
    if inj is None:
        passes.append("INJURY_REPORT_MISSING")
    else:
        reviewed, inj_rows = inj
        rec["lineage"]["operator_injuries"] = _lineage(sel["operator_injuries"][0])
        if gid not in reviewed:
            passes.append("INJURY_REPORT_NOT_REVIEWED_FOR_GAME")
        rows = _side_rows(inj_rows, gid, teams_by_id, "INJURY", passes)
        if gid in reviewed and not rows:
            rec["notes"].append("INJURY_LIST_EMPTY_NOT_PROOF_OF_NO_INJURIES")
        for r in rows:
            if r.get("role") not in INJURY_ROLES:
                passes.append("INJURY_ROLE_INVALID")
                continue
            inj_norm.append({"team_id": team_id(r["team_id"]), "player_id": str(r.get("player_id")),
                             "status": r.get("status")})
            model_row = {"team": teams_by_id[r["team_id"]], "player": r.get("player") or str(r.get("player_id")),
                         "role": r["role"], "status": r.get("status")}
            if _num(r.get("impact")):
                model_row["impact"] = r["impact"]
            inj_model.append(model_row)
    if passes:
        rec.update(status="PASS", reasons=sorted(set(passes + holds)))
        return rec
    if holds and qb_rows is None:
        rec.update(status="HOLD", reasons=sorted(set(holds)))
        return rec
    # ---------------- normalized contract input (exact IDs, hashed, clocked)
    payloads = {
        "game": {"event_id": rec["event_id"], "season": season, "kickoff_utc": rec["kickoff_utc"],
                 "home_team_id": team_id(hid), "away_team_id": team_id(aid)},
        "team_stats": [_stats_row(adv[n], tid, season) for n, tid in ((H, hid), (A, aid))],
        "qb": qb_norm,
        "weather": {"event_id": rec["event_id"], "is_forecast": True,
                    "wind_mph": weather["forecast"]["wind_speed_10m"],
                    "forecast_valid_hour_utc": weather["report"]["forecast_valid_hour_utc"],
                    "roof_status_owner_claim": weather["roof"]},
        "injuries": inj_norm,
    }
    raw = {k: canon(v) for k, v in payloads.items()}
    stat_clocks = [_clock(sel["cfbd_advanced"][0])]
    if early:
        stat_clocks += [_clock(sel["cfbd_talent"][0]), _clock(sel["cfbd_returning"][0])]
    spr = sp["receipt"]
    stat_clocks.append({"provider": "collegefootballdata.com", "published_utc": _zs(spr["observed_utc"]),
                        "observed_utc": _zs(spr["observed_utc"]), "captured_utc": _zs(spr["observed_utc"])})
    wcap = stamp(weather["captured"])
    clocks = {
        "game": _clock(sel["cfbd_games"][0]),
        "team_stats": _derived_clock(stat_clocks, "collegefootballdata.com:derived"),
        "qb": _clock(sel["operator_qb"][0]),
        "weather": {"provider": "OPEN_METEO_FREE", "published_utc": wcap, "observed_utc": wcap,
                    "captured_utc": wcap},
        "injuries": _clock(sel["operator_injuries"][0]),
    }
    for k in contract.SOURCES:
        clocks[k]["sha256"] = sha256(raw[k]).hexdigest()
    census = []
    for fam in contract.FAMILIES:
        if fam in OUT_OF_SCOPE_FAMILIES:
            census.append({"family": fam, "state": "NOT_CAPTURED",
                           "reason": "OUT_OF_SCOPE_FULL_GAME_ML_SPREAD_TOTAL_ONLY"})
        elif quote_receipts.get(fam):
            census.append({"family": fam, "state": "CAPTURED_UNVERIFIED", "receipt_sha256": quote_receipts[fam]})
        else:
            census.append({"family": fam, "state": "NOT_CAPTURED", "reason": "NO_PREFREEZE_TWO_SIDED_QUOTE"})
    manifest = {"schema": contract.SCHEMA, "event_id": rec["event_id"], "season": season,
                "frozen_utc": stamp(frozen), "kickoff_utc": rec["kickoff_utc"],
                "source_clock_receipts": clocks, "market_family_census": census}
    try:
        verdict = contract.audit(raw, manifest)
    except contract.PITRefused as exc:
        rec.update(status="PASS", reasons=["CONTRACT_REFUSED:" + str(exc)])
        return rec
    rec["contract"] = {"status": verdict["status"], "reasons": verdict["reasons"],
                       "normalized_source_sha256": verdict["source_raw_sha256"],
                       "source_clock_receipts": clocks}
    blocking = [r for r in verdict["reasons"] if r not in NONBLOCKING_CONTRACT_REASONS]
    if blocking or holds:
        rec.update(status="HOLD", reasons=sorted(set(blocking + holds)))
        return rec
    rec["status"] = "READY"
    # ---------------- model inputs (consumed in-process, never re-read later)
    mean_off = sum(r["offense"]["rating"] for r in sp["rows"].values()) / len(sp["rows"])
    mean_def = sum(r["defense"]["rating"] for r in sp["rows"].values()) / len(sp["rows"])
    centred = {}
    for name, r in sp["rows"].items():
        centred[name] = {"team": name, "rating": r["rating"],
                         "offense": {"rating": r["offense"]["rating"] - mean_off},
                         "defense": {"rating": r["defense"]["rating"] - mean_def}}
    roof = "open" if weather["roof"] == "OPEN" else "closed"
    if roof == "closed":
        rec["notes"].append("WEATHER_NOT_APPLIED_ROOF_NOT_CONFIRMED_OPEN")
    rec["notes"].append("PRECIP_TYPE_NOT_IN_FORECAST_FIELDS_NO_PRECIP_ADJUSTMENT")
    rec["_model"] = {
        "game_row": {"id": gid, "homeTeam": H, "awayTeam": A, "week": week,
                     "neutralSite": bool(g.get("neutralSite")), "venue": g.get("venue")},
        "ctx": {"adv": adv, "lm": lm, "talent": talent or {}, "ret": ret or {}, "ratings": centred,
                "teams": {}, "venues": {}, "injuries": inj_model,
                "weather": {gid: {"gameId": gid, "windSpeed": weather["forecast"]["wind_speed_10m"],
                                  "precipitation_type": "not_in_forecast_fields",
                                  "isForecast": True, "roof": roof}},
                "rest": {}, "cross": {}, "usage": []},
        "sp_home": sp["rows"][H], "sp_away": sp["rows"][A], "sp_means": (mean_off, mean_def),
    }
    return rec


def _zs(value):
    """daily_ratings_capture stamps may carry microseconds; keep a strict Z string."""
    return stamp(utc(value if value.endswith("Z") else value.replace("+00:00", "Z")))


def _stats_row(r, tid, season):
    gp, ppg = runit.team_games_plays(r)
    return {"team_id": team_id(tid), "season": season, "offense_ppa": r["offense"]["ppa"],
            "defense_ppa": r["defense"]["ppa"], "plays_per_game": round(ppg, 4)}
