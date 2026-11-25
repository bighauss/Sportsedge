#!/usr/bin/env python3
"""Output-equivalence harness: pinned CBB model blob f02dd29e vs PR #292 candidate 8bbe83b7.

Research/audit only. Loads BOTH versions of models/cbb/sportsedge_cbb_model.py in isolated
namespaces, feeds them byte-identical inputs and compares results bit for bit (floats compared
by float.hex, so the tolerance is exactly zero). Inputs:

  * BOARDS  - every committed CBB board in the repo (real matchups, lines and prices);
              Torvik team ratings / rosters are NOT committed anywhere in the repo, so they are
              generated deterministically from a hash of the team name (SYNTHETIC, labelled as such).
  * RANDOM  - a seeded synthetic corpus that exercises neutral/b2b/travel/altitude/injury/preseason
              branches and every priced market.
  * PROP_CASES - adversarial prop-identity fixtures; these are the INTENDED behaviour changes.

No network, no wall clock, no randomness beyond fixed seeds.
"""
from __future__ import annotations
import csv, hashlib, importlib.util, json, math, os, random, struct, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINNED_BLOB = "f02dd29ef444f49cdf4560a86d5b8a517519081d"
CANDIDATE_BLOB = "8bbe83b7a17d184b3521094b40e00be66ba0f852"
OLD_SRC = Path(__file__).with_name("pinned_blobs") / "f02dd29e_sportsedge_cbb_model.py.txt"
NEW_SRC = ROOT / "models/cbb/sportsedge_cbb_model.py"
BOARDS = (
    "models/cbb/lines/board_2026-11-21_0914CT_CBB.csv",
    "models/cbb/lines/board_2026-11-24_operator_transcript.csv",
    "research/cbb/boards/2026-11-24_operator_main_fallback.csv",
    "models/cbb/lines/board_2026-11-25_0636CT_pdf_capture.csv",
    "models/cbb/lines/board_2026-11-25_0636CT_pdf_capture_h1_corrected.csv",
    "models/cbb/lines/board_2026-11-25_0900CT_operator_transcript.csv",
)
RANDOM_SEED = 20261125
RANDOM_GAMES = 2500
RANDOM_TEAMS = 260


