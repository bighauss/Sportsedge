"""Versioned strict neutral-site entry point for the pinned CFB model (issue #432).

sportsedge_cfb_model.py is NOT modified (git blob a07f4cd429e344e8ee0d131bdfa8e1ef7a91da20).
Its run_game() uses bool(game.get("neutralSite")): missing/null become False (home field
applied) and any non-empty string, including "false", becomes True (zero home field).
This module validates the flag first, then delegates to the unchanged model, so
coefficients, weights and pricing are identical for every admitted game.

Identity transition: pinned model blob unchanged; new entry point STRICT_VERSION.
Games with an invalid flag are WITHHELD with a named reason, never defaulted.
PAPER / 0u / NON_COUNTED. Not a validation claim.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sportsedge_cfb_model as M

STRICT_VERSION = "cfb-neutral-strict-v1"
BASE_MODEL_BLOB_SHA = "a07f4cd429e344e8ee0d131bdfa8e1ef7a91da20"
WITHHOLD_REASON = "CFBD neutralSite missing or not boolean"


class NeutralSiteError(ValueError):
    pass


def require_neutral_flag(game):
    v = game.get("neutralSite") if isinstance(game, dict) else None
    if not isinstance(v, bool):
        gid = game.get("id") if isinstance(game, dict) else None
        raise NeutralSiteError(f"{WITHHOLD_REASON} (game {gid!r}: {v!r})")
    return v


def run_game_strict(game, ctx):
    neutral = require_neutral_flag(game)
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
        except NeutralSiteError as e:
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
