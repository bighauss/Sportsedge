"""Convert full-game walk-forward JSON (PR #534 / models/cbb/fullgame) into a projections CSV
the halves refit can read (PAPER/0u, NON_COUNTED).

Expected input: a directory of ``wf_<tag>_<season>.json`` files as written by
``models.cbb.fullgame.backtest``, each row having ``game_id``, ``n_home``, ``n_away`` and
``f.<engine>.{home_points, away_points, possessions}``.

Optionally applies the same chronological early/late linear de-bias that produces FG1C
(coefficients for season S are fit on seasons < S only; 2026 can be excluded with
``--train-until 2025`` so it is never used to form the 2026 de-bias, and is omitted
from the output when ``--seasons`` stops at 2025).

This script does not import or copy the fullgame package; it only reads the published JSON.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

EARLY_N = 5


def _mean(xs):
    return sum(xs) / len(xs)


def _ols(x, y):
    mx, my = _mean(x), _mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx if sxx else 1.0
    return my - b * mx, b


def fit_recal(rows, eng, min_rows=300):
    out = {}
    for grp, pred in (("early", lambda n: n < EARLY_N), ("late", lambda n: n >= EARLY_N)):
        rs = [r for r in rows if eng in r.get("f", {}) and pred(min(r["n_home"], r["n_away"]))]
        if len(rs) < min_rows:
            return None
        out[grp] = {
            "margin": _ols([r["f"][eng]["margin"] for r in rs],
                           [r["home_points"] - r["away_points"] for r in rs]),
            "total": _ols([r["f"][eng]["total"] for r in rs],
                          [r["home_points"] + r["away_points"] for r in rs]),
            "n": len(rs),
        }
    return out


def apply_recal(f, coef, n_min):
    c = coef["early" if n_min < EARLY_N else "late"]
    m = c["margin"][0] + c["margin"][1] * f["margin"]
    t = c["total"][0] + c["total"][1] * f["total"]
    return {"home_points": (t + m) / 2, "away_points": (t - m) / 2, "margin": m, "total": t,
            "possessions": f.get("possessions")}


def load_wf(directory, tag, seasons, engine):
    by = {}
    for s in seasons:
        p = Path(directory) / f"wf_{tag}_{s}.json"
        if not p.exists():
            p = Path(directory) / f"{tag}_{s}.json"
        if not p.exists():
            raise SystemExit(f"missing walk-forward file for season {s}: tried {p}")
        rows = json.loads(p.read_text())
        by[s] = rows
        n = sum(1 for r in rows if engine in r.get("f", {}))
        print(f"loaded {p.name}: {len(rows)} rows, {n} with {engine}", flush=True)
    return by


def add_recal(by_season, eng, train_until, min_prior=2):
    """Add eng+'C' using only seasons <= train_until as prior data, and only seasons < S for season S."""
    new = eng + "C"
    coefs = {}
    for s in sorted(by_season):
        prior = [r for p, rs in by_season.items() if p < s and p <= train_until for r in rs]
        n_prior_seasons = len({p for p in by_season if p < s and p <= train_until})
        if n_prior_seasons < min_prior:
            continue
        c = fit_recal(prior, eng)
        if c is None:
            continue
        coefs[s] = c
        for r in by_season[s]:
            if eng in r.get("f", {}):
                r["f"][new] = apply_recal(r["f"][eng], c, min(r["n_home"], r["n_away"]))
    return coefs


def write_csv(by_season, engine, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["game_id", "season", "proj_home", "proj_away",
                                           "proj_poss", "n_home", "n_away", "engine"])
        w.writeheader()
        for s, rows in sorted(by_season.items()):
            for r in rows:
                f = r.get("f", {}).get(engine)
                if not f:
                    continue
                w.writerow({"game_id": int(r["game_id"]), "season": int(r.get("season", s)),
                            "proj_home": f["home_points"], "proj_away": f["away_points"],
                            "proj_poss": f.get("possessions") if f.get("possessions") is not None else "",
                            "n_home": r.get("n_home", ""), "n_away": r.get("n_away", ""),
                            "engine": engine})
                n += 1
    print(f"wrote {n} rows to {dest}")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf-dir", required=True, help="directory of wf_<tag>_<season>.json files")
    ap.add_argument("--tag", default="fg1t")
    ap.add_argument("--engine", default="FG1", help="engine key inside each row's f object")
    ap.add_argument("--debias", action="store_true",
                    help="apply chronological FG1C-style de-bias and emit the C engine")
    ap.add_argument("--train-until", type=int, default=2025,
                    help="last season allowed in any de-bias training window (default 2025: 2026 unused)")
    ap.add_argument("--seasons", default="2020-2025")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if "-" in a.seasons:
        lo, hi = (int(x) for x in a.seasons.split("-"))
        seasons = list(range(lo, hi + 1))
    else:
        seasons = [int(x) for x in a.seasons.split(",")]
    if max(seasons) > a.train_until and a.debias:
        # still allowed to *emit* later seasons, but they must not enter training
        pass
    by = load_wf(a.wf_dir, a.tag, seasons, a.engine)
    engine = a.engine
    if a.debias:
        add_recal(by, a.engine, a.train_until)
        engine = a.engine + "C"
        # drop any season whose C forecasts would have required 2026+ in the prior? already guarded.
    write_csv(by, engine, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
