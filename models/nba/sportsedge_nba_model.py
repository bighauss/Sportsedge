"""SportsEdge NBA "RUN IT" model  (2026-11-15, Claude)
Stdlib only (csv, math, statistics). ALL WEIGHTS ARE UNTESTED STARTING VALUES.

Pipeline: load CSVs -> team projection (50% ratings model + 50% advanced-stats
matchup) -> adjustments (injuries, rest/travel, altitude, time zone, home court)
-> pricing (normal approx) for ML / spread / total / team totals / 1H / 1Q
-> props (minutes x usage x per-minute rate x opp positional defense x pace,
blended 70/30 with market-implied mean) -> raw EV + blended EV
(p_blend = 0.30 model + 0.70 no-vig market) -> projection filter -> stack flags
-> ranked card (CSV + markdown) with 1-5 stars.

EXPECTED CSV COLUMNS
teams.csv:   team,games,rating,ortg,drtg,pace,ortg_l15,drtg_l15,
             efg,tov,orb,ftr,opp_efg,opp_tov,opp_orb,opp_ftr
             (rating = existing ratings-model points vs average team, neutral court;
              four factors as decimals; opp_* = what the defense allows)
games.csv:   game_id,date,tipoff_et,home,away,neutral,home_b2b,away_b2b,
             home_3in4,away_3in4,away_tz_shift   (flags 0/1; tz_shift = hours)
injuries.csv: team,player,status,minutes,on_off_net
             (status OUT/DOUBTFUL/QUESTIONABLE/PROBABLE; on_off_net = team net
              rating per 100 with player on minus off)
players.csv: player,team,pos,starter,minutes,usage,pts_pm,reb_pm,ast_pm,fg3m_pm
             (pos G/F/C; usage decimal; *_pm = per-minute rates)
positional_defense.csv: team,pos,pts_f,reb_f,ast_f,fg3m_f  (1.00 = league avg
             allowed to that position; missing rows default to 1.00)
odds.csv:    game_id,market,selection,line,price
             market: ML, SPREAD, TOTAL, TT_<TEAM>, 1H_ML, 1H_SPREAD, 1H_TOTAL,
                     1Q_ML, 1Q_SPREAD, 1Q_TOTAL
             selection: team code (ML/SPREAD) or OVER/UNDER; line = that side's
             line (spread from the selection's view, e.g. -3.5); price American
props.csv:   game_id,player,stat,line,over_price,under_price  (stat PTS/REB/AST/3PM/PRA)
"""
import csv, math, os
from statistics import NormalDist

# ----------------------------- WEIGHTS (untested) -----------------------------
LG_ORTG, LG_PACE = 114.5, 99.0
LG_FF = {"efg": 0.545, "tov": 0.128, "orb": 0.260, "ftr": 0.230}
FF_W = {"efg": 0.40, "tov": 0.25, "orb": 0.20, "ftr": 0.15}  # Dean Oliver
FF_SCALE, FF_CAP = 40.0, 3.0          # pts per unit weighted FF edge, cap
REGRESS_K = 20                        # games of league-mean regression
W_L15, W_SEASON = 0.40, 0.60
W_RATINGS, W_STATS = 0.50, 0.50
HOME_COURT = 2.0
B2B_HOME, B2B_ROAD = -1.5, -2.5
THREE_IN_FOUR = -1.0
ALTITUDE_TEAMS, ALTITUDE_PEN = {"DEN", "UTA"}, -1.0
TZ_PEN_PER_HR, TZ_CAP = -0.3, -1.0    # applied for shift beyond 1 hour
INJ_PROB = {"OUT": 1.0, "DOUBTFUL": 0.75, "QUESTIONABLE": 0.40, "PROBABLE": 0.10}
INJ_REPLACEMENT = 0.40                # share of on/off loss recovered by bench
SD = {"margin": 12.5, "total": 18.0, "tt": 11.0}
SEG = {"FG": (1.0, 1.0), "1H": (0.49, 0.71), "1Q": (0.245, 0.50)}  # mean, sd mult
P_MODEL_W = 0.30                      # p_blend = 0.30 model + 0.70 no-vig
PROP_MODEL_W = 0.70                   # prop mean blend 70 model / 30 market
PROP_SD = {"PTS": (2.0, 0.25), "REB": (1.2, 0.25), "AST": (1.0, 0.30),
           "3PM": (0.6, 0.40), "PRA": (3.0, 0.22)}   # sd = a + b*mean
