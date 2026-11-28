#!/usr/bin/env python3
"""CFB player-stat challenger with a market-blind forecast (issue #455).

Versioned beside the pinned model; sportsedge_cfb_model.py is imported and never modified.

The forecast distribution is built from usage, the team projection and opponent features ONLY.
It is frozen and hashed BEFORE any sportsbook quote is read. Quotes are joined afterwards
solely to price a threshold against the already-frozen distribution.

Three separate things, never mixed:
  * independent forecast  -> independent_distribution / freeze_distributions (label INDEPENDENT)
  * quote pricing         -> price_props_independent (uses the frozen distribution unchanged)
  * quote-anchored mean   -> market_implied_mean / hybrid_mean (label MARKET_ANCHORED_RESEARCH,
                             diagnostic only; not used by the pricing path, never bet-eligible)

Identity: distributions are keyed by (team, player, market). A quote that omits the team and
matches more than one player is withheld as AMBIGUOUS_PLAYER_IDENTITY.

Duplicates: identical duplicate quotes collapse to one row; conflicting duplicates (same
selection and threshold, different prices) are all withheld.

Push: whole-number thresholds use a continuity-corrected push probability and push-aware EV
(win * (decimal - 1) - loss). Half-point thresholds have push probability 0.

Limits: normal distribution, weights are the pinned model's untested starting values.
Nothing here is validated. PAPER / 0u / NON_COUNTED.
"""
from __future__ import annotations
import hashlib, json, math, sys
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sportsedge_cfb_model as M  # noqa: E402

VERSION = "cfb-prop-independent-v2"
LABEL = "INDEPENDENT_MARKET_BLIND_UNVALIDATED"
ANCHORED_LABEL = "MARKET_ANCHORED_RESEARCH"
SUPPORTED = tuple(sorted(M.PROP_SD_FRAC))


def _num(x):
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _digest(obj):
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def independent_distribution(u, proj, ctx):
    """Forecast distribution from usage, team projection and opponent features only."""
    if not isinstance(u, dict) or u.get("market") not in SUPPORTED:
        return {"state": "WITHHELD", "reason": "UNSUPPORTED_STAT_MARKET"}
    share, eff = _num(u.get("share")), _num(u.get("eff"))
    if share is None or eff is None or share <= 0 or eff <= 0:
        return {"state": "WITHHELD", "reason": "INVALID_USAGE_NUMBER"}
    try:
        mean, why = M.project_prop(dict(u, share=share, eff=eff), proj, ctx)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return {"state": "WITHHELD", "reason": "PROJECTION_INPUT_MISSING"}
    if not (isinstance(mean, float) and math.isfinite(mean) and mean > 0):
        return {"state": "WITHHELD", "reason": "NONPOSITIVE_FORECAST"}
    sd = max(1.0, M.PROP_SD_FRAC[u["market"]] * mean)
    body = {"version": VERSION, "game_id": proj["game"]["id"], "player": u.get("player"),
            "team": u.get("team"), "market": u["market"], "family": "normal",
            "mean": mean, "sd": sd, "inputs": why, "label": LABEL}
    return dict(body, state="PROJECTED", sha256=_digest(body))


def freeze_distributions(proj, ctx):
    """All distributions for one game, built before any sportsbook input is read."""
    teams = {proj["home"], proj["away"]}
    rows = [u for u in ctx["usage"] if isinstance(u, dict) and u.get("team") in teams]
    seen = {}
    for u in rows:
        k = (u.get("team"), u.get("player"), u.get("market"))
        seen[k] = seen.get(k, 0) + 1
    out = {}
    for u in rows:
        k = (u.get("team"), u.get("player"), u.get("market"))
        out[k] = ({"state": "WITHHELD", "reason": "DUPLICATE_USAGE_ROW"} if seen[k] > 1
                  else independent_distribution(u, proj, ctx))
    return out


def _skey(k):
    return tuple(str(x) for x in k)


def _set_digest(frozen):
    items = sorted([*_skey(k), d.get("sha256") or d.get("reason")] for k, d in frozen.items())
    return _digest(items)


