"""NFL public historical score benchmark, research only, PAPER/0u.

Reconstructed final PBP, not original point-in-time snapshots. No odds used.
Source: nflverse/nflverse-data PBP releases (see nflreadr load_pbp).
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict, Counter
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean
import unittest

FIELDS = ("game_id", "season", "season_type", "week", "game_date",
          "home_team", "away_team", "play_id", "desc",
          "total_home_score", "total_away_score")
MODELS = ("league_mean", "rolling_ppg", "offense_defense")


def integer(s):
    x = float(s)
    if not math.isfinite(x) or x != int(x) or x < 0:
        raise ValueError("invalid nonnegative integer")
    return int(x)


def read_games(path, season):
    groups = {}
    rejected = set()
    counts = Counter()
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not set(FIELDS) <= set(reader.fieldnames or ()):
            raise ValueError("missing PBP columns")
        for r in reader:
            gid = r["game_id"]
            if not gid:
                raise ValueError("missing game_id")
            if r["season_type"] != "REG":
                counts["nonreg_play_rows"] += 1
                continue
            try:
                yr, wk = integer(r["season"]), integer(r["week"])
                day = date.fromisoformat(r["game_date"])
                h, a = r["home_team"], r["away_team"]
                if yr != season or not h or not a or h == a or not 1 <= wk <= 18:
                    raise ValueError("bad event identity")
                if gid != f"{yr}_{wk:02d}_{a}_{h}":
                    raise ValueError("game id mismatch")
                ident = (yr, wk, day, h, a)
                g = groups.setdefault(gid, {"identity": ident, "last": -1, "final": None})
                if g["identity"] != ident:
                    raise ValueError("conflicting event metadata")
                pid = integer(r["play_id"])
                if pid > g["last"]:
                    g["last"] = pid
                if "END GAME" in r["desc"].upper():
                    score = (integer(r["total_home_score"]), integer(r["total_away_score"]))
                    if g["final"] is not None and g["final"] != (pid, score):
                        raise ValueError("conflicting final marker")
                    g["final"] = (pid, score)
            except (ValueError, TypeError, OverflowError):
                rejected.add(gid)
    out = []
    for gid, g in sorted(groups.items()):
        if gid in rejected:
            continue
        if g["final"] is None or g["final"][0] != g["last"]:
            counts["no_terminal_end_game"] += 1
            continue
        yr, wk, day, h, a = g["identity"]
        hs, aws = g["final"][1]
        out.append(dict(game_id=gid, season=yr, week=wk, day=day.isoformat(),
                        home=h, away=a, home_score=hs, away_score=aws))
    counts["invalid_events"] = len(rejected)
    counts["regular_event_groups"] = len(groups)
    counts["eligible_finals"] = len(out)
    return out, dict(counts)


def forecast(games, start_week=9):
    ids = [g["game_id"] for g in games]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate game")
    rows = []
    for g in sorted(games, key=lambda x: (x["season"], x["day"], x["game_id"])):
        if g["week"] < start_week:
            continue
        # No same-week results; additional conservative two-calendar-day lag.
        # Retrospective availability proxy, not a verified publication clock.
        target = date.fromisoformat(g["day"])
        prior = [p for p in games if p["season"] == g["season"]
                 and p["week"] < g["week"]
                 and (target - date.fromisoformat(p["day"])).days >= 2]
        pf, pa = defaultdict(list), defaultdict(list)
        for p in prior:
            h, a = p["home"], p["away"]
            hs, aws = p["home_score"], p["away_score"]
            pf[h].append(hs); pa[h].append(aws)
            pf[a].append(aws); pa[a].append(hs)
        h, a = g["home"], g["away"]
        row = dict(g, training_n=len(prior), forecasts={})
        if min(len(pf[h]), len(pf[a])) < 4:
            row["hold"] = "INSUFFICIENT_PRIOR_TEAM_GAMES"
        else:
            league = mean([s for p in prior for s in (p["home_score"], p["away_score"])])
            row["forecasts"] = {
                "league_mean": [league, league],
                "rolling_ppg": [mean(pf[h]), mean(pf[a])],
                "offense_defense": [(mean(pf[h])+mean(pa[a]))/2,
                                    (mean(pf[a])+mean(pa[h]))/2],
            }
        rows.append(row)
    return rows


def metrics(rows):
    eligible = [r for r in rows if r["forecasts"]]
    result = {}
    for model in MODELS:
        errors = defaultdict(list)
        for r in eligible:
            h, a = r["forecasts"][model]
            dh, da = h-r["home_score"], a-r["away_score"]
            for key, val in (("home",dh),("away",da),("margin",dh-da),("total",dh+da)):
                errors[key].append(val)
        result[model] = {key: {"mae": mean(abs(x) for x in v),
                               "rmse": math.sqrt(mean(x*x for x in v)),
                               "bias": mean(v)} for key,v in errors.items()}
    return dict(attempted=len(rows), paired_n=len(eligible), models=result,
                holds=dict(Counter(r["hold"] for r in rows if "hold" in r)))


def publish(path, obj):
    """Complete staged bytes, fsync, atomic no-replace link; POSIX only."""
    path = Path(path)
    raw = (json.dumps(obj, sort_keys=True, allow_nan=False, indent=2)+"\n").encode()
    fd, tmp = tempfile.mkstemp(prefix=".benchmark-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        if Path(tmp).read_bytes() != raw:
            raise IOError("staged bytes mismatch")
        os.link(tmp, path)
        dirfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        os.unlink(tmp)


def run(args):
    games, sources = [], []
    for path in args.input:
        path = Path(path)
        season = int(path.name.removeprefix("play_by_play_").removesuffix(".csv.gz"))
        if not 1999 <= season <= 2024:
            raise ValueError("closed historical seasons only")
        raw_hash = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        gs, census = read_games(path, season)
        if not gs:
            raise ValueError("no terminal finals admitted")
        games.extend(gs)
        sources.append(dict(season=season, sha256=raw_hash, census=census,
                            source_url=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz"))
    rows = forecast(games)
    report = dict(status="RETROSPECTIVE_RECONSTRUCTED_PAPER_0U",
                  source_attribution="nflverse / nflverse-pbp", sources=sources,
                  evaluated_utc=datetime.now(timezone.utc).isoformat(),
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  chronology="strictly earlier same-season week and >=2 calendar days; no authenticated publication timestamps",
                  model_definition="simple new baselines; not reproduction of Grok or frozen SportsEdge",
                  pooled=metrics(rows), seasons={str(s):metrics([r for r in rows if r["season"]==s])
                                                  for s in sorted({g["season"] for g in games})},
                  forecasts=rows, official_counted=0, approved_stake_u=0)
    if not report["pooled"]["paired_n"]:
        raise ValueError("no eligible evaluation games")
    publish(args.output, report)
    print(json.dumps({k:v for k,v in report.items() if k!="forecasts"}, sort_keys=True))


class Regression(unittest.TestCase):
    def fixture(self):
        return [dict(game_id=str(i),season=2023,week=i,day=f"2023-09-{i*3:02d}",
                     home="A",away="B",home_score=20,away_score=10) for i in range(1,10)]
    def test_future_and_target_scores_do_not_change_forecast(self):
        g=self.fixture(); before=forecast(g)[0]["forecasts"]
        g[-1]["home_score"]=99
        self.assertEqual(before,forecast(g)[0]["forecasts"])
        self.assertEqual(before["rolling_ppg"],[20,10])
    def test_order_invariant(self):
        g=self.fixture()
        self.assertEqual(forecast(g),forecast(list(reversed(g))))
    def test_duplicate_rejected(self):
        g=self.fixture()
        with self.assertRaises(ValueError): forecast(g+[g[0]])
    def test_same_week_excluded(self):
        g=self.fixture(); g[0]["week"]=9
        self.assertEqual([r for r in forecast(g) if r["game_id"]=="9"][0]["training_n"],7)
    def test_metrics_common_rows(self):
        result=metrics(forecast(self.fixture()))
        self.assertEqual(result["paired_n"],1)
        self.assertEqual(result["models"]["rolling_ppg"]["margin"]["mae"],0)
    def test_no_replace(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"report.json";publish(p,{"a":1})
            before=p.read_bytes()
            with self.assertRaises(FileExistsError):publish(p,{"a":2})
            self.assertEqual(before,p.read_bytes())
            self.assertEqual(list(Path(d).iterdir()),[p])


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--input",nargs="+")
    parser.add_argument("--output")
    args=parser.parse_args()
    if args.self_test:
        unittest.main(argv=[__file__],verbosity=2)
    else:
        if not args.input or not args.output: parser.error("--input and --output required")
        run(args)