def git_blob(body: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()


def load_module(src: Path, name: str):
    body = src.read_bytes()
    spec = importlib.util.spec_from_loader(name, loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(body, str(src), "exec"), mod.__dict__)
    return mod, git_blob(body)


def load_pair():
    old, old_sha = load_module(OLD_SRC, "cbb_model_pinned_f02dd29e")
    new, new_sha = load_module(NEW_SRC, "cbb_model_candidate")
    return old, old_sha, new, new_sha


def canon(o):
    """Bit-exact canonical form: floats -> hex string (distinguishes -0.0, NaN payload-free)."""
    if isinstance(o, float):
        return "f:" + o.hex()
    if isinstance(o, dict):
        return {str(k): canon(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [canon(v) for v in o]
    return o


def digest(o) -> str:
    return hashlib.sha256(json.dumps(canon(o), sort_keys=True).encode()).hexdigest()


def _h(*parts) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big"))


# ----------------------------------------------------------------------------- synthetic inputs
def synth_team(name: str) -> dict:
    r = _h("team", name)
    g = r.randint(3, 30)
    oe, de, tp = r.uniform(95, 122), r.uniform(92, 115), r.uniform(62, 75)
    row = dict(team=name, games=g, adjoe=round(oe, 2), adjde=round(de, 2), adj_t=round(tp, 2),
               efg_o=round(r.uniform(46, 56), 1), efg_d=round(r.uniform(46, 56), 1),
               tov_o=round(r.uniform(14, 22), 1), tov_d=round(r.uniform(14, 22), 1),
               orb_o=round(r.uniform(24, 36), 1), orb_d=round(r.uniform(24, 36), 1),
               ftr_o=round(r.uniform(25, 42), 1), ftr_d=round(r.uniform(25, 42), 1),
               three_pa_rate=round(r.uniform(30, 48), 1), three_p_o=round(r.uniform(30, 40), 1),
               three_p_d=round(r.uniform(30, 40), 1),
               pre_adjoe=round(oe + r.uniform(-4, 4), 2) if r.random() < .5 else "",
               pre_adjde=round(de + r.uniform(-4, 4), 2) if r.random() < .5 else "",
               pre_adj_t=round(tp + r.uniform(-2, 2), 2) if r.random() < .5 else "",
               venue_hca=round(r.uniform(1.0, 5.5), 1) if r.random() < .35 else "",
               altitude=1 if r.random() < .06 else "")
    for k in ("efg_o", "tov_d", "orb_o", "ftr_d", "three_p_o", "adj_t"):   # exercise None paths
        if r.random() < .06:
            row[k] = ""
    return row


def synth_roster(team: str, extra=()) -> list:
    r = _h("roster", team)
    rows = []
    for i in range(8):
        rows.append(dict(player=f"{team} P{i + 1}", team=team, mpg=round(r.uniform(8, 36), 1),
                         usg=round(r.uniform(12, 31), 1), pts40=round(r.uniform(8, 28), 1),
                         reb40=round(r.uniform(2, 13), 1), ast40=round(r.uniform(1, 8), 1),
                         tpm40=round(r.uniform(0, 3.6), 2)))
    for nm in extra:
        rr = _h("extra", team, nm)
        rows.append(dict(player=nm, team=team, mpg=round(rr.uniform(18, 35), 1), usg=round(rr.uniform(16, 30), 1),
                         pts40=round(rr.uniform(10, 27), 1), reb40=round(rr.uniform(2, 12), 1),
                         ast40=round(rr.uniform(1, 8), 1), tpm40=round(rr.uniform(0, 3.4), 2)))
    return rows


def synth_game_flags(gid: str) -> dict:
    r = _h("game", gid)
    return dict(neutral=1 if r.random() < .12 else 0, away_tz_diff=r.choice([0, 0, 1, 2, 3]),
                away_b2b=1 if r.random() < .1 else 0, home_b2b=1 if r.random() < .1 else 0)


def synth_injuries(teams, rosters) -> list:
    out = []
    for t in sorted(teams):
        r = _h("inj", t)
        if r.random() < .18:
            p = r.choice(rosters[t])["player"]
            out.append(dict(team=t, player=p, status=r.choice(["out", "doubtful", "questionable", "probable"]),
                            role=r.choice(["", "", "top2", "rotation"])))
    return out


def write_csv(path, rows, cols=None):
    cols = cols or list(rows[0].keys()) if rows else cols
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


MARKET_MAP = {"SPREAD": "spread", "TOTAL": "total", "ML": "ml", "TT_HOME": "team_total_home",
              "TT_AWAY": "team_total_away", "ALT_SPREAD": "spread", "ALT_TOTAL": "total"}
PROP_STAT = {"PLAYER_POINTS_AT_LEAST": "pts", "PLAYER_REBOUNDS_AT_LEAST": "reb",
             "PLAYER_ASSISTS_AT_LEAST": "ast", "PLAYER_THREES_AT_LEAST": "tpm"}
UNSUPPORTED = ("PLAYER_PR_AT_LEAST", "PLAYER_PA_AT_LEAST", "PLAYER_PRA_AT_LEAST", "BOTH_TEAM_TOTAL")


def _am(x):
    x = (x or "").strip().replace("+", "")
    return int(float(x)) if x else None


def board_inputs(rel: str, idx: int, include_alt: bool = True) -> dict:
    """Translate one committed board into the model's CSV schemas (ratings/rosters synthetic)."""
    with open(ROOT / rel, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    games, gid_of, odds, props, skipped = [], {}, [], [], {}
    team_names, prop_players, seen_prop_names = set(), {}, {}
    for r in rows:
        if not include_alt and r.get("market", "").startswith("ALT_"):
            skipped[r["market"]] = skipped.get(r["market"], 0) + 1
            continue
        if r.get("market") in UNSUPPORTED:
            skipped[r["market"]] = skipped.get(r["market"], 0) + 1
            continue
        period = (r.get("period") or "FG").strip() or "FG"
        key = (r["home"], r["away"])
        if key not in gid_of:
            gid = f"B{idx}-{len(gid_of) + 1:03d}"
            gid_of[key] = gid
            games.append(dict(game_id=gid, home=r["home"], away=r["away"], **synth_game_flags(gid)))
            team_names.update(key)
        gid = gid_of[key]
        mk = r["market"]
        if mk in PROP_STAT:
            player = r["player"].strip()
            if not player:
                skipped["PROP_BLANK_PLAYER"] = skipped.get("PROP_BLANK_PLAYER", 0) + 1
                continue
            if seen_prop_names.setdefault(player, gid) != gid:      # keep names unique across games
                skipped["PROP_NAME_IN_TWO_GAMES"] = skipped.get("PROP_NAME_IN_TWO_GAMES", 0) + 1
                continue
            tm = r["home"] if _h("propteam", player).random() < .5 else r["away"]
            prop_players.setdefault(tm, [])
            if player not in prop_players[tm]:
                prop_players[tm].append(player)
            pa, pb = _am(r["price_a"]), _am(r["price_b"])
            props.append(dict(game_id=gid, player=player, stat=PROP_STAT[mk], line=float(r["line"]) - 0.5,
                              over_price=pa if pa else -110, under_price=pb if pb else -110))
            continue
        if mk not in MARKET_MAP:
            skipped[mk] = skipped.get(mk, 0) + 1
            continue
        if period == "1H":
            mkt = {"TOTAL": "h1_total", "SPREAD": "h1_spread"}.get(mk)
            if not mkt:
                skipped["1H_" + mk] = skipped.get("1H_" + mk, 0) + 1
                continue
        else:
            mkt = MARKET_MAP[mk]
        pa, pb = _am(r["price_a"]), _am(r["price_b"])
        if pa is None or pb is None:
            skipped["MISSING_PRICE_" + mk] = skipped.get("MISSING_PRICE_" + mk, 0) + 1
            continue
        line = r["line"].strip()
        if mkt == "ml":
            sides = (("home", "", pb, pa), ("away", "", pa, pb))     # a/b order is arbitrary here
        elif mkt in ("spread", "h1_spread"):
            L = float(line)
            sides = (("home", L, pa, pb), ("away", -L, pb, pa))
        else:
            L = float(line)
            sides = (("over", L, pa, pb), ("under", L, pb, pa))
        for side, ln, p1, p2 in sides:
            odds.append(dict(game_id=gid, market=mkt, side=side, line=ln, price_american=p1, opp_price_american=p2))
    rosters = {t: synth_roster(t, prop_players.get(t, ())) for t in sorted(team_names)}
    return dict(teams=[synth_team(t) for t in sorted(team_names)],
                players=[p for t in sorted(rosters) for p in rosters[t]],
                games=games, injuries=synth_injuries(team_names, rosters), odds=odds, props=props,
                meta=dict(board=rel, skipped=skipped, games=len(games), odds=len(odds), props=len(props),
                          teams=len(team_names)))


def random_inputs(n_games: int = RANDOM_GAMES) -> dict:
    r = random.Random(RANDOM_SEED)
    names = [f"Team{i:03d}" for i in range(RANDOM_TEAMS)] + ["BYU", "Utah", "Air Force", "Wyoming", "New Mexico",
                                                             "Utah St.", "Colorado St.", "Denver", "Nevada", "Weber St."]
    rosters = {t: synth_roster(t) for t in names}
    games, odds, props = [], [], []
    for i in range(n_games):
        h, a = r.sample(names, 2)
        gid = f"R{i:05d}"
        games.append(dict(game_id=gid, home=h, away=a, neutral=r.choice([0, 0, 0, 1, ""]),
                          away_tz_diff=r.choice([0, 1, 2, 3, ""]), away_b2b=r.choice([0, 0, 1, ""]),
                          home_b2b=r.choice([0, 0, 1])))
        def pair():
            pr = r.choice([-250, -190, -150, -120, -110, -105, 100, 105, 110, 130, 180, 240])
            return pr, r.choice([-250, -190, -150, -120, -110, -105, 100, 105, 110, 130, 180, 240])
        for mk, sides, lines in (("ml", ("home", "away"), [""]),
                                 ("spread", ("home", "away"), [round(r.uniform(-18, 18) * 2) / 2]),
                                 ("total", ("over", "under"), [round(r.uniform(120, 170) * 2) / 2]),
                                 ("team_total_home", ("over", "under"), [round(r.uniform(55, 90) * 2) / 2]),
                                 ("team_total_away", ("over", "under"), [round(r.uniform(55, 90) * 2) / 2]),
                                 ("h1_total", ("over", "under"), [round(r.uniform(55, 85) * 2) / 2]),
                                 ("h1_spread", ("home", "away"), [round(r.uniform(-9, 9) * 2) / 2])):
            if r.random() < .15:
                continue
            p1, p2 = pair()
            L = lines[0]
            l1, l2 = (L, -L if L != "" else "") if mk in ("spread", "h1_spread") else (L, L)
            if mk == "ml":
                l1 = l2 = ""
            odds.append(dict(game_id=gid, market=mk, side=sides[0], line=l1, price_american=p1, opp_price_american=p2))
            odds.append(dict(game_id=gid, market=mk, side=sides[1], line=l2, price_american=p2, opp_price_american=p1))
        for _ in range(r.choice([0, 0, 1, 2])):
            tm = r.choice([h, a])
            pl = r.choice(rosters[tm])["player"]
            props.append(dict(game_id=gid, player=pl, stat=r.choice(["pts", "reb", "ast", "tpm"]),
                              line=round(r.uniform(1.5, 25) * 2) / 2, over_price=r.choice([-130, -115, -110, 105, 120]),
                              under_price=r.choice([-130, -115, -110, 105, 120])))
    return dict(teams=[synth_team(t) for t in names], players=[p for t in names for p in rosters[t]],
                games=games, injuries=synth_injuries(names, rosters), odds=odds, props=props,
                meta=dict(board="RANDOM_SEED_%d" % RANDOM_SEED, games=len(games), odds=len(odds),
                          props=len(props), teams=len(names), skipped={}))


# ----------------------------------------------------------------------------- comparison
def materialize(inputs: dict, d: Path) -> dict:
    paths = {}
    for k in ("teams", "players", "games", "injuries", "odds", "props"):
        p = d / f"{k}.csv"
        rows = inputs[k]
        if rows:
            cols = []
            for row in rows:
                for c in row:
                    if c not in cols:
                        cols.append(c)
            write_csv(p, rows, cols)
        else:
            p.write_text("")
        paths[k] = str(p)
    return paths


def _try(fn, *a):
    try:
        return ("ok", fn(*a))
    except Exception as e:  # noqa: BLE001 - outcome parity includes exception type/message
        return ("exc", f"{type(e).__name__}:{e}")


def compare_primitives(old, new, paths) -> dict:
    """Game projections and every market probability/price, old vs new, on identical loaded inputs."""
    res = {}
    teams_o, teams_n = old.load_teams(paths["teams"]), new.load_teams(paths["teams"])
    pl_o, pl_n = old.load_players(paths["players"]), new.load_players(paths["players"])
    games_o, games_n = old.read_csv(paths["games"]), new.read_csv(paths["games"])
    inj_o, inj_n = {}, {}
    for r in old.read_csv(paths["injuries"]):
        inj_o.setdefault(r["team"], []).append(r)
    for r in new.read_csv(paths["injuries"]):
        inj_n.setdefault(r["team"], []).append(r)
    assert canon(teams_o) == canon(teams_n) and canon(pl_o) == canon(pl_n) and canon(games_o) == canon(games_n)
    proj_o, proj_n = {}, {}
    mism_proj = 0
    for go, gn in zip(games_o, games_n):
        po, pn = old.project_game(go, teams_o, inj_o, pl_o), new.project_game(gn, teams_n, inj_n, pl_n)
        proj_o[go["game_id"]], proj_n[gn["game_id"]] = po, pn
        mism_proj += canon(po) != canon(pn)
    res["games_projected"] = len(games_o)
    res["game_projection_mismatches"] = mism_proj
    res["game_projection_sha256_old"] = digest(proj_o)
    res["game_projection_sha256_new"] = digest(proj_n)
    odds_o, odds_n = old.read_csv(paths["odds"]), new.read_csv(paths["odds"])
    n = mism = 0
    by = {}
    out_o, out_n = [], []
    for oo, on in zip(odds_o, odds_n):
        gid = oo["game_id"]
        mk, sd = oo["market"], oo["side"]
        line = old._f(oo.get("line"), 0.0)
        ro = (_try(old.projection_for, proj_o[gid], mk), _try(old.model_prob, proj_o[gid], mk, sd, line),
              _try(old.contradicts, sd, line, old.projection_for(proj_o[gid], mk)),
              _try(old.captured_opposite, oo, odds_o))
        rn = (_try(new.projection_for, proj_n[gid], mk), _try(new.model_prob, proj_n[gid], mk, sd, line),
              _try(new.contradicts, sd, line, new.projection_for(proj_n[gid], mk)),
              _try(new.captured_opposite, on, odds_n))
        if ro[3][0] == "ok" and ro[1][0] == "ok":
            po = _try(old.price_row, ro[1][1], oo["price_american"], ro[3][1])
            pn = _try(new.price_row, rn[1][1], on["price_american"], rn[3][1])
            ro, rn = ro + (po,), rn + (pn,)
        n += 1
        bad = canon(ro) != canon(rn)
        mism += bad
        s = by.setdefault(mk, [0, 0])
        s[0] += 1
        s[1] += bad
        out_o.append(ro)
        out_n.append(rn)
    res["market_rows_priced"] = n
    res["market_row_mismatches"] = mism
    res["by_market_rows_mismatches"] = {k: v for k, v in sorted(by.items())}
    res["market_sha256_old"], res["market_sha256_new"] = digest(out_o), digest(out_n)
    return res


def compare_run_card(old, new, inputs) -> dict:
    """Full run_card(): rows, dropped, projections, stacks and the two output files, byte for byte."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        paths = materialize(inputs, td)
        ro = old.run_card(paths, out_dir=str(td / "old"))
        rn = new.run_card(paths, out_dir=str(td / "new"))
        files = {}
        for f in ("cbb_card.csv", "cbb_card.md"):
            a, b = (td / "old" / f).read_bytes(), (td / "new" / f).read_bytes()
            files[f] = dict(identical=a == b, bytes=len(a), sha256_old=hashlib.sha256(a).hexdigest(),
                            sha256_new=hashlib.sha256(b).hexdigest())
        game_rows_o = [r for r in ro["rows"] if r["type"] == "game"]
        game_rows_n = [r for r in rn["rows"] if r["type"] == "game"]
        prop_rows_o = [r for r in ro["rows"] if r["type"] == "prop"]
        prop_rows_n = [r for r in rn["rows"] if r["type"] == "prop"]
        return dict(
            rows_total=len(ro["rows"]), rows_game=len(game_rows_o), rows_prop=len(prop_rows_o),
            rows_identical=canon(ro["rows"]) == canon(rn["rows"]),
            game_rows_identical=canon(game_rows_o) == canon(game_rows_n),
            prop_rows_identical=canon(prop_rows_o) == canon(prop_rows_n),
            dropped_total=len(ro["dropped"]), dropped_identical=ro["dropped"] == rn["dropped"],
            projections_identical=canon(ro["projections"]) == canon(rn["projections"]),
            stacks_identical=canon(ro["stacks"]) == canon(rn["stacks"]), files=files)


# ----------------------------------------------------------------------------- intended prop diffs
def _player(name, team, **kw):
    d = dict(player=name, team=team, mpg=30, usg=24, pts40=20.0, reb40=6.0, ast40=3.0, tpm40=2.0)
    d.update(kw)
    return d


def prop_cases() -> list:
    teams = [synth_team(t) for t in ("Alpha", "Beta", "Gamma", "Delta")]
    base_players = [
        _player("Solo Alpha", "Alpha"), _player("Dup Name", "Alpha"), _player("Dup Name", "Beta", pts40=30.0, mpg=34),
        _player("Cross Name", "Alpha"), _player("Cross Name", "Gamma", pts40=12.0, mpg=22), _player("Only Delta", "Delta"),
        _player("Idd One", "Alpha", player_id="A1"), _player("Idd Two", "Beta", player_id="B1"),
        _player("Filler Beta", "Beta"), _player("Filler Gamma", "Gamma", mpg=22),
    ]
    games = [dict(game_id="G1", home="Alpha", away="Beta", neutral=0, away_tz_diff=0, away_b2b=0, home_b2b=0),
             dict(game_id="G2", home="Gamma", away="Delta", neutral=0, away_tz_diff=0, away_b2b=0, home_b2b=0)]
    # Low line + plus-money over => the over side has positive blended EV and survives the card filter.
    mk = lambda gid, player, **kw: dict(dict(game_id=gid, player=player, stat="pts", line=8.5,
                                             over_price=150, under_price=-180), **kw)
    cases = [
        ("CONTROL_unique_player_in_event", [mk("G1", "Solo Alpha")], "IDENTICAL", None),
        ("same_name_two_teams_in_different_games", [mk("G2", "Cross Name")], "DIFFERENT",
         "old priced Alpha's Cross Name (not in G2) because first global name match wins; new resolves to Gamma's"),
        ("same_name_on_both_event_teams_no_team_hint", [mk("G1", "Dup Name")], "DIFFERENT",
         "old priced first-listed Alpha player silently; new quarantines AMBIGUOUS_PROP_PLAYER"),
        ("same_name_both_teams_with_team_hint", [mk("G1", "Dup Name", team="Beta")], "DIFFERENT_ROW_TEAM",
         "old ignored team hint (priced Alpha's player); new honours hint (Beta)"),
        ("player_exists_only_in_other_game", [mk("G1", "Only Delta")], "DIFFERENT",
         "old priced a player from a different game; new drops PROP_PLAYER_NOT_ON_EVENT_ROSTER"),
        ("player_unknown_everywhere", [mk("G1", "Nobody Known")], "DROP_REASON_ONLY",
         "both emit no row; new records PROP_PLAYER_NOT_ON_EVENT_ROSTER in dropped"),
        ("team_hint_not_in_event", [mk("G1", "Solo Alpha", team="Gamma")], "DIFFERENT",
         "old ignored hint and priced; new drops PROP_TEAM_NOT_IN_EVENT"),
        ("blank_subject", [mk("G1", "")], "DROP_REASON_ONLY",
         "both emit no row; new records PROP_SUBJECT_MISSING"),
        ("optional_player_id_mismatch", [mk("G1", "Idd One", player_id="WRONG")], "DIFFERENT",
         "old ignored player_id and priced; new drops (no roster row matches the id)"),
        ("optional_player_id_match", [mk("G1", "Idd One", player_id="A1")], "IDENTICAL", None),
        ("unknown_game_id", [mk("G9", "Solo Alpha")], "OLD_CRASH",
         "old raised KeyError and aborted the whole card; new records PROP_EVENT_NOT_FOUND"),
    ]
    out = []
    for name, props, expect, why in cases:
        out.append(dict(name=name, expect=expect, why=why, inputs=dict(
            teams=teams, players=base_players, games=games, injuries=[], odds=[], props=props)))
    return out


def run_prop_case(old, new, case) -> dict:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        inp = dict(case["inputs"])
        inp["odds"] = []
        paths = materialize(inp, td)
        paths["odds"] = ""            # model tolerates a missing odds file (read_csv -> [])
        r = {}
        for tag, mod in (("old", old), ("new", new)):
            try:
                res = mod.run_card(paths, out_dir=str(td / tag))
                r[tag] = dict(status="ok", rows=[(x["bet"], x["team"]) for x in res["rows"] if x["type"] == "prop"],
                              prop_row_digest=digest([x for x in res["rows"] if x["type"] == "prop"]),
                              dropped=list(res["dropped"]))
            except Exception as e:  # noqa: BLE001
                r[tag] = dict(status="crash", error=f"{type(e).__name__}:{e}")
        o, n = r["old"], r["new"]
        if o["status"] == "crash":
            actual = "OLD_CRASH"
        elif o["rows"] == n["rows"] and o["prop_row_digest"] == n["prop_row_digest"]:
            actual = "IDENTICAL" if o["dropped"] == n["dropped"] else "DROP_REASON_ONLY"
        elif [b for b, _ in o["rows"]] == [b for b, _ in n["rows"]] and o["rows"] != n["rows"] and n["rows"]:
            actual = "DIFFERENT_ROW_TEAM" if case["expect"] == "DIFFERENT_ROW_TEAM" else "DIFFERENT"
        else:
            actual = "DIFFERENT"
        return dict(name=case["name"], expected=case["expect"], actual=actual, why=case["why"], old=o, new=n)


def build_report(quick: bool = False) -> dict:
    old, old_sha, new, new_sha = load_pair()
    rep = dict(schema="sportsedge-cbb-repin-equivalence-v1", mode="quick" if quick else "full", pinned_blob=PINNED_BLOB, candidate_blob=CANDIDATE_BLOB,
               old_blob_computed=old_sha, new_blob_computed=new_sha, tolerance="exact (float.hex equality, zero tolerance)",
               ratings_note="Torvik team ratings/rosters are not committed in the repo; they are deterministic "
                            "SYNTHETIC values derived from sha256(team name). Matchups, lines and prices on BOARDS are real committed data.",
               corpora={})
    corpora = [(rel, board_inputs(rel, i + 1, include_alt=not quick)) for i, rel in enumerate(BOARDS)] + \
        [("RANDOM", random_inputs(400 if quick else RANDOM_GAMES))]
    tot = dict(games=0, market_rows=0, prop_rows=0, game_proj_mismatch=0, market_mismatch=0)
    for name, inp in corpora:
        with tempfile.TemporaryDirectory() as td:
            paths = materialize(inp, Path(td))
            prim = compare_primitives(old, new, paths)
        rc = compare_run_card(old, new, inp)
        rep["corpora"][name] = dict(meta=inp["meta"], primitives=prim, run_card=rc)
        tot["games"] += prim["games_projected"]
        tot["market_rows"] += prim["market_rows_priced"]
        tot["prop_rows"] += rc["rows_prop"]
        tot["game_proj_mismatch"] += prim["game_projection_mismatches"]
        tot["market_mismatch"] += prim["market_row_mismatches"]
    rep["totals"] = tot
    rep["prop_cases"] = [run_prop_case(old, new, c) for c in prop_cases()]
    rep["equivalent_game_path"] = (
        old_sha == PINNED_BLOB and new_sha == CANDIDATE_BLOB and tot["game_proj_mismatch"] == 0
        and tot["market_mismatch"] == 0
        and all(v["run_card"]["rows_identical"] and v["run_card"]["dropped_identical"]
                and v["run_card"]["projections_identical"] and v["run_card"]["stacks_identical"]
                and all(f["identical"] for f in v["run_card"]["files"].values())
                for v in rep["corpora"].values()))
    rep["prop_cases_as_intended"] = all(c["expected"] == c["actual"] for c in rep["prop_cases"])
    return rep


if __name__ == "__main__":
    rep = build_report(quick="--quick" in sys.argv)
    args = [a for a in sys.argv[1:] if a != "--quick"]
    text = json.dumps(rep, indent=1, sort_keys=True)
    if args:
        Path(args[0]).write_text(text + "\n")
    print(text)
    sys.exit(0 if rep["equivalent_game_path"] and rep["prop_cases_as_intended"] else 1)
