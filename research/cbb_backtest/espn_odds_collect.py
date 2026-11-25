"""Collect historical CBB pregame odds from ESPN's public core API (research only).

Source: https://sports.core.api.espn.com/v2/sports/basketball/leagues/
mens-college-basketball/events/{id}/competitions/{id}/odds
Each provider item carries open/close/current spread, total and moneyline.
We keep a compact record per (game, provider). Live-odds providers and model
"providers" (numberfire, teamrankings, accuscore) are recorded but flagged
NOT_A_BOOK and never used as market inputs. Snapshot timing of "close" is ESPN's
own label; it is not independently authenticated against a pretip clock.
"""
import argparse, concurrent.futures as cf, gzip, json, time, urllib.request, urllib.error
from pathlib import Path

URL = ("https://sports.core.api.espn.com/v2/sports/basketball/leagues/"
       "mens-college-basketball/events/{g}/competitions/{g}/odds?limit=50")
NOT_A_BOOK = {"1001", "1002", "1003", "59", "200"}  # accuscore, teamrankings, numberfire, live odds (ESPN BET / DK)


def _am(x):
    """American price from an ESPN price node ({'american': '-110'}) or number."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return int(x) if abs(x) >= 100 else None
    v = x.get("american") or x.get("alternateDisplayValue")
    if v in (None, "", "EVEN", "even"):
        return 100 if v in ("EVEN", "even") else None
    try:
        f = float(str(v).replace("+", ""))
    except ValueError:
        return None
    return int(f) if abs(f) >= 100 else None


def _pt(x):
    if not x:
        return None
    for k in ("value", "american", "alternateDisplayValue"):
        v = x.get(k)
        if v is None:
            continue
        try:
            return float(str(v).replace("+", "")) if str(v).upper() not in ("PK", "EVEN") else 0.0
        except ValueError:
            continue
    return None


def compact(game_id, item):
    h, a = item.get("homeTeamOdds") or {}, item.get("awayTeamOdds") or {}
    rec = {"game_id": game_id, "provider_id": str(item.get("provider", {}).get("id")),
           "provider": item.get("provider", {}).get("name"),
           "current_spread_home": item.get("spread"), "current_total": item.get("overUnder"),
           "current_ml_home": h.get("moneyLine"), "current_ml_away": a.get("moneyLine"),
           "current_spread_price_home": h.get("spreadOdds"), "current_spread_price_away": a.get("spreadOdds"),
           "current_over_price": item.get("overOdds"), "current_under_price": item.get("underOdds")}
    for when in ("open", "close"):
        ho, ao, to = h.get(when) or {}, a.get(when) or {}, item.get(when) or {}
        rec[f"{when}_spread_home"] = _pt(ho.get("pointSpread"))
        rec[f"{when}_spread_price_home"] = _am(ho.get("spread"))
        rec[f"{when}_spread_price_away"] = _am(ao.get("spread"))
        rec[f"{when}_ml_home"] = _am(ho.get("moneyLine"))
        rec[f"{when}_ml_away"] = _am(ao.get("moneyLine"))
        rec[f"{when}_total"] = _pt(to.get("total"))
        rec[f"{when}_over_price"] = _am(to.get("over"))
        rec[f"{when}_under_price"] = _am(to.get("under"))
    rec["not_a_book"] = rec["provider_id"] in NOT_A_BOOK
    return rec


def fetch(game_id, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(URL.format(g=game_id), timeout=20) as r:
                return 200, json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return -1, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ids", type=Path, required=True, help="text file, one ESPN game id per line")
    p.add_argument("--out", type=Path, required=True, help="jsonl.gz output (appends; resumable)")
    p.add_argument("--workers", type=int, default=16)
    a = p.parse_args()
    done = set()
    if a.out.exists():
        with gzip.open(a.out, "rt") as f:
            for line in f:
                done.add(json.loads(line)["game_id"])
    ids = [x.strip() for x in a.ids.read_text().split() if x.strip() and x.strip() not in done]
    print(f"todo={len(ids)} done={len(done)}", flush=True)
    with gzip.open(a.out, "at") as out, cf.ThreadPoolExecutor(a.workers) as ex:
        for n, (gid, (code, d)) in enumerate(zip(ids, ex.map(fetch, ids))):
            items = [compact(gid, it) for it in (d or {}).get("items", [])]
            out.write(json.dumps({"game_id": gid, "http": code, "items": items}) + "\n")
            if n % 2000 == 0:
                print(n, gid, code, len(items), flush=True)


if __name__ == "__main__":
    main()
