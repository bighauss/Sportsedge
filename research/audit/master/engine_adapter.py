"""Wire SportsEdge engine RUN IT cards (NBA / CBB / CFB, game lines AND props) into
the master audit layer. Read-only: reads the card CSV the engine already writes;
never imports or edits the engines.

Card columns accepted (aliases tolerated so every sport's card works):
  game_id, market (PROP_PTS / PROP_REB / ... or ML/SPREAD/TOTAL/TT_*/1H_*),
  selection ("Player Name OVER" for props), line, price_dec | price | odds,
  model_p, novig_p, blend_p, blend_ev, projection, note, rank, stars
Optional side files:
  games.csv   game_id + tipoff/kickoff time  -> kickoff_ts
  results.csv game_id, market, selection, line, result (W/L/P) [, actual]
Usage:
  python -m research.audit.master.engine_adapter nba out/nba_card.csv \
      --run-ts 2026-11-21T10:00:00-06:00 --games sample/games.csv \
      --results results.csv --out nba_audit_rows.json [--prob blend]
then: python -m research.audit.master challenge nba_audit_rows.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime

from .odds import decimal_to_american

ALIASES = {
    "price_dec": ("price_dec", "dec", "decimal"),
    "odds": ("odds", "price", "american", "price_american"),
    "model_p": ("model_p", "model_prob", "p_model", "win_p"),
    "blend_p": ("blend_p", "p_blend"),
    "novig_p": ("novig_p", "nv_p", "market_p", "no_vig_p"),
    "selection": ("selection", "pick", "side"),
    "projection": ("projection", "proj", "proj_mean", "mean"),
    "line": ("line", "point"),
    "market": ("market", "mkt"),
    "game_id": ("game_id", "event_id", "gid"),
}
KICK_KEYS = ("kickoff_ts", "kickoff_utc", "tipoff_ts", "start_ts", "commence_time", "tipoff_et", "kickoff_et")


def _get(r, key):
    for k in ALIASES.get(key, (key,)):
        if r.get(k) not in (None, ""):
            return r[k]
    return None


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def _kickoffs(games, tz="-05:00"):
    out = {}
    for g in games:
        for k in KICK_KEYS:
            v = g.get(k)
            if not v:
                continue
            if "T" in v or len(v) > 10:
                out[g["game_id"]] = v
            elif g.get("date"):           # date + clock time like 19:30
                hhmm = v if len(v) > 4 else v.zfill(5)
                out[g["game_id"]] = f"{g['date']}T{hhmm}:00{tz}"   # *_et columns are US Eastern
            break
    return out


def card_to_rows(card, sport, run_ts, odds_ts=None, kickoffs=None, results=None, prob="model",
                 rule_version=None, model_version=None):
    """prob: 'model' uses model_p (what the audits should judge), 'blend' uses blend_p."""
    kickoffs, results = kickoffs or {}, results or {}
    rows, skipped = [], []
    for i, r in enumerate(card, 1):
        gid, mkt, sel = _get(r, "game_id"), (_get(r, "market") or "").upper(), _get(r, "selection") or ""
        p = _f(_get(r, "blend_p") if prob == "blend" else _get(r, "model_p"))
        dec, am = _f(_get(r, "price_dec")), _f(_get(r, "odds"))
        if am is None and dec and dec > 1:
            am = round(decimal_to_american(dec))
        if am is not None and dec is not None and abs(am) < 100:   # 'price' column held decimal
            am = round(decimal_to_american(am))
        if p is None or am is None or not gid:
            skipped.append({"row": i, "why": "missing model_p / price / game_id"})
            continue
        is_prop = mkt.startswith("PROP")
        side, player = sel, None
        if is_prop:
            parts = sel.rsplit(" ", 1)
            player, side = (parts[0], parts[1]) if len(parts) == 2 else (sel, "")
        line = _f(_get(r, "line"))
        key = (gid, mkt, sel.upper(), line)
        res = results.get(key) or {}
        rows.append({
            "pred_id": f"{sport}-{run_ts[:10]}-{gid}-{mkt}-{sel}-{line}".replace(" ", "_"),
            "game_id": gid, "sport": sport.upper(), "market": mkt, "side": side, "player": player,
            "is_prop": is_prop, "line": line, "odds": am, "book": r.get("book") or "card",
            "model_prob": p, "market_prob": _f(_get(r, "novig_p")),
            "blend_prob": _f(_get(r, "blend_p")), "blend_ev": _f(r.get("blend_ev")),
            "projection": _f(_get(r, "projection")), "note": r.get("note", ""),
            "stars": r.get("stars"), "rank": r.get("rank"),
            "pred_ts": run_ts, "odds_ts": odds_ts or run_ts, "kickoff_ts": kickoffs.get(gid),
            "result": res.get("result", ""), "actual": _f(res.get("actual")),
            "rule_version": rule_version or f"{sport}-card", "model_version": model_version,
            "inputs": [{"name": "card_note", "value": r.get("note", ""), "ts": run_ts}],
        })
    return rows, skipped


def load_results(path):
    out = {}
    for r in _read(path):
        out[(r["game_id"], r["market"].upper(), r["selection"].upper(), _f(r.get("line")))] = r
    return out


def coverage(rows):
    """Show the props are actually in the audit, by sport/market family."""
    fam = {}
    for r in rows:
        k = (r["sport"], "PROP" if r["is_prop"] else r["market"].split("_")[0])
        fam[k] = fam.get(k, 0) + 1
    return {f"{s}:{m}": n for (s, m), n in sorted(fam.items())}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="engine_adapter")
    ap.add_argument("sport", choices=["nba", "cbb", "cfb", "nfl", "mlb", "nhl"])
    ap.add_argument("card")
    ap.add_argument("--run-ts", required=True, help="when the card was produced (ISO with offset)")
    ap.add_argument("--odds-ts", help="when odds were captured (defaults to run-ts)")
    ap.add_argument("--games", help="engine games.csv for kickoff times")
    ap.add_argument("--results", help="graded results CSV")
    ap.add_argument("--tz", default="-05:00", help="UTC offset for clock-only tipoff columns (ET = -05:00 in winter)")
    ap.add_argument("--prob", choices=["model", "blend"], default="model")
    ap.add_argument("--rule-version"); ap.add_argument("--model-version")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    datetime.fromisoformat(a.run_ts)
    rows, skipped = card_to_rows(_read(a.card), a.sport, a.run_ts, a.odds_ts,
                                 _kickoffs(_read(a.games), a.tz) if a.games else None,
                                 load_results(a.results) if a.results else None,
                                 a.prob, a.rule_version, a.model_version)
    with open(a.out, "w") as f:
        json.dump(rows, f, indent=1)
    print(json.dumps({"rows": len(rows), "skipped": skipped, "coverage": coverage(rows)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
