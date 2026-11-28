"""Book-price EV for the shared NFL Monte Carlo (RESEARCH / PAPER, unvalidated).

Re-prices each captured book line on the SAME simulated scenarios that feed DFS
and markets.py: model win/push/loss probability AT THE BOOK LINE, no-vig market
probability, raw EV, blended EV (40% model / 60% market), stars out of 5, ranked
by blended EV (highest first).

Input (games/<tag>_lines.json; captured by Muse/Isaac, never invented here):
{"tag": "<cfg tag>", "source": "DK", "captured_at_utc": "2026-11-15T22:00:00Z",
 "markets": [
  {"market": "moneyline", "prices": {"PIT": 140, "CIN": -165}},
  {"market": "spread", "home_line": -3.5, "home": -110, "away": -110},
  {"market": "total", "line": 49.5, "over": -110, "under": -110},
  {"market": "team_total", "team": "CIN", "line": 26.5, "over": -115, "under": -105},
  {"market": "pass_yds", "player": "Joe Burrow", "line": 274.5, "over": -115, "under": -105},
  {"market": "anytime_td", "player": "Ja'Marr Chase", "yes": 110, "no": -140}
 ]}
Player markets: pass_yds, pass_tds, rush_yds, rec_yds, receptions (over/under),
anytime_td, td_2plus (yes/no). Either side's price may be omitted.

Rules: pushes return the stake (win/push/loss tracked separately); a two-way
market is de-vigged multiplicatively; a one-sided price keeps its vig in the
market probability, is flagged and capped at 3 stars; an entry that cannot be
priced goes to "unpriced" with a reason, never guessed. Constants are
placeholders, not calibrated on out-of-sample results.
"""
import json
import math

BLEND_MODEL = 0.4
BLEND_MARKET = 0.6
# blended-EV thresholds for 2,3,4,5 stars (1 star = positive but below first)
STAR_BREAKS = (0.01, 0.025, 0.04, 0.06)
PLAYER_OU = ("pass_yds", "pass_tds", "rush_yds", "rec_yds", "receptions")
PLAYER_TD = {"anytime_td": 1, "td_2plus": 2}


class LinesError(ValueError):
    """Lines file lacks provenance or is for a different game."""


def profit_per_unit(odds):
    if (isinstance(odds, bool) or not isinstance(odds, (int, float))
            or not math.isfinite(odds) or -100 < odds < 100):
        raise ValueError("INVALID_AMERICAN_ODDS: %r" % (odds,))
    return odds / 100 if odds > 0 else 100 / -odds


def implied(odds):
    return 1 / (1 + profit_per_unit(odds))


def devig(odds_a, odds_b):
    pa, pb = implied(odds_a), implied(odds_b)
    s = pa + pb
    if s < 1 - 1e-9:
        raise ValueError("NEGATIVE_VIG_CHECK_PRICES")
    return pa / s, pb / s


def stars_for(ev_raw, ev_blended, se_ev, one_sided):
    if ev_blended is None or ev_raw <= 0 or ev_blended <= 0:
        return 0
    s = 1 + sum(ev_blended >= t for t in STAR_BREAKS)
    if one_sided:
        s = min(s, 3)
    if ev_raw < se_ev:
        s = min(s, 1)
    return s


def _num(x, what):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError("INVALID_%s: %r" % (what, x))
    return x


def _row(market, subject, side, line, odds, outcome, mkt_p, one_sided, n):
    p_win, p_push, p_lose = outcome
    b = profit_per_unit(odds)
    ev_raw = p_win * b - p_lose
    nonpush = p_win + p_lose
    if nonpush > 0:
        blended_cond = BLEND_MODEL * (p_win / nonpush) + BLEND_MARKET * mkt_p
        ev_blended = nonpush * (blended_cond * (b + 1) - 1)
    else:
        ev_blended = None
    se_ev = (b + 1) * math.sqrt(p_win * (1 - p_win) / n)
    flags = []
    if one_sided:
        flags.append("ONE_SIDED_VIG_INCLUDED")
    if 0 < ev_raw < se_ev:
        flags.append("RAW_EV_WITHIN_MC_NOISE")
    return {
        "market": market, "subject": subject, "side": side, "line": line,
        "price": odds,
        "model": {"p_win": round(p_win, 4), "p_push": round(p_push, 4),
                  "p_lose": round(p_lose, 4)},
        "market_prob": round(mkt_p, 4),
        "market_basis": "ONE_SIDED_VIG_INCLUDED" if one_sided else "NO_VIG_TWO_WAY",
        "ev_raw": round(ev_raw, 4),
        "ev_blended": None if ev_blended is None else round(ev_blended, 4),
        "mc_se_ev": round(se_ev, 4),
        "stars": stars_for(ev_raw, ev_blended, se_ev, one_sided),
        "flags": flags,
    }