BLOWOUT_SPREAD, BLOWOUT_CUT_PER_PT, BLOWOUT_CAP = 10.0, 0.03, 0.15
MAX_MIN = 40.0
SAME_POS_SHARE = 0.60   # share of a missing player's minutes to same-position mates
STARS = [(0.06, 5), (0.04, 4), (0.025, 3), (0.01, 2), (0.0, 1)]
N = NormalDist()

# ----------------------------- loaders ---------------------------------------
def _num(v, d=0.0):
    try:
        return float(v) if v not in (None, "") else d
    except ValueError:
        return d

def read_csv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]

def load_inputs(paths):
    d = {k: read_csv(paths.get(k)) for k in
         ("teams", "games", "injuries", "players", "positional_defense", "odds", "props")}
    d["teams"] = {r["team"]: r for r in d["teams"]}
    d["posdef"] = {(r["team"], r["pos"]): r for r in d.pop("positional_defense")}
    return d

# ----------------------------- odds helpers ----------------------------------
def am_to_dec(a):
    a = float(a)
    return 1 + (a / 100 if a > 0 else 100 / -a)

def ev(p_win, dec, p_push=0.0):
    return p_win * (dec - 1) - (1 - p_win - p_push)

def stars(e):
    return next(s for t, s in STARS if e >= t)

def p_over(mean, sd, line):
    """returns (p_over, p_push); integer lines get a +-0.5 push band"""
    if float(line).is_integer():
        po = 1 - N.cdf((line + 0.5 - mean) / sd)
        pu = N.cdf((line - 0.5 - mean) / sd)
        return po, 1 - po - pu
    return 1 - N.cdf((line - mean) / sd), 0.0

# ----------------------------- projection ------------------------------------
def regress(val, n, lg):
    w = n / (n + REGRESS_K)
    return w * val + (1 - w) * lg

def team_eff(t):
    n = _num(t["games"])
    o = W_SEASON * regress(_num(t["ortg"]), n, LG_ORTG) + W_L15 * _num(t["ortg_l15"], _num(t["ortg"]))
    dr = W_SEASON * regress(_num(t["drtg"]), n, LG_ORTG) + W_L15 * _num(t["drtg_l15"], _num(t["drtg"]))
    return o, dr, regress(_num(t["pace"]), n, LG_PACE)

def ff_edge(off, de):
    """four-factor matchup points for `off` scoring vs `de` (regressed)"""
    n = (_num(off["games"]) + _num(de["games"])) / 2
    e = 0.0
    for f, w in FF_W.items():
        o = regress(_num(off[f]), n, LG_FF[f]) - LG_FF[f]
        d = regress(_num(de["opp_" + f]), n, LG_FF[f]) - LG_FF[f]
        sign = -1 if f == "tov" else 1
        e += w * sign * (o + d) / 2
    return max(-FF_CAP, min(FF_CAP, e * FF_SCALE))

def injury_adj(injuries, team, pace):
    pts, notes = 0.0, []
    for r in injuries:
        if r["team"] != team:
            continue
        p = INJ_PROB.get(r["status"].upper(), 0.0)
        loss = _num(r["on_off_net"]) * (_num(r["minutes"]) / 48) * (pace / 100) * (1 - INJ_REPLACEMENT) * p
        if loss:
            pts -= loss
            notes.append(f"{r['player']} {r['status']} ({-loss:+.1f})")
    return pts, notes

