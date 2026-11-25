"""Extract pregame closing quotes from cached ESPN core-API odds payloads (RESEARCH ONLY).

Source: sports.core.api.espn.com .../events/{id}/competitions/{id}/odds, one compact JSON per event
cached by the research fetcher. NOT an admitted production odds source; used only to diagnose
model-vs-market disagreement and EV inflation retrospectively. Provider preference: DraftKings (100),
then ESPN BET (58). Live-odds providers are never used. Every rejection carries a reason code.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

PREFERRED = ("100", "58")
LIVE = {"59"}


def _num(x):
    if x is None:
        return None
    try:
        s = str(x).strip().replace("EVEN", "+100")
        if s.lower() in ("", "ok", "pk", "nan", "none"):
            return 0.0 if s.lower() == "pk" else None
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _price(x):
    v = _num(x)
    if v is None or abs(v) < 100 or abs(v) > 100000 or not float(v).is_integer():
        return None
    return int(v)


def extract(items, which="close"):
    """Return (quote dict, None) or (None, reason). ``which``: 'close' (default) or 'open'."""
    if not isinstance(items, list) or not items:
        return None, "NO_ODDS_PAYLOAD"
    by = {str(it.get("pid")): it for it in items if isinstance(it, dict)}
    it = next((by[p] for p in PREFERRED if p in by), None)
    if it is None:
        return None, "NO_PREFERRED_PREGAME_PROVIDER"
    h, a = it.get("home") or {}, it.get("away") or {}
    if which not in ("close", "open"):
        raise ValueError("WHICH_INVALID")
    hc, ac = h.get(which) or {}, a.get(which) or {}
    tc = (it.get("tot") or {}).get(which) or {}
    q = {"provider": it.get("provider"), "pid": str(it.get("pid"))}
    sp = _num(hc.get("ps"))
    sp_away = _num(ac.get("ps"))
    if sp is not None and sp_away is not None and abs(sp + sp_away) > 1e-9:
        sp = None  # orientation inconsistent: reject spread rather than guess
    if sp is not None and (abs(sp) > 60 or (sp * 2) % 1):
        sp = None  # e.g. 2023 payloads carry a PRICE in the point-spread field: reject, never reinterpret
    q["spread_home"] = sp
    q["spread_price_home"], q["spread_price_away"] = _price(hc.get("sp")), _price(ac.get("sp"))
    q["total"] = _num(tc.get("total"))
    if q["total"] is not None and (not 80 <= q["total"] <= 220 or (q["total"] * 2) % 1):
        q["total"] = None
    q["over_price"], q["under_price"] = _price(tc.get("over")), _price(tc.get("under"))
    q["ml_home"], q["ml_away"] = _price(hc.get("ml")), _price(ac.get("ml"))
    if q["spread_home"] is not None and q["ml_home"] and q["ml_away"] and q["spread_home"] != 0:
        dh, da = q["ml_home"], q["ml_away"]
        home_fav_ml = (dh < 0 and (da > 0 or dh < da)) or (dh > 0 and da > 0 and dh < da)
        if home_fav_ml != (q["spread_home"] < 0) and abs(q["spread_home"]) >= 3:
            q["spread_home"] = None  # spread orientation contradicts the moneyline favourite
    if all(q[k] is None for k in ("spread_home", "total", "ml_home")):
        return None, "NO_CLOSING_VALUES"
    return q, None


def load_dir(path, game_ids, which="close"):
    out, census = {}, {}
    for gid in game_ids:
        p = Path(path) / f"{gid}.json"
        if not p.exists():
            census["NOT_FETCHED"] = census.get("NOT_FETCHED", 0) + 1
            continue
        q, why = extract(json.loads(p.read_text()), which)
        if q is None:
            census[why] = census.get(why, 0) + 1
            continue
        census["OK:" + q["pid"]] = census.get("OK:" + q["pid"], 0) + 1
        out[gid] = q
    return out, census
