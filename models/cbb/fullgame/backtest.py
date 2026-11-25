"""Rolling-origin (daily walk-forward) multi-season driver for the full-game engines. RESEARCH ONLY.

Stage 1: a season-final schedule-adjusted fit per season (D1 only) -> preseason prior for season+1.
Stage 2: per season, every engine forecasts each game from strictly-earlier dates only. FG1 uses the
prior built from season-1's final fit; its hyper-parameters are chosen on TUNE seasons only.
Output: one JSON per (season, config) under --out. No odds are used here.
"""
from __future__ import annotations
import argparse
import json
from datetime import timedelta
from pathlib import Path

from . import ratings as R
from . import sdv_loader as L

TUNE = (2020, 2021, 2022)
EVAL = (2023, 2024, 2025, 2026, 2027)
DEFAULT_FG1 = {"carry": 0.6, "carry_pace": 0.7, "lam": 6.0, "lam_pace": 4.0, "half_life": 60.0, "hca_lam": 400.0}


def season_final(games):
    gs = [g for g in games if R.usable(g)]
    f = R.AdjustedFit(lam=2.0, lam_pace=2.0, iters=40)
    end = R._d(max(g["date"] for g in gs)) + timedelta(days=1)
    f.fit(gs, end)
    return f.final_state()


def fg1_config(prev_final, hca_hist, params):
    prior, new_team = R.make_prior(prev_final, params["carry"], params["carry_pace"])
    return {"prior": prior, "new_team": new_team, "lam": params["lam"], "lam_pace": params["lam_pace"],
            "half_life": params["half_life"], "hca_prior": hca_hist, "hca_lam": params["hca_lam"],
            "mu0": prev_final[1], "pi0": prev_final[2]}


def run_season(args):
    season, games_dir, finals, params, engines, tag = args
    games = L.read_csv(Path(games_dir) / f"games_{season}.csv")
    priors = {}
    prev = finals.get(season - 1)
    hist = [finals[s][3] for s in finals if s < season]
    if prev is not None and "FG1" in engines:
        priors["FG1"] = fg1_config(prev, sum(hist) / len(hist), params)
    eng = [e for e in engines if e != "FG1" or "FG1" in priors]
    out, _ = R.walk_forward(games, eng, priors=priors)
    return season, tag, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seasons", nargs="+", type=int, default=list(range(2020, 2028)))
    ap.add_argument("--engines", nargs="+", default=["RAW", "REG", "NATIVE_RECON", "SA", "FG1"])
    ap.add_argument("--params", default=json.dumps(DEFAULT_FG1))
    ap.add_argument("--tag", default="base")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fpath = out / "season_finals.json"
    if fpath.exists():
        finals = {int(k): (v[0], v[1], v[2], v[3]) for k, v in json.loads(fpath.read_text()).items()}
    else:
        finals = {}
        for s in range(min(a.seasons) - 1, max(a.seasons)):
            p = Path(a.games) / f"games_{s}.csv"
            if p.exists():
                finals[s] = season_final(L.read_csv(p))
                print("final", s, round(finals[s][1], 2), round(finals[s][2], 2), round(finals[s][3], 3), flush=True)
        fpath.write_text(json.dumps({str(k): v for k, v in finals.items()}))
    params = json.loads(a.params)
    from multiprocessing import Pool
    jobs = [(s, a.games, finals, params, a.engines, a.tag) for s in a.seasons]
    with Pool(a.jobs) as pool:
        for season, tag, rows in pool.imap_unordered(run_season, jobs):
            (out / f"wf_{tag}_{season}.json").write_text(json.dumps(rows))
            print("done", tag, season, len(rows), flush=True)


if __name__ == "__main__":
    main()
