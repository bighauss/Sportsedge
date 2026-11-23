"""SportsEdge NFL all-markets pricer from the SAME Monte Carlo as DFS (showdown_mc.run).

One sim -> game lines (ML, spread, total, team totals) and player props
(pass/rush/rec yards, receptions, pass TDs, anytime TD). DFS and betting
therefore share identical numbers. Output: fair probabilities + fair American odds.
Book-price EV: when games/<tag>_lines.json exists (captured DK prices with source
and captured_at_utc), book_ev.py re-prices each line on the same scenarios and adds
a "book" block (no-vig prob, raw EV, 40/60 blended EV, stars, ranked by EV).
RESEARCH / PAPER until graded against closing lines.

python models/nfl_dfs/markets.py games/PIT_CIN_2026-11-15.json 20000
"""
import json, os, statistics, sys
import showdown_mc as mc
import book_ev

def american(p):
    """Sampled P=0 or P=1 cannot support a finite fair price: return missing."""
    if not 0 < p < 1:
        return None
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)

def implied(odds):
    return -odds / (-odds + 100) if odds < 0 else 100 / (odds + 100)

PROPS = {"pass_yds": lambda s: s["py"], "pass_tds": lambda s: s["ptd"], "rush_yds": lambda s: s["ry"],
         "rec_yds": lambda s: s["rcy"], "receptions": lambda s: s["rec"],
         "anytime_td": lambda s: s["rtd"] + s["rctd"]}

