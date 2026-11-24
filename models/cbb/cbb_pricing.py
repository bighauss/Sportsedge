"""CBB RUN IT pricing config + adapters (PAPER / 0u). Does NOT edit the frozen native model.

* SD constants: margin 12.5, total 17 (tighter fitted SDs overstated confidence). Applied by
  wrapping ``project`` for the duration of a build; the fitted SDs stay in the card context.
* Blend: p_blend = w * p_model + (1 - w) * (1 - p_push) * p_market_no_vig. w default 0.25 is EXPERIMENTAL;
  candidate weights below await a chronological test. Nothing here is validated.
* Blowout guard: early-season ratings compress blowout margins (large-underdog spread bias),
  so spreads with |market line| > 15 are excluded from best plays (priced, but flagged).
* Ladders (alt spread / alt total / team totals): same projected mean and SD, normal model.
  Team-total SD = sd_total * team_total_sd_factor (default 1/sqrt(2): ASSUMES equal,
  uncorrelated team variances; configurable). Rows not posted are skipped, never invented.
"""
from __future__ import annotations
import math
from contextlib import contextmanager

import cbbd_paper_card as PC
import cbbd_native_score_model as NM

CANDIDATE_BLEND_WEIGHTS = (0.0, 0.25, 0.5, 0.6, 0.75, 0.8, 0.9, 0.95, 1.0)  # model weight; test pending
DEFAULT_CONFIG = {
    "sd_margin": 12.5,
    "sd_total": 17.0,
    "blend_weight_model": 0.25,          # EXPERIMENTAL
    "blowout_spread_abs": 15.0,
    "team_total_sd_factor": 1 / math.sqrt(2),
}
LADDER_MARKETS = {"ALT_SPREAD": "alt_spread", "ALT_TOTAL": "alt_total",
                  "TT_HOME": "team_total_home", "TT_AWAY": "team_total_away"}


def make_config(**over):
    cfg = {**DEFAULT_CONFIG, **{k: v for k, v in over.items() if v is not None}}
    if not (cfg["sd_margin"] > 0 and cfg["sd_total"] > 0 and cfg["team_total_sd_factor"] > 0):
        raise ValueError("SD_CONFIG_INVALID")
    if not 0.0 <= cfg["blend_weight_model"] <= 1.0:
        raise ValueError("BLEND_WEIGHT_OUT_OF_RANGE")
    return cfg


def blend(p_model, p_market, w, *, push=0.0):
    """Blend unconditional model win mass with conditional market win mass.

    Hold the modeled push probability fixed; two side probabilities and push sum to one.
    """
    return w * p_model + (1 - w) * (1 - push) * p_market


def is_blowout(market, line, cfg):
    return market == "spread" and line is not None and abs(line) > cfg["blowout_spread_abs"]


@contextmanager
def patched_card(cfg):
    """Constant SDs + blend/guard fields on every priced market, restored on exit."""
    orig_project, orig_price = PC.project, PC._price_market

    def project(ctx, home, away, *, neutral):
        p = NM.project(ctx, home, away, neutral=neutral, _need_sd=False)
        p.update(sd_margin=cfg["sd_margin"], sd_total=cfg["sd_total"],
                 sd_basis="CONFIG_CONSTANT_NOT_FITTED", sd_n=0)
        return p

    def price(proj, q):
        m = orig_price(proj, q)
        s0, s1 = m["sides"]
        w = cfg["blend_weight_model"]
        pm, mk = m["model_prob"], m["market_novig_prob"]
        bp = {s0: blend(pm[s0], mk[s0], w, push=pm["push"]),
              s1: blend(pm[s1], mk[s1], w, push=pm["push"])}
        m["blend"] = {"label": "EXPERIMENTAL", "weight_model": w, "prob": bp, "push": pm["push"],
                      "paper_ev_per_1u_at_price": {
                          s0: NM.ev_per_unit(bp[s0], pm["push"], q["price_a"]),
                          s1: NM.ev_per_unit(bp[s1], pm["push"], q["price_b"])}}
        m["blowout_excluded"] = is_blowout(q["market"], q["line"], cfg)
        return m

    PC.project, PC._price_market = project, price
    try:
        yield
    finally:
        PC.project, PC._price_market = orig_project, orig_price


