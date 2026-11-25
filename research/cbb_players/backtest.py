"""Rolling-origin backtest of the CBB matchup player-prop model vs PR #519.

PAPER/0u, NON_COUNTED research. Public sportsdataverse ESPN player boxes and
schedules (seasons labelled by spring year). No historical sportsbook prop
odds are admitted anywhere in this repository, so there is NO ROI/CLV here:
lines are (a) the #519 fixed diagnostic half-lines, (b) a preregistered
DK-style "N+" milestone ladder, and (c) a prior-mean-centred line
N = floor(#519 native_5 mean) + 1 chosen from #519 information only.

Origins: every Monday of each evaluated season. Parameters are refit at each
origin on feature rows dated <= origin - 2 days within the preceding 365 days
(earlier season included); forecasts cover [origin, origin + 7 days).
Features obey the #519 two-day lag and eligibility (>=5 prior same-team
appearances in the last 8, distinct dates).
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "models" / "cbb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from players import distributions as D                        # noqa: E402
from players import features as F                             # noqa: E402
from players.fit import fit                                    # noqa: E402
from players.model import FAMILIES, predictive                 # noqa: E402
from research import cbb_player_distribution as PR519          # noqa: E402

LADDERS = {"POINTS": (8, 10, 12, 15, 18, 20), "REBOUNDS": (3, 4, 5, 6, 8, 10),
           "ASSISTS": (2, 3, 4, 5, 6), "THREES": (1, 2, 3, 4), "PRA": (15, 20, 25, 30),
           "PR": (10, 15, 20, 25), "PA": (10, 15, 20, 25), "RA": (5, 8, 10)}
EPS = 1e-6
COPULA_MOD = 20          # deterministic 1-in-20 subsample for the copula comparison
COPULA_DRAWS = 2000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finals(schedule_path):
    import pyarrow.parquet as pq
    t = pq.read_table(schedule_path, columns=["game_id", "status_type_name"]).to_pylist()
    return {str(r["game_id"]) for r in t if r["status_type_name"] == "STATUS_FINAL"}


def actual_of(row, fam):
    a = row["actual"]
    if fam in F.COMBOS:
        return sum(a[p] for p in F.COMBOS[fam])
    return a[fam]


def values_of(row, fam):
    rv = row["recent_values"]
    if fam in F.COMBOS:
        return [sum(t) for t in zip(*(rv[p] for p in F.COMBOS[fam]))]
    return rv[fam]


def baseline_pmf(vals):
    """#519 negative-binomial family: moments of the same 5-8 prior values."""
    n = len(vals)
    m = sum(vals) / n
    v = sum((x - m) ** 2 for x in vals) / (n - 1)
    return D.nb_pmf(m, D.moment_alpha(m, v))


def clip(p):
    return min(1 - EPS, max(EPS, p))


def score_row(row, params, *, copula=False):
    pred = predictive(row, params)
    ind = predictive(row, params, combo="independent")
    cop = predictive(row, params, combo="copula", copula_draws=COPULA_DRAWS,
                     seed=int(row["game_id"]) % 100000) if copula else None
    out = {"day": row["day"], "game_id": row["game_id"], "player_id": row["player_id"],
           "minutes": (row["proj_minutes"], row["recent_mean_minutes"], row["actual"]["MINUTES"]),
           "fam": {}}
    for fam in FAMILIES:
        y = actual_of(row, fam)
        vals = values_of(row, fam)
        bpmf = baseline_pmf(vals)
        native5 = (sum(row["native5"][p] for p in F.COMBOS[fam]) if fam in F.COMBOS
                   else row["native5"][fam])
        roll8 = sum(vals) / len(vals)
        rel = int(math.floor(native5)) + 1
        models = {"model": pred[fam]["pmf"], "pr519_nb": bpmf}
        if fam in F.COMBOS:
            models["model_independent"] = ind[fam]["pmf"]
            if cop:
                models["model_copula"] = cop[fam]["pmf"]
        rec = {"y": y, "mean": {"model": pred[fam]["mean"], "native_5": native5, "rolling_8": roll8},
               "crps": {k: D.crps_discrete(p, y) for k, p in models.items()},
               "ladder": {}, "rel": {}}
        for n in LADDERS[fam]:
            rec["ladder"][n] = {k: D.prob_at_least(p, n) for k, p in models.items()}
        rec["rel"] = {"n": rel, "p": {k: D.prob_at_least(p, rel) for k, p in models.items()}}
        if fam in PR519.LINES:
            line = PR519.LINES[fam]
            q = PR519.predict(vals, line)
            rec["fixed"] = {"line": line, "p": {"model": 1 - math.fsum(pred[fam]["pmf"][: math.floor(line) + 1]),
                                                **{"pr519_" + f: q["p_over"][f] for f in PR519.FAMILIES}}}
        out["fam"][fam] = rec
    return out


