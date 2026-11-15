#!/usr/bin/env python3
# Engine of record: v4 + edge audit FIX-7 (adopted Nov 11, 2026).
# See candidate 3 / build_candidate3.py for the original audit spec.
# Withholds an ML side when the book's ML no-vig prob disagrees with
# the win prob implied by the book's own spread by >15% relative.
# An SGP containing a withheld ML leg is withheld as a whole.
"""SportsEdge portable engine v2 - all sports, game markets + props. Needs only numpy.
v2 (Nov 9 2026): card shows the game and one best row per bet type per game; ANCHOR uses the
spread instead of a lopsided moneyline; PROJECTION games print how far they sit from the book;
basketball favorites build more of the margin in the first half (CBB 55%, NBA 52%).
v3 CANDIDATE 1 (Nov 10 2026, Claude) - NOT the engine of record. One code change, NFL quarters and halves only:
each team's drives are dealt to the four quarters in order (one random offset per team per simulation, instead
of a random quarter for every drive), using the real split of points (qs) and of the favourite's margin (qm)
by quarter, fitted on nflverse 2015-2021 (1,889 games). Two effects: the split by quarter moves to the real
one, AND quarter/half totals get narrower (typical game: 1Q total sd about 8.3 -> 6.1, 1H total 11.8 -> 9.9;
1H and 2H totals are no longer negatively linked). Pre-registered test on 2022-2026 (1,275 games): PASS,
first-half and first-quarter Brier 0.23786 -> 0.23605. Full-game results are bit-identical to v2. CFB unchanged.
v3 CANDIDATE 2 (Nov 11 2026, Claude) - NOT the engine of record. Built on v3. NFL full-game width only (queue B2):
drives per team 11.0 -> 9.0 and drive-count spread 1.2 -> 0.0 (every NFL game gets exactly 9 drives a side).
Chosen on 2015-2021 train games; tested once on 2022-2026 (1,275 games, 700 line pairs) and reproduced by Rocky:
16 alt-line Brier 0.17595 -> 0.17536 (z -3.85); margin sd vs actual +0.958 -> +0.129, total sd +1.168 -> -0.562.
CFB and every other sport unchanged. NFL quarter/half prices also move (they are cut from the same drives).
Run:  python sportsedge.py board.csv

Sports: NFL CFB NBA CBB MLB NHL UFC DWCS PGA

Board columns (one row per market; blank columns are fine):
  sport,home,away,home_proj,away_proj,player,team,proj,market,line,price_a,price_b,sgp,side,
  home_score,away_score,remaining

GAME ROWS (player blank)
  Full game : ML  SPREAD  TOTAL  HOME_TT  AWAY_TT
              OT (yes/no)  BTTS (both teams score)  REG_HOME  REG_AWAY  REG_DRAW (3-way regulation)
              HOME_BY_lo_hi / AWAY_BY_lo_hi  winning-margin band, e.g. HOME_BY_1_6 (exact = HOME_BY_3_3)
  Periods   : put a prefix on ML / SPREAD / TOTAL / HOME_TT / AWAY_TT
              NFL CFB NBA : 1Q_ 2Q_ 3Q_ 4Q_ 1H_ 2H_
              CBB         : 1H_ 2H_
              NHL         : P1_ P2_ P3_
              MLB         : I1_ (1st inning; NRFI = I1_TOTAL 0.5 under) F3_ F5_ F7_
  line      SPREAD = the HOME team's line (home favored by 3.5 -> -3.5; MLB run line, NHL puck line same)
            TOTAL / TT = the number.  Others blank.
  price_a   HOME / OVER / YES        price_b   AWAY / UNDER / NO  (blank = one-sided)
  home_proj / away_proj   projected points / runs / goals (optional)
  Alt lines and ladders are just more rows.

FIGHTS (UFC, DWCS): home = fighter A, away = fighter B
  ML | TOTAL (rounds) | GTD (goes the distance yes/no) | SCHEDULED (line = 5 for a 5-rounder; default 3)
  A_INSIDE  B_INSIDE  A_DEC  B_DEC | ROUND_1 .. ROUND_5 (fight ends in that round)
  home_proj = fighter A win probability 0-1 (optional)

GOLF (PGA): home = tournament name, away blank, one row per golfer per market
  WIN | TOP5 | TOP10 | TOP20 | MAKE_CUT | FRL (first-round leader) | H2H (team = the opponent's name)
  proj = strokes per round better than the field average (optional; else fitted to WIN odds)

PLAYER PROPS (player filled; team must match the home or away name exactly)
  NFL CFB : PASS_YDS RUSH_YDS REC_YDS PASS_RUSH_YDS RUSH_REC_YDS RECEPTIONS COMPLETIONS PASS_ATT
            RUSH_ATT PASS_TDS INTS KICKING_PTS FG_MADE TACKLES_AST SACKS | ATD TD2 FTD
  NBA CBB : POINTS REBOUNDS ASSISTS THREES PRA PTS_REB PTS_AST REB_AST STEALS BLOCKS TURNOVERS STL_BLK
  MLB     : STRIKEOUTS OUTS HITS_ALLOWED ER WALKS_ALLOWED HITS TOTAL_BASES HR RBIS RUNS SB HRR WALKS
  NHL     : SOG GOALS ASSISTS POINTS SAVES BLOCKS
  line    the number (a "100+ yards" rung is 99.5; "to hit a HR" / anytime goal is 0.5), price_a only if one-sided
  proj    stat props: the player's projected MEAN for this game (optional)
          TD markets: the player's share of his team's touchdowns, 0-1 (required)

LIVE (in-play): on the game's rows fill home_score, away_score and remaining (share of the game
  left, 0-1; halftime = 0.5). Prices full-game ML / SPREAD / TOTAL / team totals / OT / margin bands
  from the current score. Periods and player props are not priced live.

SAME-GAME PARLAYS (game-market legs, stat props, ATD and TD2)
  Give each leg row the same id in `sgp` and A or B in `side` (A = home/over/yes).
  Add one row: market SGP, same `sgp` id, price_a = the parlay price.

HOW A NUMBER IS SET
  PROJECTION  a projection is supplied; the model has its own opinion.
  ANCHOR      projection blank; fitted to the no-vig main line (ML or SPREAD, plus TOTAL; a prop's
              most balanced two-sided line; golf WIN odds). No opinion on the rows it was fitted
              to - it prices every OTHER row. Edges mean "this price disagrees with the main line".
"""
import csv, sys, math, hashlib
import numpy as np

