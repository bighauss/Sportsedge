#!/usr/bin/env python3
"""SportsEdge NFL run-it card with the owner guards approved Nov 23 2026.

Wraps engine v5 without changing it. NFL rows only:
  1. 30/70 blend - two-sided rows are ranked by EV on
     p = 0.30 * model_p + 0.70 * no-vig market_p (probabilities, not points).
     Push share is kept from the model.
  2. 6-point hold - SPREAD / TOTAL rows are HELD when the model's projection for THAT
     period (full game, 1H, 2H, 1Q..4Q) is more than 6 points off the book-implied
     projection for the same period. Not applied to ML or props.
  3. Probability-disagreement hold (Nov 15 ruling, separate check) - two-sided rows are
     HELD when raw model_p is > 1.5x or < 0.67x the no-vig market_p, or > 12 points apart.
  4. Rows with no valid two-sided no-vig price are never blended and never go on the
     blended card; they are listed separately as MODEL-ONLY.
  5. Monte Carlo noise - N_FIT 20,000 -> 100,000 for this run only (restored afterwards).
Every held row is listed with its reason at 0u. Non-NFL rows pass through with v5 numbers.

Usage:  python engine/run_nfl.py board.csv
"""
import contextlib
import csv
import io
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sportsedge_v5 as v5  # noqa: E402

BLEND_W = 0.30
GAP_PTS = 6.0
P_RATIO_HI, P_RATIO_LO, P_ABS = 1.5, 0.67, 0.12
N_FIT = 100000
N_GAP = 40000


def load_nfl_lines(path):
    """Game-line rows per NFL game, parsed the same way v5.run parses them."""
    games = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            if not r.get("market") or r.get("sport", "").upper() != "NFL":
                continue
            r["sport"], r["market"] = "NFL", r["market"].upper()
            r["line"] = v5.num(r.get("line")) or 0.0
            r["hp"], r["ap"] = v5.num(r.get("home_proj")), v5.num(r.get("away_proj"))
            r["price_a"], r["price_b"] = v5.num(r.get("price_a")), v5.num(r.get("price_b"))
            r["rem"] = v5.num(r.get("remaining"))
            g = games.setdefault((r["home"], r.get("away", "")), dict(lines=[], all=[]))
            g["all"].append(r)
            if not r.get("player"):
                g["lines"].append(r)
    return games


def _period_means(S, ix):
    if ix is None:
        h, a = S["h"], S["a"]
    else:
        h, a = S["H"][:, ix].sum(1), S["A"][:, ix].sum(1)
    return float(np.mean(h - a)), float(np.mean(h + a))


def projection_gaps(games):
    """{game: {period prefix ('' = full game): (spread gap, total gap)}}.

    Gap = model projection minus book-implied projection for the same period, both read
    from the same v5 simulator (same seed), so each period is compared with itself.
    Spread gap is in home-margin points (+ = model likes home more than the book)."""
    out = {}
    for (home, away), g in games.items():
        if any(r["rem"] is not None for r in g["all"]):
            continue                                   # live games: no hold
        proj = next(((r["hp"], r["ap"]) for r in g["all"]
                     if r["hp"] is not None and r["ap"] is not None), None)
        if proj is None:
            continue                                   # ANCHOR games have no opinion on the main line
        seed = v5.seed_of(f"NFL|{home}|{away}")
        bk = v5.anchor("NFL", g["lines"], seed)
        if not bk:
            continue
        Sm = v5.simulate("NFL", proj[0], proj[1], seed, N_GAP)
        Sb = v5.simulate("NFL", bk[0], bk[1], seed, N_GAP)
        per = {"": ((proj[0] - proj[1]) - (bk[0] - bk[1]), (proj[0] + proj[1]) - (bk[0] + bk[1]))}
        for pre, ix in v5.PERIODS["NFL"].items():
            mm, mt = _period_means(Sm, ix)
            bm, bt = _period_means(Sb, ix)
            per[pre] = (mm - bm, mt - bt)
        out[f"{away} @ {home}"] = per
    return out


