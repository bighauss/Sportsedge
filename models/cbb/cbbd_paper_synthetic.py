"""SYNTHETIC fixtures for the CBBD paper-card tests. Not real data; never a source."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone

from sportsedge.validation.daily_ratings_capture import cbbd_source

SEASON = 2027
FREEZE = "2026-11-21T15:00:00Z"
BUILT = "2026-11-21T15:05:00Z"
TIP = "2026-11-21T23:00:00Z"
RATINGS_OBSERVED = "2026-11-21T12:00:00Z"
HCA_TRUE = 3.0


def z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ratings_rows(n=360, season=SEASON):
    rows = []
    for i in range(1, n + 1):
        o = 95.0 + (i * 37 % 30)
        d = 95.0 + (i * 53 % 30)
        rows.append({"teamId": i, "team": f"Synthetic {i}", "season": season,
                     "offensiveRating": o, "defensiveRating": d, "netRating": o - d})
    return rows


def ratings_body(**kw):
    return json.dumps(ratings_rows(**kw)).encode()


def receipt(body, observed=RATINGS_OBSERVED, season=SEASON):
    obs = datetime.fromisoformat(observed[:-1] + "+00:00")
    return {"source": "cbbd_ratings_adjusted", "url": cbbd_source(season)["url"],
            "season": season, "state": "CAPTURED",
            "request_started_utc": z(obs - timedelta(seconds=1)), "observed_utc": observed,
            "bytes": len(body), "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
            "row_count": len(json.loads(body))}


def prior_games(n=200, teams=40, start="2026-11-04T00:00:00Z"):
    r = {x["teamId"]: x for x in ratings_rows()}
    lg = sum(x["offensiveRating"] for x in r.values()) / len(r)
    t0 = datetime.fromisoformat(start[:-1] + "+00:00")
    out = []
    for k in range(n):
        h = 1 + k % teams
        a = 1 + (k * 7 + 3) % teams
        if a == h:
            a = 1 + (a % teams)
        poss = 64.0 + k % 9
        neutral = k % 10 == 0
        eh = r[h]["offensiveRating"] + r[a]["defensiveRating"] - lg
        ea = r[a]["offensiveRating"] + r[h]["defensiveRating"] - lg
        noise = (k * 13) % 21 - 10
        hca = 0 if neutral else HCA_TRUE
        hp = round(eh * poss / 100 + hca / 2 + noise / 2)
        ap = round(ea * poss / 100 - hca / 2 - noise / 2)
        if hp == ap:
            hp += 1
        tip = t0 + timedelta(hours=2 * k)
        out.append({"game_id": str(5000 + k), "season": SEASON, "tipoff_utc": z(tip),
                    "final_captured_utc": z(tip + timedelta(hours=3)),
                    "home_team_id": str(h), "away_team_id": str(a), "neutral": neutral,
                    "home_points": hp, "away_points": ap, "possessions": poss})
    return out


SLATE = [  # game_id, home, away, neutral
    ("9001", "1", "2", "0"),
    ("9002", "3", "4", "1"),
    ("9003", "5", "999", "0"),   # 999 is a valid-looking ID with no CBBD rating
    ("9004", "6", "300", "0"),   # 300 is rated but has no pace history
]


def write_csv(path, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def write_slate(dirpath, games=SLATE, tip=TIP, season=SEASON, registry_skip=(),
                registry_tip=None):
    slate = write_csv(dirpath / "slate.csv",
                      ["game_id", "season", "tipoff_utc", "home_team_id", "away_team_id", "neutral"],
                      [[g, str(season), tip, h, a, n] for g, h, a, n in games])
    reg = write_csv(dirpath / "registry.csv",
                    ["game_id", "neutral", "source", "source_sha256", "published_utc",
                     "captured_utc", "tipoff_utc"],
                    [[g, n, "ESPN", "c" * 64, "2026-11-21T13:00:00Z", "2026-11-21T14:00:00Z",
                      registry_tip or tip]
                     for g, h, a, n in games if g not in registry_skip])
    return slate, reg


def quote(game_id, market, line, a, b, captured="2026-11-21T14:30:00Z", book="bookA"):
    return {"game_id": game_id, "market": market, "book": book, "line": line,
            "price_a": a, "price_b": b, "captured_utc": captured}


def full_quotes(game_id, captured="2026-11-21T14:30:00Z", book="bookA"):
    return [quote(game_id, "moneyline", None, -150, 130, captured, book),
            quote(game_id, "spread", -3.5, -110, -110, captured, book),
            quote(game_id, "total", 140.5, -110, -110, captured, book)]


def provider_games(results, season=SEASON, tip=TIP):
    """results: list of (game_id, home_id, away_id, home_pts, away_pts)."""
    return [{"id": int(g), "season": season, "homeTeamId": int(h), "awayTeamId": int(a),
             "homePoints": hp, "awayPoints": ap, "startDate": tip,
             "startTimeTbd": False, "status": "final"} for g, h, a, hp, ap in results]