def run_season(season, root, prior_root_season=None):
    apps, tg, census = F.load_player_box(root / f"player_box_{season}.csv",
                                         final_game_ids=finals(root / f"mbb_schedule_{season}.parquet"))
    prior = None
    if prior_root_season and (root / f"player_box_{prior_root_season}.csv").exists():
        papps, _, _ = F.load_player_box(root / f"player_box_{prior_root_season}.csv",
                                        final_game_ids=finals(root / f"mbb_schedule_{prior_root_season}.parquet"))
        prior = F.prior_season_rates(papps)
    rows, holds = F.walk_season(apps, tg, prior)
    for r in rows:
        r["season"] = season
    return rows, {"census": census, "holds": holds, "feature_rows": len(rows)}


def mondays(first, last):
    d = first - timedelta(days=first.weekday())
    while d <= last:
        yield d
        d += timedelta(days=7)


def brier_ll(ps, ys):
    b = sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)
    ll = -sum(y * math.log(clip(p)) + (1 - y) * math.log(1 - clip(p)) for p, y in zip(ps, ys)) / len(ys)
    return b, ll


def reliability(ps, ys, bins=10):
    g = defaultdict(list)
    for p, y in zip(ps, ys):
        g[min(bins - 1, int(p * bins))].append((p, y))
    tab = [{"bin": k, "n": len(v), "mean_p": sum(x for x, _ in v) / len(v),
            "observed": sum(y for _, y in v) / len(v)} for k, v in sorted(g.items())]
    ece = sum(t["n"] * abs(t["mean_p"] - t["observed"]) for t in tab) / len(ps)
    return tab, ece


def week_ci(days, deltas, draws=1000, seed=57):
    blocks = defaultdict(list)
    for d, x in zip(days, deltas):
        blocks[date.fromisoformat(d).isocalendar()[:2]].append(x)
    bl = [(sum(v), len(v)) for v in blocks.values()]
    if len(bl) < 2:
        return None, len(bl)
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        s = rng.choices(bl, k=len(bl))
        out.append(sum(a for a, _ in s) / sum(n for _, n in s))
    out.sort()
    return [out[int(.025 * draws)], out[int(.975 * draws)]], len(bl)


