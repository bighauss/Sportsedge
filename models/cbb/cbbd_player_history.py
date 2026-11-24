"""Source-bound CBB player-history research intake; no activity inference or odds.

Provider documented /games/players team box rows. Prior finals must be joined
by exact game, team, opponent, season and start clock. Source observation is
a conservative availability bound. Historical means are conditional on
recorded participation, NOT a game-day forecast. Missing stats are not zeros.
"""
from collections import Counter, defaultdict
from hashlib import sha256
import math
import json
from statistics import mean, stdev
from cbbd_prospective_capture import Hold, decoded, utc, _unique_pairs, _bad_constant

URL = "https://api.collegebasketballdata.com/games/players"


def decode_player_boxes(raw):
    # Player boxes are substantially larger than schedule records.
    if type(raw) is not bytes or not 0 < len(raw) <= 32 * 1024 * 1024:
        raise Hold("PLAYER_BODY_SIZE_INVALID")
    try:
        rows = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs,
                          parse_constant=_bad_constant)
    except (ValueError, UnicodeError) as exc:
        raise Hold("PLAYER_BODY_JSON_INVALID") from exc
    if not isinstance(rows, list) or len(rows) >= 2000:
        raise Hold("PLAYER_TEAM_BOX_LIMIT_OR_SCHEMA_INVALID")
    return rows


def normalize(raw, receipt, finals_raw, finals_receipt, *, season, asof_utc):
    cutoff = utc(asof_utc, "asof")
    def verify(blob, rec, source):
        if (rec.get("source") != source or rec.get("sha256") != sha256(blob).hexdigest()
                or rec.get("bytes") != len(blob)):
            raise Hold("PLAYER_SOURCE_RECEIPT_MISMATCH")
        observed = utc(rec.get("observed_utc"), "observation")
        if observed >= cutoff:
            raise Hold("PLAYER_SOURCE_NOT_PRIOR")
        return (decode_player_boxes(blob) if source == "cbbd_games_players" else decoded(blob)), observed
    games, go = verify(finals_raw, finals_receipt, "cbbd_games_season")
    boxes, bo = verify(raw, receipt, "cbbd_games_players")
    counts = Counter(g.get("id") for g in games if isinstance(g, dict) and type(g.get("id")) is int)
    finals = {g["id"]: g for g in games if isinstance(g, dict) and type(g.get("id")) is int
              and g["id"] > 0 and counts[g["id"]] == 1 and g.get("status") == "final"
              and g.get("startTimeTbd") is False and g.get("season") == season}
    key = lambda b: (b.get("gameId"), b.get("teamId")) if isinstance(b, dict) and all(
        type(b.get(k)) is int for k in ("gameId", "teamId")) else None
    duplicate = Counter(key(b) for b in boxes)
    records, rejected = [], Counter()
    for b in boxes:
        try:
            k = key(b)
            if k is None or duplicate[k] != 1:
                raise Hold("PLAYER_DUPLICATE_OR_INVALID_TEAM_BOX")
            gid, team = k
            g = finals.get(gid)
            if g is None:
                raise Hold("PLAYER_NO_UNIQUE_PRIOR_FINAL")
            tip = utc(g.get("startDate"), "game_start")
            if tip >= min(go, bo) or utc(b.get("startDate"), "box_start") != tip:
                raise Hold("PLAYER_FINAL_TIME_MISMATCH")
            if b.get("season") != season or b.get("startTimeTbd") is not False:
                raise Hold("PLAYER_SEASON_OR_TIP_UNVERIFIED")
            h, a = g.get("homeTeamId"), g.get("awayTeamId")
            if any(type(t) is not int or t <= 0 for t in (h, a)) or h == a:
                raise Hold("PLAYER_FINAL_TEAM_IDS_INVALID")
            if team not in (h, a) or b.get("opponentId") != (a if team == h else h):
                raise Hold("PLAYER_TEAM_OPPONENT_MISMATCH")
            if type(b.get("isHome")) is not bool or b["isHome"] != (team == h):
                raise Hold("PLAYER_HOME_AWAY_MISMATCH")
            players = b.get("players")
            if not isinstance(players, list) or not players:
                raise Hold("PLAYER_BOX_EMPTY")
            ids = Counter(p.get("athleteId") for p in players if isinstance(p, dict)
                          and type(p.get("athleteId")) is int)
            for p in players:
                if not isinstance(p, dict) or type(p.get("athleteId")) is not int or p["athleteId"] <= 0 or ids[p["athleteId"]] != 1:
                    rejected["PLAYER_ID_INVALID_OR_DUPLICATE"] += 1
                    continue
                mins = p.get("minutes")
                if type(mins) not in (int, float) or not math.isfinite(mins) or not 0 < mins <= 100:
                    rejected["PLAYER_MINUTES_MISSING_OR_ZERO"] += 1
                    continue
                reb, threes = p.get("rebounds"), p.get("threePointFieldGoals")
                values = {"POINTS": p.get("points"), "REBOUNDS": reb.get("total") if isinstance(reb, dict) else None,
                          "ASSISTS": p.get("assists"), "THREES": threes.get("made") if isinstance(threes, dict) else None}
                if any(type(v) is not int or not 0 <= v <= 250 for v in values.values()):
                    rejected["PLAYER_REQUIRED_STAT_MISSING_OR_INVALID"] += 1
                    continue
                values["PRA"] = values["POINTS"] + values["REBOUNDS"] + values["ASSISTS"]
                records.append({"game_id": str(gid), "team_id": str(team), "player_id": str(p["athleteId"]),
                                "game_start_utc": g["startDate"], "minutes": mins, "stats": values})
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            rejected[str(e)] += 1
    # A player cannot represent two teams in one game; quarantine all copies.
    ids = Counter((r["game_id"], r["player_id"]) for r in records)
    clean = [r for r in records if ids[(r["game_id"], r["player_id"])] == 1]
    rejected["PLAYER_CROSS_TEAM_DUPLICATE"] += len(records) - len(clean)
    return clean, {"label": "PAPER_0U_CONDITIONAL_HISTORY_ONLY", "team_boxes": len(boxes),
                   "accepted_player_games": len(clean), "rejected": dict(rejected),
                   "source_sha256": receipt["sha256"], "finals_sha256": finals_receipt["sha256"],
                   "source_observed_utc": receipt["observed_utc"], "confirmed_activity": False,
                   "approved_stake_u": 0}


