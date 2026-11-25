#!/usr/bin/env python3
"""SportsEdge NFL run-it card with the owner guards approved Nov 23 2026.

Wraps engine v5 without changing it. NFL rows only:
  1. 30/70 blend - two-sided rows are ranked by EV on
     p = 0.30 * model_p + 0.70 * no-vig market_p (probabilities, not points).
     Push share is kept from the model.
  2. 6-point hold - each two-sided SPREAD / TOTAL quote (any period, alts too) is HELD
     when the model's projection for that period is more than 6 points off the projection
     implied by that exact quote. Not applied to ML or props.
  3. Probability-disagreement hold (Nov 15 ruling, separate check) - two-sided rows are
     HELD when raw model_p is > 1.5x or < 0.67x the no-vig market_p, or > 12 points apart.
  4. Rows with no valid two-sided no-vig price are never blended and never go on the
     blended card; they are listed separately as MODEL-ONLY.
  5. Monte Carlo noise - N_FIT 20,000 -> 100,000 for this run only (restored afterwards).
Every held row is listed with its reason at 0u. Every exported row carries row_id, quote_id and
selected_for_card (true only for rows on the final research card; approved_stake_u stays 0 regardless). Non-NFL rows pass through with v5 numbers.

Usage:  python engine/run_nfl.py board.csv
"""
import contextlib
import csv
import hashlib
import io
import os
import sys


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


def _quote_values(S, pre, base):
    ix = v5.PERIODS["NFL"].get(pre) if pre else None
    h, a = (S["h"], S["a"]) if ix is None else (S["H"][:, ix].sum(1), S["A"][:, ix].sum(1))
    return (h - a) if base == "SPREAD" else (h + a)


def quote_gap(S, r):
    """Model projection minus the projection implied by THIS two-sided quote, same period.

    Shift the model's own simulated period distribution by d until the quote's no-vig
    price is a fair coin (pushes excluded, as v5 does); the quote-implied mean is the
    model mean + d, so the gap is -d. Spread: home-margin points (+ = model likes home
    more than the quote). Total: points (+ = model higher than the quote)."""
    pre, base = v5.split_market("NFL", r["market"])
    x = _quote_values(S, pre, base)
    sign = 1.0 if base == "SPREAD" else -1.0
    fa = v5.fair_a(r)

    def f(d):
        y = x + d + sign * r["line"]
        return v5.cond(float((y > 0).mean()), float((y < 0).mean())) - fa
    return -v5.bisect(f, -80.0, 80.0, 40)


def projection_gaps(games):
    """{(game, market, line, side, price): gap} for every two-sided NFL SPREAD / TOTAL quote (all
    periods, alts included) in pregame games that have a projection. Each quote is compared
    with the model's projection for the same period."""
    out = {}
    for (home, away), g in games.items():
        if any(r["rem"] is not None for r in g["all"]):
            continue                                   # live games: no hold
        proj = next(((r["hp"], r["ap"]) for r in g["all"]
                     if r["hp"] is not None and r["ap"] is not None), None)
        if proj is None:
            continue                                   # ANCHOR games have no opinion on the main line
        S = v5.simulate("NFL", proj[0], proj[1], v5.seed_of(f"NFL|{home}|{away}"), N_GAP)
        for r in g["lines"]:
            base = v5.split_market("NFL", r["market"])[1]
            if base in ("SPREAD", "TOTAL") and r["price_a"] and r["price_b"]:
                gap = quote_gap(S, r)
                for side, price in ((0, r["price_a"]), (1, r["price_b"])):
                    key = (f"{away} @ {home}", r["market"], float(r["line"]), side, int(price))
                    if key in out and (out[key] is None or abs(out[key] - gap) > 1e-9):
                        out[key] = None                # ambiguous duplicate quote: never guess
                    else:
                        out[key] = gap
    return out


def _row_line(o):
    """Home-side line (SPREAD) or number (TOTAL) of a priced side, from its v5 label."""
    ln = float(o["pick"].split()[-1])
    side = o["bet_type"].split("|")[1]
    return -ln if o["bet_type"].split("|")[0].endswith("SPREAD") and side == "1" else ln


