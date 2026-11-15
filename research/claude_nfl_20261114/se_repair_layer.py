#!/usr/bin/env python3
"""SportsEdge repair layer R2 (Claude, Nov 14 2026) - post-processes a v5 picks CSV. v5 is NOT edited.

Adds columns; never deletes a row (owner ruling Nov 1: +EV picks always show, validation runs beside them).
  pooled_p   model_p blended toward the no-vig market:  p ~ model^w * market^(1-w)   (w default 0.30 = Run 55 Benter)
  pooled_ev  EV at the original price using pooled_p
  gap_pts    |model_p - market_p| in percentage points
  flags      GAP>CAP (model far from market), STACK (beyond the per-game limit), NO_MKT (no no-vig market_p),
             PERIOD_DERIVED (ANCHOR 1H/1Q/P1 row: edge comes from the period conversion, not a projection)
  r2_keep    1 if pooled_ev >= floor and no GAP/STACK flag  -> the "repaired card"

Also: stretch_margin() - the CFB/CBB margin de-compression candidate (k fitted on early folds; NOT adopted).

Usage:  python se_repair_layer.py picks.csv out.csv [--w 0.30] [--cap 15] [--per-game 2] [--floor 0.01]
"""
import csv, sys, argparse
from collections import defaultdict

PERIOD_PREFIX = ("1H_", "2H_", "1Q_", "2Q_", "3Q_", "4Q_", "P1_", "P2_", "P3_", "I1_", "F3_", "F5_", "F7_")


def payout(price):
    price = float(price)
    return price / 100 if price > 0 else 100 / -price


def pool(pm, pk, w):
    """Logarithmic pool of model and market probability for one side."""
    eps = 1e-6
    pm, pk = min(max(pm, eps), 1 - eps), min(max(pk, eps), 1 - eps)
    a = pm ** w * pk ** (1 - w)
    b = (1 - pm) ** w * (1 - pk) ** (1 - w)
    return a / (a + b)


def stretch_margin(home_proj, away_proj, k=1.23):
    """Widen a projected margin by k around the projected total (total unchanged). Candidate only."""
    t, m = home_proj + away_proj, (home_proj - away_proj) * k
    return (t + m) / 2, (t - m) / 2


def repair(rows, w=0.30, cap=15.0, per_game=2, floor=0.01):
    out = []
    for r in rows:
        r = dict(r)
        p = float(r["model_p"])
        mk = r.get("market_p")
        flags = []
        bt = (r.get("bet_type") or "").split("|")[0]
        if r.get("mode") == "ANCHOR" and bt.startswith(PERIOD_PREFIX):
            flags.append("PERIOD_DERIVED")
        if mk in (None, "", "None"):
            flags.append("NO_MKT")
            pp, gap = p, None
        else:
            mk = float(mk)
            pp, gap = pool(p, mk, w), abs(p - mk) * 100
            if gap > cap:
                flags.append("GAP>CAP")
        r["pooled_p"] = round(pp, 6)
        r["pooled_ev"] = round(pp * payout(r["price"]) - (1 - pp), 6)
        r["gap_pts"] = "" if gap is None else round(gap, 2)
        r["_flags"] = flags
        out.append(r)
    # per-game stacking: rank qualifying rows by pooled EV inside each game
    by_game = defaultdict(list)
    for r in out:
        if float(r["pooled_ev"]) >= floor and "GAP>CAP" not in r["_flags"]:
            by_game[(r.get("sport"), r["game"])].append(r)
    for g in by_game.values():
        for i, r in enumerate(sorted(g, key=lambda x: -float(x["pooled_ev"]))):
            if i >= per_game:
                r["_flags"].append("STACK")
    for r in out:
        r["r2_keep"] = int(float(r["pooled_ev"]) >= floor and not ({"GAP>CAP", "STACK"} & set(r["_flags"])))
        r["flags"] = ";".join(r.pop("_flags"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--w", type=float, default=0.30)
    ap.add_argument("--cap", type=float, default=15.0)
    ap.add_argument("--per-game", type=int, default=2)
    ap.add_argument("--floor", type=float, default=0.01)
    a = ap.parse_args(argv)
    rows = list(csv.DictReader(open(a.src, newline="", encoding="utf-8-sig")))
    out = repair(rows, a.w, a.cap, a.per_game, a.floor)
    cols = list(rows[0].keys()) + ["pooled_p", "pooled_ev", "gap_pts", "flags", "r2_keep"]
    with open(a.dst, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=cols); wtr.writeheader(); wtr.writerows(out)
    k = sum(r["r2_keep"] for r in out)
    print(f"{len(out)} rows in, {len(out)} rows out (none deleted); repaired card keeps {k}")


if __name__ == "__main__":
    main()
