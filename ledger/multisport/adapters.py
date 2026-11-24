"""Sport-specific market normalization, push/dead-heat rules, and settlement adapters.

Covers all seven SportsEdge sports: NFL, CFB, CBB, NBA, MLB, NHL, PGA.
Stdlib only. Read-only grading helpers; never approves stakes or modifies frozen files.
"""
import math

SPORTS = ("NFL", "CFB", "CBB", "NBA", "MLB", "NHL", "PGA")

REQUIRED_FAMILIES = {
    "NFL": ("spread", "total", "ml", "team_total", "periods", "alt_line", "prop", "td"),
    "CFB": ("spread", "total", "ml", "team_total", "periods", "prop"),
    "CBB": ("spread", "total", "ml", "team_total", "halves", "prop"),
    "NBA": ("spread", "total", "ml", "quarters", "halves", "prop", "combo_prop"),
    "MLB": ("run_line", "total", "ml", "innings", "batter_prop", "pitcher_prop"),
    "NHL": ("puck_line", "total", "ml", "periods", "prop"),
    "PGA": ("outright", "placement", "matchup", "round"),
}

PERIOD_PREFIXES = {
    "NFL": ("1Q", "2Q", "3Q", "4Q", "1H", "2H"),
    "CFB": ("1Q", "2Q", "3Q", "4Q", "1H", "2H"),
    "CBB": ("1H", "2H"),
    "NBA": ("1Q", "2Q", "3Q", "4Q", "1H", "2H"),
    "MLB": ("1I", "3I", "F5", "5I", "7I"),
    "NHL": ("1P", "2P", "3P"),
    "PGA": ("R1", "R2", "R3", "R4"),
}

NBA_COMBO_STATS = frozenset({"pra", "pr", "pa", "ra", "pts_reb_ast", "pts_reb", "pts_ast", "reb_ast"})
MLB_PITCHER_STATS = frozenset({"strikeouts", "ks", "outs", "earned_runs", "hits_allowed", "walks_allowed", "pitch_outs"})


def fnum(value, default=None):
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _cmp_ou(actual, line, side):
    if actual == line:
        return "P"
    return "W" if (actual > line) == (side == "over") else "L"


def _cmp_spread(mine, theirs, line):
    adj = mine + line - theirs
    if adj == 0:
        return "P"
    return "W" if adj > 0 else "L"


def market_family(sport, market):
    s = (sport or "").strip().upper()
    m = (market or "").strip().lower()
    if s not in SPORTS:
        raise ValueError(f"unsupported sport: {sport!r}")
    if s == "PGA":
        if m in ("outright", "winner"):
            return "outright"
        if m.startswith(("top_", "make_cut", "miss_cut", "placement")):
            return "placement"
        if m.startswith(("h2h", "matchup", "3ball")):
            return "matchup"
        if m.startswith(("r1_", "r2_", "r3_", "r4_", "round_")):
            return "round"
        return m
    if m.startswith("alt_"):
        return "alt_line"
    if m.startswith("prop_") or m.startswith("prop:"):
        stat = m.split("_", 1)[1] if "_" in m else m.split(":", 1)[1]
        if s == "NFL" and stat in ("atd", "td2", "ftd", "anytime_td", "first_td"):
            return "td"
        if s == "NBA" and stat in NBA_COMBO_STATS:
            return "combo_prop"
        if s == "MLB":
            return "pitcher_prop" if stat in MLB_PITCHER_STATS else "batter_prop"
        return "prop"
    if m in ("home_tt", "away_tt", "team_total"):
        return "team_total"
    if "_" in m:
        pre = m.split("_", 1)[0].upper()
        if pre in PERIOD_PREFIXES[s]:
            if s == "CBB":
                return "halves"
            if s == "NBA":
                return "halves" if pre in ("1H", "2H") else "quarters"
            if s == "MLB":
                return "innings"
            return "periods"
    if m in ("run_line", "runline") or (s == "MLB" and m in ("spread", "spreads")):
        return "run_line"
    if m in ("puck_line", "puckline") or (s == "NHL" and m in ("spread", "spreads")):
        return "puck_line"
    if m in ("spread", "spreads"):
        return "spread"
    if m in ("total", "totals"):
        return "total"
    if m in ("ml", "moneyline", "h2h", "reg_3way"):
        return "ml"
    return m


def is_push_capable(sport, row):
    """True when a market can push or settle via dead-heat."""
    s = (sport or "").strip().upper()
    m = (row.get("market") or "").strip().lower()
    fam = market_family(s, m)
    if s == "PGA":
        return fam in ("placement", "matchup")
    if fam == "ml" and s in ("NFL", "CFB", "NHL"):
        return True
    line = fnum(row.get("line"))
    if line is not None and line.is_integer():
        return True
    return False