MAIN_MARKETS = ("SPREAD", "TOTAL", "ML")
LINE_BOUNDS = {"alt_spread": (-60, 60), "alt_total": (80, 220),
               "team_total_home": (30, 130), "team_total_away": (30, 130)}
OVERROUND_RANGE = (-0.005, 0.25)   # no-vig sum outside this is a bad pair, not a price
MAX_ABS_PRICE = 5000
MONO_TOL = 0.02                    # no-vig side prob may not move against the line by more than this


def _rung(b, kind):
    """(line, price_a, price_b) from a board row, or (None, reason). Both sides required."""
    raw = [b.get(k) for k in ("line", "price_a", "price_b")]
    if any(v is None or str(v).strip() == "" for v in raw):
        return None, "rung not posted two-sided (missing line or price)"
    try:
        line = float(raw[0]); pa, pb = int(str(raw[1]).strip()), int(str(raw[2]).strip())
        NM.decimal_odds(pa); NM.decimal_odds(pb)
    except (TypeError, ValueError, NM.Pass):
        return None, "rung price or line not valid American/numeric"
    lo, hi = LINE_BOUNDS[kind]
    if not math.isfinite(line) or not lo <= line <= hi or (line * 2) % 1:
        return None, "rung line outside plausible range or off the half-point grid"
    if abs(pa) > MAX_ABS_PRICE or abs(pb) > MAX_ABS_PRICE:
        return None, "implausible price magnitude"
    _, _, over = NM.no_vig(pa, pb)
    if not OVERROUND_RANGE[0] <= over <= OVERROUND_RANGE[1]:
        return None, f"no-vig sum out of range (overround {over:.3f})"
    return (line, pa, pb), None


def _main_ref(card, gid):
    ref = {}
    for r in card["rows"]:
        if r["game_id"] == gid:
            for m in r["markets"]:
                if m["status"] == "PRICED_PAPER" and m["market"] in ("spread", "total"):
                    ref[m["market"]] = m["quote"]
    return ref