def guard(o, gaps):
    """Add blend_p / model_ev / held / status to one priced side; EV becomes the blended EV."""
    o["model_ev"], o["blend_p"], o["held"], o["status"] = o["ev"], o["model_p"], "", "v5"
    o["approved_stake_u"] = 0
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
        if abs(den) > 1e-6:
            s = min(max(o["ev"] / den, 0.0), 1.0)       # share of sims that don't push
        else:                                           # model exactly break-even: push share
            s = 0.0                                     # unrecoverable -> no blended edge claimed
            reasons.append("push share not recoverable at break-even (hold)")
        o["blend_p"] = p
        o["ev"] = s * (p * pay - (1 - p))
        o["score"] = v5.score(o["ev"])
        o["stars"] = v5.stars(o["score"])
        if mp > P_RATIO_HI * fp or mp < P_RATIO_LO * fp or abs(mp - fp) > P_ABS:
            reasons.append(f"model {mp * 100:.1f}% vs market {fp * 100:.1f}% (prob guard)")
    market = o["bet_type"].split("|")[0]
    pre, base = v5.split_market("NFL", market)
    if base in ("SPREAD", "TOTAL") and not o["player"]:
        key = (o["game"], market, _row_line(o), int(o["bet_type"].split("|")[1]), int(o["price"]))
        if key in gaps and gaps[key] is None:
            reasons.append("duplicate quote with conflicting gap (hold)")
        gap = gaps.get(key)
        if gap is not None and abs(gap) > GAP_PTS:
            name = pre or "full-game"
            kind = "spread" if base == "SPREAD" else "total"
            reasons.append(f"{name} projection {gap:+.1f} pts off this {kind} quote (>{GAP_PTS:g})")
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