def rest_adj(g, side):
    a, notes = 0.0, []
    if _num(g[f"{side}_b2b"]):
        v = B2B_HOME if side == "home" else B2B_ROAD
        a += v; notes.append(f"B2B {v:+.1f}")
    if _num(g[f"{side}_3in4"]):
        a += THREE_IN_FOUR; notes.append(f"3-in-4 {THREE_IN_FOUR:+.1f}")
    if side == "away":
        if g["home"] in ALTITUDE_TEAMS and not _num(g.get("neutral")):
            a += ALTITUDE_PEN; notes.append(f"altitude {ALTITUDE_PEN:+.1f}")
        tz = abs(_num(g.get("away_tz_shift")))
        if tz > 1:
            v = max(TZ_CAP, TZ_PEN_PER_HR * (tz - 1))
            a += v; notes.append(f"TZ {tz:.0f}h {v:+.1f}")
    return a, notes

def project_game(g, data):
    T = data["teams"]
    h, a = T[g["home"]], T[g["away"]]
    ho, hd, hp = team_eff(h)
    ao, ad, ap = team_eff(a)
    pace = (hp + ap) / 2
    h_pts = (ho + ad - LG_ORTG) / 100 * pace + ff_edge(h, a)
    a_pts = (ao + hd - LG_ORTG) / 100 * pace + ff_edge(a, h)
    stats_margin = h_pts - a_pts
    ratings_margin = _num(h["rating"]) - _num(a["rating"])
    margin = W_RATINGS * ratings_margin + W_STATS * stats_margin
    total = h_pts + a_pts
    # adjustments: each team's net effect split half to own offense, half to opp
    hc = 0.0 if _num(g.get("neutral")) else HOME_COURT
    hi, hin = injury_adj(data["injuries"], g["home"], pace)
    ai, ain = injury_adj(data["injuries"], g["away"], pace)
    hr, hrn = rest_adj(g, "home")
    ar, arn = rest_adj(g, "away")
    h_net, a_net = hc + hi + hr, ai + ar
    margin += h_net - a_net
    total += (hi + hr + ai + ar) * 0.5   # injuries/fatigue also lower scoring a bit
    hp_final, ap_final = (total + margin) / 2, (total - margin) / 2
    return {"game_id": g["game_id"], "home": g["home"], "away": g["away"],
            "pace": pace, "margin": margin, "total": total,
            "home_pts": hp_final, "away_pts": ap_final,
            "stats_margin": stats_margin, "ratings_margin": ratings_margin,
            "inputs": "; ".join([f"pace {pace:.1f}", f"HCA {hc:+.1f}"]
                                + [f"{g['home']} " + n for n in hin + hrn]
                                + [f"{g['away']} " + n for n in ain + arn])}

# ----------------------------- game markets ----------------------------------
def novig(rows):
    """Attach no-vig probability only to a verified complementary quote pair."""
    groups = {}
    for r in rows:
        r["nv_p"] = None
        key = (r["game_id"], r["market"], abs(_num(r["line"])) if r["line"] else "")
        groups.setdefault(key, []).append(r)
    for g in groups.values():
        if len(g) != 2:
            continue
        a, b = g
        sa, sb = a["selection"].upper(), b["selection"].upper()
        mk = a["market"].upper()
        if mk.endswith("TOTAL") or "_TT_" in mk or mk.startswith("TT_"):
            if {sa, sb} != {"OVER", "UNDER"} or _num(a["line"]) != _num(b["line"]):
                continue
        elif mk.endswith("SPREAD"):
            if sa == sb or abs(_num(a["line"]) + _num(b["line"])) > 1e-9:
                continue
        elif mk.endswith("ML"):
            if sa == sb or a["line"] or b["line"]:
                continue
        else:
            continue
        try:
            values = [float(r["price"]) for r in g]
            if any(not math.isfinite(p) or int(p) != p or abs(p) < 100 for p in values):
                continue
            imps = [1 / am_to_dec(p) for p in values]
            total = sum(imps)
            for r, i in zip(g, imps):
                r["nv_p"] = i / total
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            continue
    return rows