def price_ladders(board_rows, match, slate_rows, card, cfg, captured_utc, *,
                  totals_order=None, event_id=None, max_age_hours=24):
    """Price alt spread/total and team-total rungs for PROJECTED games. Returns (rows, skipped).

    Every rung must be: captured before the card freeze and not stale; two-sided with valid, plausible
    prices and a sane no-vig sum; on the half-point grid; matched by name + tip (+ DK event ID bound
    one-to-one with the main-line rows); totals order verified for the board format (swap honoured);
    and oriented consistently with the main line (alt spread/total must move the home-cover / over
    no-vig probability the right way relative to the posted main line; team totals must be monotone
    within their own ladder). Duplicate (game, kind, line) rows quarantine every copy.
    """
    freeze = NM.utc(card["freeze_utc"], "freeze_utc")
    proj = {r["game_id"]: r["projection"] for r in card["rows"] if r["status"] == "PROJECTED"}
    event_id = event_id or (lambda b: None)
    skipped = []
    try:
        cap = NM.utc(captured_utc, "board_captured_utc")
        if cap > freeze: raise NM.Pass("after freeze")
        if (freeze - cap).total_seconds() > max_age_hours * 3600: raise NM.Pass("stale")
        stamp_ok = True
    except NM.Pass as exc:
        stamp_ok = False; stamp_why = f"board capture time invalid for freeze ({exc})"
    # pass 1: match every relevant board row (main + ladder) to build the event <-> game binding
    cand = []
    for b in board_rows:
        if b.get("sport") != "CBB":
            continue
        is_ladder = b.get("market") in LADDER_MARKETS
        if not is_ladder and b.get("market") not in MAIN_MARKETS:
            continue
        g, why = match(slate_rows, b["home"], b["away"], b)
        cand.append((b, g, why, is_ladder))
    ev_games, game_evs = {}, {}
    for b, g, _, _ in cand:
        e = event_id(b)
        if g and e:
            ev_games.setdefault(e, set()).add(g["game_id"]); game_evs.setdefault(g["game_id"], set()).add(e)
    # pass 2: per-row validation
    valid = []
    for b, g, why, is_ladder in cand:
        if not is_ladder:
            continue
        kind = LADDER_MARKETS[b["market"]]; name = f"{b.get('away')} @ {b.get('home')}"
        def skip(reason, name=name, m=b["market"]): skipped.append((name, m, reason))
        if not stamp_ok: skip(stamp_why); continue
        if not g: skip(why); continue
        e = event_id(b)
        if (e and (len(ev_games[e]) > 1 or len(game_evs[g["game_id"]]) > 1)) or (
                not e and game_evs.get(g["game_id"])):
            skip("DK event id conflict or missing for this game"); continue
        p = proj.get(g["game_id"])
        if p is None: skip("game not projected"); continue
        rung, why2 = _rung(b, kind)
        if rung is None: skip(why2); continue
        line, pa, pb = rung
        if kind in ("alt_total", "team_total_home", "team_total_away"):
            order = totals_order(b) if totals_order else None
            if order is None: skip("over/under price order not verified for this board format"); continue
            if order == "swap": pa, pb = pb, pa
        valid.append((b, g, kind, line, pa, pb, name))
    dup = {}
    for _, g, kind, line, _, _, _ in valid:
        dup[(g["game_id"], kind, line)] = dup.get((g["game_id"], kind, line), 0) + 1
    ladders = {}
    for v in valid:
        _, g, kind, line, pa, pb, name = v
        if dup[(g["game_id"], kind, line)] > 1:
            skipped.append((name, kind, "duplicate rung (all copies quarantined)")); continue
        ladders.setdefault((g["game_id"], kind), []).append(v)
    out = []
    for (gid, kind), rungs in ladders.items():
        ref = _main_ref(card, gid); p = proj[gid]
        rungs.sort(key=lambda v: v[3])
        key = {"alt_spread": "spread", "alt_total": "total"}.get(kind)
        if key and key not in ref:
            skipped += [(v[6], kind, "no posted main line to orient against") for v in rungs]; continue
        # points: (line, no-vig prob of side_a); side_a = home cover (spread) or over (totals)
        pts = [(v[3], NM.no_vig(v[4], v[5])[0]) for v in rungs]
        if key:
            q = ref[key]; mp = NM.no_vig(q["price_a"], q["price_b"])[0]
            pts.append((q["line"], mp))
            pts.sort()
        # home-cover prob rises with the home line; over prob falls with the line
        sign = 1 if kind == "alt_spread" else -1
        bad = set()
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                if sign * (pts[j][1] - pts[i][1]) < -MONO_TOL:   # both ends of a violating pair are suspect
                    bad.update((pts[i][0], pts[j][0]))
        for v in rungs:
            line, pa, pb, name = v[3], v[4], v[5], v[6]
            if line in bad:
                skipped.append((name, kind, "orientation inconsistent with main line / ladder")); continue
            if kind == "alt_spread":
                a, push, c = NM._line_probs(p["margin"], cfg["sd_margin"], -line); sides = ("home", "away")
            elif kind == "alt_total":
                a, push, c = NM._line_probs(p["total"], cfg["sd_total"], line); sides = ("over", "under")
            else:
                mu = p["home_points"] if kind.endswith("home") else p["away_points"]
                a, push, c = NM._line_probs(mu, cfg["sd_total"] * cfg["team_total_sd_factor"], line)
                sides = ("over", "under")
            ma, mb, _ = NM.no_vig(pa, pb)
            w = cfg["blend_weight_model"]
            out.append({"game_id": gid, "kind": kind, "line": line, "sides": sides,
                        "price": (pa, pb), "model_prob": (a, c), "push": push, "market_novig": (ma, mb),
                        "paper_ev": (NM.ev_per_unit(a, push, pa), NM.ev_per_unit(c, push, pb)),
                        "blend_ev": (NM.ev_per_unit(blend(a, ma, w, push=push), push, pa),
                                     NM.ev_per_unit(blend(c, mb, w, push=push), push, pb)),
                        "blowout_excluded": is_blowout("spread", line, cfg) if kind == "alt_spread" else False,
                        "captured_utc": captured_utc})
    return out, skipped