def summarize(scored):
    res = {"n_rows": len(scored)}
    mins = [s["minutes"] for s in scored]
    res["minutes"] = {"n": len(mins),
                      "mae_projection": sum(abs(a - c) for a, _, c in mins) / len(mins),
                      "mae_recent_mean": sum(abs(b - c) for _, b, c in mins) / len(mins),
                      "bias_projection": sum(a - c for a, _, c in mins) / len(mins)}
    fams = {}
    for fam in FAMILIES:
        recs = [(s["day"], s["fam"][fam]) for s in scored]
        days = [d for d, _ in recs]
        rr = [r for _, r in recs]
        ys = [r["y"] for r in rr]
        f = {"n": len(rr), "mean_actual": sum(ys) / len(ys), "point": {}, "crps": {}, "ladder": {},
             "relative_line": {}, "fixed_line": {}}
        for m in ("model", "native_5", "rolling_8"):
            e = [r["mean"][m] - r["y"] for r in rr]
            f["point"][m] = {"mae": sum(map(abs, e)) / len(e), "rmse": math.sqrt(sum(x * x for x in e) / len(e)),
                             "bias_pred_minus_actual": sum(e) / len(e)}
        keys = list(rr[0]["crps"])
        for k in keys:
            vals = [r["crps"][k] for r in rr if k in r["crps"]]
            if vals:
                f["crps"][k] = {"n": len(vals), "mean": sum(vals) / len(vals)}
        if "model_copula" in keys or any("model_copula" in r["crps"] for r in rr):
            sub = [r for r in rr if "model_copula" in r["crps"]]
            f["crps_copula_subsample"] = {k: sum(r["crps"][k] for r in sub) / len(sub)
                                          for k in sub[0]["crps"]} if sub else None
            f["crps_copula_subsample_n"] = len(sub)
        pooled = defaultdict(lambda: ([], []))
        for n in LADDERS[fam]:
            yy = [int(r["y"] >= n) for r in rr]
            row = {"line": f"{n}+", "observed_rate": sum(yy) / len(yy)}
            for k in ("model", "pr519_nb", "model_independent"):
                if k not in rr[0]["ladder"][n]:
                    continue
                ps = [r["ladder"][n][k] for r in rr]
                b, ll = brier_ll(ps, yy)
                row[k] = {"brier": b, "log_loss": ll, "mean_p": sum(ps) / len(ps),
                          "over_bias_p_minus_rate": sum(ps) / len(ps) - sum(yy) / len(yy)}
                pooled[k][0].extend(ps); pooled[k][1].extend(yy)
            dm = [(r["ladder"][n]["model"] - y) ** 2 - (r["ladder"][n]["pr519_nb"] - y) ** 2 for r, y in zip(rr, yy)]
            ci, wb = week_ci(days, dm)
            row["delta_brier_model_minus_pr519nb"] = {"mean": sum(dm) / len(dm), "week_block_ci95": ci, "week_blocks": wb}
            f["ladder"][f"{n}+"] = row
        f["ladder_pooled"] = {}
        for k, (ps, yy) in pooled.items():
            b, ll = brier_ll(ps, yy)
            tab, ece = reliability(ps, yy)
            f["ladder_pooled"][k] = {"n": len(ps), "brier": b, "log_loss": ll, "ece": ece, "reliability": tab}
        yy = [int(r["y"] >= r["rel"]["n"]) for r in rr]
        for k in ("model", "pr519_nb", "model_independent"):
            if k in rr[0]["rel"]["p"]:
                ps = [r["rel"]["p"][k] for r in rr]
                b, ll = brier_ll(ps, yy)
                tab, ece = reliability(ps, yy)
                f["relative_line"][k] = {"brier": b, "log_loss": ll, "ece": ece, "mean_p": sum(ps) / len(ps),
                                         "observed_over_rate": sum(yy) / len(yy),
                                         "over_bias_p_minus_rate": sum(ps) / len(ps) - sum(yy) / len(yy),
                                         "reliability": tab}
        dm = [(r["rel"]["p"]["model"] - y) ** 2 - (r["rel"]["p"]["pr519_nb"] - y) ** 2 for r, y in zip(rr, yy)]
        ci, wb = week_ci(days, dm)
        f["relative_line"]["delta_brier_model_minus_pr519nb"] = {"mean": sum(dm) / len(dm), "week_block_ci95": ci, "week_blocks": wb}
        if "fixed" in rr[0]:
            line = rr[0]["fixed"]["line"]
            yy = [int(r["y"] > line) for r in rr]
            for k in rr[0]["fixed"]["p"]:
                ps = [r["fixed"]["p"][k] for r in rr]
                b, ll = brier_ll(ps, yy)
                f["fixed_line"][k] = {"line": line, "brier": b, "log_loss": ll,
                                      "over_bias_p_minus_rate": sum(ps) / len(ps) - sum(yy) / len(yy)}
        fams[fam] = f
    res["families"] = fams
    return res


def load_jsonl(paths):
    out = []
    for p in paths:
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                for fam in r["fam"].values():
                    fam["ladder"] = {int(k): v for k, v in fam["ladder"].items()}
                out.append(r)
    return out


def parity(pr519_json, rows_jsonl, season):
    """Row-identity check: #519 paired rows vs this model's scored rows for one season."""
    mine = set()
    with open(rows_jsonl) as f:
        for line in f:
            r = json.loads(line)
            mine.add((r["player_id"], r["game_id"]))
    j = json.loads(Path(pr519_json).read_text())
    k519 = {(r["player_id"], r["game_id"]) for r in j["seasons"][str(season)]["rows"] if r.get("forecasts")}
    return {"pr519_paired_rows": len(k519), "model_rows": len(mine), "intersection": len(k519 & mine),
            "pr519_only": len(k519 - mine), "model_only": len(mine - k519)}


