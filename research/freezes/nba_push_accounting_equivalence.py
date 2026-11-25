#!/usr/bin/env python3
"""NBA push-accounting transition evidence (da0c1503 -> b353de86). Research only.

Runs the previously approved model blob (pinned copy, git-blob-checked) and the
current model in isolated namespaces on byte-identical inputs and proves:
  * every market other than 1H_ML / 1Q_ML is bit-identical (float.hex, zero tolerance);
  * 1H_ML / 1Q_ML change exactly as the push-accounting contract says;
  * win/loss/push mass normalises (sums to 1) on every affected row.
Inputs are SYNTHETIC (no real NBA ratings/boards are committed); this proves code
behaviour, not forecast quality.  No network, no wagers, no promotion.
"""
from __future__ import annotations
import csv, hashlib, json, math, os, random, sys, tempfile, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD_BLOB = "da0c1503af5ed9ad548d1458588505f695b749e5"
NEW_BLOB = "b353de86445188288cab4050f6cae13eee76bff6"
OLD_PATH = HERE / "pinned_blobs" / "da0c1503_sportsedge_nba_model.py.txt"
NEW_PATH = ROOT / "models" / "nba" / "sportsedge_nba_model.py"
AFFECTED = ("1H_ML", "1Q_ML")
SEED = 20261125


def blob_sha1(b: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def load(path: Path, want: str, name: str) -> types.ModuleType:
    raw = path.read_bytes()
    if blob_sha1(raw) != want:
        raise SystemExit("BLOB_MISMATCH:" + str(path))
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), mod.__dict__)
    return mod


def hx(x):
    return float(x).hex() if isinstance(x, float) else x


