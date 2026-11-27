#!/usr/bin/env python3
"""Chronological league scoring-baseline research (issue #431). Research only: PAPER / 0u / NON_COUNTED.

Reads the two PRIVATE Drive text extracts (PDF) of third-party final-score CSVs and reports how well
simple league-level total-score baselines predict later games. Every prediction for a game uses only
games on STRICTLY EARLIER dates. No sportsbook price, pregame feature or team-level model is used.

Usage:  python scoring_baselines.py CFB_EXTRACT.pdf NFL_EXTRACT.pdf OUT_DIR
Needs:  pdfplumber, numpy, pandas.   The bootstrap is seeded (20261127), so reruns are identical.
The extracts are NOT committed. Re-hash the upstream sources before relying on any number here.
"""
import csv, hashlib, logging, re, sys
from pathlib import Path
import numpy as np, pandas as pd
import pdfplumber

logging.disable(logging.CRITICAL)
SEED = 20261127


def pdf_text(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def sha(rows):
    return hashlib.sha256("\n".join(",".join(map(str, r)) for r in rows).encode()).hexdigest()


def parse_cfb(txt):
    body = txt.split("BEGIN CSV EXTRACT", 1)[1].split("END CSV EXTRACT")[0]
    flat = body.replace("\n", "")
    flat = flat[flat.find("postseason") + len("postseason"):]
    pat = re.compile(r"^(\d{4}-\d{2}-\d{2}),(\d{4}),(.*),(\d+),(\d+),(\d+),(-?\d+),([^,]*),(True|False),(True|False)$")
    rows = []
    for c in re.split(r"(?=\d{4}-\d{2}-\d{2},\d{4},)", flat):
        c = c.strip().replace("END CSV EXTRACT", "")
        if not c:
            continue
        m = pat.match(c)
        if not m:
            raise SystemExit("CFB_ROW_UNPARSED: " + c[:80])
        d, s, teams, hp, ap, tp, pd_, w, n, po = m.groups()
        rows.append((d, int(s), teams, int(hp), int(ap), int(tp), int(pd_), n == "True", po == "True"))
    df = pd.DataFrame(rows, columns=["date", "season", "teams", "hp", "ap", "tp", "pd", "neutral", "post"])
    assert (df.tp == df.hp + df.ap).all() and (df.pd == df.hp - df.ap).all()
    df["dt"] = pd.to_datetime(df["date"])
    df = df.sort_values(["dt", "teams"]).reset_index(drop=True)
    return df, sha(df[["date", "season", "teams", "hp", "ap"]].astype(str).values.tolist())


def parse_nfl(txt):
    body = txt.split("BEGIN CSV EXTRACT", 1)[1].split("END CSV EXTRACT")[0]
    flat = body.replace("\n", "")
    flat = flat[flat.find("stadium") + len("stadium"):]
    rows = []
    for c in re.split(r"(?=\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3},)", flat):
        if not re.match(r"\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3},", c):
            continue
        f = next(csv.reader([c]))
        rows.append(f[:15])
    cols = ["game_id", "season", "game_type", "week", "gameday", "weekday", "gametime", "away_team", "away_score",
            "home_team", "home_score", "location", "result", "total", "overtime"]
    g = pd.DataFrame(rows, columns=cols)
    for c in ["season", "week", "away_score", "home_score", "result", "total", "overtime"]:
        g[c] = pd.to_numeric(g[c])
    assert (g.total == g.home_score + g.away_score).all() and (g.result == g.home_score - g.away_score).all()
    g["dt"] = pd.to_datetime(g.gameday)
    g = g.sort_values(["dt", "game_id"]).reset_index(drop=True)
    return g, sha(g[cols].astype(str).values.tolist())


def boot_ci(by_season, rng, B=2000):
    keys = list(by_season)
    out = []
    for _ in range(B):
        pick = rng.choice(len(keys), len(keys))
        out.append(np.concatenate([by_season[keys[i]] for i in pick]).mean())
    return np.percentile(out, [2.5, 97.5])


def baselines(df, tcol, season_col, extra=None):
    tp = df[tcol].astype(float).values
    dates = df["dt"].values
    cum = np.cumsum(tp)
    cs = np.concatenate([[0], cum])
    first = pd.Series(range(len(df))).groupby(df["dt"]).transform("min").values
    sm = df.groupby(season_col)[tcol].mean()
    prior_season = df[season_col].map(lambda s: sm.get(s - 1, np.nan)).values.astype(float)
    expanding = np.where(first > 0, cum[np.maximum(first - 1, 0)] / np.maximum(first, 1), np.nan)
    left = np.searchsorted(dates, dates - np.timedelta64(365, "D"))
    roll365 = np.array([(cs[f] - cs[l]) / (f - l) if f - l > 0 else np.nan for f, l in zip(first, left)])
    roll1000 = np.array([tp[max(0, f - 1000):f].mean() if f > 0 else np.nan for f in first])
    preds = {"prior_season_mean": prior_season, "expanding_mean": expanding,
             "rolling_1000_games": roll1000, "rolling_365_days": roll365}
    if extra:
        preds.update(extra)
    return tp, preds


def score(df, tp, preds, season_col, first_season, last_season, rng):
    rows, by_rows = [], []
    seasons = df[season_col].values
    for name, p in preds.items():
        e = tp - p
        m = (seasons >= first_season) & ~np.isnan(p)
        by = {k: e[m & (seasons == k)] for k in range(first_season, last_season + 1) if (m & (seasons == k)).any()}
        lo, hi = boot_ci(by, rng)
        rows.append((name, int(m.sum()), np.abs(e[m]).mean(), np.sqrt((e[m] ** 2).mean()), e[m].mean(), lo, hi))
        for k, v in by.items():
            by_rows.append((name, k, len(v), np.abs(v).mean(), v.mean()))
    summ = pd.DataFrame(rows, columns=["baseline", "n", "MAE", "RMSE", "signed_resid_actual_minus_pred",
                                       "signed_CI95_lo_season_block_bootstrap", "signed_CI95_hi_season_block_bootstrap"])
    byd = pd.DataFrame(by_rows, columns=["baseline", "season", "n", "MAE", "signed_resid_actual_minus_pred"])
    return summ.round(4), byd.round(4)


def main(cfb_pdf, nfl_pdf, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    cfb, cfb_hash = parse_cfb(pdf_text(cfb_pdf))
    sm = cfb.groupby("season").tp.mean()
    tp, preds = baselines(cfb, "tp", "season", {"frozen_LG_PPG_28_total_56": np.full(len(cfb), 56.0)})
    cum = np.concatenate([[0], np.cumsum(tp)])
    first = pd.Series(range(len(cfb))).groupby(cfb["dt"]).transform("min").values
    start = cfb.reset_index().groupby("season")["index"].min().to_dict()
    shr = np.full(len(cfb), np.nan)
    for i in range(len(cfb)):
        ps = sm.get(cfb.season[i] - 1, np.nan)
        if np.isnan(ps):
            continue
        st, f = start[cfb.season[i]], first[i]
        n = max(0, f - st)
        shr[i] = (((cum[f] - cum[st]) if n else 0.0) + 300 * ps) / (n + 300)
    preds["season_to_date_shrunk_to_prior_k300"] = shr
    s, b = score(cfb, tp, preds, "season", 2016, 2024, rng)
    s.to_csv(out / "cfb_scoring_baseline_summary_2016_2024.csv", index=False)
    b.to_csv(out / "cfb_scoring_baseline_by_season.csv", index=False)
    reg = cfb[~cfb.post]
    env = cfb.groupby("season").agg(n=("tp", "size"), mean_total=("tp", "mean"), sd_total=("tp", "std"),
                                    postseason_games=("post", "sum")).round(3)
    env["mean_total_regular_season"] = reg.groupby("season").tp.mean().round(3)
    env.to_csv(out / "cfb_season_scoring_environment.csv")

    nfl, nfl_hash = parse_nfl(pdf_text(nfl_pdf))
    nn = nfl[nfl.location == "Home"]
    tp2, preds2 = baselines(nfl, "total", "season", {"constant_45": np.full(len(nfl), 45.0)})
    s2, b2 = score(nfl, tp2, preds2, "season", 2016, 2025, rng)
    s2.to_csv(out / "nfl_scoring_baseline_summary_2016_2025.csv", index=False)
    b2.to_csv(out / "nfl_scoring_baseline_by_season.csv", index=False)
    env2 = nfl.groupby("season").agg(n=("total", "size"), mean_total=("total", "mean"), sd_total=("total", "std"),
                                     overtime_rate=("overtime", lambda x: (x > 0).mean())).round(3)
    ns = nn.groupby("season").agg(non_neutral_n=("result", "size"), home_margin=("result", "mean"),
                                  home_win_rate_ties_half=("result", lambda x: (x > 0).mean() + 0.5 * (x == 0).mean())).round(3)
    pd.concat([env2, ns], axis=1).to_csv(out / "nfl_season_environment_and_hfa.csv")
    hv = {k: v.result.values.astype(float) for k, v in nn.groupby("season")}
    lo, hi = boot_ci(hv, rng, 4000)
    meta = pd.DataFrame([
        ("cfb_rows", len(cfb)), ("cfb_dataset_sha256_canonical_parsed_rows", cfb_hash),
        ("nfl_rows", len(nfl)), ("nfl_dataset_sha256_canonical_parsed_rows", nfl_hash),
        ("nfl_hfa_margin_non_neutral_all_seasons", round(float(nn.result.mean()), 4)),
        ("nfl_hfa_CI95_season_block_bootstrap", f"{lo:.3f}..{hi:.3f}"), ("seed", SEED)],
        columns=["item", "value"])
    meta.to_csv(out / "run_metadata.csv", index=False)
    print(meta.to_string(index=False))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
