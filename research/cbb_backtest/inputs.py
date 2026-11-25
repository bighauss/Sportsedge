"""Committed, hash-pinned inputs for the CBB backtest (research only; PAPER / 0u; NON_COUNTED).

Two layers, both pinned in data/MANIFEST.json:

1. DERIVATIVES (committed, text, in data/): the exact inputs the harness consumes.
     games_{season}.csv        admitted finals (+ possessions, site class) for 2018..2026, i.e. the
                               output of research.cbb_hca.public_factorial_backtest.schedule_games
                               on the sportsdataverse parquets
     odds_selected_{season}.csv  ONE sportsbook close record per admitted game (the fixed provider
                               preference in data.PROVIDER_PREFERENCE), as chosen by data.select_market
     census.json               admission / odds census numbers the report prints
     espn_game_ids.txt         the ESPN event ids whose odds were fetched
   Verification is offline and fails on any byte mismatch.

2. EXTERNAL SOURCES (not committed, hash-pinned): the 18 sportsdataverse parquet files and the raw
   ESPN odds cache. `fetch` re-downloads them and fails on hash mismatch; `rederive` rebuilds every
   derivative from them and fails unless the bytes equal the committed files.

Nothing is imputed. open_* ESPN fields are NOT carried: they fail validation (data.OPEN_LINES_STATUS)
and the harness nulls them anyway, so they never reached any result.
CLI:  python -m research.cbb_backtest.inputs {verify|fetch|rederive|export|manifest} ...
"""
import argparse
import csv
import gzip
import hashlib
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

from . import data as D

DATA_DIR = Path(__file__).parent / "data"
SEASONS_GAMES = tuple(range(2018, 2027))   # 2018 = previous-season carry for the 2019 origins
SEASONS_ODDS = tuple(range(2019, 2027))
GAME_COLS = ("event_id", "day", "home", "away", "neutral", "home_points", "away_points", "margin", "total",
             "possessions", "box_hold", "season", "site")
ODDS_COLS = ("event_id", "provider_id", "provider", "close_spread_home", "close_spread_price_home",
             "close_spread_price_away", "close_total", "close_over_price", "close_under_price",
             "close_ml_home", "close_ml_away", "close_from_current_fallback")
_FLOAT = {"close_spread_home", "close_total"}
_INT = {"close_spread_price_home", "close_spread_price_away", "close_over_price", "close_under_price",
        "close_ml_home", "close_ml_away"}
MANIFEST = "MANIFEST.json"
SCHEMA = "CBB_BACKTEST_INPUT_MANIFEST_V1"


class InputError(RuntimeError):
    pass


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ csv helpers (deterministic)
def _w(path, cols, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])


def _bool(x):
    return {"True": True, "False": False}[x]


# ------------------------------------------------------------------ games
def export_games(raw_root, out_dir, seasons=SEASONS_GAMES):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    census = {}
    for s in seasons:
        games, c = D.load_games(raw_root, s)
        games = sorted(games, key=lambda g: g["event_id"])
        rows = [{**g, "day": g["day"].isoformat()} for g in games]
        _w(out_dir / f"games_{s}.csv", GAME_COLS, rows)
        census[str(s)] = dict(sorted(c.items()))
    return census


def load_games_normalized(data_dir, season):
    """Same (games, census) as data.load_games, from the committed CSV. Games sorted by event_id
    exactly as schedule_games emits them (sorted(sg.items()))."""
    data_dir = Path(data_dir)
    p = data_dir / f"games_{season}.csv"
    if not p.exists():
        raise FileNotFoundError(p)
    games = []
    with open(p, newline="") as f:
        for r in csv.DictReader(f):
            games.append({"event_id": r["event_id"], "day": date.fromisoformat(r["day"]), "home": r["home"],
                          "away": r["away"], "neutral": _bool(r["neutral"]),
                          "home_points": int(r["home_points"]), "away_points": int(r["away_points"]),
                          "margin": int(r["margin"]), "total": int(r["total"]),
                          "possessions": float(r["possessions"]) if r["possessions"] != "" else None,
                          "box_hold": r["box_hold"] if r["box_hold"] != "" else None,
                          "season": int(r["season"]), "site": r["site"]})
    census = json.loads((data_dir / "census.json").read_text())["games"][str(season)]
    return games, census