def price_game_market(r, proj):
    m, sel, line = r["market"], r["selection"].upper(), _num(r["line"])
    seg = m.split("_")[0] if m[:2] in ("1H", "1Q") else "FG"
    mm, sm = SEG[seg]
    margin, total = proj["margin"] * mm, proj["total"] * mm
    home = proj["home"]
    base = m.split("_", 1)[1] if seg != "FG" else m
    if base == "ML":
        mu = margin if sel == home else -margin
        p = 1 - N.cdf((0 - mu) / (SD["margin"] * sm))
        return p, 0.0, mu, "margin"
    if base == "SPREAD":
        mu = margin if sel == home else -margin
        po, push = p_over(mu, SD["margin"] * sm, -line)
        return po, push, mu, "margin"
    if base == "TOTAL":
        po, push = p_over(total, SD["total"] * sm, line)
        return (po if sel == "OVER" else 1 - po - push), push, total, "total"
    if base.startswith("TT"):
        team = m.split("_")[-1]
        mu = (proj["home_pts"] if team == home else proj["away_pts"]) * mm
        po, push = p_over(mu, SD["tt"] * sm, line)
        return (po if sel == "OVER" else 1 - po - push), push, mu, "tt"
    raise ValueError("unknown market " + m)

# ----------------------------- props -----------------------------------------
def project_players(data, projs):
    """Calculate each player separately for each event; never key only by name.

    Original minutes/usage math remains unchanged. Structural matching is not
    authentication of player roster status or source-publication time.
    """
    out = {}
    by_team = {}
    for p in data["players"]:
        by_team.setdefault(p["team"], []).append(dict(p))
    # An injury on one team must not affect a same-name player on another.
    inj = {(r["team"], r["player"]): INJ_PROB.get(r["status"].upper(), 0)
           for r in data["injuries"]}
    for gid, proj in projs.items():
        for team in (proj["home"], proj["away"]):
            if team not in by_team:
                continue
            plist = [dict(p) for p in by_team[team]]
            for p in plist:
                p["min"] = _num(p["minutes"]) * (1 - inj.get((team, p["player"]), 0))
                p["use"] = _num(p["usage"])
            for miss in plist:
                lost = _num(miss["minutes"]) - miss["min"]
                if lost <= 0:
                    continue
                mates = [q for q in plist if q is not miss
                         and inj.get((team, q["player"]), 0) < 1]
                same = [q for q in mates if q["pos"] == miss["pos"]]
                # Retain the original 60/40 minutes and 0.5 usage redistribution.
                for grp, share in ((same, SAME_POS_SHARE if same else 0),
                                   (mates, 1 - (SAME_POS_SHARE if same else 0))):
                    tot = sum(_num(q["minutes"]) for q in grp) or 1
                    for q in grp:
                        q["min"] = min(MAX_MIN, q["min"] + lost * share * _num(q["minutes"]) / tot)
                lost_use = miss["use"] * lost / max(_num(miss["minutes"]), 1)
                tu = sum(q["use"] for q in mates) or 1
                for q in mates:
                    q["use"] += lost_use * q["use"] / tu * 0.5
            spread = abs(proj["margin"])
            cut = min(BLOWOUT_CAP, max(0, spread - BLOWOUT_SPREAD) * BLOWOUT_CUT_PER_PT)
            opp = proj["away"] if team == proj["home"] else proj["home"]
            team_pace = regress(_num(data["teams"][team]["pace"]),
                                _num(data["teams"][team]["games"]), LG_PACE)
            for p in plist:
                if _num(p["starter"]):
                    p["min"] *= 1 - cut
                p["opp"], p["pace_f"], p["blowout_cut"] = opp, proj["pace"] / team_pace, cut
                key = (gid, team, p["player"], str(p.get("player_id") or "").strip())
                # Duplicated same-subject roster entries are ambiguous, not last-write wins.
                out[key] = None if key in out else p
    # Backwards-compatible alias only for a uniquely resolved player in one event.
    by_name = {}
    for key, p in out.items():
        if p is not None:
            by_name.setdefault(p["player"], []).append(p)
    for name, matches in by_name.items():
        if len(matches) == 1:
            out[name] = matches[0]
    return out


def prop_mean(p, stat, posdef):
    pd = posdef.get((p["opp"], p["pos"]), {})
    f = lambda k: _num(pd.get(k), 1.0)
    use_f = p["use"] / max(_num(p["usage"]), 1e-9)
    base = {"PTS": _num(p["pts_pm"]) * use_f * f("pts_f"),
            "REB": _num(p["reb_pm"]) * f("reb_f"),
            "AST": _num(p["ast_pm"]) * f("ast_f"),
            "3PM": _num(p["fg3m_pm"]) * use_f * f("fg3m_f")}
    base["PRA"] = base["PTS"] + base["REB"] + base["AST"]
    return base[stat] * p["min"] * p["pace_f"]