def price(cfg, n, seed=7, lines=None):
    if type(n) is not int or n < 2:
        raise ValueError("Need at least two Monte Carlo samples")
    if len(cfg["teams"]) != 2:
        raise ValueError("Two distinct game teams required")
    raw = []
    mc.run(cfg, n, seed=seed, raw=raw)
    away, home = list(cfg["teams"])
    A = [r[away][1] for r in raw]; H = [r[home][1] for r in raw]
    out = {"tag": cfg["tag"], "sims": n, "label": "RESEARCH / PAPER",
           "book_prices_available": False, "contest_ev": "BLOCKED_NO_OWNERSHIP_AND_PAYOUTS",
           "market_ev": "BLOCKED_NO_AUTHENTICATED_MATCHED_BOOK_QUOTES",
           "game": {}, "props": [], "inventory": {
               "modeled_research": ["moneyline", "spread", "total", "team_total",
                                    "player_pass_yards", "player_pass_tds",
                                    "player_rush_yards", "player_rec_yards",
                                    "player_receptions", "anytime_td", "td_2plus",
                                    "1h_2h_q1_q4_moneyline_spread_total"],
               "blocked": {
                   "first_td": "NO_ORDERED_SCORE_EVENTS",
                   "sgp": "NO_CALIBRATED_JOINT_SETTLEMENT_AND_BOOK_PRICE",
                   "alternate_lines": "NOT_CAPTURED_AND_NOT_ENUMERATED",
                   "player_completions": "NO_STAT_SIMULATION",
                   "player_attempts": "NO_STAT_SIMULATION",
                   "player_targets": "NO_STAT_SIMULATION",
                   "dst_sacks": "NO_INDEPENDENTLY_VALIDATED_DEFENSE_PROP",
                   "other_offered_markets": "NOT_CAPTURED",
               },
               "source_status": "NO_AUTHENTICATED_BOOK_PRICE_RECEIPTS"
           }}
    g = out["game"]
    g["proj"] = {away: round(statistics.fmean(A), 2), home: round(statistics.fmean(H), 2),
                 "total": round(statistics.fmean(a + h for a, h in zip(A, H)), 2),
                 "home_margin": round(statistics.fmean(h - a for a, h in zip(A, H)), 2)}
    pw = sum(h > a for a, h in zip(A, H)) / n; pt = sum(h == a for a, h in zip(A, H)) / n
    p_home_cond = pw / (1 - pt) if pt < 1 else None
    g["moneyline"] = {home: american(p_home_cond) if p_home_cond is not None else None,
                      away: american(1 - p_home_cond) if p_home_cond is not None else None}
    g["moneyline_note"] = "Fair American odds conditional on non-tie; missing if unpriceable"
    g["p_tie"] = round(pt, 4)
    sp = cfg["market"]["spread_home"]; tot = cfg["market"]["total"]
    cover = sum(h - a > sp for a, h in zip(A, H)) / n
    spread_push = sum(h - a == sp for a, h in zip(A, H)) / n
    over = sum(a + h > tot for a, h in zip(A, H)) / n
    total_push = sum(a + h == tot for a, h in zip(A, H)) / n
    g[f"{home} -{sp}"] = round(cover, 4)
    g[f"over {tot}"] = round(over, 4)
    g["spread_settlement"] = {
        "home_cover": round(cover, 4), "away_cover": round(1-cover-spread_push, 4),
        "push": round(spread_push, 4)}
    g["total_settlement"] = {
        "over": round(over, 4), "under": round(1-over-total_push, 4),
        "push": round(total_push, 4)}
    # Periods from the SAME draws: scoring events allocated to quarters (no OT in sim;
    # 2H/Q4 books usually include OT, so a regulation tie leaves 2H unchanged).
    PER = {"Q1": (0,), "Q2": (1,), "Q3": (2,), "Q4": (3,), "1H": (0, 1), "2H": (2, 3)}
    g["periods"] = {}
    if not all("_periods" in r for r in raw):
        g["periods"] = "NO_PERIOD_SIMULATION"
        out["inventory"]["blocked"].update(halves="NO_PERIOD_SIMULATION", quarters="NO_PERIOD_SIMULATION")
    for name, qs in (PER.items() if isinstance(g["periods"], dict) else ()):
        ph = [sum(r["_periods"][home][i] for i in qs) for r in raw]
        pa = [sum(r["_periods"][away][i] for i in qs) for r in raw]
        tie = sum(h == a for h, a in zip(ph, pa)) / n
        hw = sum(h > a for h, a in zip(ph, pa)) / n
        mt = statistics.fmean(h + a for h, a in zip(ph, pa))
        g["periods"][name] = {
            "proj_home": round(statistics.fmean(ph), 2), "proj_away": round(statistics.fmean(pa), 2),
            "proj_total": round(mt, 2), "home_win": round(hw, 4), "tie": round(tie, 4),
            "away_win": round(1 - hw - tie, 4),
            "home_win_2way_tie_refund": round(hw / (1 - tie), 4) if tie < 1 else None}
    for tm, xs in ((away, A), (home, H)):
        med = statistics.median(xs) + 0.5
        g[f"{tm} team total fair"] = med
        g[f"{tm} over {med}"] = round(sum(x > med for x in xs) / n, 4)
    for p, meta in cfg["players"].items():
        if meta["pos"] in ("K", "DST"): continue
        tm = meta["team"]
        for mk, f in PROPS.items():
            vals = [f(r[tm][0][p]) if p in r[tm][0] else 0 for r in raw]
            if mk == "pass_yds" and meta["pos"] != "QB": continue
            if mk == "pass_tds" and meta["pos"] != "QB": continue
            if mk in ("rec_yds", "receptions") and meta["pos"] == "QB": continue
            if statistics.fmean(vals) < (0.25 if mk == "anytime_td" else 1.5): continue
            if mk == "anytime_td":
                pr = sum(v >= 1 for v in vals) / n
                p2 = sum(v >= 2 for v in vals) / n
                out["props"].append(dict(player=p, team=tm, market="anytime_td",
                                         p_yes=round(pr, 4), fair=american(pr),
                                         fair_status="INSUFFICIENT_SAMPLE_EXTREME" if pr in (0,1) else "RESEARCH"))
                out["props"].append(dict(player=p, team=tm, market="td_2plus",
                                         p_yes=round(p2, 4), fair=american(p2),
                                         fair_status="INSUFFICIENT_SAMPLE_EXTREME" if p2 in (0,1) else "RESEARCH"))
            else:
                line = round(statistics.median(vals)) + 0.5
                pr = sum(v > line for v in vals) / n
                out["props"].append(dict(player=p, team=tm, market=mk, mean=round(statistics.fmean(vals), 2),
                                         fair_line=line, p_over=round(pr, 4)))
    out["inventory"]["note"] = (
        "These markets are distributions, not verified prices or full DK board coverage. "
        "Unmodeled or uncaptured families remain visible. Simulation alone is not a betting edge.")
    if lines is not None:
        out["book"] = book_ev.price_lines(cfg, raw, away, home, lines, PROPS)
        out["book_prices_available"] = True
        out["market_ev"] = "RESEARCH_UNVALIDATED_SEE_book_BLOCK"
        out["inventory"]["source_status"] = (
            "BOOK_PRICES_FROM_LINES_FILE_%s_%s_UNAUTHENTICATED" % (
                lines["source"], lines["captured_at_utc"]))
    return out

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "games", "PIT_CIN_2026-11-15.json")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    cfg = json.load(open(path))
    lines = None
    lpath = os.path.join(os.path.dirname(os.path.abspath(path)), f"{cfg['tag']}_lines.json")
    if os.path.exists(lpath):
        lines = json.load(open(lpath))
    out = price(cfg, n, lines=lines)
    od = os.path.join(here, "out"); os.makedirs(od, exist_ok=True)
    json.dump(out, open(os.path.join(od, f"{cfg['tag']}_markets.json"), "w"), indent=1)
    print(json.dumps(out["game"], indent=1))
    for x in sorted(out["props"], key=lambda r: (r["market"], r["team"])):
        print(x)
    if "book" in out:
        for r in out["book"]["rows"]:
            print(r["rank"], r["stars"], r["market"], r["subject"], r["side"], r["line"],
                  r["price"], "EV raw", r["ev_raw"], "blend", r["ev_blended"])
        for u in out["book"]["unpriced"]:
            print("UNPRICED", u["reason"], u["entry"])

if __name__ == "__main__":
    main()
