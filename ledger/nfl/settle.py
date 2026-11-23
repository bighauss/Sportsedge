"""Postgame settlement: grade a frozen run without touching it.

Usage:
  python3 ledger/nfl/settle.py --run ledger/nfl/runs/<run_id> --finals finals.json \
      --source "ESPN box score" [--stats stats.csv]

finals.json: {"away":"CIN","home":"WAS","away_score":20,"home_score":17,
              "periods":{"1H":[10,7],"1Q":[3,7]}}          (periods = [away, home], optional)
stats.csv:   player,stat,value      (one row per player stat; e.g. Joe Burrow,pass_yds,287)

Pick-row conventions (picks_nfl.csv from engine/run_nfl.py):
  market: spread | total | ml | <period>_spread|_total|_ml (e.g. 1H_spread) | prop_<stat>
  pick:   team abbrev for spread/ml; over/under for totals and props; yes/no for TD-type props
  line:   spread/total/prop line (spread from the picked team's view, e.g. -3.5)
  price|price_american: American odds frozen at capture. player: for props.
Every priced row is graded W/L/P at its frozen price, 1u flat. Held rows are graded and
flagged held=True. Rows that cannot be graded (missing period/stat) get result "NG" + reason.

Output: APPENDS a settlement record to ledger/nfl/settlements/<run_id>.json
(list of records; newest last). The frozen run folder is never written.
"""
import argparse, json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (SETTLE_DIR, _profit, fnum, market_family, price_of, read_csv,  # noqa: E402
                    read_json, truthy)
from freeze import verify  # noqa: E402


def _cmp(x, line, side):
    """Over/under style: side 'over' wins if x > line."""
    if x == line:
        return "P"
    return "W" if (x > line) == (side == "over") else "L"


def grade_row(row, finals, stats):
    market = (row.get("market") or "").strip().lower()
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
    if "_" in market:
        per, kind = market.split("_", 1)
        p = (finals.get("periods") or {}).get(per.upper())
        if not p:
            return "NG", f"no {per.upper()} score"
        a, h = float(p[0]), float(p[1])
    else:
        kind = fam
        a, h = float(finals["away_score"]), float(finals["home_score"])
    kind = {"moneyline": "ml", "h2h": "ml", "spreads": "spread", "totals": "total"}.get(kind, kind)
    if kind == "total":
        if line is None:
            return "NG", "total missing line"
        return _cmp(a + h, line, "over" if pl.startswith("o") else "under"), None
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


def load_stats(path):
    if not path:
        return {}
    return {((r["player"] or "").strip().lower(), (r["stat"] or "").strip().lower()): float(r["value"])
            for r in read_csv(path) if r.get("value") not in (None, "")}


def settle(run_dir, finals, source, stats_path=None, settle_dir=SETTLE_DIR, now=None):
    run_dir = os.path.abspath(run_dir)
    manifest = read_json(os.path.join(run_dir, "manifest.json"))
    bad = verify(run_dir)
    stats = load_stats(stats_path)
    graded = []
    for label in manifest["pick_sets"]:
        for i, row in enumerate(read_csv(os.path.join(run_dir, label, "picks_nfl.csv"))):
            try:
                price = price_of(row)
            except ValueError:
                continue  # unpriced row: nothing to grade
            res, why = grade_row(row, finals, stats)
            g = {"pick_set": label, "row": i, "market": row.get("market"),
                 "family": market_family(row.get("market")), "pick": row.get("pick"),
                 "player": row.get("player") or None, "line": fnum(row.get("line")),
                 "price": price, "result": res,
                 "units": round(_profit(price, res), 4) if res in ("W", "L", "P") else None,
                 "held": truthy(row.get("held")), "status": row.get("status") or None,
                 "model_p": fnum(row.get("model_p")), "market_p": fnum(row.get("market_p")),
                 "blend_p": fnum(row.get("blend_p")), "ev": fnum(row.get("ev")),
                 "model_ev": fnum(row.get("model_ev"))}
            if why:
                g["reason"] = why
            graded.append(g)
    now = now or datetime.now(timezone.utc)
    rec = {"run_id": manifest["run_id"], "game": manifest["game"],
           "retrieved_utc": now.isoformat(timespec="seconds"), "source": source,
           "finals": finals, "stats_rows": len(stats), "run_integrity_ok": not bad,
           "run_integrity_mismatch": bad, "stake_units": 1.0, "graded": graded}
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
    a = ap.parse_args(argv)
    path, rec = settle(a.run, read_json(a.finals), a.source, a.stats, a.settle_dir)
    n = {k: sum(1 for g in rec["graded"] if g["result"] == k) for k in ("W", "L", "P", "NG")}
    print(path, n, f"units={sum(g['units'] or 0 for g in rec['graded']):+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