def guard(o, gaps):
    """Add blend_p / model_ev / held / status to one priced side; EV becomes the blended EV."""
    o["model_ev"], o["blend_p"], o["held"], o["status"] = o["ev"], o["model_p"], "", "v5"
    if o["sport"] != "NFL":
        return o
    mp, fp = o["model_p"], o["market_p"]
    reasons = []
    if fp is None or not (0.0 < fp < 1.0):
        o["status"] = "MODEL_ONLY"                    # no valid no-vig price: never blended
    else:
        o["status"] = "BLENDED"
        p = BLEND_W * mp + (1 - BLEND_W) * fp
        pay = v5.payout(o["price"])
        den = mp * pay - (1 - mp)
        s = o["ev"] / den if abs(den) > 1e-9 else 1.0      # share of sims that don't push
        s = min(max(s, 0.0), 1.0) if s == s else 1.0
        o["blend_p"] = p
        o["ev"] = s * (p * pay - (1 - p))
        o["score"] = v5.score(o["ev"])
        o["stars"] = v5.stars(o["score"])
        if mp > P_RATIO_HI * fp or mp < P_RATIO_LO * fp or abs(mp - fp) > P_ABS:
            reasons.append(f"model {mp * 100:.1f}% vs market {fp * 100:.1f}% (prob guard)")
    market = o["bet_type"].split("|")[0]
    pre, base = v5.split_market("NFL", market)
    per = gaps.get(o["game"], {}).get(pre)
    if per and not o["player"]:
        sg, tg = per
        name = pre or "full-game"
        if base == "SPREAD" and abs(sg) > GAP_PTS:
            reasons.append(f"{name} projection {sg:+.1f} pts off book spread (>{GAP_PTS:g})")
        elif base == "TOTAL" and abs(tg) > GAP_PTS:
            reasons.append(f"{name} projection {tg:+.1f} pts off book total (>{GAP_PTS:g})")
    o["held"] = "; ".join(reasons)
    return o


def best_per_group(rows):
    groups = {}
    for o in sorted(rows, key=lambda x: -x["ev"]):
        groups.setdefault((o["sport"], o["game"], o["player"] or o["bet_type"]), []).append(o)
    picks = []
    for g in groups.values():
        solid = [o for o in g if o["model_p"] >= 0.20]
        pick = dict((solid or g)[0])
        pick["also"] = len(g) - 1
        picks.append(pick)
    return sorted(picks, key=lambda x: -x["ev"])


def build(path):
    path = os.path.abspath(path)
    old = v5.N_FIT
    v5.N_FIT = N_FIT
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = v5.run(path)
        gaps = projection_gaps(load_nfl_lines(path))
    finally:
        v5.N_FIT = old
    notes = buf.getvalue().split("CARD (")[0].rstrip()
    out = [guard(o, gaps) for o in out]
    held = sorted([o for o in out if o["held"]], key=lambda x: (x["game"], x["pick"]))
    ok = [o for o in out if not o["held"] and o["ev"] >= v5.EV_FLOOR]
    blended = best_per_group([o for o in ok if o["status"] != "MODEL_ONLY"])
    card = [o for o in blended if o["ev"] < v5.DOUBT_EV]
    doubted = [o for o in blended if o["ev"] >= v5.DOUBT_EV]
    model_only = best_per_group([o for o in ok if o["status"] == "MODEL_ONLY"])
    return dict(notes=notes, gaps=gaps, out=out, card=card, doubted=doubted,
                model_only=model_only, held=held)


def table(rows, held=False):
    print("| # | Game | Pick | Price | Model % | Blend % | Mkt % | EV | Stars |" + (" Held |" if held else ""))
    print("|---|------|------|-------|---------|---------|-------|----|-------|" + ("------|" if held else ""))
    for i, o in enumerate(rows, 1):
        mk = f"{o['market_p'] * 100:.1f}%" if o["market_p"] is not None else "-"
        more = f" (+{o['also']} other numbers)" if o.get("also") else ""
        stake = f" 0u - {o['held']} |" if held else ""
        print(f"| {i} | {o['sport']} {o['game']} | {o['pick']}{more} | {o['price']:+d} | "
              f"{o['model_p'] * 100:.1f}% | {o['blend_p'] * 100:.1f}% | {mk} | {o['ev'] * 100:+.1f}% | "
              f"{'*' * o['stars']} |{stake}")


def main(path):
    r = build(path)
    print(r["notes"], "\n")
    for g, per in r["gaps"].items():
        sg, tg = per[""]
        print(f"NFL {g}: projection vs book  spread {sg:+.1f}  total {tg:+.1f}")
    print(f"\nCARD ({len(r['card'])}) - NFL two-sided rows ranked by 30/70 blended EV\n")
    table(r["card"])
    if r["doubted"]:
        print(f"\nMODEL-DOUBTED ({len(r['doubted'])}) - blended EV 40%+\n")
        table(r["doubted"])
    if r["model_only"]:
        print(f"\nMODEL-ONLY ({len(r['model_only'])}) - no two-sided no-vig price, not blended, not on the card\n")
        table(r["model_only"])
    if r["held"]:
        print(f"\nHELD ({len(r['held'])}) - every held priced side, 0u\n")
        table(r["held"], held=True)
    with open("picks_nfl.csv", "w", newline="") as f:
        keys = list(r["out"][0].keys()) if r["out"] else ["pick"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(r["out"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "board.csv")
