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


def _rung(b):
    """(line, price_a, price_b) from a board row, or None when not posted two-sided."""
    try:
        line = float(b["line"])
        pa, pb = int(b["price_a"]), int(b["price_b"])
        NM.decimal_odds(pa); NM.decimal_odds(pb)
        return (line, pa, pb) if math.isfinite(line) else None
    except (TypeError, ValueError, KeyError, NM.Pass):
        return None


def price_ladders(board_rows, match, slate_rows, card, cfg, captured_utc):
    """Price alt spread/total and team-total rungs for PROJECTED games. Returns (rows, skipped)."""
    proj = {r["game_id"]: r["projection"] for r in card["rows"] if r["status"] == "PROJECTED"}
    out, skipped = [], []
    for b in board_rows:
        kind = LADDER_MARKETS.get(b.get("market"))
        if b.get("sport") != "CBB" or kind is None:
            continue
        name = f"{b.get('away')} @ {b.get('home')}"
        g, why = match(slate_rows, b["home"], b["away"], b)
        if not g:
            skipped.append((name, b["market"], why)); continue
        p = proj.get(g["game_id"])
        rung = _rung(b)
        if p is None or rung is None:
            skipped.append((name, b["market"], "not projected or rung not posted two-sided")); continue
        line, pa, pb = rung
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
        out.append({"game_id": g["game_id"], "kind": kind, "line": line, "sides": sides,
                    "price": (pa, pb), "model_prob": (a, c), "push": push, "market_novig": (ma, mb),
                    "paper_ev": (NM.ev_per_unit(a, push, pa), NM.ev_per_unit(c, push, pb)),
                    "blend_ev": (NM.ev_per_unit(blend(a, ma, w, push=push), push, pa),
                                 NM.ev_per_unit(blend(c, mb, w, push=push), push, pb)),
                    "blowout_excluded": is_blowout("spread", line, cfg) if kind == "alt_spread" else False,
                    "captured_utc": captured_utc})
    return out, skipped
