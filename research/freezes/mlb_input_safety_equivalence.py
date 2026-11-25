#!/usr/bin/env python3
"""Output-equivalence + fail-closed harness: MLB approved blob 3f630532 vs current 30c6cb33 (commit b73874a, pr-446).

Research/audit only. Loads BOTH versions of models/mlb/sportsedge_mlb_model.py in isolated
namespaces, feeds them byte-identical input FILES (so the changed function, load_keyed, is on the
path) and compares every result bit for bit: floats are compared by float.hex (tolerance exactly 0).

Corpora
  * SAMPLE  - the only MLB fixtures in the repo: the deterministic output of the committed
              models/mlb/make_samples.py (seed 20261115, SYNTHETIC fake teams/players/odds). The repo
              commits NO real MLB board/CSV, so none could be fed; this is stated, not hidden.
  * RANDOM  - seeded synthetic slates (seed 20261125) that exercise blank numeric cells, partial
              lineups (unpriced branch), missing bullpen/defense/park rows, whole and half lines
              (push mass), one-sided books, every game market and every prop market.
  * NEGATIVE - input-contract cases (duplicate / blank / missing / short-row / malformed keys). These are
              the INTENDED behaviour changes; each is run on both versions and its old/new outcome recorded.

No network, no wall clock, no randomness beyond fixed seeds.
"""
from __future__ import annotations
import csv, hashlib, importlib.util, json, os, random, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVED_BLOB = "3f630532e9ff499912bc06041906d3b7c11d9887"
CURRENT_BLOB = "30c6cb3355ac5f6b6cbb018729c4fdc41255e057"
OLD_SRC = Path(__file__).with_name("pinned_blobs") / "3f630532_sportsedge_mlb_model.py.txt"
NEW_SRC = ROOT / "models/mlb/sportsedge_mlb_model.py"
MAKE_SAMPLES = ROOT / "models/mlb/make_samples.py"
RANDOM_SEED = 20261125
RANDOM_SLATES = 100
TEAMS_PER_SLATE = 30
PITCHES = ["FF", "SI", "FC", "SL", "CU", "CH", "FS"]