N_SIM, N_FIT, N_GOLF = 40000, 20000, 20000
EV_FLOOR, PRICE_CAP, DOUBT_EV = 0.01, None, 0.40   # owner ruling Nov 9: gates open, every +EV row shows

KIND = dict(NFL="drive", CFB="drive", NBA="hoop", CBB="hoop", NHL="puck", MLB="ball",
            UFC="fight", DWCS="fight", PGA="golf")
DRIVE = {
    "NFL": dict(drives=9.0, dsd=0.0, fg=0.75, otm=[3, 6, 7], otp=[0.55, 0.35, 0.10], both=0.0,
                snap=[(3, 0.40), (7, 0.20)],
                qs=[0.197, 0.308, 0.207, 0.288], qm=[0.236, 0.321, 0.256, 0.187]),
    # qs = split of regulation points by quarter; qm = split of the favourite's margin by quarter.
    # Evidence: nflverse play-by-play 2015-2021, n=1,889 games. A league with no qs (CFB) keeps the v2 quarters.
    "CFB": dict(drives=12.5, fg=0.42, otm=[3, 7, 6, 1, 8], otp=[0.35, 0.30, 0.10, 0.10, 0.15], both=0.4,
                snap=[(3, 0.30), (7, 0.15)]),
}
HOOP = {
    "NBA": dict(sdm=12.5, sdt=18.5, shares=[0.25, 0.25, 0.25, 0.25], mshares=[0.26, 0.26, 0.25, 0.23], ot=20),
    "CBB": dict(sdm=11.329, sdt=17.691, shares=[0.47, 0.53], mshares=[0.55, 0.45], ot=15),
    # shares = split of scoring; mshares = split of the margin (favorites build more of it early)
}
PUCK_SHARES = [0.31, 0.35, 0.34]
PUCK_TIE_SNAP = 0.19     # share of one-goal games pulled level late (calibrated to real OT rate)
NO_SCRIPT = {"TACKLES_AST", "SACKS", "INTS", "STRIKEOUTS", "OUTS", "HITS_ALLOWED", "ER", "WALKS_ALLOWED",
             "SAVES", "BLOCKS", "STEALS", "TURNOVERS", "STL_BLK"}   # props not tied to own team scoring
QTR = {"1Q": [0], "2Q": [1], "3Q": [2], "4Q": [3], "1H": [0, 1], "2H": [2, 3]}
PERIODS = dict(NFL=QTR, CFB=QTR, NBA=QTR, CBB={"1H": [0], "2H": [1]},
               NHL={"P1": [0], "P2": [1], "P3": [2]},
               MLB={"I1": [0], "F3": [0, 1, 2], "F5": [0, 1, 2, 3, 4], "F7": list(range(7))})

# prop spread assumptions: ("y", sd as a fraction of the mean) or ("c", variance / mean)
def _c(**kw):
    return {k: ("c", v) for k, v in kw.items()}
PROPS = {
    "drive": dict({k: ("y", v) for k, v in dict(PASS_YDS=0.28, RUSH_YDS=0.55, REC_YDS=0.70,
                                                PASS_RUSH_YDS=0.27, RUSH_REC_YDS=0.50).items()},
                  **_c(RECEPTIONS=1.3, COMPLETIONS=1.0, PASS_ATT=1.0, RUSH_ATT=1.4, PASS_TDS=1.0,
                       INTS=1.0, KICKING_PTS=1.3, FG_MADE=1.0, TACKLES_AST=1.2, SACKS=1.0)),
    "hoop": _c(POINTS=2.4, REBOUNDS=1.4, ASSISTS=1.4, THREES=1.3, PRA=2.6, PTS_REB=2.5, PTS_AST=2.5,
               REB_AST=1.5, STEALS=1.1, BLOCKS=1.2, TURNOVERS=1.1, STL_BLK=1.2),
    "ball": _c(STRIKEOUTS=1.1, OUTS=1.0, HITS_ALLOWED=1.1, ER=1.4, WALKS_ALLOWED=1.1, HITS=1.0,
               TOTAL_BASES=1.9, HR=1.0, RBIS=1.5, RUNS=1.1, SB=1.1, HRR=1.6, WALKS=1.0),
    "puck": _c(SOG=1.1, GOALS=1.0, ASSISTS=1.0, POINTS=1.05, SAVES=1.3, BLOCKS=1.1),
}
TD_NAMES = dict(ATD="Anytime TD", TD2="2+ TDs", FTD="First TD")
GOLF_NAMES = dict(FRL="First Round Leader", WIN="To Win", TOP5="Top 5", TOP10="Top 10", TOP20="Top 20", MAKE_CUT="Make Cut")

