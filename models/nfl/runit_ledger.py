"""Complete-denominator candidate ledger for the NFL RUN IT v3 runner.

Every attempted offer (game-market direction or prop) gets exactly one ledger
row, written BEFORE any qualification or contradiction filter. Rejected rows
are retained with an explicit reason. Probabilities and EV are kept at full
float precision. `qualifies` (runner card rule) and `on_image` (display
subset) are separate fields.

The pricing formulas and constants below are copied unchanged from the frozen
v3 runner (sportsedge_nfl_wk11_run_v3.py, sha256 d252e22e...). This module
does not change v3; it only stops v3's early `continue`s from discarding rows
and turns malformed offers into retained rejection rows. The total-direction
filter reproduces v3's one-decimal note comparison by default (see game_rows).
No quotes or private data live in this file.
"""
from __future__ import annotations

import math
from statistics import NormalDist

N = NormalDist()

# ---- frozen v3 constants (do not tune here) ----
SD_MARGIN, SD_TOTAL, SD_1H = 13.5, 13.0, 9.5
H1_TIE = 0.07
BLEND_MODEL = 0.3
ONE_SIDED_VIG = 1.045          # assumed, not recovered from two prices
EV_MIN, EV_MAX = 0.02, 0.25
PROP_MARKETS = {  # file code: (name, cv, elasticity, kind)
    "8.03.30": ("Pass Yds", .28, .6, "n"),
    "8.03.35": ("Rec Yds", .65, .6, "n"),
    "8.03.40": ("Rush Yds", .5, .6, "n"),
    "8.03.46": ("Receptions", .45, .6, "n"),
    "8.03.53": ("Pass TDs", 0, 1.0, "p"),
    "8.03.59": ("Rush+Rec Yds", .5, .6, "n"),
}
# display rule reconstructed from the v3 card image (row-for-row match, 20/20)
IMAGE_TOP_N, IMAGE_MAX_PROPS_PER_GAME = 20, 3

GAME_FIELDS = ("away", "home", "spread", "sp_a", "sp_h", "total", "o", "u",
               "ml_a", "ml_h", "h1_spread", "h1_a", "h1_h", "h1_total",
               "h1_o", "h1_u", "h1_ml_a", "h1_ml_h")
PROP_FIELDS = ("file", "game", "player", "line", "odds")


def dec(o): return 1 + (o / 100 if o > 0 else 100 / -o)
def imp(o): return 1 / dec(o)


def nv(a, b):
    x, y = imp(a), imp(b)
    return x / (x + y), y / (x + y)


def cover(mu, sd, line):
    if line == int(line):
        hi = N.cdf((line + 0.5 - mu) / sd)
        return 1 - hi, hi - N.cdf((line - 0.5 - mu) / sd)
    return 1 - N.cdf((line - mu) / sd), 0.0


def pois_ge(lam, k):
    return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k))


def _row(game, mkt, sel, odds, pw, pp, mkp, note, kind="game", **extra):
    d = dec(odds)
    ev = pw * (d - 1) - (1 - pw - pp)
    bw = BLEND_MODEL * pw + (1 - BLEND_MODEL) * mkp * (1 - pp)
    bev = bw * (d - 1) - (1 - bw - pp)
    r = dict(game=game, kind=kind, market=mkt, selection=sel, odds=odds,
             model_p=pw, p_push=pp, market_p=mkp, raw_ev=ev, blended_ev=bev,
             note=note, status=None, reject_reason="", qualifies=False,
             on_image=False, display_rank=None)
    r.update(extra)
    return r


def _missing(d, fields):
    return [f for f in fields if d.get(f) in (None, "")]


def _num(v):
    return type(v) in (int, float) and math.isfinite(v)


def _american(v):
    return _num(v) and abs(v) >= 100


GAME_ODDS = ("sp_a", "sp_h", "o", "u", "ml_a", "ml_h", "h1_a", "h1_h",
             "h1_o", "h1_u", "h1_ml_a", "h1_ml_h")


def _bad_game(g):
    """Return a rejection reason for a malformed game quote, else ''."""
    if not isinstance(g, dict):
        return "invalid_input:not_a_mapping"
    miss = _missing(g, GAME_FIELDS)
    if miss:
        return f"missing_input:{','.join(miss)}"
    if type(g["away"]) is not str or type(g["home"]) is not str or g["away"] == g["home"]:
        return "invalid_input:teams"
    for f in GAME_ODDS:
        if not _american(g[f]):
            return f"invalid_odds:{f}"
    for f in ("spread", "h1_spread"):
        if not _num(g[f]):
            return f"invalid_input:{f}"
    for f in ("total", "h1_total"):
        if not _num(g[f]) or g[f] <= 0:
            return f"invalid_input:{f}"
    return ""