def _resolve(frozen, team, player, market):
    """Return (key, reason). Team-scoped when the quote names a team."""
    if team is not None:
        k = (team, player, market)
        return (k, None) if k in frozen else (None, "NO_USAGE_ROW")
    hits = [k for k in frozen if k[1] == player and k[2] == market]
    if not hits:
        return None, "NO_USAGE_ROW"
    if len(hits) > 1:
        return None, "AMBIGUOUS_PLAYER_IDENTITY"
    return hits[0], None


def threshold_probs(mean, sd, threshold):
    """(p_over, p_push, p_under). Whole numbers get a continuity-corrected push band."""
    if float(threshold).is_integer():
        nd = NormalDist(mean, sd)
        lo, hi = nd.cdf(threshold - 0.5), nd.cdf(threshold + 0.5)
        return 1.0 - hi, hi - lo, lo
    p_over = M.pgt(mean, threshold, sd)
    return p_over, 0.0, 1.0 - p_over


def push_aware_ev(p_win, p_loss, american):
    return p_win * (M.dec(american) - 1.0) - p_loss


def price_props_independent(proj, ctx, prop_rows):
    frozen = freeze_distributions(proj, ctx)
    set_sha = _set_digest(frozen)
    rows, withheld, valid = [], [], []
    for p in prop_rows:
        if p.get("gameId") != proj["game"]["id"]:
            continue
        team, player, market = p.get("team"), p.get("player"), p.get("market")
        key, why = _resolve(frozen, team, player, market)
        if key is None:
            withheld.append({"team": team, "player": player, "market": market, "reason": why})
            continue
        d = frozen[key]
        if d["state"] != "PROJECTED":
            withheld.append({"team": key[0], "player": player, "market": market, "reason": d["reason"]})
            continue
        threshold, oo, uo = _num(p.get("line")), _num(p.get("overOdds")), _num(p.get("underOdds"))
        if (threshold is None or threshold <= 0 or oo is None or uo is None
                or abs(oo) < 100 or abs(uo) < 100):
            withheld.append({"team": key[0], "player": player, "market": market, "reason": "INVALID_QUOTE"})
            continue
        valid.append((key, threshold, oo, uo))

    groups = {}
    for key, threshold, oo, uo in valid:
        groups.setdefault((key, threshold), []).append((oo, uo))
    for (key, threshold), quotes in groups.items():
        if len(set(quotes)) > 1:
            withheld.append({"team": key[0], "player": key[1], "market": key[2],
                             "line": threshold, "reason": "DUPLICATE_CONFLICTING_QUOTE"})
            continue
        oo, uo = quotes[0]
        d = frozen[key]
        p_over, p_push, p_under = threshold_probs(d["mean"], d["sd"], threshold)
        rows.append({"gameId": proj["game"]["id"], "team": key[0], "player": key[1], "market": key[2],
                     "line": threshold, "over_odds": oo, "under_odds": uo,
                     "dist_sha256": d["sha256"], "mean": d["mean"], "sd": d["sd"],
                     "p_over": p_over, "p_push": p_push, "p_under": p_under,
                     "ev_over": push_aware_ev(p_over, p_under, oo),
                     "ev_under": push_aware_ev(p_under, p_over, uo),
                     "duplicates_collapsed": len(quotes) - 1,
                     "market_novig_over": M.novig(oo, uo)[0],
                     "label": LABEL, "state": "PAPER_0U_NON_COUNTED",
                     "approved_stake_u": 0, "official_counted": 0})
    return {"version": VERSION, "label": LABEL, "distribution_set_sha256": set_sha,
            "distributions": [frozen[k] for k in sorted(frozen, key=_skey)],
            "rows": rows, "withheld": withheld}


# ---- quote-anchored helpers: diagnostics only, not reachable from the pricing path ----
def market_implied_mean(market, threshold, over_odds, under_odds):
    """Mean implied by one two-sided quote (same construction as the pinned model)."""
    sd_f = M.PROP_SD_FRAC.get(market, 0.45)
    no, _ = M.novig(over_odds, under_odds)
    sd_q = max(1.0, sd_f * float(threshold))
    return float(threshold) + sd_q * M.N.inv_cdf(min(max(no, 1e-4), 1 - 1e-4))


def hybrid_mean(independent_mean, implied_mean, w_model=None):
    w = M.PROP_MODEL_W if w_model is None else w_model
    return w * independent_mean + (1 - w) * implied_mean