def grade_row(sport, row, finals, stats=None):
    """Grade one normalized row for any of the 7 sports. Returns (result, reason).

    Results: "W", "L", "P", or "NG".
    """
    s = (sport or "").strip().upper()
    if s not in SPORTS:
        return "NG", f"unsupported sport {sport}"
    stats = stats or {}
    market = (row.get("market") or "").strip().lower()
    pick = (row.get("pick") or "").strip()
    pl = pick.lower()
    line = fnum(row.get("line"))
    fam = market_family(s, market)

    if s == "PGA":
        return _grade_pga(market, fam, row, pick, pl, line, finals)

    if fam in ("prop", "td", "combo_prop", "batter_prop", "pitcher_prop"):
        stat = market.split("_", 1)[1] if "_" in market else market.split(":", 1)[-1]
        player = (row.get("player") or "").strip().lower()
        val = stats.get((player, stat))
        if val is None:
            return "NG", f"no stat {row.get('player')}/{stat}"
        if pl in ("yes", "no"):
            thr = line if line is not None else 0.5
            hit = float(val) > thr
            return ("W" if hit == (pl == "yes") else "L"), None
        if line is None:
            return "NG", "prop missing line"
        return _cmp_ou(float(val), line, "over" if pl.startswith("o") else "under"), None

    away = str(finals.get("away", "")).upper()
    home = str(finals.get("home", "")).upper()
    a, h = float(finals["away_score"]), float(finals["home_score"])
    kind = market

    if "_" in market and market.split("_", 1)[0].upper() in PERIOD_PREFIXES[s]:
        pre, kind = market.split("_", 1)
        per = (finals.get("periods") or {}).get(pre.upper())
        if not per:
            return "NG", f"no {pre.upper()} score"
        a, h = float(per[0]), float(per[1])
    elif market.startswith("alt_"):
        kind = market[4:]

    kind = {"moneyline": "ml", "h2h": "ml", "spreads": "spread", "totals": "total",
            "run_line": "spread", "runline": "spread",
            "puck_line": "spread", "puckline": "spread"}.get(kind, kind)

    if kind == "total":
        if line is None:
            return "NG", "total missing line"
        return _cmp_ou(a + h, line, "over" if pl.startswith("o") else "under"), None
    if kind in ("home_tt", "away_tt"):
        if line is None:
            return "NG", "team total missing line"
        return _cmp_ou(h if kind == "home_tt" else a, line, "over" if pl.startswith("o") else "under"), None

    team = pick.split()[0].upper() if pick else ""
    if team not in (away, home):
        return "NG", f"pick team {team} not in {away}@{home}"
    mine, theirs = (a, h) if team == away else (h, a)
    if kind == "ml":
        if mine == theirs:
            return "P", None
        return ("W" if mine > theirs else "L"), None
    if kind == "spread":
        if line is None:
            return "NG", "spread missing line"
        return _cmp_spread(mine, theirs, line), None
    return "NG", f"unknown market {market}"


def _grade_pga(market, fam, row, pick, pl, line, finals):
    positions = finals.get("positions") or {}
    scores = finals.get("round_scores") or {}
    player = (row.get("player") or pick).strip()

    if fam == "outright":
        pos = positions.get(player)
        if pos is None:
            return "NG", f"no position for {player}"
        return ("W" if int(pos) == 1 else "L"), None

    if fam == "placement":
        if market in ("make_cut", "miss_cut"):
            made = (finals.get("made_cut") or {}).get(player)
            if made is None:
                return "NG", f"no cut status for {player}"
            want = (market == "make_cut") == (pl != "no")
            return ("W" if bool(made) == want else "L"), None
        if market.startswith("top_"):
            k = int(market.split("_", 1)[1])
            pos = positions.get(player)
            if pos is None:
                return "NG", f"no position for {player}"
            tied_at_pos = sum(1 for v in positions.values() if int(v) == int(pos))
            if int(pos) + tied_at_pos - 1 <= k:
                return "W", None
            if int(pos) > k:
                return "L", None
            return "P", f"dead_heat_at_{pos}_for_top_{k}"

    if fam == "matchup":
        opp = (row.get("opponent") or "").strip()
        rkey = (row.get("round") or "tournament").lower()
        board = finals.get("tournament_strokes") if rkey == "tournament" else (scores.get(rkey) or {})
        if not board or player not in board or opp not in board:
            return "NG", f"missing matchup scores for {player} vs {opp}"
        p_score, o_score = float(board[player]), float(board[opp])
        if p_score == o_score:
            return "P", None
        return ("W" if p_score < o_score else "L"), None

    if fam == "round":
        rkey = market.split("_", 1)[0].lower()
        rboard = scores.get(rkey) or {}
        val = rboard.get(player)
        if val is None:
            return "NG", f"no {rkey} score for {player}"
        if line is None:
            return "NG", "round market missing line"
        return _cmp_ou(float(val), line, "over" if pl.startswith("o") else "under"), None

    return "NG", f"unknown PGA market {market}"