def _bad_proj(p):
    if (not isinstance(p, (tuple, list)) or len(p) != 2 or
            not all(_num(v) and v >= 0 for v in p)):
        return "invalid_input:projection"
    return ""


def _bad_prop(x):
    if not isinstance(x, dict):
        return "invalid_input:not_a_mapping"
    miss = _missing(x, PROP_FIELDS)
    if miss:
        return f"missing_input:{','.join(miss)}"
    if type(x["file"]) is not str:
        return "invalid_input:file"
    if x["file"] not in PROP_MARKETS:
        return f"unsupported_market:{x['file']}"
    g = x["game"]
    if (not isinstance(g, (list, tuple)) or len(g) != 2 or
            not all(type(t) is str and t for t in g)):
        return "invalid_input:game"
    if type(x["player"]) is not str or not x["player"].strip():
        return "invalid_input:player"
    if not _american(x["odds"]):
        return "invalid_odds:odds"
    k = x["line"]
    kind = PROP_MARKETS[x["file"]][3]
    if not _num(k) or k <= 0 or (kind == "p" and k != int(k)) or k > 1000:
        return "invalid_input:line"
    return ""


def game_rows(g, proj, legacy_note_rounding=True):
    """12 rows per game; proj = (away_pts, home_pts).

    legacy_note_rounding=True reproduces frozen v3 exactly: v3 parsed the
    projection back out of the one-decimal `note`, so 44.54 vs a 44.5 line
    compares as 44.5 and BOTH Over and Under are filtered. False compares
    full precision (a separate, versioned correction; not v3)."""
    a, h = g["away"], g["home"]
    gm = f"{a}@{h}"
    ap, hp = proj
    M, T = hp - ap, hp + ap
    out = []
    sp = g["spread"]
    pa, ph = nv(g["sp_a"], g["sp_h"])
    w, p = cover(M, SD_MARGIN, -sp)
    out.append(_row(gm, "Spread", f"{h} {sp:+g}", g["sp_h"], w, p, ph, f"proj margin {h} {M:+.1f}"))
    w2, _ = cover(-M, SD_MARGIN, sp)
    out.append(_row(gm, "Spread", f"{a} {-sp:+g}", g["sp_a"], w2, p, pa, f"proj margin {a} {-M:+.1f}"))
    o_, u_ = nv(g["o"], g["u"])
    w, p = cover(T, SD_TOTAL, g["total"])
    out.append(_row(gm, "Total", f"Over {g['total']}", g["o"], w, p, o_, f"proj total {T:.1f}", proj_value=T, line=g["total"]))
    out.append(_row(gm, "Total", f"Under {g['total']}", g["u"], 1 - w - p, p, u_, f"proj total {T:.1f}", proj_value=T, line=g["total"]))
    ma, mh = nv(g["ml_a"], g["ml_h"])
    pwh = 1 - N.cdf(-M / SD_MARGIN)
    out.append(_row(gm, "Moneyline", f"{h} ML", g["ml_h"], pwh, 0, mh, f"win% {pwh:.0%}"))
    out.append(_row(gm, "Moneyline", f"{a} ML", g["ml_a"], 1 - pwh, 0, ma, f"win% {1 - pwh:.0%}"))
    M1, T1 = M * 0.5, T * 0.5
    s1 = g["h1_spread"]
    a1, h1 = nv(g["h1_a"], g["h1_h"])
    w, p = cover(M1, SD_1H, -s1)
    out.append(_row(gm, "1H Spread", f"{h} 1H {s1:+g}", g["h1_h"], w, p, h1, f"1H margin {M1:+.1f}"))
    w, p = cover(-M1, SD_1H, s1)
    out.append(_row(gm, "1H Spread", f"{a} 1H {-s1:+g}", g["h1_a"], w, p, a1, f"1H margin {-M1:+.1f}"))
    o1, u1 = nv(g["h1_o"], g["h1_u"])
    w, p = cover(T1, SD_1H, g["h1_total"])
    out.append(_row(gm, "1H Total", f"1H Over {g['h1_total']}", g["h1_o"], w, p, o1, f"1H total {T1:.1f}", proj_value=T1, line=g["h1_total"]))
    out.append(_row(gm, "1H Total", f"1H Under {g['h1_total']}", g["h1_u"], 1 - w - p, p, u1, f"1H total {T1:.1f}", proj_value=T1, line=g["h1_total"]))
    m1a, m1h = nv(g["h1_ml_a"], g["h1_ml_h"])
    q = 1 - N.cdf(-M1 / SD_1H)
    out.append(_row(gm, "1H ML", f"{h} 1H ML", g["h1_ml_h"], q * (1 - H1_TIE), H1_TIE, m1h, "1H tie ~7%"))
    out.append(_row(gm, "1H ML", f"{a} 1H ML", g["h1_ml_a"], (1 - q) * (1 - H1_TIE), H1_TIE, m1a, "1H tie ~7%"))
    for r in out:
        if r["market"] in ("Total", "1H Total"):
            over = "Over" in r["selection"]
            t = float(f"{r['proj_value']:.1f}") if legacy_note_rounding else r["proj_value"]
            ok = t > r["line"] if over else t < r["line"]
            r["filter_basis"] = "v3_note_1dp" if legacy_note_rounding else "full_precision"
            if not ok:
                r["status"] = "filtered_contradicts_projection"
                r["reject_reason"] = (f"projection {r['proj_value']:.3f} "
                                      f"(compared as {t}) not on {'Over' if over else 'Under'} side of {r['line']}")
    return out


