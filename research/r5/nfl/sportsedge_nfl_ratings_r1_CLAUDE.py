#!/usr/bin/env python3
"""SportsEdge NFL ratings r1 -- PROVISIONAL_ESTIMATE / PAPER 0u. numpy + stdlib only.

Own NFL score projections from completed game RESULTS ONLY. No sportsbook lines, no
market-implied numbers, no outside power ratings. Strict point-in-time: a fit "as of D"
uses only games dated strictly before D.

Model (same family as the SportsEdge football ratings, one league):
  points(team T vs opp O) = LG + off_T - def_O + (+/- hfa/2 if not neutral)
  def > 0 means a GOOD defense (it removes points from the opponent).
  Weighted ridge least squares, each game = 2 observations, recency weight
  0.5 ** (age_days / HALF_LIFE). HFA is fitted but shrunk to a prior. LG = weighted mean points.
  Win probability = Normal(margin / SD).  Spread/total are the projected margin / sum.

QB / injuries: NO automatic source. Optional --qb file (team,adj_pts,status,source,info_ct);
only CONFIRMED or PROBABLE rows with a source and info_ct <= capture time are applied;
RUMOR/other rows are listed and ignored. Default: none applied (flagged on the card).

Missing by design (needs data we do not have here): prior-season results / preseason priors,
play-level efficiency (EPA, success rate), injuries. Scoring efficiency enters only through
points per game. These limits are printed on every card.

CLI
  python sportsedge_nfl_ratings_r1.py fit  games.csv --asof 2026-11-10 --out nfl_ratings.csv
  python sportsedge_nfl_ratings_r1.py scores nfl_ratings.csv --board board.csv --slate SLATE.csv \
        --asof-ct 2026-11-10T00:00:00-06:00 [--captured-ct 2026-11-12T18:08:00-06:00] \
        [--qb qb.csv] --out-dir out
  python sportsedge_nfl_ratings_r1.py backtest games.csv --start 2026-10-04 [--ridge 5 --half-life 45]
games.csv: sport,date,home,away,home_pts,away_pts,neutral
"""
import csv, sys, math, hashlib, json, datetime as dt
from pathlib import Path
import numpy as np

try:
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
except Exception:                       # pragma: no cover
    CT = None

MODEL_VERSION = "SPORTSEDGE_NFL_RIDGE_R1"
PARAMS = dict(half_life=45.0, ridge=5.0, hfa_prior=1.6, hfa_w=40.0, sd=13.5)
PROJ_COLUMNS = ("sport", "home", "away", "home_proj", "away_proj", "asof_ct", "start_ct",
                "model_version", "source_file_sha256")
LIMITS = ("2026 season-to-date results only (no prior seasons/preseason priors); "
          "points-based (no EPA/success-rate); no automatic QB/injury feed")


def ncdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def key(*xs):
    return tuple(" ".join(x.casefold().split()) for x in xs)


