"""Postgame settlement: grade a frozen run without touching it.

Usage:
  python3 ledger/nfl/settle.py --run ledger/nfl/runs/<run_id> --finals finals.json \
      --source "ESPN box score" [--stats stats.csv]

finals.json: {"away":"CIN","home":"WAS","away_score":20,"home_score":17,
              "periods":{"1H":[10,7],"1Q":[3,7]}}          (periods = [away, home], optional)
stats.csv:   game,player,stat,value (game = AWAY@HOME of the frozen run; e.g. CIN@WAS,Joe Burrow,pass_yds,287)

Pick-row conventions (picks_nfl.csv from engine/run_nfl.py):
  market: spread | total | ml | <period>_spread|_total|_ml (e.g. 1H_spread) | prop_<stat>
  pick:   team abbrev for spread/ml; over/under for totals and props; yes/no for TD-type props
  line:   spread/total/prop line (spread from the picked team's view, e.g. -3.5)
  price|price_american: American odds frozen at capture. player: for props.
Every priced row is graded W/L/P at its frozen price as a hypothetical 1u diagnostic
(never an approved stake; any row with approved_stake_u != 0 is refused). Held rows are graded and
flagged held=True. Rows that cannot be graded (missing period/stat) get result "NG" + reason.

Output: APPENDS a settlement record to ledger/nfl/settlements/<run_id>.json
(list of records; newest last). The frozen run folder is never written.
"""
import argparse, json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (SETTLE_DIR, _profit, fnum, market_family, normalize_row, price_of,  # noqa: E402
                    read_csv, read_json, is_held)
from freeze import verify  # noqa: E402


def _cmp(x, line, side):
    """Over/under style: side 'over' wins if x > line."""
    if x == line:
        return "P"
    return "W" if (x > line) == (side == "over") else "L"


def grade_row(row, finals, stats):
    row = normalize_row(row)
    market = (row.get("market") or "").strip().lower()
    if market.startswith(("unsupported_", "unparsed_")):
        return "NG", f"{market.split('_', 1)[0]} market {row.get('v5_market')}"
    pick = (row.get("pick") or "").strip()
    pl = pick.lower()
    line = fnum(row.get("line"))
    fam = market_family(market)
    away, home = finals["away"].upper(), finals["home"].upper()
    if fam.startswith("prop:"):
        stat = fam[5:]
        player = (row.get("player") or "").strip().lower()
        val = stats.get((player, stat))
        if val is None:
            return "NG", f"no stat {row.get('player')}/{stat}"
        if pl in ("yes", "no"):
            thr = line if line is not None else 0.5
            hit = val > thr
            return ("W" if hit == (pl == "yes") else "L"), None
        side = "over" if pl.startswith("o") else "under"
        if line is None:
            return "NG", "prop missing line"
        return _cmp(val, line, side), None
    if "_" in market and market.split("_", 1)[0].upper() in ("1Q", "2Q", "3Q", "4Q", "1H", "2H"):
        per, kind = market.split("_", 1)
        p = (finals.get("periods") or {}).get(per.upper())
        if not p:
            return "NG", f"no {per.upper()} score"
        a, h = float(p[0]), float(p[1])
    else:
        kind = market if market in ("home_tt", "away_tt") else fam
        a, h = float(finals["away_score"]), float(finals["home_score"])
    kind = {"moneyline": "ml", "h2h": "ml", "spreads": "spread", "totals": "total"}.get(kind, kind)
    if kind == "total":
        if line is None:
            return "NG", "total missing line"
        return _cmp(a + h, line, "over" if pl.startswith("o") else "under"), None
    if kind in ("home_tt", "away_tt"):
        if line is None:
            return "NG", "team total missing line"
        return _cmp(h if kind == "home_tt" else a, line, "over" if pl.startswith("o") else "under"), None
    team = pick.split()[0].upper()
    if team not in (away, home):
        return "NG", f"pick team {team} not in {away}@{home}"
    mine, theirs = (a, h) if team == away else (h, a)
    if kind == "ml":
        return ("P" if mine == theirs else ("W" if mine > theirs else "L")), None
    if kind == "spread":
        if line is None:
            return "NG", "spread missing line"
        adj = mine + line - theirs
        return ("P" if adj == 0 else ("W" if adj > 0 else "L")), None
    return "NG", f"unknown market {market}"


class SettlementError(ValueError):
    """Settlement refused: integrity, identity or stake contract violated."""


def _game_key(g):
    return (g or "").replace(" ", "").upper()