def prop_sd(stat, mean):
    a, b = PROP_SD[stat]
    return a + b * mean

def resolve_prop_player(prop, players):
    """Require exactly one bound event/team/player/optional stable-ID tuple."""
    event = str(prop.get("game_id") or "")
    name = str(prop.get("player") or "").strip()
    team = str(prop.get("team") or "").strip()
    player_id = str(prop.get("player_id") or "").strip()
    if not event or not (name or player_id):
        return None
    matches = [
        p for key, p in players.items()
        if isinstance(key, tuple) and len(key) == 4 and p is not None
        and key[0] == event
        and (not team or key[1] == team)
        and (not name or key[2] == name)
        and (not player_id or key[3] == player_id)
    ]
    return matches[0] if len(matches) == 1 else None


def price_props(data, players):
    rows = []
    for r in data["props"]:
        p = resolve_prop_player(r, players)
        if not p or p["min"] <= 0:
            continue
        stat, line = r["stat"].upper(), _num(r["line"])
        model = prop_mean(p, stat, data["posdef"])
        do, du = am_to_dec(r["over_price"]), am_to_dec(r["under_price"])
        nv_o = (1 / do) / (1 / do + 1 / du)
        sd = prop_sd(stat, model)
        mkt_mean = line + sd * N.inv_cdf(min(max(nv_o, 0.01), 0.99))
        mean = PROP_MODEL_W * model + (1 - PROP_MODEL_W) * mkt_mean
        po, push = p_over(mean, prop_sd(stat, mean), line)
        for side, dec, pm, nv in (("OVER", do, po, nv_o), ("UNDER", du, 1 - po - push, 1 - nv_o)):
            rows.append(_pick(r["game_id"], f"PROP_{stat}", f"{r['player']} {side}", line,
                              dec, pm, push, nv, mean, side,
                              f"min {p['min']:.1f}, model {model:.1f}, mkt {mkt_mean:.1f}"
                              + (f", blowout cut {p['blowout_cut']:.0%}" if p["blowout_cut"] else ""),
                              signal=(r["game_id"], p["team"], "OVER" if side == "OVER" else "UNDER")))
    return rows

# ----------------------------- picks / filter / stacks -----------------------
def _pick(gid, market, sel, line, dec, p, push, nv, proj_val, ou, note, signal):
    if nv is None:
        raise ValueError("NO_VIG_OPPOSITE_PRICE_MISSING")
    if not (math.isfinite(p) and math.isfinite(push) and math.isfinite(nv)
            and 0 <= p <= 1 and 0 <= push < 1 and 0 <= nv <= 1
            and p + push <= 1 + 1e-9):
        raise ValueError("INVALID_MODEL_OR_MARKET_PROBABILITIES")
    raw = ev(p, dec, push)
    # Two-way no-vig odds imply P(win | no push). Blend on THAT same basis.
    # Retain the model's push probability and settle pushes as stake refunds.
    model_conditional = p / (1 - push)
    pb = (P_MODEL_W * model_conditional + (1 - P_MODEL_W) * nv) * (1 - push)
    blend = ev(pb, dec, push)
    return {"game_id": gid, "market": market, "selection": sel, "line": line,
            "price_dec": round(dec, 3), "model_p": round(p, 4),
            "novig_p": round(nv, 4) if nv is not None else "", "blend_p": round(pb, 4),
            "raw_ev": round(raw, 4), "blend_ev": round(blend, 4),
            "projection": round(proj_val, 2), "ou": ou, "note": note, "signal": signal}

