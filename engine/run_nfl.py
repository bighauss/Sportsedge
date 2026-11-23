#!/usr/bin/env python3
"""SportsEdge NFL run-it card with the owner guards approved Nov 23 2026.

Wraps engine v5 without changing it:
  1. 30/70 blend - two-sided NFL rows are ranked by EV on
     p = 0.30 * model_p + 0.70 * no-vig market_p (probabilities, not points).
     Push share is kept from the model. One-sided rows keep model_p.
  2. 6-point hold - NFL SPREAD / TOTAL rows (full game and periods) are HELD when
     the projection is more than 6 points off the book-implied spread / total.
     Held rows are listed with the reason and a 0u stake; they never reach the card.
     Not applied to ML or props.
  3. Monte Carlo noise - N_FIT 20,000 -> 100,000 (prop SE(p) ~0.35% -> ~0.16%).
Non-NFL rows pass through with v5 numbers.

Usage:  python engine/run_nfl.py board.csv
"""
import contextlib
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sportsedge_v5 as v5  # noqa: E402

BLEND_W = 0.30
GAP_PTS = 6.0
N_FIT = 100000


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


def projection_gaps(games):
    """{game label: (spread gap, total gap)} for pregame NFL games that have a projection."""
    out = {}
    for (home, away), g in games.items():
        if any(r["rem"] is not None for r in g["all"]):
            continue                                   # live games: no hold
        proj = next(((r["hp"], r["ap"]) for r in g["all"]
                     if r["hp"] is not None and r["ap"] is not None), None)
        if proj is None:
            continue                                   # ANCHOR games have no opinion on the main line
        bk = v5.anchor("NFL", g["lines"], v5.seed_of(f"NFL|{home}|{away}"))
        if bk:
            hp, ap = proj
            out[f"{away} @ {home}"] = ((hp - ap) - (bk[0] - bk[1]), (hp + ap) - (bk[0] + bk[1]))
    return out


def guard(o, gaps):
    """Add blend_p / model_ev / held to one priced side; EV becomes the blended EV."""
    o["model_ev"], o["blend_p"], o["held"] = o["ev"], o["model_p"], ""
    if o["sport"] != "NFL":
        return o
    mp, fp = o["model_p"], o["market_p"]
    if fp is not None:
        p = BLEND_W * mp + (1 - BLEND_W) * fp
        pay = v5.payout(o["price"])
        den = mp * pay - (1 - mp)
        s = o["ev"] / den if abs(den) > 1e-9 else 1.0      # share of sims that don't push
        s = min(max(s, 0.0), 1.0) if s == s else 1.0
        o["blend_p"] = p
        o["ev"] = s * (p * pay - (1 - p))
        o["score"] = v5.score(o["ev"])
        o["stars"] = v5.stars(o["score"])
    market = o["bet_type"].split("|")[0]
    base = v5.split_market("NFL", market)[1]
    gap = gaps.get(o["game"])
    if gap and not o["player"]:
        sg, tg = gap
        if base == "SPREAD" and abs(sg) > GAP_PTS:
            o["held"] = f"projection {sg:+.1f} pts off book spread (>{GAP_PTS:g})"
        elif base == "TOTAL" and abs(tg) > GAP_PTS:
            o["held"] = f"projection {tg:+.1f} pts off book total (>{GAP_PTS:g})"
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
    v5.N_FIT = N_FIT
    buf = io.StringIO()
    cwd = os.getcwd()
    with contextlib.redirect_stdout(buf):
        out = v5.run(path)
    notes = buf.getvalue().split("CARD (")[0].rstrip()
    gaps = projection_gaps(load_nfl_lines(os.path.join(cwd, path) if not os.path.isabs(path) else path))
    out = [guard(o, gaps) for o in out]
    live = [o for o in out if not o["held"]]
    held = [o for o in out if o["held"] and o["model_ev"] >= v5.EV_FLOOR]
    picks = best_per_group([o for o in live if o["ev"] >= v5.EV_FLOOR])
    card = [o for o in picks if o["ev"] < v5.DOUBT_EV]
    doubted = [o for o in picks if o["ev"] >= v5.DOUBT_EV]
    return dict(notes=notes, gaps=gaps, out=out, card=card, doubted=doubted,
                held=best_per_group(held))


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
    for g, (sg, tg) in r["gaps"].items():
        print(f"NFL {g}: projection vs book  spread {sg:+.1f}  total {tg:+.1f}")
    print(f"\nCARD ({len(r['card'])}) - NFL ranked by 30/70 blended EV\n")
    table(r["card"])
    if r["held"]:
        print(f"\nHELD ({len(r['held'])}) - 6-pt projection/book gap, 0u\n")
        table(r["held"], held=True)
    if r["doubted"]:
        print(f"\nMODEL-DOUBTED ({len(r['doubted'])}) - EV 40%+\n")
        table(r["doubted"])
    with open("picks_nfl.csv", "w", newline="") as f:
        keys = list(r["out"][0].keys()) if r["out"] else ["pick"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(r["out"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "board.csv")