# ---------- odds math ----------
def implied(odds):
    o = float(odds)
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)

def payout(odds):
    o = float(odds)
    return o / 100.0 if o > 0 else 100.0 / -o

def american(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)

def devig_power(pa, pb):
    """Power-method no-vig (POWER_V1): find k with pa^k + pb^k = 1."""
    lo, hi = 0.2, 10.0
    for _ in range(60):
        k = (lo + hi) / 2
        if pa ** k + pb ** k > 1:
            lo = k
        else:
            hi = k
    return pa ** k, pb ** k

def bisect(f, lo, hi, steps=14):
    """f must increase with x; returns x where f crosses 0."""
    for _ in range(steps):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2

def cond(pw, pl):
    return pw / (pw + pl) if pw + pl > 0 else 0.5

def fair_a(row):
    return devig_power(implied(row["price_a"]), implied(row["price_b"]))[0]

ML_TOL = 0.15  # candidate 3: max relative ML-vs-spread book inconsistency


def ml_blocked_sides(r, spr, S):
    """Candidate 3: sides of ML row r whose book price contradicts the
    book's own spread row spr. Returns (blocked emit-side indices,
    (p_ml_a, p_sp_a)). The spread-implied win prob is fit from the
    game's OWN simulated margins: the margin mean m* that makes the
    book's spread a fair coin-flip against the sim's margin shape
    (bisect on P(margin + spr.line > 0) = fair_a(spr), the same
    construction anchor() uses), then p_sp_a = P(margin > 0) at m*.
    No distributional assumption — exact for the discrete/low-scoring
    sims (puck/ball/drive) where a normal approx on the margin fails
    (ties, run/goal granularity)."""
    margins = S["h"] - S["a"]

    def cover(m):
        return float((margins + m + spr["line"] > 0).mean())

    m_star = bisect(lambda m: cover(m) - fair_a(spr), -60.0, 60.0, 40)
    p_sp_a = float((margins + m_star > 0).mean())
    p_ml_a = fair_a(r)                    # book ML no-vig prob, side A
    out = set()
    for i, (pm, pp) in enumerate(((p_ml_a, p_sp_a), (1 - p_ml_a, 1 - p_sp_a))):
        if pp > 0.005 and abs(pm - pp) / pp > ML_TOL:
            out.add(i)
    return out, (p_ml_a, p_sp_a)


def seed_of(text):
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)

def score(ev):
    """Master-brief score: 50 = break-even, capped at 79."""
    return int(round(min(max(50 + 29 * ev / (abs(ev) + 0.25), 1), 79)))

def stars(sc):
    return 5 if sc >= 65 else 4 if sc >= 60 else 3 if sc >= 55 else 2 if sc >= 50 else 1

# ---------- game simulators: return per-period scores H, A plus finals h, a ----------
def sim_drive(hp, ap, lg, rng, n, live):
    ch, ca, rem = live
    P, K = DRIVE[lg], 18
    d = np.clip(np.rint(rng.normal(P["drives"] * rem, P.get("dsd", 1.2) * math.sqrt(rem), n)), 0, K).astype(int)
    idx = np.arange(K)[None, :]
    live_d = idx < d[:, None]
    q = rng.choice(4, (n, K), p=[0.21, 0.29, 0.21, 0.29])   # 2nd and 4th quarters score most

    def team(pts):
        ptd = min(max(pts, 0.5) / P["drives"] / (7.0 + 3 * P["fg"]), 0.6)
        u, v = rng.random((n, K)), rng.random((n, K))
        td = (u < ptd) & live_d
        fg = (u >= ptd) & (u < ptd * (1 + P["fg"])) & live_d
        x = td * np.where(v < 0.05, 6, np.where(v < 0.10, 8, 7)) + fg * 3
        return x, td.sum(1)

    xh, htd = team(hp)
    xa, atd = team(ap)
    hs, as_ = xh.sum(1), xa.sum(1)
    sh, sa = np.zeros(n, int), np.zeros(n, int)
    for t, pr in P["snap"]:                    # pull near-misses onto the key numbers 3 and 7
        m = hs + sh + ch - as_ - sa - ca
        r, am = rng.random(n) < pr, np.abs(m)
        sh += r & (((am == t - 1) & (m > 0)) | ((am == t + 1) & (m < 0)))
        sa += r & (((am == t - 1) & (m < 0)) | ((am == t + 1) & (m > 0)))
    h, a = hs + sh + ch, as_ + sa + ca
    tie = h == a
    both = tie & (rng.random(n) < P["both"])
    w = rng.random(n) < min(max(0.5 + (hp - ap) * 0.012, 0.2), 0.8)
    mg = rng.choice(P["otm"], n, p=P["otp"])

    def deal(x, own, opp):                     # every draw above is in the v2 order; the new draws come last
        if "qs" not in P:
            qq = q                             # v2 behaviour: each drive lands in a random quarter
        else:                                  # drives in order; this team's own share of scoring per quarter
            wq = (np.array(P["qs"]) * (own + opp) + np.array(P["qm"]) * (own - opp)) / (2 * max(own, 0.25))
            wq = np.maximum(wq, 0.02)
            cut = np.cumsum(wq / wq.sum())[:3]
            tpos = (idx + rng.random(n)[:, None]) / np.maximum(d, 1)[:, None]
            qq = (tpos[:, :, None] >= cut[None, None, :]).sum(2)
        return np.stack([(x * (qq == k)).sum(1) for k in range(4)], 1)

    H, A = deal(xh, hp, ap), deal(xa, ap, hp)
    H[:, 3] += sh
    A[:, 3] += sa
    return dict(H=H, A=A, h=h + 7 * both + tie * w * mg, a=a + 7 * both + tie * (~w) * mg,
                ot=tie, htd=htd, atd=atd)