def price_games(data, projs):
    rows = novig([dict(r) for r in data["odds"]])
    out = []
    for r in rows:
        proj = projs.get(r["game_id"])
        if not proj:
            continue
        # A one-sided / ambiguous board cannot supply a no-vig market baseline.
        if r.get("nv_p") is None:
            continue
        p, push, mu, kind = price_game_market(r, proj)
        sel = r["selection"].upper()
        ou = sel if sel in ("OVER", "UNDER") else ""
        if kind == "margin":
            signal = (r["game_id"], sel, "SIDE")
            proj_val = mu
        elif kind == "tt":
            team = r["market"].split("_")[-1]
            signal = (r["game_id"], team, "SIDE") if sel == "OVER" else (r["game_id"], "TOT", sel)
            proj_val = mu
        else:
            signal, proj_val = (r["game_id"], "TOT", sel), mu
        out.append(_pick(r["game_id"], r["market"], sel, _num(r["line"]) if r["line"] else "",
                         am_to_dec(r["price"]), p, push, r.get("nv_p"), proj_val, ou,
                         proj["inputs"], signal))
    return out

def projection_filter(picks):
    keep = []
    for p in picks:
        if p["ou"] == "UNDER" and p["line"] != "" and p["line"] < p["projection"]:
            continue
        if p["ou"] == "OVER" and p["line"] != "" and p["line"] > p["projection"]:
            continue
        keep.append(p)
    return keep

def flag_stacks(picks):
    seen = {}
    for p in picks:
        seen.setdefault(p["signal"], []).append(p)
    for grp in seen.values():
        for p in grp:
            p["stack"] = f"STACK x{len(grp)}" if len(grp) > 1 else ""
    return picks

# ----------------------------- run card --------------------------------------
CARD_COLS = ["rank", "stars", "flame", "game_id", "market", "selection", "line",
             "price_dec", "model_p", "novig_p", "blend_p", "raw_ev", "blend_ev",
             "projection", "stack", "note"]

def run_card(inputs, out_dir="."):
    """inputs: dict of CSV paths (keys teams, games, injuries, players,
    positional_defense, odds, props). Writes nba_card.csv + nba_card.md."""
    data = load_inputs(inputs)
    projs = {g["game_id"]: project_game(g, data) for g in data["games"]}
    picks = price_games(data, projs)
    picks += price_props(data, project_players(data, projs))
    picks = [p for p in picks if p["blend_ev"] > 0]
    picks = flag_stacks(projection_filter(picks))
    picks.sort(key=lambda p: p["blend_ev"], reverse=True)
    for i, p in enumerate(picks, 1):
        p["rank"], p["stars"] = i, stars(p["blend_ev"])
        p["flame"] = "FIRE" if i <= 3 and p["stars"] >= 4 else ""
    os.makedirs(out_dir, exist_ok=True)
    csv_path, md_path = os.path.join(out_dir, "nba_card.csv"), os.path.join(out_dir, "nba_card.md")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CARD_COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(picks)
    md = ["# SportsEdge NBA RUN IT card", "", "## Projections", "",
          "| Game | Home pts | Away pts | Margin (home) | Total | Key inputs |", "|---|---|---|---|---|---|"]
    for pr in projs.values():
        md.append(f"| {pr['away']} @ {pr['home']} | {pr['home']} {pr['home_pts']:.1f} | {pr['away']} {pr['away_pts']:.1f} "
                  f"| {pr['margin']:+.1f} | {pr['total']:.1f} | {pr['inputs']} |")
    md += ["", "## Picks (ranked by blended EV)", "",
           "| # | Stars | Game | Market | Pick | Line | Dec | Win% | EV raw | EV blend | Stack |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in picks:
        md.append(f"| {p['rank']} | {'*' * p['stars']}{' FIRE' if p['flame'] else ''} | {p['game_id']} | {p['market']} "
                  f"| {p['selection']} | {p['line']} | {p['price_dec']} | {p['blend_p']:.1%} "
                  f"| {p['raw_ev']:+.1%} | {p['blend_ev']:+.1%} | {p['stack']} |")
    with open(md_path, "w") as f:
        f.write("\n".join(md) + "\n")
    return {"projections": projs, "picks": picks, "csv": csv_path, "md": md_path}

if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "sample"
    names = ["teams", "games", "injuries", "players", "positional_defense", "odds", "props"]
    res = run_card({n: os.path.join(d, n + ".csv") for n in names}, out_dir=sys.argv[2] if len(sys.argv) > 2 else "out")
    print(open(res["md"]).read())