def git_blob(body: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()


def load_module(src: Path, name: str):
    body = src.read_bytes()
    spec = importlib.util.spec_from_loader(name, loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(body, str(src), "exec"), mod.__dict__)
    return mod, git_blob(body)


def load_pair():
    old, old_sha = load_module(OLD_SRC, "mlb_model_approved_3f630532")
    new, new_sha = load_module(NEW_SRC, "mlb_model_current")
    return old, old_sha, new, new_sha


def canon(o):
    """Bit-exact canonical form: floats -> hex string."""
    if isinstance(o, float):
        return "f:" + o.hex()
    if isinstance(o, dict):
        return {repr(k): canon(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [canon(v) for v in o]
    return o


def digest(o) -> str:
    return hashlib.sha256(json.dumps(canon(o), sort_keys=True, default=repr).encode()).hexdigest()


def write_csv(path: Path, rows, cols=None):
    cols = cols or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- corpora
def make_sample_folder(dest: Path) -> Path:
    spec = importlib.util.spec_from_file_location("mlb_make_samples", MAKE_SAMPLES)
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    ms.OUT = str(dest / "sample_inputs")
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        ms.main()
    return dest / "sample_inputs"


def random_slate(folder: Path, idx: int):
    r = random.Random(RANDOM_SEED * 1000 + idx)
    teams = [f"T{idx:03d}_{i:02d}" for i in range(TEAMS_PER_SLATE)]
    blank = lambda v, p=.07: "" if r.random() < p else v
    pitchers, batters, lineups, bullpen, defense, parks, games, odds, props = [], [], [], [], [], [], [], [], []
    for t in teams:
        for s in range(3):
            usage = [r.uniform(5, 30) for _ in PITCHES]; u = sum(usage)
            pitchers.append(dict(
                player_id=f"P{t}_{s}", name=f"SP {t} {s}", team=t, p_throws=r.choice("RL"),
                g=r.randint(0, 33), gs=r.randint(0, 33), ip=round(r.uniform(20, 190), 1),
                xera=blank(round(r.uniform(2.6, 5.4), 2)), xwoba=blank(round(r.uniform(.27, .35), 3)),
                k_percent=blank(round(r.uniform(16, 32), 1)), bb_percent=blank(round(r.uniform(5, 11), 1)),
                csw_percent=blank(round(r.uniform(24, 33), 1)), velo_season=blank(round(r.uniform(90, 97), 1)),
                velo_last3=blank(round(r.uniform(89, 97), 1)), bf_per_start=blank(round(r.uniform(18, 27), 1)),
                tto3_xwoba=blank(round(r.uniform(.30, .37), 3)),
                **{f"usage_{p}": round(x / u * 100, 1) for p, x in zip(PITCHES, usage)},
                **{f"whiff_{p}": blank(round(r.uniform(12, 40), 1)) for p in PITCHES}))
        for slot in range(1, 15):
            pa = r.randint(40, 680)
            batters.append(dict(
                player_id=f"B{t}_{slot}", name=f"B {t} {slot}", team=t, stand=r.choice("LRS"), pa=pa,
                xwoba=blank(round(r.uniform(.28, .39), 3)), xslg=blank(round(r.uniform(.34, .53), 3)),
                barrel_batted_rate=blank(round(r.uniform(3, 15), 1)), hard_hit_percent=blank(round(r.uniform(30, 52), 1)),
                bat_speed=blank(round(r.uniform(67, 76), 1)), k_percent=blank(round(r.uniform(13, 30), 1)),
                ba=blank(round(r.uniform(.2, .3), 3)), iso=blank(round(r.uniform(.1, .25), 3)),
                hr_per_pa=blank(round(r.uniform(.01, .06), 3)),
                xwoba_vs_L=blank(round(r.uniform(.27, .4), 3)), xwoba_vs_R=blank(round(r.uniform(.27, .4), 3)),
                pa_vs_L=int(pa * .3), pa_vs_R=int(pa * .7),
                **{f"xwoba_{p}": blank(round(r.uniform(.26, .41), 3)) for p in PITCHES}))
        if r.random() > .03:
            bullpen.append(dict(team=t, ip=blank(round(r.uniform(300, 540), 1)), xfip=blank(round(r.uniform(3.4, 4.8), 2)),
                                k_bb_percent=blank(round(r.uniform(10, 20), 1)), pitches_last3=r.choice([0, 40, 95, 140, 210])))
        if r.random() > .03:
            defense.append(dict(team=t, oaa=r.randint(-15, 18), framing_runs=round(r.uniform(-7, 9), 1), games=r.choice([150, 40])))
        parks.append(dict(park=f"Park {t}", pf_runs_lhb=r.randint(94, 110), pf_runs_rhb=r.randint(94, 110), pf_hr=r.randint(85, 118)))
    order = teams[:]
    r.shuffle(order)
    for gi in range(TEAMS_PER_SLATE // 2):
        a, h = order[2 * gi], order[2 * gi + 1]
        gid = f"S{idx:03d}G{gi:02d}"
        games.append(dict(
            game_id=gid, date="2026-09-20", away=a, home=h, park=f"Park {h}", start_time="19:05",
            roof=r.choice(["open", "closed", "dome"]), temp_f=blank(r.randint(38, 98)), wind_mph=blank(r.randint(0, 22)),
            wind_dir=r.choice(["out", "in", "cross", "none"]), altitude_ft=r.choice([0, 600, 5200]),
            umpire="Ump", ump_runs_per_game=blank(round(r.uniform(-.4, .5), 2)),
            away_sp_id=f"P{a}_{r.randint(0, 2)}", home_sp_id=f"P{h}_{r.randint(0, 2)}",
            away_rating_runs=blank(round(r.uniform(3.6, 5.2), 2)), home_rating_runs=blank(round(r.uniform(3.6, 5.2), 2)),
            away_rest_days=r.randint(0, 3), home_rest_days=r.randint(0, 3),
            away_travel_tz=r.randint(0, 3), home_travel_tz=r.randint(0, 2)))
        for t in (a, h):
            n = 9 if r.random() > .06 else 8                 # some partial orders -> UNPRICED branch
            for slot in range(1, n + 1):
                lineups.append(dict(game_id=gid, team=t, slot=slot, player_id=f"B{t}_{slot}"))
        def two(mk, sa, sb, la, lb):
            pa = r.choice([-250, -180, -150, -125, -110, -105, 100, 105, 120, 150, 190, 240])
            pb = r.choice([-250, -180, -150, -125, -110, -105, 100, 105, 120, 150, 190, 240])
            odds.append(dict(game_id=gid, market=mk, selection=sa, line=la, price=pa, book="DK"))
            if r.random() > .05:                              # sometimes one-sided
                odds.append(dict(game_id=gid, market=mk, selection=sb, line=lb, price=pb, book="DK"))
        two("ML", "away", "home", "", "")
        rl = r.choice([1.5, 2.5])
        two("RL", "away", "home", rl, -rl)
        for mk, lo, hi in (("TOTAL", 6.5, 11.5), ("TT_AWAY", 2.5, 6.5), ("TT_HOME", 2.5, 6.5), ("F5_TOTAL", 3.5, 6.5)):
            ln = r.choice([x / 2 for x in range(int(lo * 2), int(hi * 2) + 1)])   # whole + half lines
            two(mk, "over", "under", ln, ln)
        two("F5_ML", "away", "home", "", "")
        two("NRFI", "nrfi", "yrfi", "", "")
        for t in (a, h):
            for mk, ln in (("K", r.choice([3.5, 4.5, 5.5, 6.5])), ("OUTS", r.choice([14.5, 16.5, 17.5]))):
                props.append(dict(game_id=gid, player_id=f"P{t}_0", market=mk, line=ln,
                                  over_price=r.choice([-130, -105, 105]), under_price=r.choice([-130, -105, 105]), book="DK"))
            for slot in (1, 3, 4, 6):
                pid = f"B{t}_{slot}"
                for mk, ln, op, up in (("HITS", .5, -160, 135), ("TB", 1.5, 110, -130), ("HR", .5, 420, -600)):
                    props.append(dict(game_id=gid, player_id=pid, market=mk, line=ln, over_price=op, under_price=up, book="DK"))
    for n, rows in (("games.csv", games), ("pitchers.csv", pitchers), ("batters.csv", batters), ("lineups.csv", lineups),
                    ("bullpen.csv", bullpen), ("parks.csv", parks), ("defense.csv", defense), ("odds.csv", odds),
                    ("prop_odds.csv", props)):
        write_csv(folder / n, rows)


# ---------------------------------------------------------------- comparison
def compare_folder(old, new, folder: Path) -> dict:
    inp_o, inp_n = old.load_inputs(str(folder)), new.load_inputs(str(folder))
    keyed_files = {"pitchers.csv": "player_id", "batters.csv": "player_id", "bullpen.csv": "team",
                   "parks.csv": "park", "defense.csv": "team"}
    keyed_identical = all(
        digest(old.load_keyed(str(folder / f), k)) == digest(new.load_keyed(str(folder / f), k))
        for f, k in keyed_files.items())
    res = dict(inputs_identical=digest(inp_o) == digest(inp_n), keyed_files_identical=keyed_identical,
               games=len(inp_o["games"]), games_priced=0, games_unpriced=0, preflight_identical=True,
               projection_mismatches=0, price_tables_identical=True, market_evals=0, market_eval_mismatches=0)
    evals_o, evals_n = [], []
    for g_o, g_n in zip(inp_o["games"], inp_n["games"]):
        po, pn = old.preflight_game_inputs(inp_o, g_o), new.preflight_game_inputs(inp_n, g_n)
        if po != pn:
            res["preflight_identical"] = False
        if po:
            res["games_unpriced"] += 1
            continue
        res["games_priced"] += 1
        pr_o, pr_n = old.project_game(inp_o, g_o), new.project_game(inp_n, g_n)
        f_o, v_o, x_o = old.price_game(pr_o, g_o)
        f_n, v_n, x_n = new.price_game(pr_n, g_n)
        if digest(pr_o) != digest(pr_n) or digest(v_o) != digest(v_n) or digest(x_o) != digest(x_n):
            res["projection_mismatches"] += 1
        for s in [r for r in inp_o["odds"] if r["game_id"] == g_o["game_id"]]:
            line = old._num(s.get("line"))
            try:
                a = f_o(s["market"], s["selection"], line)
            except Exception as e:                     # same exception class/text must come out of both
                a = ("EXC", type(e).__name__, str(e))
            try:
                b = f_n(s["market"], s["selection"], line)
            except Exception as e:
                b = ("EXC", type(e).__name__, str(e))
            res["market_evals"] += 1
            if digest(a) != digest(b):
                res["market_eval_mismatches"] += 1
    with tempfile.TemporaryDirectory() as to, tempfile.TemporaryDirectory() as tn:
        rows_o, md_o = old.run_card(inp_o, out_dir=to)
        rows_n, md_n = new.run_card(inp_n, out_dir=tn)
        files = {}
        for fn in ("mlb_card.csv", "mlb_card.md"):
            bo, bn = (Path(to) / fn).read_bytes(), (Path(tn) / fn).read_bytes()
            files[fn] = dict(identical=bo == bn, sha256=hashlib.sha256(bo).hexdigest())
    res["run_card"] = dict(rows=len(rows_o), prop_rows=sum(1 for r in rows_o if r["type"] == "prop"),
                           rows_identical=digest(rows_o) == digest(rows_n), markdown_identical=md_o == md_n, files=files)
    return res


def sum_into(tot: dict, r: dict):
    for k in ("games", "games_priced", "games_unpriced", "projection_mismatches", "market_evals", "market_eval_mismatches"):
        tot[k] += r[k]
    tot["card_rows"] += r["run_card"]["rows"]
    tot["prop_rows"] += r["run_card"]["prop_rows"]
    ok = (r["inputs_identical"] and r["keyed_files_identical"] and r["preflight_identical"]
          and r["projection_mismatches"] == 0 and r["market_eval_mismatches"] == 0
          and r["run_card"]["rows_identical"] and r["run_card"]["markdown_identical"]
          and all(v["identical"] for v in r["run_card"]["files"].values()))
    if not ok:
        tot["folders_not_identical"] += 1
    tot["folders"] += 1


# ---------------------------------------------------------------- negative / contract cases
def _outcome(fn):
    try:
        v = fn()
        return dict(status="ok", keys=sorted(map(repr, v)) if isinstance(v, dict) else None,
                    value=canon(v) if not isinstance(v, dict) else None)
    except Exception as e:
        return dict(status="raises", exc=type(e).__name__, msg=str(e))


NEG_CASES = [
    # name, file body (str) or None for missing file, key, expectation of (old status, new status/exc)
    ("valid_unique_keys", "player_id,team\na,A\nb,H\n", "player_id", ("ok", "ok")),
    ("valid_case_distinct_keys_a_vs_A", "player_id,team\na,A\nA,H\n", "player_id", ("ok", "ok")),
    ("valid_header_only", "player_id,team\n", "player_id", ("ok", "ok")),
    ("valid_utf8_bom_header", "\ufeffplayer_id,team\na,A\n", "player_id", ("ok", "ok")),
    ("valid_whitespace_padded_unique", "player_id,team\n a ,A\nb,H\n", "player_id", ("ok", "ok")),
    ("missing_file_still_empty", None, "player_id", ("ok", "ok")),
    ("duplicate_key_adjacent", "player_id,team,k9\na,A,9.1\na,A,4.0\n", "player_id", ("ok", "DuplicateInputKey")),
    ("duplicate_key_nonadjacent", "player_id,team\na,A\nb,H\nc,A\na,H\n", "player_id", ("ok", "DuplicateInputKey")),
    ("duplicate_key_after_strip", "player_id,team\na,A\n a ,H\n", "player_id", ("ok", "DuplicateInputKey")),
    ("duplicate_key_identical_rows", "player_id,team\na,A\na,A\n", "player_id", ("ok", "DuplicateInputKey")),
    ("blank_key_first_row", "player_id,team\n,A\n", "player_id", ("ok", "DuplicateInputKey")),
    ("blank_key_after_good_row", "player_id,team\na,A\n,H\n", "player_id", ("ok", "DuplicateInputKey")),
    ("whitespace_only_key", "player_id,team\n   ,A\n", "player_id", ("ok", "DuplicateInputKey")),
    ("two_blank_keys", "player_id,team\n,A\n,H\n", "player_id", ("ok", "DuplicateInputKey")),
    ("short_row_key_cell_absent", "team,player_id\nA\n", "player_id", ("ok", "DuplicateInputKey")),
    ("key_column_absent_from_header", "pid,team\na,A\n", "player_id", ("KeyError", "DuplicateInputKey")),
    ("header_key_misspelled_case", "Player_ID,team\na,A\n", "player_id", ("KeyError", "DuplicateInputKey")),
    ("ragged_extra_cells_malformed", "player_id,team\na,A,EXTRA\n", "player_id", ("AttributeError", "AttributeError")),
    ("invalid_utf8_malformed", b"player_id,team\na\xff\xfeb,A\n", "player_id", ("UnicodeDecodeError", "UnicodeDecodeError")),
]


def run_neg_case(old, new, name, body, key, expect) -> dict:
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "pitchers.csv")
        if body is not None:
            if isinstance(body, bytes):
                Path(p).write_bytes(body)
            else:
                with open(p, "w", encoding="utf-8", newline="") as fh:
                    fh.write(body)
        o, n = _outcome(lambda: old.load_keyed(p, key)), _outcome(lambda: new.load_keyed(p, key))
    ost = "ok" if o["status"] == "ok" else o["exc"]
    nst = "ok" if n["status"] == "ok" else n["exc"]
    same_when_ok = (o == n) if (ost == "ok" and nst == "ok") else None
    return dict(name=name, expected=list(expect), actual=[ost, nst], old=o, new=n, identical_when_ok=same_when_ok,
                as_intended=([ost, nst] == list(expect)) and (same_when_ok is not False))


def run_card_duplicate_demo(old, new) -> dict:
    """End to end: duplicate starter row. Old silently overwrites and prices a card; new refuses the folder."""
    with tempfile.TemporaryDirectory() as td:
        sdir = make_sample_folder(Path(td))
        with open(sdir / "pitchers.csv", newline="") as fh:
            rows = list(csv.DictReader(fh))
        dup = dict(rows[0]); dup["xera"] = "9.99"; dup["k_percent"] = "5.0"     # a later, wrong row
        write_csv(sdir / "pitchers.csv", rows + [dup], cols=list(rows[0].keys()))
        clean = make_sample_folder(Path(td) / "clean")
        c_rows, _ = old.run_card(str(clean), out_dir=str(Path(td) / "oc"))
        try:
            o_rows, _ = old.run_card(str(sdir), out_dir=str(Path(td) / "oo"))
            o = dict(status="priced_silently", card_rows=len(o_rows),
                     card_differs_from_clean=digest(o_rows) != digest(c_rows))
        except Exception as e:
            o = dict(status="raises", exc=type(e).__name__)
        try:
            n_rows, _ = new.run_card(str(sdir), out_dir=str(Path(td) / "on"))
            n = dict(status="priced_silently", card_rows=len(n_rows))
        except Exception as e:
            n = dict(status="raises", exc=type(e).__name__, msg=str(e))
    return dict(old=o, new=n, as_intended=o["status"] == "priced_silently" and o["card_differs_from_clean"]
                and n["status"] == "raises" and n["exc"] == "DuplicateInputKey")


def build_report(quick: bool = False) -> dict:
    old, old_sha, new, new_sha = load_pair()
    rep = dict(schema="sportsedge-mlb-input-safety-equivalence-v1", mode="quick" if quick else "full",
               approved_blob=APPROVED_BLOB, current_blob=CURRENT_BLOB,
               old_blob_computed=old_sha, new_blob_computed=new_sha, seed=RANDOM_SEED, corpora={})
    tot = dict(folders=0, folders_not_identical=0, games=0, games_priced=0, games_unpriced=0, card_rows=0,
               prop_rows=0, projection_mismatches=0, market_evals=0, market_eval_mismatches=0)
    with tempfile.TemporaryDirectory() as td:
        sdir = make_sample_folder(Path(td))
        r = compare_folder(old, new, sdir)
        rep["corpora"]["SAMPLE(make_samples.py seed 20261115, synthetic)"] = r
        sum_into(tot, r)
        slates = 12 if quick else RANDOM_SLATES
        agg = None
        for i in range(slates):
            f = Path(td) / f"slate{i}"
            f.mkdir()
            random_slate(f, i)
            r = compare_folder(old, new, f)
            sum_into(tot, r)
            rr = r["run_card"]
            agg = dict(slates=0, games=0, games_priced=0, card_rows=0, prop_rows=0) if agg is None else agg
            agg["slates"] += 1
            agg["games"] += r["games"]; agg["games_priced"] += r["games_priced"]
            agg["card_rows"] += rr["rows"]; agg["prop_rows"] += rr["prop_rows"]
        rep["corpora"][f"RANDOM(seed {RANDOM_SEED}, {slates} slates x {TEAMS_PER_SLATE // 2} games)"] = agg
    rep["totals"] = tot
    rep["negative_cases"] = [run_neg_case(old, new, *c) for c in NEG_CASES]
    rep["negative_cases_as_intended"] = all(c["as_intended"] for c in rep["negative_cases"])
    rep["run_card_duplicate_demo"] = run_card_duplicate_demo(old, new)
    rep["valid_input_bit_identical"] = (
        old_sha == APPROVED_BLOB and new_sha == CURRENT_BLOB and tot["folders_not_identical"] == 0
        and tot["projection_mismatches"] == 0 and tot["market_eval_mismatches"] == 0)
    return rep


if __name__ == "__main__":
    rep = build_report(quick="--quick" in sys.argv)
    args = [a for a in sys.argv[1:] if a != "--quick"]
    text = json.dumps(rep, indent=1, sort_keys=True)
    if args:
        Path(args[0]).write_text(text + "\n")
    print(json.dumps({k: rep[k] for k in ("mode", "old_blob_computed", "new_blob_computed", "totals",
                                           "valid_input_bit_identical", "negative_cases_as_intended")}, indent=1))
    sys.exit(0 if rep["valid_input_bit_identical"] and rep["negative_cases_as_intended"]
             and rep["run_card_duplicate_demo"]["as_intended"] else 1)