def historical_baselines(records):
    """Last five participated games, minimum four; no pregame activity claim."""
    groups = defaultdict(list)
    for r in records:
        groups[r["player_id"]].append(r)
    out = []
    for pid, rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda r: utc(r["game_start_utc"], "start"), reverse=True)
        recent = rows[:5]
        if len(recent) < 4 or len({r["team_id"] for r in recent}) != 1:
            continue
        if len({r["game_start_utc"] for r in recent}) != len(recent):
            continue
        stats = {stat: {"mean": mean(r["stats"][stat] for r in recent),
                        "sample_sd": stdev(r["stats"][stat] for r in recent)}
                 for stat in recent[0]["stats"]}
        out.append({"player_id": pid, "team_id": recent[0]["team_id"], "games": len(recent),
                    "mean_minutes": mean(r["minutes"] for r in recent), "stats": stats,
                    "latest_participation_utc": recent[0]["game_start_utc"],
                    "status": "HISTORICAL_PARTICIPATION_CONDITIONAL_NOT_PREGAME_FORECAST"})
    return out


def collect_batches(batches, finals_raw, finals_receipt, *, season, asof_utc):
    """Preserve cross-batch duplicate census and expose missing final-game coverage.

    A batch is (original bytes, capture receipt). No player is inferred active.
    Provider caps at 1000 games per request; reject cap-sized result batches.
    """
    if (finals_receipt.get("source") != "cbbd_games_season"
            or finals_receipt.get("sha256") != sha256(finals_raw).hexdigest()
            or finals_receipt.get("bytes") != len(finals_raw)):
        raise Hold("PLAYER_SOURCE_RECEIPT_MISMATCH")
    final_observed = utc(finals_receipt.get("observed_utc"), "observation")
    if final_observed >= utc(asof_utc, "asof"):
        raise Hold("PLAYER_SOURCE_NOT_PRIOR")
    all_rows, batch_reports = [], []
    box_batch_counts = Counter()
    for raw, receipt in batches:
        decoded_boxes = decode_player_boxes(raw)
        box_batch_counts.update({(str(b["gameId"]), str(b["teamId"])) for b in decoded_boxes
                                 if isinstance(b, dict) and all(type(b.get(k)) is int
                                 for k in ("gameId", "teamId"))})
        unique_games = {b.get("gameId") for b in decoded_boxes if isinstance(b, dict)
                        and type(b.get("gameId")) is int}
        if len(unique_games) >= 1000:
            raise Hold("PLAYER_BATCH_PROVIDER_CAP_REACHED")
        rows, report = normalize(raw, receipt, finals_raw, finals_receipt,
                                 season=season, asof_utc=asof_utc)
        all_rows.extend(rows)
        batch_reports.append(report)
    keys = Counter((r["game_id"], r["player_id"]) for r in all_rows)
    clean = [r for r in all_rows if keys[(r["game_id"], r["player_id"])] == 1
             and box_batch_counts[(r["game_id"], r["team_id"])] == 1]
    models = historical_baselines(clean)
    # Coverage distinguishes any admissible participation from both-team
    # representation. Neither means a complete roster or confirmed availability.
    games = decoded(finals_raw)
    final_ids = Counter(g.get("id") for g in games if isinstance(g, dict)
                        and type(g.get("id")) is int)
    expected = {}
    for g in games:
        if not isinstance(g, dict) or type(g.get("id")) is not int:
            continue
        gid = g["id"]
        h, a = g.get("homeTeamId"), g.get("awayTeamId")
        if (gid <= 0 or final_ids[gid] != 1 or g.get("status") != "final"
                or g.get("season") != season or g.get("startTimeTbd") is not False
                or any(type(t) is not int or t <= 0 for t in (h, a)) or h == a):
            continue
        try:
            if utc(g.get("startDate"), "game_start") >= final_observed:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        expected[str(gid)] = {str(h), str(a)}
    represented = defaultdict(set)
    for r in clean:
        represented[r["game_id"]].add(r["team_id"])
    both = sum(represented.get(gid, set()) == teams for gid, teams in expected.items())
    any_team = sum(bool(represented.get(gid, set()) & teams) for gid, teams in expected.items())
    return {"label": "PAPER_0U_CONDITIONAL_HISTORY_ONLY", "batches": batch_reports,
            "accepted_player_games": len(clean), "cross_batch_duplicate_rows": len(all_rows)-len(clean),
            "expected_final_games": len(expected), "represented_final_games": any_team,
            "both_teams_represented_final_games": both,
            "one_team_represented_final_games": any_team - both,
            "unrepresented_final_games": len(expected) - any_team,
            "duplicate_team_boxes_across_batches": sum(n > 1 for n in box_batch_counts.values()),
            "historical_players": len(models), "confirmed_activity": False,
            "approved_stake_u": 0, "historical_baselines": models}


