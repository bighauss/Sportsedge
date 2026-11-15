#!/usr/bin/env python3
"""SportsEdge NFL full-slate runner (Claude, Nov 14 2026). PAPER research, Drive-only.

One command, every NFL market on the DK board:
  game lines  ML SPREAD TOTAL HOME_TT AWAY_TT + periods 1H_/1Q_.. -> team projections from the
              RIDGE_R1 ratings (pts = LG + off_T - def_O +/- hfa/2) fill home_proj/away_proj -> v5 PROJECTION
  props       PASS_YDS PASS_TDS RUSH_YDS REC_YDS RECEPTIONS (QB/RB/WR/TE) -> player mean from the 2026 curve,
              shrunk toward the 2026 position pool (weight n/(n+4)), scaled by the team's projected points / league
  TD markets  ATD TD2 FTD -> share from td_shares.csv (team,player,share) if supplied; else left blank and v5
              skips them with a note (never invented)
Then the R2 repair layer adds pooled_p / pooled_ev / flags / r2_keep. v5 is run unmodified (SHA checked).

Usage: python nfl_full_slate.py BOARD.csv --ratings nfl_ratings_asof_20261110.csv --curves E_prop_curves_nfl.csv
                                [--td-shares td_shares.csv] --engine sportsedge_v5.py --out OUTDIR
"""
import argparse, csv, hashlib, os, shutil, subprocess, sys, json, datetime

V5_SHA = "72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f"
CURVE = {  # board market -> curve market suffix, positions to look in (first hit wins)
    "PASS_YDS": ("passing_yards", ["QB"]), "PASS_TDS": ("passing_tds", ["QB"]),
    "RUSH_YDS": ("rushing_yards", ["RB", "QB"]), "REC_YDS": ("receiving_yards", ["WR", "TE", "RB"]),
    "RECEPTIONS": ("receptions", ["WR", "TE", "RB"]),
}
SCALED = {"PASS_YDS", "PASS_TDS", "RUSH_YDS", "REC_YDS", "RECEPTIONS"}
K_SHRINK = 4.0


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_ratings(p):
    R = {r["team"]: r for r in csv.DictReader(open(p))}
    any_r = next(iter(R.values()))
    return R, float(any_r["lg"]), float(any_r["hfa"])


def team_proj(R, lg, hfa, home, away):
    h, a = R[home], R[away]
    hp = lg + float(h["off"]) - float(a["def"]) + hfa / 2
    ap = lg + float(a["off"]) - float(h["def"]) - hfa / 2
    return round(hp, 2), round(ap, 2)


def load_curves(p):
    player, pooled = {}, {}
    for r in csv.DictReader(open(p)):
        if r["season"] != "2026":
            continue
        pos, _, stat = r["market"].partition("_")
        if r["scope"] == "POOLED":
            pooled[(pos, stat)] = float(r["mean"])
        else:
            player[(r["player"].lower(), pos, stat)] = (float(r["mean"]), int(r["n"]))
    return player, pooled


def prop_mean(player, pooled, name, market):
    stat, positions = CURVE[market]
    for pos in positions:
        hit = player.get((name.lower(), pos, stat))
        if hit:
            m, n = hit
            w = n / (n + K_SHRINK)
            return w * m + (1 - w) * pooled.get((pos, stat), m), pos, n
    return None, None, 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("board"); ap.add_argument("--ratings", required=True); ap.add_argument("--curves", required=True)
    ap.add_argument("--td-shares"); ap.add_argument("--adj"); ap.add_argument("--engine", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if sha(a.engine) != V5_SHA:
        sys.exit(f"REFUSED: engine SHA {sha(a.engine)[:12]} != v5 {V5_SHA[:12]}")
    if os.path.exists(a.out):
        sys.exit(f"REFUSED: {a.out} exists (outputs are create-only)")
    os.makedirs(a.out)
    R, lg, hfa = load_ratings(a.ratings)
    player, pooled = load_curves(a.curves)
    adj = {}
    if a.adj:
        for r in csv.DictReader(open(a.adj)):
            adj[r["team"]] = adj.get(r["team"], 0.0) + float(r["adj_pts"])
    shares = {}
    if a.td_shares:
        for r in csv.DictReader(open(a.td_shares)):
            shares[(r["team"], r["player"].lower())] = float(r["share"])
    rows = list(csv.DictReader(open(a.board, newline="", encoding="utf-8-sig")))
    cols = list(rows[0].keys())
    log, proj_cache = [], {}
    for r in rows:
        if r["sport"].upper() != "NFL":
            continue
        g = (r["home"], r["away"])
        if g not in proj_cache:
            if r["home"] not in R or r["away"] not in R:
                log.append(f"NO_RATING {r['away']} @ {r['home']} - left ANCHOR"); proj_cache[g] = None
            else:
                hp_, ap_ = team_proj(R, lg, hfa, *g)
                proj_cache[g] = (round(hp_ + adj.get(g[0], 0), 2), round(ap_ + adj.get(g[1], 0), 2))
                if adj.get(g[0]) or adj.get(g[1]): log.append(f"ADJ {g}: home {adj.get(g[0],0):+} away {adj.get(g[1],0):+}")
        pj = proj_cache[g]
        if pj:
            r["home_proj"], r["away_proj"] = pj
        mk = (r.get("market") or "").upper()
        if r.get("player"):
            if mk in CURVE:
                m, pos, n = prop_mean(player, pooled, r["player"], mk)
                if m is None:
                    log.append(f"NO_CURVE {r['player']} {mk} - ANCHOR"); continue
                if pj and mk in SCALED:
                    own = pj[0] if r.get("team") == r["home"] else pj[1]
                    m *= own / lg
                r["proj"] = round(m, 2); log.append(f"PROP {r['player']} {mk} mean {m:.1f} ({pos}, n={n})")
            elif mk in ("ATD", "TD2", "FTD"):
                s = shares.get((r.get("team"), r["player"].lower()))
                if s is None:
                    log.append(f"NO_TD_SHARE {r['player']} {mk} - skipped by v5"); continue
                r["proj"] = s
    filled = os.path.join(a.out, "board_projected.csv")
    with open(filled, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    shutil.copy(a.engine, os.path.join(a.out, "sportsedge_v5.py"))
    res = subprocess.run([sys.executable, "-I", "sportsedge_v5.py", "board_projected.csv"], cwd=a.out,
                         capture_output=True, text=True)
    open(os.path.join(a.out, "v5_output.txt"), "w").write(res.stdout + res.stderr)
    if res.returncode != 0:
        sys.exit("v5 failed - see v5_output.txt")
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import se_repair_layer as L
    picks = list(csv.DictReader(open(os.path.join(a.out, "picks.csv"))))
    out = L.repair(picks)
    with open(os.path.join(a.out, "picks_r2.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(picks[0].keys()) + ["pooled_p", "pooled_ev", "gap_pts", "flags", "r2_keep"])
        w.writeheader(); w.writerows(out)
    manifest = dict(created_ct=datetime.datetime.now().isoformat(), board=os.path.basename(a.board), board_sha=sha(a.board),
                    ratings_sha=sha(a.ratings), adj_sha=sha(a.adj) if a.adj else None, curves_sha=sha(a.curves), engine_sha=V5_SHA,
                    rows=len(rows), priced_sides=len(out), card=sum(float(p["ev"]) >= 0.01 for p in out),
                    r2_keep=sum(p["r2_keep"] for p in out), log=log)
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in manifest.items() if k != "log"}, indent=1))


if __name__ == "__main__":
    main()