def _two_way(market, subject, sides, n):
    """sides: two (name, odds_or_None, (p_win, p_push, p_lose), line) tuples."""
    priced = [s for s in sides if s[1] is not None]
    if not priced:
        raise ValueError("NO_PRICES")
    if len(priced) == 2:
        qa, qb = devig(priced[0][1], priced[1][1])
        mk = {priced[0][0]: qa, priced[1][0]: qb}
        one_sided = False
    else:
        mk = {priced[0][0]: implied(priced[0][1])}
        one_sided = True
    return [_row(market, subject, nm, ln, odds, out, mk[nm], one_sided, n)
            for nm, odds, out, ln in priced]


def _ou(vals, line):
    n = len(vals)
    over = sum(v > line for v in vals) / n
    push = sum(v == line for v in vals) / n
    under = 1 - over - push
    return (over, push, under), (under, push, over)


def _selection_key(e):
    """Identity of a board selection without its prices (None if unkeyable)."""
    if not isinstance(e, dict):
        return None
    m = e.get("market")
    line = e.get("home_line", e.get("line"))
    who = e.get("team") or e.get("player") or "game"
    try:
        return (str(m), str(who), None if line is None else float(line))
    except (TypeError, ValueError):
        return None


def _duplicate_census(markets, unpriced):
    """Indexes to skip. Identical repeats collapse to the first entry; entries for the
    same selection with different prices are ALL withheld (never pick one silently)."""
    groups = {}
    for i, e in enumerate(markets):
        k = _selection_key(e)
        if k is not None:
            groups.setdefault(k, []).append(i)
    skip = set()
    for idx in groups.values():
        if len(idx) < 2:
            continue
        first = json.dumps(markets[idx[0]], sort_keys=True, default=str)
        same = all(json.dumps(markets[j], sort_keys=True, default=str) == first for j in idx)
        drop = idx[1:] if same else idx
        reason = "DUPLICATE_QUOTE_COLLAPSED" if same else "DUPLICATE_CONFLICTING_QUOTE"
        for j in drop:
            skip.add(j)
            unpriced.append({"index": j, "entry": markets[j], "reason": reason})
    return skip