def slate_history_coverage(card, history):
    """Exact historical team-ID join, never a roster or active-player assertion.

    Report both teams for every frozen game, including unprojected games.
    Candidate IDs remain in the private research artifact; no prices.
    """
    freeze = utc(card["freeze_utc"], "freeze")
    baselines = history.get("historical_baselines", [])
    counts = Counter(b.get("player_id") for b in baselines)
    by_team = defaultdict(list)
    excluded = Counter()
    for b in baselines:
        try:
            pid, tid = b["player_id"], b["team_id"]
            if (type(pid) is not str or not pid.isdigit() or int(pid) <= 0
                    or type(tid) is not str or not tid.isdigit() or int(tid) <= 0
                    or counts[pid] != 1):
                raise Hold("PLAYER_BASELINE_ID_INVALID_OR_DUPLICATE")
            if (b.get("status") != "HISTORICAL_PARTICIPATION_CONDITIONAL_NOT_PREGAME_FORECAST"
                    or not 4 <= b["games"] <= 5):
                raise Hold("PLAYER_BASELINE_STATUS_INVALID")
            if utc(b["latest_participation_utc"], "latest_participation") >= freeze:
                raise Hold("PLAYER_BASELINE_NOT_PRIOR")
            by_team[tid].append(pid)
        except (ValueError, KeyError, TypeError) as exc:
            excluded[str(exc)] += 1
    game_counts = Counter(r["game_id"] for r in card["rows"])
    rows = []
    for r in card["rows"]:
        gid, home, away = r["game_id"], r["home_team_id"], r["away_team_id"]
        for side, tid in (("home", home), ("away", away)):
            valid = (game_counts[gid] == 1 and home != away
                     and utc(r["tipoff_utc"], "tip") > freeze)
            ids = sorted(by_team.get(tid, [])) if valid else []
            rows.append({"game_id": gid, "team_id": tid, "side": side,
                         "historical_candidate_ids": ids,
                         "historical_candidates": len(ids),
                         "state": ("HISTORICAL_CANDIDATES_ONLY" if ids else
                                   "NO_ELIGIBLE_HISTORY" if valid else "GAME_IDENTITY_OR_CLOCK_INVALID"),
                         "confirmed_activity": False, "prop_forecast": None})
    return {"label": "PAPER_0U_SLATE_HISTORY_ONLY", "input_games": len(card["rows"]),
            "team_rows": len(rows), "team_rows_with_history": sum(bool(r["historical_candidates"]) for r in rows),
            "team_rows_without_history": sum(not r["historical_candidates"] for r in rows),
            "excluded_baselines": dict(excluded), "rows": rows,
            "confirmed_active_players": 0, "priced_props": 0, "approved_stake_u": 0}