def football_reporting_rows(rows, board_raw):
    """Presentation-only projection estimates for NFL and CFB.
    Exact local board-label reconciliation is not provider authentication.
    The frozen v5 emitter does not expose W/L/push; never invent a nine-weight EV.
    """
    from collections import Counter, defaultdict
    from datetime import datetime
    import math
    import re

    def utc(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
            raise ValueError("UTC_Z_REQUIRED")
        return datetime.fromisoformat(value[:-1] + "+00:00")

    def key(o):
        return tuple(o.get(k) for k in ("sport", "game", "bet_type", "player", "pick", "price"))

    quotes = defaultdict(list)
    if board_raw is not None:
        for raw in csv.DictReader(io.StringIO(board_raw.decode("utf-8-sig"))):
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            sport, market = r.get("sport", "").upper(), r.get("market", "").upper()
            if sport not in ("NFL", "CFB") or not market or market == "SGP":
                continue
            if not r.get("home") or not r.get("away") or v5.num(r.get("remaining")) is not None:
                continue
            r["sport"], r["market"], r["line"] = sport, market, v5.num(r.get("line")) or 0.0
            player = r.get("player", "")
            try:
                if player and market in v5.TD_NAMES:
                    labels = (f"{player} {v5.TD_NAMES[market]}", f"{player} No {v5.TD_NAMES[market]}")
                elif player:
                    name = market.replace("_", " ").title()
                    labels = (f"{player} Over {r['line']:g} {name}", f"{player} Under {r['line']:g} {name}")
                else:
                    labels = v5.game_labels(sport, r)
                for i, col in enumerate(("price_a", "price_b")):
                    price = v5.num(r.get(col))
                    if price is None or not math.isfinite(price) or price != int(price) or abs(price) < 100:
                        continue
                    k = (sport, f"{r['away']} @ {r['home']}", f"{market}|{i}|{r.get('sgp', '')}", player, labels[i], int(price))
                    quotes[k].append(r)
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
    football = [o for o in rows if o.get("sport") in ("NFL", "CFB")]
    counts = Counter(key(o) for o in football)
    report = []
    for o in football:
        candidates = quotes.get(key(o), [])
        cap = None
        event = None
        book = None
        provenance = "BLOCKED_BOARD_CHANGED" if board_raw is None else "BLOCKED_QUOTE_UNMATCHED_OR_AMBIGUOUS"
        if len(candidates) == 1 and counts[key(o)] == 1:
            q = candidates[0]
            try:
                capture = q.get("captured_utc")
                tip = q.get("tip_utc") or q.get("start_utc")
                if utc(capture) >= utc(tip):
                    raise ValueError("NOT_PREGAME")
                event = q.get("dk_event_id") or q.get("event_id")
                book = q.get("book")
                if not event or not book:
                    raise ValueError("EVENT_OR_BOOK_MISSING")
                cap = capture
                provenance = "LOCAL_EXACT_LABEL_MATCH_NOT_AUTHENTICATED"
            except (TypeError, ValueError):
                event = book = None
                provenance = "BLOCKED_QUOTE_METADATA"
        ev = o.get("model_ev")
        if type(ev) not in (int, float) or not math.isfinite(ev):
            ev = None
        mode = o.get("mode")
        state = ("BLOCKED_MODEL_EV_MISSING" if ev is None else
                 "MODEL_ESTIMATED_POSITIVE_WITHHELD" if ev > 0 else "NO_POSITIVE_MODEL_EV")
        report.append(dict(sport=o["sport"], game=o["game"], pick=o["pick"], price=o["price"],
                           row_id=o["row_id"], quote_id=o["quote_id"],
                           model_basis="SUPPLIED_PROJECTION_UNVERIFIED" if mode == "PROJECTION" else
                           "MARKET_ANCHORED_NOT_INDEPENDENT" if mode == "ANCHOR" else "UNKNOWN_MODEL_BASIS",
                           model_ev=ev, captured_utc=cap, event_id=event, book=book,
                           provenance=provenance, state=state, held=o.get("held", ""),
                           nine_weight_status="BLOCKED_EXPLICIT_OUTCOME_MASS_MISSING",
                           external_consensus="BLOCKED_NO_EXTERNAL_CONSENSUS", approved_stake_u=0))
    return report


def print_football_reporting(rows):
    print("\nALL EMITTED NFL/CFB SIDES — model estimates, PAPER / 0u, not validated EV")
    print("Market-anchored estimates are not independent. Exact local quote matches are not provider authentication.")
    print("Nine-weight EV blocked until explicit outcome masses are available. External consensus blocked.")
    print("| Sport | Game | Pick | Price | Model EV | Capture UTC | Basis | Quote provenance | Validation | Guard |")
    print("|---|---|---|---:|---:|---|---|---|---|---|")
    def clean(x):
        return str(x if x is not None else "UNKNOWN").replace("|", "/").replace("\n", " ").replace("\r", " ")
    for o in rows:
        ev = "UNKNOWN" if o["model_ev"] is None else f"{100*o['model_ev']:+.2f}%"
        cells = [o["sport"], o["game"], o["pick"], o["price"], ev, o["captured_utc"],
                 o["model_basis"], o["provenance"], o["state"], o["held"] or "UNVALIDATED"]
        print("| " + " | ".join(clean(x) for x in cells) + " |")


def build(path):
    path = os.path.abspath(path)
    with open(path, 'rb') as f:
        board_raw = f.read()
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
    for i, o in enumerate(out):                      # stable identity: v5 emission order + quote content
        o["row_id"] = i
        o["quote_id"] = hashlib.sha256("|".join(str(o.get(k, "")) for k in (
            "sport", "game", "bet_type", "player", "pick", "price")).encode() + f"|{i}".encode()).hexdigest()[:16]
        o["selected_for_card"] = False
    held = sorted([o for o in out if o["held"]], key=lambda x: (x["game"], x["pick"]))
    ok = [o for o in out if not o["held"] and o["ev"] >= v5.EV_FLOOR]
    blended = best_per_group([o for o in ok if o["status"] != "MODEL_ONLY"])
    card = [o for o in blended if o["ev"] < v5.DOUBT_EV]
    doubted = [o for o in blended if o["ev"] >= v5.DOUBT_EV]
    model_only = best_per_group([o for o in ok if o["status"] == "MODEL_ONLY"])
    chosen = {c["row_id"] for c in card}             # marker only: selection logic above is unchanged
    for o in out:
        o["selected_for_card"] = o["row_id"] in chosen
    # best_per_group copies row dicts. Sync each display copy to its exact
    # original identity; a returned card must agree with the exported CSV.
    for group in (card, doubted, model_only):
        for c in group:
            origin = out[c["row_id"]]
            if c["quote_id"] != origin["quote_id"]:
                raise ValueError("card row identity differs from exported priced side")
            c["selected_for_card"] = origin["selected_for_card"]
    with open(path, 'rb') as f:
        if f.read() != board_raw:
            board_raw = None
    report = football_reporting_rows(out, board_raw)
    return dict(notes=notes, gaps=gaps, out=out, card=card, doubted=doubted,
                model_only=model_only, held=held, football_report=report)


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
    print_football_reporting(r["football_report"])
    seen = set()
    for (g, mk, ln, _side, _price), gap in sorted(r["gaps"].items(), key=lambda kv: kv[0][:4]):
        if (g, mk, ln) in seen:
            continue
        seen.add((g, mk, ln))
        txt = "ambiguous duplicate" if gap is None else f"{gap:+.1f} pts"
        print(f"NFL {g} {mk} {ln:+g}: projection vs quote {txt}")
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
    import datetime
    name = "picks_nfl_" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".csv"
    with open(name, "x", newline="") as f:                     # create-only, never overwrite
        keys = list(r["out"][0].keys()) if r["out"] else ["pick"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(r["out"])
    print(f"\nAll priced sides saved to {name} (research only; approved_stake_u = 0 on every row)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "board.csv")
