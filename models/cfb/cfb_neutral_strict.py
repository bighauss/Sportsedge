"""Versioned strict neutral-site entry point for the pinned CFB model (issue #432).

sportsedge_cfb_model.py is NOT modified (git blob a07f4cd429e344e8ee0d131bdfa8e1ef7a91da20).
Its run_game() uses bool(game.get("neutralSite")): missing/null become False (home field
applied) and any non-empty string, including "false", becomes True (home field removed).
This module validates the flag first, then delegates to the unchanged model, so
coefficients, weights and pricing are identical for every admitted game.

Venue HFA safeguard: the pinned model computes float(ven.get("hfa") or HFA_DEFAULT), so an
explicit 0 silently becomes 2.5. For NON-neutral games this module therefore withholds
an explicit zero, and any malformed, negative or nonfinite venue hfa, with a named reason.
A missing key or None means 'no venue hfa configured' and the documented default applies.
Neutral games skip the venue hfa check because the pinned model sets hfa to 0.0 for them.
A versioned challenger that preserves legitimate zero-HFA venues is a separate follow-up.

Identity transition: pinned model blob unchanged; new entry point STRICT_VERSION.
PAPER / 0u / NON_COUNTED. Not a validation claim.
"""
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sportsedge_cfb_model as M

STRICT_VERSION = "cfb-neutral-strict-v1"
BASE_MODEL_BLOB_SHA = "a07f4cd429e344e8ee0d131bdfa8e1ef7a91da20"
WITHHOLD_REASON = "CFBD neutralSite missing or not boolean"
HFA_ZERO_REASON = "VENUE_HFA_ZERO_UNSUPPORTED_BY_PINNED_MODEL"
HFA_INVALID_REASON = "VENUE_HFA_INVALID"


class NeutralSiteError(ValueError):
    pass


class VenueHfaError(ValueError):
    pass


def require_neutral_flag(game):
    v = game.get("neutralSite") if isinstance(game, dict) else None
    if not isinstance(v, bool):
        gid = game.get("id") if isinstance(game, dict) else None
        raise NeutralSiteError(f"{WITHHOLD_REASON} (game {gid!r}: {v!r})")
    return v


def check_venue_hfa(game, ctx, neutral):
    """Only for non-neutral games. Missing key or None -> pinned default applies (allowed)."""
    if neutral:
        return
    ven = (ctx.get("venues") or {}).get(game.get("venue"))
    if not isinstance(ven, dict) or "hfa" not in ven or ven["hfa"] is None:
        return
    v = ven["hfa"]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise VenueHfaError(f"{HFA_INVALID_REASON} (game {game.get('id')!r}: {v!r})")
    if v == 0:
        raise VenueHfaError(f"{HFA_ZERO_REASON} (game {game.get('id')!r})")


def run_game_strict(game, ctx):
    neutral = require_neutral_flag(game)
    check_venue_hfa(game, ctx, neutral)
    admitted = dict(game)
    admitted["neutralSite"] = neutral
    proj = M.run_game(admitted, ctx)
    if neutral and proj["hfa"] != 0.0:
        raise AssertionError("neutral game produced nonzero home-field advantage")
    proj["model_path"] = STRICT_VERSION
    return proj


def run_card_strict(inputs, out_dir="."):
    """Same flow as the pinned run_card, but every game passes run_game_strict.
    Returns (card_rows, projections, withheld). Withheld games are written to cfb_withheld.csv."""
    if isinstance(inputs, str):
        base = os.path.dirname(os.path.abspath(inputs))
        with open(inputs) as f:
            inputs = json.load(f)
        inputs = {k: (os.path.join(base, v) if isinstance(v, str) and not os.path.isabs(v) else v)
                  for k, v in inputs.items()}
    ctx = M.build_ctx(inputs)
    lines = {}
    for r in M.load(inputs.get("lines")) + M.load(inputs.get("lines_extra")):
        L = M.normalize_line(r)
        lines[(L["homeTeam"], L["awayTeam"])] = L
    props = M.load(inputs.get("props"))
    rows, projs, withheld = [], [], []
    for game in M.load(inputs.get("games")):
        try:
            pj = run_game_strict(game, ctx)
        except (NeutralSiteError, VenueHfaError) as e:
            withheld.append((game.get("id"), str(e)))
            continue
        projs.append(pj)
        L = lines.get((pj["home"], pj["away"]))
        if L:
            rows += M.price_game(pj, L)
        rows += M.price_props(pj, ctx, props)
    card = M.finalize(rows)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "cfb_card.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=M.CARD_COLS, extrasaction="ignore")
        w.writeheader()
        for r in card:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    with open(os.path.join(out_dir, "cfb_card.md"), "w") as f:
        f.write(M.render_md(card, projs, ctx))
    with open(os.path.join(out_dir, "cfb_withheld.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gameId", "reason"])
        w.writerows(withheld)
    return card, projs, withheld


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python cfb_neutral_strict.py inputs.json [out_dir]")
        sys.exit(1)
    c, p, w = run_card_strict(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ".")
    print(f"{len(p)} games projected, {len(w)} withheld, {len(c)} card rows ({STRICT_VERSION})")