def price_lines(cfg, raw, away, home, lines, props):
    """Return the "book" block. raw: per-sim {team: (player_stats, score)}."""
    if not isinstance(lines, dict):
        raise LinesError("lines must be a JSON object")
    if lines.get("tag") != cfg.get("tag"):
        raise LinesError("lines tag %r does not match game tag %r"
                         % (lines.get("tag"), cfg.get("tag")))
    for k in ("source", "captured_at_utc"):
        if not isinstance(lines.get(k), str) or not lines[k]:
            raise LinesError("lines missing provenance field %s" % k)
    if not isinstance(lines.get("markets"), list):
        raise LinesError("lines missing markets list")
    n = len(raw)
    if n < 2:
        raise ValueError("Need at least two simulations")
    A = [r[away][1] for r in raw]
    H = [r[home][1] for r in raw]
    margin = [h - a for a, h in zip(A, H)]
    teams = {away: A, home: H}
    players = cfg.get("players", {})

    def pvals(player, market):
        meta = players.get(player)
        if meta is None:
            raise ValueError("NOT_MODELED_PLAYER: %s" % player)
        if meta["pos"] in ("K", "DST"):
            raise ValueError("NOT_MODELED_POSITION: %s" % meta["pos"])
        if market in ("pass_yds", "pass_tds") and meta["pos"] != "QB":
            raise ValueError("NOT_MODELED_NON_QB_PASSING")
        if market in ("rec_yds", "receptions") and meta["pos"] == "QB":
            raise ValueError("NOT_MODELED_QB_RECEIVING")
        f = props["anytime_td" if market in PLAYER_TD else market]
        tm = meta["team"]
        return [f(r[tm][0][player]) if player in r[tm][0] else 0 for r in raw]

    rows, unpriced = [], []
    skip = _duplicate_census(lines["markets"], unpriced)
    for i, e in enumerate(lines["markets"]):
        if i in skip:
            continue
        try:
            m = e["market"]
            if m == "moneyline":
                pr = e["prices"]
                if not isinstance(pr, dict) or not pr or not set(pr) <= set(teams):
                    raise ValueError("MONEYLINE_PRICES_MUST_BE_KEYED_BY_GAME_TEAM")
                tie = sum(x == 0 for x in margin) / n
                hw = sum(x > 0 for x in margin) / n
                aw = sum(x < 0 for x in margin) / n
                rows += _two_way("moneyline", "game", [
                    (home, pr.get(home), (hw, tie, aw), None),
                    (away, pr.get(away), (aw, tie, hw), None)], n)
            elif m == "spread":
                hl = _num(e["home_line"], "LINE")
                need = -hl
                hw = sum(x > need for x in margin) / n
                pu = sum(x == need for x in margin) / n
                aw = 1 - hw - pu
                rows += _two_way("spread", "game", [
                    (home, e.get("home"), (hw, pu, aw), hl),
                    (away, e.get("away"), (aw, pu, hw), -hl)], n)
            elif m == "total":
                ln = _num(e["line"], "LINE")
                o, u = _ou([a + h for a, h in zip(A, H)], ln)
                rows += _two_way("total", "game", [
                    ("over", e.get("over"), o, ln), ("under", e.get("under"), u, ln)], n)
            elif m == "team_total":
                t = e["team"]
                if t not in teams:
                    raise ValueError("UNKNOWN_TEAM: %s" % t)
                ln = _num(e["line"], "LINE")
                o, u = _ou(teams[t], ln)
                rows += _two_way("team_total", t, [
                    ("over", e.get("over"), o, ln), ("under", e.get("under"), u, ln)], n)
            elif m in PLAYER_OU:
                ln = _num(e["line"], "LINE")
                o, u = _ou(pvals(e["player"], m), ln)
                rows += _two_way(m, e["player"], [
                    ("over", e.get("over"), o, ln), ("under", e.get("under"), u, ln)], n)
            elif m in PLAYER_TD:
                p = sum(x >= PLAYER_TD[m] for x in pvals(e["player"], m)) / n
                rows += _two_way(m, e["player"], [
                    ("yes", e.get("yes"), (p, 0.0, 1 - p), None),
                    ("no", e.get("no"), (1 - p, 0.0, p), None)], n)
            else:
                raise ValueError("NOT_MODELED_MARKET: %s" % m)
        except (ValueError, KeyError, TypeError) as err:
            reason = err.args[0] if err.args and isinstance(err.args[0], str) else repr(err)
            unpriced.append({"index": i, "entry": e, "reason": reason})
    rows.sort(key=lambda r: -(r["ev_blended"] if r["ev_blended"] is not None else -9))
    for k, r in enumerate(rows, 1):
        r["rank"] = k
    return {
        "status": "RESEARCH_PAPER_UNVALIDATED",
        "source": lines["source"], "captured_at_utc": lines["captured_at_utc"],
        "sims": n,
        "blend": {"model": BLEND_MODEL, "market": BLEND_MARKET},
        "star_rule": {"blended_ev_breaks_for_2_to_5_stars": list(STAR_BREAKS),
                      "zero_if_raw_or_blended_ev_not_positive": True,
                      "one_sided_cap": 3, "one_star_cap_if_raw_ev_below_mc_se": True,
                      "calibrated": False},
        "rows": rows, "unpriced": unpriced,
        "n_plays": sum(r["stars"] > 0 for r in rows),
    }