def game_offers(g):
    """The 12 original offers of a well-formed game input, in game_rows order,
    without pricing: used to keep each known offer when the game is rejected."""
    a, h, sp, s1 = g["away"], g["home"], g["spread"], g["h1_spread"]
    return [("Spread", f"{h} {sp:+g}", g["sp_h"]), ("Spread", f"{a} {-sp:+g}", g["sp_a"]),
            ("Total", f"Over {g['total']}", g["o"]), ("Total", f"Under {g['total']}", g["u"]),
            ("Moneyline", f"{h} ML", g["ml_h"]), ("Moneyline", f"{a} ML", g["ml_a"]),
            ("1H Spread", f"{h} 1H {s1:+g}", g["h1_h"]), ("1H Spread", f"{a} 1H {-s1:+g}", g["h1_a"]),
            ("1H Total", f"1H Over {g['h1_total']}", g["h1_o"]), ("1H Total", f"1H Under {g['h1_total']}", g["h1_u"]),
            ("1H ML", f"{h} 1H ML", g["h1_ml_h"]), ("1H ML", f"{a} 1H ML", g["h1_ml_a"])]


def prop_row(x, gm, proj, market_total):
    name, cv, el, kind = PROP_MARKETS[x["file"]]
    ap, hp = proj
    pm = min(.97, imp(x["odds"]) / ONE_SIDED_VIG)
    k = x["line"]
    lo, hi = 0.01, 600
    for _ in range(80):
        m = (lo + hi) / 2
        q = pois_ge(m, k) if kind == "p" else 1 - N.cdf((k - 0.5 - m) / (cv * m))
        lo, hi = (m, hi) if q < pm else (lo, m)
    r_ = (ap + hp) / market_total          # whole-game ratio (known v3 limitation)
    mm = m * (1 + el * (r_ - 1))
    pmod = pois_ge(mm, k) if kind == "p" else 1 - N.cdf((k - 0.5 - mm) / (cv * mm))
    d = dec(x["odds"])
    row = _row(gm, name, f"{x['player']} {k}+ {name}", x["odds"], pmod, 0, pm,
               f"proj {mm:.1f}", kind="prop", model_mean=mm, market_mean=m, line=k,
               scaling="whole_game_total_ratio", vig_basis="assumed_one_sided_1.045")
    row["raw_ev"] = pmod * d - 1                           # v3 prop formulas
    row["blended_ev"] = (BLEND_MODEL * pmod + (1 - BLEND_MODEL) * pm) * d - 1
    if mm < k - 0.5:
        row["status"] = "filtered_contradicts_projection"
        row["reject_reason"] = f"model mean {mm:.3f} below line-0.5 {k - 0.5}"
    return row


def _signal(x):
    s = x["selection"]
    if x["market"] in ("Spread", "Moneyline", "1H Spread", "1H ML"):
        return x["game"] + s.split()[0]
    if "Total" in x["market"]:
        return x["game"] + ("O" if "Over" in s else "U")
    p = s.split(" ")
    return p[0] + p[1] + x["market"]


def team_abbr(name, abbr):
    for k, v in abbr.items():
        if k in name:
            return v
    return None