def row_key(p):
    return (p["game_id"], p["market"], p["selection"], p["line"])


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def sample_board(tmp: Path):
    """models/nba/make_samples.py output (synthetic) + synthetic 1H/1Q ML rows."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ms", ROOT / "models/nba/make_samples.py")
    ms = importlib.util.module_from_spec(spec); spec.loader.exec_module(ms)
    d = tmp / "sample"; d.mkdir()
    ms.OUT = str(d); ms.main()
    return {n: str(d / (n + ".csv")) for n in
            ("teams", "games", "injuries", "players", "positional_defense", "odds", "props")}


def augment(paths, tmp: Path):
    rows = list(csv.DictReader(open(paths["odds"])))
    ext = []
    for gid, h, a in (("G1", "DEN", "LAL"), ("G2", "BOS", "MIA")):
        for seg in ("1H", "1Q"):
            ext += [dict(game_id=gid, market=seg + "_ML", selection=h, line="", price="-135"),
                    dict(game_id=gid, market=seg + "_ML", selection=a, line="", price="+115")]
    d = tmp / "augmented"; d.mkdir()
    out = dict(paths); out["odds"] = str(d / "odds.csv")
    write_csv(out["odds"], rows + ext)
    return out


def seeded_corpus(tmp: Path, n_games=2000):
    rnd = random.Random(SEED)
    teams = ["T%02d" % i for i in range(30)]
    d = tmp / "seeded"; d.mkdir()
    trows = []
    for t in teams:
        o = rnd.uniform(108, 122); df = rnd.uniform(108, 122)
        trows.append(dict(team=t, games=rnd.randint(5, 70), rating=round(o - df + rnd.uniform(-1, 1), 2),
                          ortg=round(o, 2), drtg=round(df, 2), pace=round(rnd.uniform(95, 103), 2),
                          ortg_l15=round(o + rnd.uniform(-3, 3), 2), drtg_l15=round(df + rnd.uniform(-3, 3), 2),
                          efg=round(rnd.uniform(.5, .59), 3), tov=round(rnd.uniform(.11, .15), 3),
                          orb=round(rnd.uniform(.23, .30), 3), ftr=round(rnd.uniform(.19, .27), 3),
                          opp_efg=round(rnd.uniform(.5, .59), 3), opp_tov=round(rnd.uniform(.11, .15), 3),
                          opp_orb=round(rnd.uniform(.23, .30), 3), opp_ftr=round(rnd.uniform(.19, .27), 3)))
    grows, orows, prows, plrows, inj = [], [], [], [], []
    for t in teams:
        for k, pos in enumerate("GGFFC"):
            plrows.append(dict(player=f"{t}-P{k}", team=t, pos=pos, starter=int(k < 4), minutes=rnd.randint(14, 36),
                               usage=round(rnd.uniform(.12, .32), 3), pts_pm=round(rnd.uniform(.3, .8), 3),
                               reb_pm=round(rnd.uniform(.08, .38), 3), ast_pm=round(rnd.uniform(.05, .3), 3),
                               fg3m_pm=round(rnd.uniform(.01, .12), 3)))
    def am(p):
        p = min(max(p, 0.03), 0.97)
        return int(round(-100 * p / (1 - p))) if p >= .5 else int(round(100 * (1 - p) / p))
    for g in range(n_games):
        h, a = rnd.sample(teams, 2); gid = "S%04d" % g
        grows.append(dict(game_id=gid, date="2026-01-01", tipoff_et="19:30", home=h, away=a, neutral=int(rnd.random() < .03),
                          home_b2b=int(rnd.random() < .15), away_b2b=int(rnd.random() < .2),
                          home_3in4=int(rnd.random() < .1), away_3in4=int(rnd.random() < .1),
                          away_tz_shift=rnd.choice([0, 0, 1, 2, 3])))
        if rnd.random() < .1:
            inj.append(dict(team=h, player=f"{h}-P{rnd.randint(0, 4)}", status=rnd.choice(["OUT", "QUESTIONABLE"]),
                            minutes=30, on_off_net=round(rnd.uniform(1, 6), 1)))
        # per-game market lines drawn around a noisy mean (integers included so pushes occur)
        mu = rnd.gauss(0, 7); tot = rnd.uniform(210, 240)
        def two(market, sel_a, sel_b, line_a, line_b):
            pa = 1 / (1 + math.exp(-rnd.uniform(-2.2, 2.2)))
            orows.append(dict(game_id=gid, market=market, selection=sel_a, line=line_a, price=am(pa + .02)))
            orows.append(dict(game_id=gid, market=market, selection=sel_b, line=line_b, price=am(1 - pa + .02)))
        for seg, f in (("", 1.0), ("1H_", .49), ("1Q_", .245)):
            if seg == "":
                two("ML", h, a, "", "")
            else:
                two(seg + "ML", h, a, "", "")
            sp = round(mu * f * 2) / 2 if rnd.random() < .5 else float(round(mu * f))
            two(seg + "SPREAD", h, a, -sp, sp)
            tl = round(tot * f * 2) / 2 if rnd.random() < .5 else float(round(tot * f))
            two(seg + "TOTAL", "OVER", "UNDER", tl, tl)
        two("TT_" + h, "OVER", "UNDER", round(tot / 2 * 2) / 2, round(tot / 2 * 2) / 2)
        if rnd.random() < .5:
            pl = f"{h}-P{rnd.randint(0, 4)}"
            prows.append(dict(game_id=gid, player=pl, stat=rnd.choice(["PTS", "REB", "AST", "3PM", "PRA"]),
                              line=rnd.choice([2.5, 5.5, 14.5, 21.5, 28.5, 3.0, 22.0]), over_price=-110, under_price=-110))
    for name, rows in (("teams", trows), ("games", grows), ("odds", orows), ("props", prows), ("players", plrows),
                       ("injuries", inj or [dict(team="", player="", status="", minutes=0, on_off_net=0)]),
                       ("positional_defense", [dict(team=teams[0], pos="G", pts_f=1.02, reb_f=1, ast_f=1, fg3m_f=1)])):
        write_csv(d / (name + ".csv"), rows)
    return {n: str(d / (n + ".csv")) for n in ("teams", "games", "injuries", "players", "positional_defense", "odds", "props")}


def run_corpus(label, paths, old, new):
    res = {"corpus": label, "games": 0, "priced_rows": 0, "affected_rows": 0, "unaffected_rows": 0,
           "unaffected_mismatch": 0, "projection_mismatch": 0, "prop_rows": 0, "prop_mismatch": 0,
           "affected_changed": 0, "affected_old_push_nonzero": 0, "affected_new_push_zero": 0,
           "affected_norm_violations": 0, "affected_push_asymmetry": 0,
           "card_unaffected_rows": 0, "card_unaffected_mismatch": 0, "by_market": {}}
    d_old, d_new = old.load_inputs(paths), new.load_inputs(paths)
    pj_o = {g["game_id"]: old.project_game(g, d_old) for g in d_old["games"]}
    pj_n = {g["game_id"]: new.project_game(g, d_new) for g in d_new["games"]}
    res["games"] = len(pj_o)
    for gid in pj_o:
        if {k: hx(v) for k, v in pj_o[gid].items()} != {k: hx(v) for k, v in pj_n[gid].items()}:
            res["projection_mismatch"] += 1
    # raw pricing function, every odds row (including rows the card would drop)
    raw = {}
    for r in d_old["odds"]:
        if r["game_id"] not in pj_o:
            continue
        a = old.price_game_market(r, pj_o[r["game_id"]]); b = new.price_game_market(r, pj_n[r["game_id"]])
        mk = r["market"]
        m = res["by_market"].setdefault(mk if mk.startswith(("1H_", "1Q_")) or not mk.startswith("TT_") else "TT_*",
                                        {"rows": 0, "identical": 0, "different": 0})
        m["rows"] += 1; res["priced_rows"] += 1
        same = tuple(map(hx, a)) == tuple(map(hx, b))
        m["identical" if same else "different"] += 1
        if mk in AFFECTED:
            res["affected_rows"] += 1
            res["affected_changed"] += (not same)
            res["affected_old_push_nonzero"] += (a[1] != 0)
            res["affected_new_push_zero"] += (b[1] == 0)
            raw[(r["game_id"], mk, r["selection"])] = (a, b)
        else:
            res["unaffected_rows"] += 1
            res["unaffected_mismatch"] += (not same)
    # normalisation + symmetry per game/market for affected rows
    seen = {}
    for (gid, mk, sel), (a, b) in raw.items():
        seen.setdefault((gid, mk), []).append((sel, a, b))
    for (gid, mk), lst in seen.items():
        if len(lst) != 2:
            continue
        (s1, a1, b1), (s2, a2, b2) = lst
        if abs(a1[0] + a2[0] - 1) > 1e-12 or a1[1] or a2[1]:
            res["affected_norm_violations"] += 1  # old: must be 2-outcome, sum 1
        if abs(b1[0] + b2[0] + b1[1] - 1) > 1e-12 or abs(b1[1] - b2[1]) > 1e-12:
            res["affected_norm_violations"] += 1
        res["affected_push_asymmetry"] += (abs(b1[1] - b2[1]) > 1e-12)
    # per-pick probability / EV shift on the affected markets (pre-rank, both sides priced two-way)
    ao = {row_key(p): p for p in old.price_games(d_old, pj_o) if p["market"] in AFFECTED}
    an = {row_key(p): p for p in new.price_games(d_new, pj_n) if p["market"] in AFFECTED}
    dp, dr, db, push = [], [], [], []
    flips = incl = stars_changed = 0
    for k in ao:
        o_, n_ = ao[k], an[k]
        dp.append(n_["model_p"] - o_["model_p"]); dr.append(n_["raw_ev"] - o_["raw_ev"]); db.append(n_["blend_ev"] - o_["blend_ev"])
        flips += ((o_["blend_ev"] > 0) != (n_["blend_ev"] > 0))
        incl += (n_["blend_ev"] > 0) - (o_["blend_ev"] > 0)
        stars_changed += ((old.stars(o_["blend_ev"]) if o_["blend_ev"] > 0 else 0) != (old.stars(n_["blend_ev"]) if n_["blend_ev"] > 0 else 0))
    st = lambda v: ({"n": len(v), "mean": sum(v) / len(v), "min": min(v), "max": max(v)} if v else {"n": 0})
    res["affected_pick_shift"] = {"model_p_delta": st(dp), "raw_ev_delta": st(dr), "blend_ev_delta": st(db),
                                  "blend_ev_positive_flips": flips, "net_card_inclusion_change": incl,
                                  "star_bucket_changes": stars_changed, "old_pick_rows": len(ao), "new_pick_rows": len(an)}
    # props + pre-rank card picks
    pl_o = old.project_players(d_old, pj_o); pl_n = new.project_players(d_new, pj_n)
    po, pn = old.price_props(d_old, pl_o), new.price_props(d_new, pl_n)
    res["prop_rows"] = len(po)
    res["prop_mismatch"] = (len(po) != len(pn)) + sum({k: hx(v) for k, v in a.items()} != {k: hx(v) for k, v in b.items()} for a, b in zip(po, pn))
    go, gn = old.price_games(d_old, pj_o), new.price_games(d_new, pj_n)
    mo = {row_key(p): p for p in go if p["market"] not in AFFECTED}
    mn = {row_key(p): p for p in gn if p["market"] not in AFFECTED}
    res["card_unaffected_rows"] = len(mo)
    res["card_unaffected_mismatch"] = (set(mo) != set(mn)) + sum({k: hx(v) for k, v in mo[k].items()} != {k: hx(v) for k, v in mn[k].items()} for k in mo if k in mn)
    # full run_card output: rows excluding affected markets, identical on every field except rank-derived ones
    with tempfile.TemporaryDirectory() as td:
        ro = old.run_card(paths, os.path.join(td, "o")); rn = new.run_card(paths, os.path.join(td, "n"))
        strip = lambda rows: {(r["game_id"], r["market"], r["selection"], r["line"]):
                              {k: hx(v) for k, v in r.items() if k not in ("rank", "flame", "stack")}
                              for r in rows if r["market"] not in AFFECTED}
        res["card_run_unaffected_identical"] = strip(ro["picks"]) == strip(rn["picks"])
        res["card_rows_old"], res["card_rows_new"] = len(ro["picks"]), len(rn["picks"])
        res["card_affected_rows_old"] = sum(p["market"] in AFFECTED for p in ro["picks"])
        res["card_affected_rows_new"] = sum(p["market"] in AFFECTED for p in rn["picks"])
        res["card_byte_identical"] = (open(ro["csv"], "rb").read() == open(rn["csv"], "rb").read()
                                      and open(ro["md"], "rb").read() == open(rn["md"], "rb").read())
    return res


def normalization_grid(old, new):
    """win/loss/push mass for every margin on a fine grid, both versions, both segments."""
    out = {}
    N = new.N
    for seg in ("1H", "1Q", "FG"):
        worst_sum, worst_sym, worst_tie, n = 0.0, 0.0, 0.0, 0
        min_push, max_push = 1.0, 0.0
        old_sum_dev = 0.0
        sm = new.SEG[seg][1]; sdv = new.SD["margin"] * sm
        for i in range(-800, 801):               # home margin projection -40.0 .. +40.0 in 0.05 steps
            mu_h = i * 0.05
            proj = {"margin": mu_h / new.SEG[seg][0], "total": 226.0, "home": "H", "away": "A",
                    "home_pts": 113.0, "away_pts": 113.0}
            mk = "ML" if seg == "FG" else seg + "_ML"
            h = new.price_game_market({"market": mk, "selection": "H", "line": ""}, proj)
            a = new.price_game_market({"market": mk, "selection": "A", "line": ""}, proj)
            oh = old.price_game_market({"market": mk, "selection": "H", "line": ""}, proj)
            oa = old.price_game_market({"market": mk, "selection": "A", "line": ""}, proj)
            worst_sum = max(worst_sum, abs(h[0] + a[0] + h[1] - 1))
            worst_sym = max(worst_sym, abs(h[1] - a[1]))
            old_sum_dev = max(old_sum_dev, abs(oh[0] + oa[0] - 1), abs(oh[1]), abs(oa[1]))
            tie = N.cdf((0.5 - mu_h) / sdv) - N.cdf((-0.5 - mu_h) / sdv)
            if seg != "FG":
                worst_tie = max(worst_tie, abs(h[1] - tie))
                min_push, max_push = min(min_push, h[1]), max(max_push, h[1])
            n += 1
        out[seg] = {"grid_points": n, "max_abs_dev_win_home_plus_win_away_plus_push_minus_1": worst_sum,
                    "max_abs_push_home_minus_push_away": worst_sym,
                    "max_abs_push_minus_closed_form_tie_band": worst_tie,
                    "push_range": [min_push, max_push] if seg != "FG" else [0.0, 0.0],
                    "old_max_dev_two_outcome_sum_or_push": old_sum_dev}
    return out


def contract_probes(old, new):
    proj = {"margin": 3.0, "total": 225.0, "home": "H", "away": "A", "home_pts": 114.0, "away_pts": 111.0,
            "game_id": "G", "inputs": ""}

    def price(mod, rows):
        try:
            return [{"market": p["market"], "selection": p["selection"], "model_p": p["model_p"], "raw_ev": p["raw_ev"]}
                    for p in mod.price_games({"odds": [dict(x) for x in rows]}, {"G": proj})]
        except Exception as e:  # pragma: no cover
            return "EXC:" + repr(e)
    mk = lambda market, legs: [dict(game_id="G", market=market, selection=s, line="", price=pr) for s, pr in legs]
    cases = {
        "three_way_H_A_TIE_under_1H_ML": mk("1H_ML", (("H", "-120"), ("A", "+210"), ("TIE", "+1000"))),
        "three_way_labelled_1H_ML_3WAY_H_A": mk("1H_ML_3WAY", (("H", "-120"), ("A", "+210"))),
        "three_way_labelled_1H_ML_3WAY_H_A_TIE": mk("1H_ML_3WAY", (("H", "-120"), ("A", "+210"), ("TIE", "+1000"))),
        "PARTIAL_capture_H_plus_TIE_only_under_1H_ML": mk("1H_ML", (("H", "-120"), ("TIE", "+1000"))),
        "two_way_H_A": mk("1H_ML", (("H", "-135"), ("A", "+115"))),
    }
    return {k: {"old": price(old, v), "new": price(new, v)} for k, v in cases.items()}


def run(n_games=2000):
    old = load(OLD_PATH, OLD_BLOB, "nba_v1"); new = load(NEW_PATH, NEW_BLOB, "nba_v2")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        base = sample_board(td)
        corp = [("sample_board_make_samples (synthetic; contains zero 1H/1Q ML rows)", base),
                ("sample_board_plus_synthetic_1H_1Q_ML_rows", augment(base, td)),
                (f"seeded_random_seed{SEED}_{n_games}games", seeded_corpus(td, n_games))]
        results = [run_corpus(l, p, old, new) for l, p in corp]
    return {"schema": "sportsedge-nba-push-accounting-equivalence-v1", "old_blob": OLD_BLOB, "new_blob": NEW_BLOB,
            "seed": SEED, "results": results, "normalization_grid": normalization_grid(old, new),
            "contract_probes": contract_probes(old, new)}


if __name__ == "__main__":
    out = run(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
    print(json.dumps(out, indent=1, sort_keys=True))