def code_hashes():
    return {p: sha(ROOT / p) for p in (
        "research/cbb_players/backtest.py", "models/cbb/players/features.py",
        "models/cbb/players/fit.py", "models/cbb/players/model.py",
        "models/cbb/players/distributions.py", "research/cbb_player_distribution.py")}


HEADER = {"status": "RESEARCH_PAPER_0U_NON_COUNTED", "approved_stake_u": 0, "official_counted": 0,
          "odds": "NONE: no historical sportsbook player-prop odds are admitted; ROI/CLV not computable"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("season", help="evaluate one season (trains on the preceding season too)")
    e.add_argument("--root", type=Path, required=True)
    e.add_argument("--season", type=int, required=True)
    e.add_argument("--output", type=Path, required=True)
    e.add_argument("--rows-output", type=Path, required=True)
    c = sub.add_parser("combine", help="pooled summary over several seasons' row files")
    c.add_argument("--rows", type=Path, nargs="+", required=True)
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--label", required=True)
    q = sub.add_parser("parity")
    q.add_argument("--pr519-json", type=Path, required=True)
    q.add_argument("--rows", type=Path, required=True)
    q.add_argument("--season", type=int, required=True)
    q.add_argument("--output", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "parity":
        a.output.write_text(json.dumps({**HEADER, "season": a.season, "parity": parity(a.pr519_json, a.rows, a.season)},
                                       indent=1, sort_keys=True) + "\n")
        return
    if a.cmd == "combine":
        rows = load_jsonl(a.rows)
        a.output.write_text(json.dumps({**HEADER, "label": a.label, "code_sha256": code_hashes(),
                                        "row_files": {str(p): sha(p) for p in a.rows}, "summary": summarize(rows)},
                                       sort_keys=True, allow_nan=False, indent=1) + "\n")
        return
    s = a.season
    all_rows, meta = [], {}
    for t in (s - 1, s):
        rows, m = run_season(t, a.root, t - 1)
        m["player_csv_sha256"] = sha(a.root / f"player_box_{t}.csv")
        m["schedule_sha256"] = sha(a.root / f"mbb_schedule_{t}.parquet")
        meta[str(t)] = m
        all_rows.extend(rows)
        print(json.dumps({"season": t, **m}), flush=True)
    all_rows.sort(key=lambda r: (r["day"], r["game_id"], r["player_id"]))
    ev = [r for r in all_rows if r["season"] == s]
    first, last = date.fromisoformat(ev[0]["day"]), date.fromisoformat(ev[-1]["day"])
    origins, scored = [], []
    with a.rows_output.open("w") as out:
        for o in mondays(first, last):
            lo, hi = o.isoformat(), (o + timedelta(days=7)).isoformat()
            tcut, tstart = (o - timedelta(days=2)).isoformat(), (o - timedelta(days=365)).isoformat()
            test = [r for r in ev if lo <= r["day"] < hi]
            if not test:
                continue
            train = [r for r in all_rows if tstart < r["day"] <= tcut]
            try:
                params = fit(train)
            except ValueError as exc:
                origins.append({"origin": lo, "held": str(exc), "n_test": len(test)})
                continue
            origins.append({"origin": lo, "n_train": params["n_train"], "n_test": len(test), "params": params})
            for r in test:
                cop = int(hashlib.sha256((r["player_id"] + r["game_id"]).encode()).hexdigest(), 16) % COPULA_MOD == 0
                sr = score_row(r, params, copula=cop)
                out.write(json.dumps(sr, sort_keys=True) + "\n")
                scored.append(sr)
            print(json.dumps({"season": s, "origin": lo, "n_train": params["n_train"], "n_test": len(test)}), flush=True)
    del all_rows, ev
    a.output.write_text(json.dumps({**HEADER, "season": s, "code_sha256": code_hashes(), "data": meta,
                                    "ladders": {k: list(v) for k, v in LADDERS.items()}, "origins": origins,
                                    "rows_sha256": sha(a.rows_output), "summary": summarize(scored)},
                                   sort_keys=True, allow_nan=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