def build_ledger(games, props, projections, abbr, legacy_note_rounding=True):
    """games: list of dicts with GAME_FIELDS; props: list of dicts with PROP_FIELDS;
    projections: {'AWAY@HOME': (away_pts, home_pts)}; abbr: nickname->abbr map.
    Returns (rows, summary). len(rows) == 12*well_formed_games + malformed_games + len(props):
    a well-formed game that is rejected (duplicate, no projection, pricing error) keeps
    one rejected row per known original offer; only a malformed input collapses to one row."""
    rows, proj, mtot = [], {}, {}
    seen_games, rejected_offer_rows, malformed_games = set(), 0, 0
    for i, g in enumerate(games):
        reason = _bad_game(g)
        well_formed = not reason
        gm = f"{g.get('away')}@{g.get('home')}" if isinstance(g, dict) else f"game input #{i}"
        if not reason:
            if gm in seen_games:
                reason = "duplicate_offer"
            elif gm not in projections:
                reason = "missing_input:projection"
            else:
                reason = _bad_proj(projections[gm])
        built = None
        if not reason:
            try:
                built = game_rows(g, projections[gm], legacy_note_rounding)
            except (ArithmeticError, ValueError, TypeError) as exc:
                reason = f"pricing_error:{type(exc).__name__}"
        if reason and well_formed:
            for mkt, sel, odds in game_offers(g):
                rows.append(dict(game=gm, kind="game", market=mkt, selection=sel, odds=odds,
                                 status="rejected_input", reject_reason=reason, input_index=i,
                                 qualifies=False, on_image=False, display_rank=None))
            rejected_offer_rows += 12
            continue
        if reason:
            rows.append(dict(game=gm, kind="game", market="ALL", selection=f"game input #{i}",
                             odds=None, status="rejected_input", reject_reason=reason,
                             qualifies=False, on_image=False, display_rank=None))
            malformed_games += 1
            continue
        seen_games.add(gm)
        proj[gm], mtot[gm] = projections[gm], g["total"]
        rows.extend(built)
    seen_props = set()
    for i, x in enumerate(props):
        reason = _bad_prop(x)
        xd = x if isinstance(x, dict) else {}
        f = xd.get("file")
        base = dict(kind="prop",
                    market=PROP_MARKETS[f][0] if isinstance(f, str) and f in PROP_MARKETS else "?",
                    selection=f"{xd.get('player')} {xd.get('line')}+", odds=xd.get("odds"),
                    qualifies=False, on_image=False, display_rank=None, status="rejected_input",
                    game="?", input_index=i)
        if reason:
            rows.append(dict(base, reject_reason=reason)); continue
        ha, hh = team_abbr(x["game"][0], abbr), team_abbr(x["game"][1], abbr)
        if ha is None or hh is None:
            rows.append(dict(base, reject_reason="unknown_team")); continue
        gm = f"{ha}@{hh}"
        base["game"] = gm
        key = (gm, x["file"], x["player"], x["line"])
        if key in seen_props:
            rows.append(dict(base, reject_reason="duplicate_offer")); continue
        seen_props.add(key)
        if gm not in proj:
            rows.append(dict(base, reject_reason="game_not_on_slate")); continue
        try:
            rows.append(prop_row(x, gm, proj[gm], mtot[gm]))
        except (ArithmeticError, ValueError, TypeError) as exc:
            rows.append(dict(base, reject_reason=f"pricing_error:{type(exc).__name__}"))

    # qualification (v3 card rule), then dedupe by signal in blended-EV order
    live = [r for r in rows if r["status"] is None]
    elig = sorted([r for r in live if EV_MIN <= r["raw_ev"] <= EV_MAX and r["blended_ev"] > 0],
                  key=lambda r: -r["blended_ev"])
    sig = set()
    for r in elig:
        k = _signal(r)
        if k in sig:
            continue
        sig.add(k)
        r["qualifies"] = True
        r["status"] = "on_card"
    for r in live:
        if r["status"] is None:
            r["status"] = ("held_outlier_ev_gt_25pct" if r["raw_ev"] > EV_MAX else
                           "negative_ev" if r["raw_ev"] <= 0 else
                           "below_2pct" if r["raw_ev"] < EV_MIN else
                           "nonpositive_blended_ev" if r["blended_ev"] <= 0 else
                           "deduped_same_signal")
    # display subset: top N by raw EV, max props per game
    per_game, rank = {}, 0
    for r in sorted([r for r in rows if r["qualifies"]], key=lambda r: -r["raw_ev"]):
        if rank >= IMAGE_TOP_N:
            break
        if r["kind"] == "prop":
            if per_game.get(r["game"], 0) >= IMAGE_MAX_PROPS_PER_GAME:
                continue
            per_game[r["game"]] = per_game.get(r["game"], 0) + 1
        rank += 1
        r["on_image"], r["display_rank"] = True, rank

    attempted = 12 * len(seen_games) + rejected_offer_rows + malformed_games + len(props)
    from collections import Counter
    summary = dict(filter_basis="v3_note_1dp" if legacy_note_rounding else "full_precision",
                   games_input=len(games), props_input=len(props), attempted_rows=attempted,
                   ledger_rows=len(rows), status_counts=dict(Counter(r["status"] for r in rows)),
                   qualifies=sum(r["qualifies"] for r in rows),
                   on_image=sum(r["on_image"] for r in rows))
    if summary["ledger_rows"] != attempted:
        raise AssertionError(f"denominator mismatch {summary}")
    return rows, summary