def sim_hoop(hp, ap, lg, rng, n, live):
    ch, ca, rem = live
    P = HOOP[lg]
    mu_m, mu_t = (hp - ap) * rem, (hp + ap) * rem
    Hs, As = [], []
    for s, ms in zip(P["shares"], P["mshares"]):
        m = rng.normal(ms * mu_m, P["sdm"] * math.sqrt(s * rem), n)
        t = rng.normal(s * mu_t, P["sdt"] * math.sqrt(s * rem), n)
        Hs.append(np.rint((t + m) / 2))
        As.append(np.rint((t - m) / 2))
    H, A = np.stack(Hs, 1), np.stack(As, 1)
    h, a = H.sum(1) + ch, A.sum(1) + ca
    ot = h == a
    for _ in range(6):
        tie = h == a
        if not tie.any():
            break
        om = np.rint(rng.normal((hp - ap) * 0.1, 4.0, n))
        h = h + tie * (P["ot"] // 2 + np.maximum(om, 0))
        a = a + tie * (P["ot"] // 2 + np.maximum(-om, 0))
    return dict(H=H, A=A, h=h + (h == a), a=a, ot=ot)

def sim_puck(hp, ap, rng, n, live):
    ch, ca, rem = live
    hp, ap = hp * 0.96, ap * 0.96            # leave room for the late equaliser and the OT goal
    H = np.stack([rng.poisson(hp * s * rem, n) for s in PUCK_SHARES], 1)
    A = np.stack([rng.poisson(ap * s * rem, n) for s in PUCK_SHARES], 1)
    m = H.sum(1) + ch - A.sum(1) - ca
    r = rng.random(n) < PUCK_TIE_SNAP          # trailing team equalises late
    H[:, 2] += r & (m == -1)
    A[:, 2] += r & (m == 1)
    h, a = H.sum(1) + ch, A.sum(1) + ca
    tie = h == a
    w = rng.random(n) < min(max(0.5 + 0.06 * (hp - ap), 0.3), 0.7)
    return dict(H=H, A=A, h=h + tie * w, a=a + tie * (~w), ot=tie)

def sim_ball(hp, ap, rng, n, live):
    ch, ca, rem = live
    k = 0.4                                   # inning-run clumpiness (about 72% scoreless innings)
    def innings(per):
        x = rng.poisson(rng.gamma(k, max(per, 0.01) / k, (n, 9)))
        x[:, :9 - max(1, math.ceil(9 * rem - 1e-9))] = 0   # live: only the innings still to play
        return x
    A = innings(ap / 9.0 * 0.975)
    H = innings(hp / 8.72 * 0.975)
    H[:, 8] *= ~(H[:, :8].sum(1) + ch > A.sum(1) + ca)   # no bottom 9th when the home team already leads
    h, a = H.sum(1) + ch, A.sum(1) + ca
    tie = h == a
    w = rng.random(n) < min(max(0.52 + 0.02 * (hp - ap), 0.35), 0.65)
    mg = rng.choice([1, 2, 3, 4], n, p=[0.60, 0.20, 0.12, 0.08])
    base = rng.choice([0, 1, 2], n, p=[0.55, 0.35, 0.10])
    return dict(H=H, A=A, h=h + tie * (base + w * mg), a=a + tie * (base + (~w) * mg), ot=tie)

def sim_fight(p, hazard, sched, rng, n):
    r = rng.geometric(max(hazard, 1e-4), n)
    return dict(awin=rng.random(n) < p, sched=sched, rnd=np.minimum(r, sched),
                dur=np.where(r > sched, float(sched), r - 1 + rng.random(n)))

def simulate(sport, hp, ap, seed, n, live=(0, 0, 1.0)):
    rng, kind = np.random.default_rng(seed), KIND[sport]
    if kind == "drive":
        return sim_drive(hp, ap, sport, rng, n, live)
    if kind == "hoop":
        return sim_hoop(hp, ap, sport, rng, n, live)
    if kind == "puck":
        return sim_puck(hp, ap, rng, n, live)
    return sim_ball(hp, ap, rng, n, live)

# ---------- market readout ----------
def split_market(sport, market):
    pre, _, rest = market.partition("_")
    return (pre, rest) if rest and pre in PERIODS.get(sport, {}) else ("", market)

def diff(S, sport, market, line):
    """Per-simulation result for side A: >0 win, 0 push, <0 loss."""
    if "awin" in S:
        if market == "ML":
            return np.where(S["awin"], 1, -1)
        if market == "TOTAL":
            return S["dur"] - line
        fin = S["dur"] < S["sched"]
        if market == "GTD":
            return np.where(~fin, 1, -1)
        if market in ("A_INSIDE", "B_INSIDE", "A_DEC", "B_DEC"):
            who = S["awin"] if market[0] == "A" else ~S["awin"]
            return np.where(who & (fin if market.endswith("INSIDE") else ~fin), 1, -1)
        if market.startswith("ROUND_"):
            return np.where(fin & (S["rnd"] == int(market[6:])), 1, -1)
        raise ValueError("unknown fight market: " + market)
    pre, base = split_market(sport, market)
    if pre:
        ix = PERIODS[sport][pre]
        h, a = S["H"][:, ix].sum(1), S["A"][:, ix].sum(1)
    else:
        h, a = S["h"], S["a"]
    if base == "ML":
        return h - a
    if base == "SPREAD":
        return h + line - a
    if base == "TOTAL":
        return h + a - line
    if base == "HOME_TT":
        return h - line
    if base == "AWAY_TT":
        return a - line
    if not pre:
        rh, ra = S["H"].sum(1), S["A"].sum(1)
        if base == "OT":
            return np.where(S["ot"], 1, -1)
        if base == "BTTS":
            return np.where((h > 0) & (a > 0), 1, -1)
        if base == "REG_HOME":
            return np.where(rh > ra, 1, -1)
        if base == "REG_AWAY":
            return np.where(ra > rh, 1, -1)
        if base == "REG_DRAW":
            return np.where(ra == rh, 1, -1)
        if base.startswith(("HOME_BY_", "AWAY_BY_")):      # winning-margin band, e.g. HOME_BY_1_6
            lo, hi = (int(x) for x in base[8:].split("_"))
            m = (h - a) if base[0] == "H" else (a - h)
            return np.where((m >= lo) & (m <= hi), 1, -1)
    raise ValueError("unknown market: " + market)

def wl(d):
    return float((d > 0).mean()), float((d < 0).mean())

def anchor(sport, rows, seed, live=(0, 0, 1.0)):
    two = [r for r in rows if r["price_a"] and r["price_b"]]
    tot = [r for r in two if r["market"] == "TOTAL"]
    mls = [r for r in two if r["market"] == "ML"]
    sps = [r for r in two if r["market"] == "SPREAD"]
    if not tot or not (mls or sps):
        return None
    tot = min(tot, key=lambda r: abs(fair_a(r) - 0.5))
    # a lopsided moneyline pins the margin poorly, so use the most balanced spread instead
    use_ml = mls and (0.15 <= fair_a(mls[0]) <= 0.85 or not sps)
    side = mls[0] if use_ml else min(sps, key=lambda r: abs(fair_a(r) - 0.5))
    T, m, rem = tot["line"], 0.0, live[2]
    lo_t, hi_t = (0.6 * T, 1.4 * T) if rem >= 1 else (0.05 * T, 2.5 * T / rem)

    def gap(mm, tt, row):
        S = simulate(sport, (tt + mm) / 2, (tt - mm) / 2, seed, N_FIT, live)
        return cond(*wl(diff(S, sport, row["market"], row["line"]))) - fair_a(row)

    for _ in range(2):
        m = bisect(lambda x: gap(x, T, side), -0.6 * T, 0.6 * T, 16)
        T = bisect(lambda x: gap(m, x, tot), lo_t, hi_t, 16)
    return (T + m) / 2, (T - m) / 2

# ---------- player props ----------
def stat_probs(spec, mean, line, seed):
    """(win, loss) for OVER on a yards or count prop."""
    mean, (form, v) = max(mean, 0.01), spec
    if form == "y":
        shape = 1.0 / v ** 2
        x = np.rint(np.random.default_rng(seed).gamma(shape, 1.0, N_FIT) / shape * mean)
        return float((x > line).mean()), float((x < line).mean())
    ks = range(int(mean * 4 + 40))
    if v <= 1.001:
        lp = [k * math.log(mean) - mean - math.lgamma(k + 1) for k in ks]
    else:
        s = mean / (v - 1)
        lp = [math.lgamma(k + s) - math.lgamma(s) - math.lgamma(k + 1)
              + s * math.log(s / (s + mean)) + k * math.log(mean / (s + mean)) for k in ks]
    p, k = np.exp(lp), np.arange(len(lp))
    return float(p[k > line].sum()), float(p[k < line].sum())

def prop_sample(spec, mean, f, rng):
    """Per-simulation stat draws for SGP legs; f ties the stat to the player's team scoring."""
    form, v = spec
    if form == "y":
        shape = 1.0 / v ** 2
        return np.rint(rng.gamma(shape, 1.0, len(f)) / shape * mean * f)
    if v <= 1.001:
        return rng.poisson(mean * f)
    return rng.poisson(rng.gamma(mean / (v - 1), v - 1, len(f)) * f)

def td_probs(S, market, share, is_home):
    k = (S["htd"] if is_home else S["atd"]).astype(float)
    miss = (1 - share) ** k
    if market == "ATD":
        p = 1 - miss
    elif market == "TD2":
        p = 1 - miss - k * share * (1 - share) ** np.maximum(k - 1, 0)
    else:  # FTD: any touchdown in the game equally likely to be first
        p = share * k / np.maximum((S["htd"] + S["atd"]).astype(float), 1)
    w = float(p.mean())
    return w, 1 - w

# ---------- golf ----------
def run_golf(event, rows, emit, notes):
    names = sorted({r["player"] for r in rows} | {r.get("team", "") for r in rows if r["market"] == "H2H"} - {""})
    ix = {p: i for i, p in enumerate(names)}
    m, rng = len(names), np.random.default_rng(seed_of("PGA|" + event))
    skill = np.zeros(m)
    given = {r["player"]: r["proj"] for r in rows if r["proj"] is not None}
    mode = "PROJECTION"
    if len(given) == m:
        for p, v in given.items():
            skill[ix[p]] = v
    else:
        win = {r["player"]: implied(r["price_a"]) for r in rows if r["market"] == "WIN" and r["price_a"]}
        if len(win) < max(m - 1, 30):
            notes.append(f"PGA {event}: skipped - needs proj for every golfer, or WIN odds for the whole field (30+ golfers)")
            return
        mode = "ANCHOR"
        tgt = np.array([win.get(p, min(win.values())) for p in names])
        tgt = tgt / tgt.sum()
        Z = rng.normal(0, 5.5, (N_GOLF, m))
        for _ in range(40):
            simp = np.bincount((Z - 4 * skill).argmin(1), minlength=m) / N_GOLF
            skill += np.clip(0.5 * np.log((tgt + 2e-5) / (simp + 2e-5)), -0.4, 0.4)
            skill -= skill.mean()
    notes.append(f"PGA {event}: {mode}, {m} golfers")
    half = 5.5 / math.sqrt(2)
    r12 = rng.normal(0, half, (N_GOLF, m)) - 2 * skill
    tot = r12 + rng.normal(0, half, (N_GOLF, m)) - 2 * skill
    made = np.ones_like(tot, dtype=bool)
    if m > 65:
        made = r12 <= np.sort(r12, 1)[:, 64:65]
    key = tot + 1000.0 * ~made
    frl = (rng.normal(0, 2.75, (N_GOLF, m)) - skill).argmin(1)
    pos = key.argsort(1).argsort(1)
    for r in rows:
        i, mk = ix[r["player"]], r["market"]
        if mk == "H2H":
            if r.get("team", "") not in ix:
                notes.append(f"  {r['player']} H2H: put the opponent's name in team")
                continue
            j = ix[r["team"]]
            w = float((key[:, i] < key[:, j]).mean())
            emit("PGA", event, mode, r, (f"{r['player']} over {r['team']}", f"{r['team']} over {r['player']}"), w, 1 - w)
            continue
        if mk == "WIN" and mode == "ANCHOR":
            continue                      # fitted to these odds, so no opinion on them
        if mk not in GOLF_NAMES:
            notes.append(f"  {r['player']} {mk}: unknown golf market")
            continue
        top = dict(WIN=1, TOP5=5, TOP10=10, TOP20=20).get(mk)
        if mk == "FRL":
            w = float((frl == i).mean())
        else:
            w = float(made[:, i].mean()) if top is None else float(((pos[:, i] < top) & made[:, i]).mean())
        emit("PGA", event, mode, r, (f"{r['player']} {GOLF_NAMES[mk]}", f"{r['player']} No {GOLF_NAMES[mk]}"), w, 1 - w)

# ---------- board ----------
def num(x):
    x = (x or "").strip().replace("+", "").replace("−", "-")
    return float(x) if x else None

def game_labels(sport, r):
    pre, m = split_market(sport, r["market"])
    pre, ln, home, away = (pre + " " if pre else ""), r["line"], r["home"], r["away"]
    if m == "ML":
        return f"{pre}{home} ML", f"{pre}{away} ML"
    if m == "SPREAD":
        return f"{pre}{home} {ln:+g}", f"{pre}{away} {-ln:+g}"
    if m in ("TOTAL", "HOME_TT", "AWAY_TT"):
        who = "" if m == "TOTAL" else (home if m == "HOME_TT" else away) + " "
        unit = " Rounds" if KIND[sport] == "fight" else ""
        return f"{pre}{who}Over {ln:g}{unit}", f"{pre}{who}Under {ln:g}{unit}"
    if m.startswith(("HOME_BY_", "AWAY_BY_")):
        lo, hi = m[8:].split("_")
        return f"{home if m[0] == 'H' else away} by {lo}-{hi}", "Not " + m
    if m in ("A_INSIDE", "B_INSIDE", "A_DEC", "B_DEC"):
        return f"{home if m[0] == 'A' else away} {'inside distance' if m.endswith('INSIDE') else 'by decision'}", "Not " + m
    if m.startswith("ROUND_"):
        return f"Fight ends in round {m[6:]}", "Not " + m
    name = dict(OT="Overtime", BTTS="Both Teams Score", GTD="Goes The Distance", REG_HOME=f"{home} in Regulation",
                REG_AWAY=f"{away} in Regulation", REG_DRAW="Regulation Draw").get(m, m)
    return f"{name} - Yes", f"{name} - No"

def run(path):
    games, out, notes = {}, [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            if not r.get("market") or not r.get("sport"):
                continue
            r["sport"], r["market"] = r["sport"].upper(), r["market"].upper()
            if r["sport"] not in KIND:
                notes.append(f"unsupported sport: {r['sport']}")
                continue
            r["line"] = num(r.get("line")) or 0.0
            r["hp"], r["ap"], r["proj"] = num(r.get("home_proj")), num(r.get("away_proj")), num(r.get("proj"))
            r["price_a"], r["price_b"] = num(r.get("price_a")), num(r.get("price_b"))
            r["hs"], r["as"], r["rem"] = num(r.get("home_score")), num(r.get("away_score")), num(r.get("remaining"))
            g = games.setdefault((r["sport"], r["home"], r.get("away", "")), dict(lines=[], props=[]))
            g["props" if r.get("player") else "lines"].append(r)

    def emit(sport, game, mode, r, labels, pw, pl, only=None):
        fair = devig_power(implied(r["price_a"]), implied(r["price_b"])) \
            if r["price_a"] and r["price_b"] else (None, None)
        for i, (lab, price, w, l, fp) in enumerate(((labels[0], r["price_a"], pw, pl, fair[0]),
                                                    (labels[1], r["price_b"], pl, pw, fair[1]))):
            if not price:
                continue
            if only is not None and i != only:
                continue
            ev, p = w * payout(price) - l, cond(w, l)
            out.append(dict(sport=sport, game=game, mode=mode, pick=lab, price=int(price),
                            model_p=p, fair_odds=american(p), market_p=fp,
                            edge=(p - fp) if fp is not None else None, ev=ev,
                            score=score(ev), stars=stars(score(ev)), player=r.get("player", ""),
                            bet_type=f"{r['market']}|{i}|{r.get('sgp', '')}"))

    for (sport, home, away), g in games.items():
        kind, rows = KIND[sport], g["lines"]
        if kind == "golf":
            run_golf(home, g["props"], emit, notes)
            continue
        game, seed = f"{away} @ {home}", seed_of(f"{sport}|{home}|{away}")
        if kind == "fight":
            game = f"{home} vs {away}"
            two = [r for r in rows if r["price_a"] and r["price_b"]]
            p = next((r["hp"] for r in rows if r["hp"] is not None), None)
            mode = "PROJECTION"
            if p is None:
                ml = [r for r in two if r["market"] == "ML"]
                p, mode = (fair_a(ml[0]) if ml else None), "ANCHOR"
            if p is None:
                notes.append(f"{sport} {game}: skipped - needs a two-sided ML or home_proj = win probability")
                continue
            sched = int(next((r["line"] for r in rows if r["market"] == "SCHEDULED"), 3))
            hz, tr = 0.206, [r for r in two if r["market"] == "TOTAL"]
            if tr:
                t = min(tr, key=lambda r: abs(fair_a(r) - 0.5))
                fl = math.floor(t["line"])
                hz = bisect(lambda x: fair_a(t) - (1 - x) ** fl * (1 - x * (t["line"] - fl)), 0.001, 0.9, 30)
            S = sim_fight(p, hz, sched, np.random.default_rng(seed), N_SIM)
            notes.append(f"{sport} {game}: {mode} {home} {p * 100:.1f}%, finish chance per round {hz * 100:.0f}%, {sched} rounds")
            for r in rows:
                if r["market"] == "SCHEDULED":
                    continue
                try:
                    emit(sport, game, mode, r, game_labels(sport, r), *wl(diff(S, sport, r["market"], r["line"])))
                except ValueError as e:
                    notes.append(f"  {e}")
            continue

        allr = rows + g["props"]
        cs = next(((r["hs"], r["as"], r["rem"]) for r in rows if r["rem"] is not None), None)
        live = (int(cs[0] or 0), int(cs[1] or 0), min(max(cs[2], 0.02), 1.0)) if cs else (0, 0, 1.0)
        if cs:
            game += " (LIVE)"
        proj = next(((r["hp"], r["ap"]) for r in allr if r["hp"] is not None and r["ap"] is not None), None)
        mode = "PROJECTION"
        if proj is None:
            mode, proj = "ANCHOR", anchor(sport, rows, seed, live)
        S, legs = None, {}
        blocked_sgp = set()  # A withheld ML leg invalidates its quoted combination.

        def add_leg(r, win_a, lose_a, labels):
            if r.get("sgp"):
                b = r.get("side", "").upper() == "B"
                legs.setdefault(r["sgp"], []).append((lose_a if b else win_a, labels[1 if b else 0]))

        if proj is None:
            notes.append(f"{sport} {game}: no game model - needs projections, or a two-sided TOTAL plus ML or SPREAD")
        else:
            hp, ap = proj
            S = simulate(sport, hp, ap, seed, N_SIM, live)
            now = f" | now {home} {live[0]} - {away} {live[1]}, {live[2] * 100:.0f}% left" if cs else ""
            if mode == "PROJECTION":
                bk = anchor(sport, rows, seed, live)
                if bk:
                    now += (f" | book implies {bk[0]:.1f} - {bk[1]:.1f}; projection is "
                            f"{(hp - ap) - (bk[0] - bk[1]):+.1f} on the spread, {(hp + ap) - (bk[0] + bk[1]):+.1f} on the total")
            notes.append(f"{sport} {game}: {mode} full-game pace {home} {hp:.1f} - {away} {ap:.1f} "
                         f"(spread {ap - hp:+.1f}, total {hp + ap:.1f}){now}")
            for r in rows:
                if r["market"] == "SGP":
                    continue
                if cs and (split_market(sport, r["market"])[0] or r["market"].startswith("REG_")):
                    notes.append(f"  {r['market']}: period and regulation markets are not priced live")
                    continue
                try:
                    d = diff(S, sport, r["market"], r["line"])
                except ValueError as e:
                    notes.append(f"  {e}")
                    continue
                only = None
                if r["market"] == "ML" and r["price_a"] and r["price_b"]:
                    spr = next((q for q in rows if q["market"] == "SPREAD"
                                and q["price_a"] and q["price_b"]), None)
                    if spr is not None:
                        bad, (pa, ps) = ml_blocked_sides(r, spr, S)
                        if bad:
                            labs = game_labels(sport, r)
                            for i in sorted(bad):
                                pm, pp = (pa, ps) if i == 0 else (1 - pa, 1 - ps)
                                notes.append(f"  {labs[i]}: WITHHELD (ML_SPREAD_INCONSISTENT)"
                                             f" - book ML no-vig {pm * 100:.2f}% vs book"
                                             f" spread-implied {pp * 100:.2f}%"
                                             f" (rel gap {abs(pm - pp) / pp * 100:.0f}% > {ML_TOL * 100:.0f}%)")
                            only = -1 if len(bad) == 2 else 1 - next(iter(bad))
                if r.get("sgp") and only is not None:
                    sgp_side = 1 if r.get("side", "").upper() == "B" else 0
                    if sgp_side != only:
                        blocked_sgp.add(r["sgp"])
                if r.get("sgp") not in blocked_sgp:
                    add_leg(r, d > 0, d < 0, game_labels(sport, r))
                if only != -1:
                    emit(sport, game, mode, r, game_labels(sport, r), *wl(d), only=only)

        players = {}
        for r in ([] if cs else g["props"]):
            players.setdefault((r["player"], r["market"]), []).append(r)
        if cs and g["props"]:
            notes.append("  player props are not priced live")
        for (player, stat), prs in players.items():
            team = prs[0].get("team", "")
            prng = np.random.default_rng(seed_of(f"{game}|{player}|{stat}|sgp"))
            if stat in TD_NAMES:
                share = next((r["proj"] for r in prs if r["proj"] is not None), None)
                if S is None or "htd" not in S or share is None or team not in (home, away):
                    notes.append(f"  {player} {stat}: skipped - needs a football game model, team, and proj = TD share")
                    continue
                labels = (f"{player} {TD_NAMES[stat]}", f"{player} No {TD_NAMES[stat]}")
                for r in prs:
                    emit(sport, game, "PROJECTION", r, labels, *td_probs(S, stat, share, team == home))
                    if r.get("sgp") and stat != "FTD":
                        x = prng.binomial(S["htd"] if team == home else S["atd"], share)
                        hit = x >= (1 if stat == "ATD" else 2)
                        add_leg(r, hit, ~hit, labels)
                continue
            spec = PROPS[kind].get(stat)
            if spec is None:
                notes.append(f"  {player} {stat}: unknown prop market for {sport}")
                continue
            ps = seed_of(f"{game}|{player}|{stat}")
            mean = next((r["proj"] for r in prs if r["proj"] is not None), None)
            pmode = "PROJECTION"
            if mean is None:
                two = [r for r in prs if r["price_a"] and r["price_b"]]
                if not two:
                    notes.append(f"  {player} {stat}: skipped - needs proj or a two-sided line")
                    continue
                fit = min(two, key=lambda r: abs(fair_a(r) - 0.5))
                mean = bisect(lambda x: cond(*stat_probs(spec, x, fit["line"], ps)) - fair_a(fit),
                              0.02, fit["line"] * 3 + 5, 24)
                pmode = "ANCHOR"
            notes.append(f"  {player} {stat}: {pmode} mean {mean:.2f}")
            name = stat.replace("_", " ").title()
            for r in prs:
                labels = (f"{player} Over {r['line']:g} {name}", f"{player} Under {r['line']:g} {name}")
                emit(sport, game, pmode, r, labels, *stat_probs(spec, mean, r["line"], ps))
                if r.get("sgp") and S is not None:
                    f = np.ones(N_SIM)
                    if team in (home, away) and stat not in NO_SCRIPT:
                        sc = (S["h"] if team == home else S["a"]).astype(float)
                        f = np.sqrt(np.maximum(sc, 0) / max(sc.mean(), 1e-9))
                        f = f / f.mean()
                    x = prop_sample(spec, mean, f, prng)
                    add_leg(r, x > r["line"], x < r["line"], labels)

        for r in rows:
            if r["market"] == "SGP":
                if r.get("sgp") in blocked_sgp:
                    notes.append(f"  SGP {r.get('sgp', '')}: WITHHELD (ML_SPREAD_INCONSISTENT leg)")
                    continue
                ls = legs.get(r.get("sgp", ""))
                if not ls or len(ls) < 2:
                    notes.append(f"  SGP {r.get('sgp', '')}: needs 2+ priced legs with the same sgp id")
                    continue
                w = float(np.all([x[0] for x in ls], 0).mean())
                emit(sport, game, mode, r, ("SGP: " + " + ".join(x[1] for x in ls), ""), w, 1 - w)

    out.sort(key=lambda x: -x["ev"])
    print("\n".join(notes), "\n")
    groups = {}
    for o in out:                          # out is sorted by EV, best first
        if o["ev"] < EV_FLOOR or (PRICE_CAP is not None and o["price"] < PRICE_CAP):
            continue
        key = (o["sport"], o["game"], o["player"] or o["bet_type"])
        groups.setdefault(key, []).append(o)
    card, doubted = [], []
    for rows_ in groups.values():          # one row per bet type (or player) per game:
        solid = [o for o in rows_ if o["model_p"] >= 0.20]     # best EV, preferring non-longshot rungs
        pick = (solid or rows_)[0]
        pick["also"] = len(rows_) - 1
        (doubted if pick["ev"] >= DOUBT_EV else card).append(pick)
    card.sort(key=lambda x: -x["ev"])
    doubted.sort(key=lambda x: -x["ev"])

    def table(rows):
        print("| # | Game | Pick | Price | Model % | Fair | Edge | EV | Score | Stars |")
        print("|---|------|------|-------|---------|------|------|----|-------|-------|")
        for i, o in enumerate(rows, 1):
            edge = f"{o['edge'] * 100:+.1f}%" if o["edge"] is not None else "-"
            more = f" (+{o['also']} other numbers)" if o["also"] else ""
            print(f"| {i} | {o['sport']} {o['game']} | {o['pick']}{more} | {o['price']:+d} | {o['model_p'] * 100:.1f}% | "
                  f"{o['fair_odds']:+d} | {edge} | {o['ev'] * 100:+.1f}% | {o['score']} | {'*' * o['stars']} |")

    print(f"CARD ({len(card)}) - ranked by EV, every sport and market (best number per bet type per game)\n")
    table(card)
    if doubted:
        print(f"\nMODEL-DOUBTED ({len(doubted)}) - EV 40%+, check the price and inputs before trusting\n")
        table(doubted)
    for o in out:
        o.pop("also", None)
    with open("picks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ["pick"])
        w.writeheader()
        w.writerows(out)
    print(f"\nAll {len(out)} priced sides saved to picks.csv")
    return out

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "board.csv")