def check_finals_identity(manifest, finals):
    """Finals must name the frozen game exactly: away@home from the manifest."""
    want = _game_key(manifest["game"])
    if "@" not in want:
        raise SettlementError(f"manifest game {manifest['game']!r} is not AWAY@HOME")
    got = _game_key(f"{finals.get('away', '')}@{finals.get('home', '')}")
    if got != want:
        raise SettlementError(f"finals are for {got}, frozen run is {want}")
    if finals.get("game") is not None and _game_key(finals["game"]) != want:
        raise SettlementError(f"finals game id {finals['game']!r} != frozen {manifest['game']!r}")


def load_stats(path, game=None):
    """stats.csv: game,player,stat,value. Every row must carry the frozen game (AWAY@HOME)."""
    if not path:
        return {}
    rows = read_csv(path)
    if game is not None:
        if rows and "game" not in rows[0]:
            raise SettlementError("stats file has no game column; cannot bind stats to the frozen game")
        bad = {r.get("game") for r in rows if _game_key(r.get("game")) != _game_key(game)}
        if bad:
            raise SettlementError(f"stats rows for other games {sorted(map(str, bad))} (frozen {game})")
    return {((r["player"] or "").strip().lower(), (r["stat"] or "").strip().lower()): float(r["value"])
            for r in rows if r.get("value") not in (None, "")}


def settle(run_dir, finals, source, stats_path=None, settle_dir=SETTLE_DIR, now=None, quarantine=False):
    """Grade a frozen run. Refuses (SettlementError) on: integrity mismatch (unless quarantine=True,
    which writes a QUARANTINED record that the scorecard excludes), finals/stats for another game,
    or any row claiming a nonzero approved stake. Grading is a hypothetical 1u diagnostic only."""
    run_dir = os.path.abspath(run_dir)
    manifest = read_json(os.path.join(run_dir, "manifest.json"))
    bad = verify(run_dir)
    if bad and not quarantine:
        raise SettlementError(f"frozen run failed integrity check: {bad}")
    check_finals_identity(manifest, finals)
    stats = load_stats(stats_path, manifest["game"])
    graded = []
    for label in manifest["pick_sets"]:
        for i, raw in enumerate(read_csv(os.path.join(run_dir, label, "picks_nfl.csv"))):
            row = normalize_row(raw)
            try:
                price = price_of(row)
            except ValueError:
                continue  # unpriced row: nothing to grade
            raw_stake = row.get("approved_stake_u")
            if raw_stake not in (None, "") and fnum(raw_stake) != 0:      # unparseable also refused
                raise SettlementError(f"{label} row {i} claims approved_stake_u={row.get('approved_stake_u')}; "
                                      "research ledger accepts 0 only")
            res, why = grade_row(row, finals, stats)
            g = {"pick_set": label, "row": i, "market": row.get("market"),
                 "family": market_family(row.get("market")), "pick": row.get("pick"),
                 "player": row.get("player") or None, "line": fnum(row.get("line")),
                 "price": price, "result": res,
                 "units": round(_profit(price, res), 4) if res in ("W", "L", "P") else None,
                 "on_card": is_held(row.get("on_card")) if row.get("on_card") not in (None, "") else None,
                 "held": is_held(row.get("held")), "status": row.get("status") or None,
                 "model_p": fnum(row.get("model_p")), "market_p": fnum(row.get("market_p")),
                 "blend_p": fnum(row.get("blend_p")), "ev": fnum(row.get("ev")),
                 "model_ev": fnum(row.get("model_ev")),
                 "approved_stake_u": 0.0}
            if why:
                g["reason"] = why
            graded.append(g)
    now = now or datetime.now(timezone.utc)
    rec = {"run_id": manifest["run_id"], "game": manifest["game"],
           "retrieved_utc": now.isoformat(timespec="seconds"), "source": source,
           "finals": finals, "stats_rows": len(stats), "run_integrity_ok": not bad,
           "run_integrity_mismatch": bad, "quarantined": bool(bad),
           "diagnostic_units_per_row": 1.0, "approved_stake_u": 0.0, "graded": graded}
    os.makedirs(settle_dir, exist_ok=True)
    path = os.path.join(settle_dir, manifest["run_id"] + ".json")
    hist = read_json(path) if os.path.exists(path) else []
    hist.append(rec)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(hist, f, indent=2)
    os.replace(tmp, path)
    return path, rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--finals", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--stats")
    ap.add_argument("--settle-dir", default=SETTLE_DIR)
    ap.add_argument("--quarantine", action="store_true", help="record a failed-integrity run as QUARANTINED")
    a = ap.parse_args(argv)
    path, rec = settle(a.run, read_json(a.finals), a.source, a.stats, a.settle_dir, quarantine=a.quarantine)
    n = {k: sum(1 for g in rec["graded"] if g["result"] == k) for k in ("W", "L", "P", "NG")}
    print(path, n, f"units={sum(g['units'] or 0 for g in rec['graded']):+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