def load_games(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        if r["sport"].upper() != "NFL":
            continue
        out.append(dict(date=dt.date.fromisoformat(r["date"]), home=r["home"], away=r["away"],
                        hp=float(r["home_pts"]), ap=float(r["away_pts"]),
                        neutral=(r.get("neutral") or "0").strip() == "1"))
    return out


def fit(games, asof, half_life=None, ridge=None, hfa_prior=None, hfa_w=None):
    p = PARAMS
    half_life = p["half_life"] if half_life is None else half_life
    ridge = p["ridge"] if ridge is None else ridge
    hfa_prior = p["hfa_prior"] if hfa_prior is None else hfa_prior
    hfa_w = p["hfa_w"] if hfa_w is None else hfa_w
    g = [x for x in games if x["date"] < asof]
    if not g:
        raise ValueError("NO_GAMES_BEFORE_ASOF")
    teams = sorted({x["home"] for x in g} | {x["away"] for x in g})
    ix = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    rows, ys, ws = [], [], []
    allw = allp = 0.0
    for x in g:
        w = 0.5 ** ((asof - x["date"]).days / half_life)
        allw += 2 * w
        allp += w * (x["hp"] + x["ap"])
    lg = allp / allw
    for x in g:
        w = 0.5 ** ((asof - x["date"]).days / half_life)
        site = 0.0 if x["neutral"] else 1.0
        for t, o, pts, s in ((x["home"], x["away"], x["hp"], site), (x["away"], x["home"], x["ap"], -site)):
            r = np.zeros(2 * n + 1)
            r[ix[t]] = 1.0
            r[n + ix[o]] = -1.0
            r[2 * n] = 0.5 * s
            rows.append(r); ys.append(pts - lg); ws.append(w)
    A = np.array(rows); y = np.array(ys); W = np.array(ws)
    R = np.zeros((2 * n + 1, 2 * n + 1))
    R[np.arange(2 * n), np.arange(2 * n)] = ridge
    R[2 * n, 2 * n] = hfa_w
    rhs = A.T @ (W * y)
    rhs[2 * n] += hfa_w * hfa_prior
    x_ = np.linalg.solve(A.T @ (A * W[:, None]) + R, rhs)
    gp = {t: 0 for t in teams}
    for x in g:
        gp[x["home"]] += 1; gp[x["away"]] += 1
    res = []
    for x in g:
        site = 0.0 if x["neutral"] else 1.0
        mh = lg + x_[ix[x["home"]]] - x_[n + ix[x["away"]]] + 0.5 * site * x_[2 * n]
        ma = lg + x_[ix[x["away"]]] - x_[n + ix[x["home"]]] - 0.5 * site * x_[2 * n]
        res.append((x["hp"] - x["ap"]) - (mh - ma))
    return dict(lg=float(lg), hfa=float(x_[2 * n]), asof=asof.isoformat(), n_games=len(g),
                half_life=half_life, ridge=ridge, insample_margin_sd=float(np.std(res, ddof=1)),
                teams={t: dict(off=float(x_[ix[t]]), dfn=float(x_[n + ix[t]]), gp=gp[t]) for t in teams})


def project(R, home, away, neutral=False, qb_home=0.0, qb_away=0.0):
    h, a = R["teams"].get(home), R["teams"].get(away)
    if h is None or a is None:
        return None
    s = 0.0 if neutral else 0.5 * R["hfa"]
    hp = R["lg"] + h["off"] - a["dfn"] + s + qb_home
    ap = R["lg"] + a["off"] - h["dfn"] - s + qb_away
    return max(hp, 3.0), max(ap, 3.0)


def write_ratings(R, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["team", "off", "def", "gp", "lg", "hfa", "asof", "half_life", "ridge"])
        for t in sorted(R["teams"]):
            v = R["teams"][t]
            w.writerow([t, f"{v['off']:.4f}", f"{v['dfn']:.4f}", v["gp"], f"{R['lg']:.4f}",
                        f"{R['hfa']:.4f}", R["asof"], R["half_life"], R["ridge"]])


def load_ratings(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    r0 = rows[0]
    return dict(lg=float(r0["lg"]), hfa=float(r0["hfa"]), asof=r0["asof"],
                teams={r["team"]: dict(off=float(r["off"]), dfn=float(r["def"]), gp=int(r["gp"])) for r in rows})


def _ct(s):
    return dt.datetime.fromisoformat(s)


def _slate_start(slate_path):
    out = {}
    for r in csv.DictReader(open(slate_path, encoding="utf-8-sig")):
        if r["sport"].upper() == "NFL":
            t = dt.datetime.strptime(r["start_ct"].strip(), "%Y-%m-%d %H:%M").replace(tzinfo=CT)
            out[key(r["away"], r["home"])] = t.isoformat()
    return out


def load_qb(path, captured_ct):
    used, ignored = {}, []
    if not path:
        return used, ignored
    cap = _ct(captured_ct) if captured_ct else None
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        st = (r.get("status") or "").strip().upper()
        ok = st in ("CONFIRMED", "PROBABLE") and (r.get("source") or "").strip() and (r.get("info_ct") or "").strip()
        if ok:
            try:
                ok = cap is not None and _ct(r["info_ct"]) <= cap
            except ValueError:
                ok = False
        if ok:
            used[r["team"]] = used.get(r["team"], 0.0) + float(r["adj_pts"])
        else:
            ignored.append(dict(team=r.get("team"), status=st, reason="STATUS_SOURCE_OR_TIME_INVALID"))
    return used, ignored


def make_scores(ratings_path, board_path, slate_path, asof_ct, out_dir, captured_ct=None, qb_path=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    R = load_ratings(ratings_path)
    src = sha256_file(ratings_path)
    starts = _slate_start(slate_path)
    qb, qb_ign = load_qb(qb_path, captured_ct)
    games, seen = [], set()
    for r in csv.DictReader(open(board_path, encoding="utf-8-sig")):
        k = key(r["sport"], r["home"], r["away"])
        if k not in seen:
            seen.add(k); games.append((r["sport"], r["home"], r["away"]))
    proj, card, problems = [], [], []
    for sport, home, away in games:
        st = starts.get(key(away, home))
        pj = project(R, home, away, False, qb.get(home, 0.0), qb.get(away, 0.0))
        if st is None:
            problems.append(f"NO_START_TIME:{away}@{home}")
        if pj is None:
            problems.append(f"TEAM_NOT_RATED:{away}@{home}")
        if st is None or pj is None:
            continue
        hp, ap = pj
        proj.append(dict(sport=sport, home=home, away=away, home_proj=f"{hp:.3f}", away_proj=f"{ap:.3f}",
                         asof_ct=asof_ct, start_ct=st, model_version=MODEL_VERSION, source_file_sha256=src))
        m = hp - ap
        card.append(dict(home=home, away=away, home_proj=f"{hp:.1f}", away_proj=f"{ap:.1f}",
                         proj_margin_home=f"{m:+.1f}", proj_total=f"{hp + ap:.1f}",
                         home_win_prob=f"{ncdf(m / PARAMS['sd']):.3f}",
                         qb_adjustment_home=f"{qb.get(home, 0.0):+.1f}", qb_adjustment_away=f"{qb.get(away, 0.0):+.1f}",
                         qb_info="NONE_SUPPLIED" if not qb_path else "FILE_APPLIED",
                         limits=LIMITS))
    with open(out / "nfl_scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PROJ_COLUMNS, lineterminator="\n")
        w.writeheader(); w.writerows(proj)
    with open(out / "nfl_projection_card.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(card[0].keys()) if card else ["empty"], lineterminator="\n")
        w.writeheader(); w.writerows(card)
    rep = dict(model_version=MODEL_VERSION, status="PROVISIONAL_ESTIMATE_PAPER_0U_NOT_PRICED",
               ratings_sha256=src, asof_ct=asof_ct, games=len(proj), problems=problems,
               qb_applied=qb, qb_ignored=qb_ign, limits=LIMITS)
    (out / "nfl_scores_report.json").write_text(json.dumps(rep, indent=2) + "\n")
    return rep


# ---------------- walk-forward backtest ----------------
def _noadj(games, asof, ridge):
    g = [x for x in games if x["date"] < asof]
    lg = np.mean([v for x in g for v in (x["hp"], x["ap"])])
    pf, pa, gp = {}, {}, {}
    for x in g:
        for t, a, b in ((x["home"], x["hp"], x["ap"]), (x["away"], x["ap"], x["hp"])):
            pf[t] = pf.get(t, 0) + a; pa[t] = pa.get(t, 0) + b; gp[t] = gp.get(t, 0) + 1
    return lg, {t: ((pf[t] - gp[t] * lg) / (gp[t] + ridge), (gp[t] * lg - pa[t]) / (gp[t] + ridge)) for t in gp}


def backtest(games, start, **kw):
    P = dict(PARAMS); P.update({k: v for k, v in kw.items() if v is not None})
    dates = sorted({x["date"] for x in games if x["date"] >= start})
    rec = {m: dict(mg=[], tt=[], p=[], y=[]) for m in ("model", "noadj", "const")}
    for d in dates:
        try:
            R = fit(games, d, P["half_life"], P["ridge"], P["hfa_prior"], P["hfa_w"])
        except ValueError:
            continue
        lg0, na = _noadj(games, d, P["ridge"])
        for x in [x for x in games if x["date"] == d]:
            m, t = x["hp"] - x["ap"], x["hp"] + x["ap"]
            site = 0.0 if x["neutral"] else 1.0
            out = {}
            pj = project(R, x["home"], x["away"], x["neutral"])
            if pj: out["model"] = pj
            if x["home"] in na and x["away"] in na:
                s = 0.5 * P["hfa_prior"] * site
                out["noadj"] = (lg0 + na[x["home"]][0] - na[x["away"]][1] + s, lg0 + na[x["away"]][0] - na[x["home"]][1] - s)
            out["const"] = (lg0 + 0.5 * P["hfa_prior"] * site, lg0 - 0.5 * P["hfa_prior"] * site)
            if "model" not in out or "noadj" not in out:
                continue
            for name, (hp, ap) in out.items():
                r = rec[name]
                r["mg"].append((hp - ap) - m); r["tt"].append((hp + ap) - t)
                if x["hp"] != x["ap"]:
                    r["p"].append(min(max(ncdf((hp - ap) / P["sd"]), 1e-4), 1 - 1e-4))
                    r["y"].append(1.0 if x["hp"] > x["ap"] else 0.0)
    res = {}
    for name, r in rec.items():
        if not r["mg"]:
            continue
        mg, tt = np.array(r["mg"]), np.array(r["tt"]); p, y = np.array(r["p"]), np.array(r["y"])
        res[name] = dict(n=len(mg), margin_mae=float(np.mean(np.abs(mg))), margin_rmse=float(np.sqrt(np.mean(mg ** 2))),
                         total_mae=float(np.mean(np.abs(tt))), brier=float(np.mean((p - y) ** 2)),
                         logloss=float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
                         acc=float(np.mean((p > 0.5) == (y == 1))), home_rate=float(y.mean()))
    return res


def main(argv):
    if len(argv) < 2:
        print(__doc__); return
    cmd = argv[0]
    opt = lambda f, d=None: argv[argv.index(f) + 1] if f in argv else d
    if cmd == "fit":
        R = fit(load_games(argv[1]), dt.date.fromisoformat(opt("--asof")), half_life=float(opt("--half-life", PARAMS["half_life"])),
                ridge=float(opt("--ridge", PARAMS["ridge"])))
        write_ratings(R, opt("--out", "nfl_ratings.csv"))
        print(f"{len(R['teams'])} teams, {R['n_games']} games as of {R['asof']}, lg={R['lg']:.2f}, hfa={R['hfa']:.2f}, "
              f"in-sample margin sd={R['insample_margin_sd']:.2f}")
    elif cmd == "scores":
        rep = make_scores(argv[1], opt("--board"), opt("--slate"), opt("--asof-ct"), opt("--out-dir", "out"),
                          opt("--captured-ct"), opt("--qb"))
        print(json.dumps(rep, indent=2))
    elif cmd == "backtest":
        res = backtest(load_games(argv[1]), dt.date.fromisoformat(opt("--start", "2026-10-04")),
                       half_life=float(opt("--half-life")) if opt("--half-life") else None,
                       ridge=float(opt("--ridge")) if opt("--ridge") else None)
        for k, v in res.items():
            print(f"{k:6s} n={v['n']} margin MAE {v['margin_mae']:.2f} RMSE {v['margin_rmse']:.2f} total MAE {v['total_mae']:.2f} "
                  f"Brier {v['brier']:.4f} logloss {v['logloss']:.4f} acc {v['acc']:.3f}")
        if res:
            hr = next(iter(res.values()))["home_rate"]
            print(f"home win rate {hr:.3f}; coin Brier 0.2500; base-rate Brier {hr * (1 - hr):.4f}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