# ------------------------------------------------------------------ odds
def export_odds(raw_odds, raw_root, out_dir, games_census=None):
    """Select one book per game from the raw cache, keep ADMITTED finals only (the only games a
    forecast row can reference), write one file per season. Returns the census dict."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    odds, census = D.load_odds(raw_odds)
    season_of = {}
    for s in SEASONS_ODDS:
        games, _ = D.load_games(raw_root, s)
        for g in games:
            season_of[g["event_id"]] = s
    per = {s: [] for s in SEASONS_ODDS}
    dropped = 0
    for gid, m in odds.items():
        s = season_of.get(gid)
        if s is None:
            dropped += 1   # selected book but not an admitted final: can never enter a forecast row
            continue
        per[s].append({"event_id": gid, **{k: m.get(k) for k in ODDS_COLS if k != "event_id"}})
    kept = {}
    for s in SEASONS_ODDS:
        rows = sorted(per[s], key=lambda r: r["event_id"])
        _w(out_dir / f"odds_selected_{s}.csv", ODDS_COLS, rows)
        kept[str(s)] = len(rows)
    return {"raw_cache_census": census, "selected_not_admitted_final_dropped": dropped,
            "selected_admitted_by_season": kept}


def load_odds_normalized(data_dir):
    """(odds dict keyed by event_id, census) equal to data.load_odds on the admitted games.
    open_* are None (blocked: see data.OPEN_LINES_STATUS); key presence matches select_market."""
    data_dir = Path(data_dir)
    out = {}
    for s in SEASONS_ODDS:
        with open(data_dir / f"odds_selected_{s}.csv", newline="") as f:
            for r in csv.DictReader(f):
                m = {"provider_id": r["provider_id"], "provider": r["provider"]}
                for k in ODDS_COLS[3:11]:
                    v = r[k]
                    m[k] = None if v == "" else (float(v) if k in _FLOAT else int(v))
                for k in ("open_spread_home", "open_spread_price_home", "open_spread_price_away", "open_total",
                          "open_over_price", "open_under_price", "open_ml_home", "open_ml_away"):
                    m[k] = None
                m["close_from_current_fallback"] = _bool(r["close_from_current_fallback"])
                out[r["event_id"]] = m
    census = json.loads((data_dir / "census.json").read_text())["odds"]
    return out, {**census["raw_cache_census"], "source": "normalized_derivative_admitted_finals_only"}


# ------------------------------------------------------------------ ids (deterministic, from schedules)
def derive_game_ids(raw_root, seasons=SEASONS_ODDS):
    import pyarrow.parquet as pq
    ids = set()
    for s in seasons:
        for r in pq.read_table(Path(raw_root) / f"mbb_schedule_{s}.parquet",
                               columns=["game_id", "status_type_completed"]).to_pylist():
            if r["status_type_completed"] is True:
                ids.add(str(r["game_id"]))
    return sorted(ids, key=int)


# ------------------------------------------------------------------ manifest
def _rows(p):
    with open(p, newline="") as f:
        return max(0, sum(1 for _ in f) - 1) if p.suffix == ".csv" else None


def build_manifest(data_dir, raw_root=None, raw_odds=None):
    data_dir = Path(data_dir)
    files = []
    for p in sorted(data_dir.iterdir()):
        if p.name == MANIFEST or not p.is_file():
            continue
        e = {"path": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        if p.suffix == ".csv":
            e["rows"] = _rows(p)
        files.append(e)
    ext = []
    if raw_root:
        for s in SEASONS_GAMES:
            for kind, url in (("schedule", D.SCHED_URL), ("team_box", D.BOX_URL)):
                name = f"mbb_schedule_{s}.parquet" if kind == "schedule" else f"team_box_{s}.parquet"
                p = Path(raw_root) / name
                ext.append({"name": name, "kind": kind, "season": s, "url": url.format(s=s),
                            "bytes": p.stat().st_size, "sha256": sha256_file(p)})
    raw = None
    if raw_odds:
        raw = {"name": "espn_odds_all.jsonl.gz", "bytes": Path(raw_odds).stat().st_size,
               "sha256": sha256_file(raw_odds),
               "fetch": "python -m research.cbb_backtest.espn_odds_collect --ids data/espn_game_ids.txt --out espn_odds_all.jsonl.gz",
               "url_template": D.ODDS_URL,
               "caveat": "ESPN may revise or drop odds after the fact; a fresh fetch is not guaranteed byte-identical "
                         "and a hash mismatch fails verification instead of being accepted."}
    results = []
    base = Path(__file__).parent
    for sub in ("results/run1_as_specified", "results/run3_final"):
        for p in sorted((base / sub).rglob("*")):
            if p.is_file():
                results.append({"path": p.relative_to(base).as_posix(), "bytes": p.stat().st_size,
                                "sha256": sha256_file(p)})
    return {"schema": SCHEMA, "status": "RESEARCH_PAPER_0U", "label": "NON_COUNTED",
            "derivatives": files, "committed_results": results, "external_sources": ext, "external_odds_cache": raw,
            "derivation": {"games": "research.cbb_backtest.inputs.export_games over the 18 parquet files above",
                           "odds": "research.cbb_backtest.inputs.export_odds over external_odds_cache using data.select_market",
                           "game_ids": "sorted(game_id with status_type_completed==True in mbb_schedule_2019..2026)"}}


def write_manifest(data_dir, raw_root=None, raw_odds=None):
    m = build_manifest(data_dir, raw_root, raw_odds)
    (Path(data_dir) / MANIFEST).write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
    return m


# ------------------------------------------------------------------ verify / fetch / rederive
def load_manifest(data_dir):
    p = Path(data_dir) / MANIFEST
    if not p.exists():
        raise InputError(f"missing {p}")
    m = json.loads(p.read_text())
    if m.get("schema") != SCHEMA:
        raise InputError("MANIFEST_SCHEMA")
    return m


def verify_derivatives(data_dir):
    """Offline. Every pinned file present with matching bytes+sha256; no unpinned files. Returns problems."""
    data_dir = Path(data_dir)
    m = load_manifest(data_dir)
    bad = []
    pinned = set()
    for e in m["derivatives"]:
        pinned.add(e["path"])
        p = data_dir / e["path"]
        if not p.exists():
            bad.append(f"MISSING {e['path']}"); continue
        if p.stat().st_size != e["bytes"]:
            bad.append(f"SIZE {e['path']}: {p.stat().st_size} != {e['bytes']}")
        h = sha256_file(p)
        if h != e["sha256"]:
            bad.append(f"SHA256 {e['path']}: {h} != {e['sha256']}")
        elif e.get("rows") is not None and _rows(p) != e["rows"]:
            bad.append(f"ROWS {e['path']}")
    for p in sorted(data_dir.iterdir()):
        if p.is_file() and p.name != MANIFEST and p.name not in pinned:
            bad.append(f"UNPINNED {p.name}")
    base = data_dir.parent
    for e in m.get("committed_results", []):
        p = base / e["path"]
        if not p.exists():
            bad.append(f"MISSING {e['path']}")
        elif sha256_file(p) != e["sha256"]:
            bad.append(f"SHA256 {e['path']}: result evidence file changed")
    if not m.get("committed_results"):
        bad.append("MANIFEST_LACKS committed_results")
    for s in SEASONS_GAMES:
        if f"games_{s}.csv" not in pinned:
            bad.append(f"MANIFEST_LACKS games_{s}.csv")
    for s in SEASONS_ODDS:
        if f"odds_selected_{s}.csv" not in pinned:
            bad.append(f"MANIFEST_LACKS odds_selected_{s}.csv")
    return bad


def verify_external(data_dir, ext_dir, need_odds=True):
    ext_dir = Path(ext_dir)
    m = load_manifest(data_dir)
    bad = []
    for e in m["external_sources"]:
        p = ext_dir / e["name"]
        if not p.exists():
            bad.append(f"MISSING {e['name']}"); continue
        h = sha256_file(p)
        if h != e["sha256"]:
            bad.append(f"SHA256 {e['name']}: {h} != {e['sha256']}")
    if need_odds and m.get("external_odds_cache"):
        e = m["external_odds_cache"]
        p = ext_dir / e["name"]
        if not p.exists():
            bad.append(f"MISSING {e['name']}")
        elif sha256_file(p) != e["sha256"]:
            bad.append(f"SHA256 {e['name']}: {sha256_file(p)} != {e['sha256']}")
    return bad


def fetch_sources(data_dir, out_dir):
    """Download the pinned parquet files; each is hash-checked and a mismatch is kept as *.rejected."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    m = load_manifest(data_dir)
    bad = []
    for e in m["external_sources"]:
        p = out_dir / e["name"]
        if p.exists() and sha256_file(p) == e["sha256"]:
            continue
        tmp = out_dir / (e["name"] + ".part")
        req = urllib.request.Request(e["url"], headers={"User-Agent": "cbb-backtest-fetch"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        if sha256_file(tmp) != e["sha256"]:
            tmp.rename(out_dir / (e["name"] + ".rejected"))
            bad.append(f"SHA256 {e['name']} (upstream asset changed or download corrupt)")
        else:
            tmp.rename(p)
    return bad


def rederive(data_dir, raw_root, raw_odds, work_dir):
    """Rebuild every derivative from the external sources into work_dir; compare to committed bytes."""
    work_dir = Path(work_dir); work_dir.mkdir(parents=True, exist_ok=True)
    gc = export_games(raw_root, work_dir)
    oc = export_odds(raw_odds, raw_root, work_dir)
    (work_dir / "census.json").write_text(json.dumps({"games": gc, "odds": oc}, indent=1, sort_keys=True) + "\n")
    ids = derive_game_ids(raw_root)
    (work_dir / "espn_game_ids.txt").write_text("\n".join(ids))
    bad = []
    for p in sorted(work_dir.iterdir()):
        q = Path(data_dir) / p.name
        if not q.exists():
            bad.append(f"NOT_COMMITTED {p.name}")
        elif sha256_file(p) != sha256_file(q):
            bad.append(f"REDERIVED_DIFFERS {p.name}")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="offline: committed derivatives vs MANIFEST (non-zero exit on any mismatch)")
    v.add_argument("--data-dir", type=Path, default=DATA_DIR)
    v.add_argument("--external", type=Path, help="also verify raw parquet files + odds cache in this dir")
    f = sub.add_parser("fetch", help="download pinned parquet sources into --out and verify hashes")
    f.add_argument("--data-dir", type=Path, default=DATA_DIR)
    f.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("rederive", help="rebuild all derivatives from external sources; fail unless byte-identical")
    r.add_argument("--data-dir", type=Path, default=DATA_DIR)
    r.add_argument("--external", type=Path, required=True)
    r.add_argument("--work", type=Path, required=True)
    e = sub.add_parser("export", help="(maintainer) write derivatives from external sources into --data-dir")
    e.add_argument("--data-dir", type=Path, default=DATA_DIR)
    e.add_argument("--external", type=Path, required=True)
    a = ap.parse_args(argv)
    bad = []
    if a.cmd == "verify":
        bad = verify_derivatives(a.data_dir)
        if a.external:
            bad += verify_external(a.data_dir, a.external)
    elif a.cmd == "fetch":
        bad = fetch_sources(a.data_dir, a.out)
        bad += verify_external(a.data_dir, a.out, need_odds=False)
    elif a.cmd == "rederive":
        bad = verify_external(a.data_dir, a.external) + rederive(a.data_dir, a.external, a.external / "espn_odds_all.jsonl.gz", a.work)
    elif a.cmd == "export":
        ext, d = a.external, a.data_dir
        d.mkdir(parents=True, exist_ok=True)
        gc = export_games(ext, d)
        oc = export_odds(ext / "espn_odds_all.jsonl.gz", ext, d)
        (d / "census.json").write_text(json.dumps({"games": gc, "odds": oc}, indent=1, sort_keys=True) + "\n")
        (d / "espn_game_ids.txt").write_text("\n".join(derive_game_ids(ext)))
        write_manifest(d, ext, ext / "espn_odds_all.jsonl.gz")
    for b in bad:
        print("FAIL", b, file=sys.stderr)
    print("OK" if not bad else f"{len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
