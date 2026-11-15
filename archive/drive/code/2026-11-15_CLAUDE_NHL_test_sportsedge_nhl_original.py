#!/usr/bin/env python3
"""Synthetic samples + end-to-end test. No network, stdlib only.
Run: python3 test_sportsedge_nhl.py   (writes samples/ and out/ next to this file)"""
import csv, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sportsedge_nhl_model as m

SD = os.path.join(HERE, "samples")
TEAMS = ["BOS", "TOR", "DET", "CHI", "VGK", "SEA"]


def w(path, rows):
    with open(path, "w", newline="") as f:
        dw = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        dw.writeheader(); dw.writerows(rows)


def make_samples():
    rnd = random.Random(7)
    os.makedirs(SD, exist_ok=True)
    teams, goalies, skaters, ratings = [], [], [], []
    for t in TEAMS:
        gp = 18; q = rnd.uniform(-0.25, 0.25)
        def row(sit, ice_min, xgf, xga, extra=None):
            r = {"team": t, "situation": sit, "games_played": gp, "iceTime": round(ice_min * 60 * gp),
                 "xGoalsFor": round(xgf * gp, 2), "xGoalsAgainst": round(xga * gp, 2),
                 "scoreVenueAdjustedxGoalsFor": round(xgf * gp * 1.01, 2),
                 "scoreVenueAdjustedxGoalsAgainst": round(xga * gp * 0.99, 2),
                 "shotsOnGoalFor": 0, "shotsOnGoalAgainst": 0, "shotAttemptsFor": 0,
                 "shotAttemptsAgainst": 0, "penaltiesFor": 0, "penaltiesAgainst": 0}
            if extra: r.update(extra)
            return r
        teams.append(row("5on5", 47, 2.2 * (1 + q), 2.2 * (1 - q)))
        teams.append(row("5on4", 5.5, 0.62, 0.05))
        teams.append(row("4on5", 5.5, 0.05, 0.60 * (1 - q / 2)))
        teams.append(row("all", 60, 3.0 * (1 + q), 3.0 * (1 - q), {
            "shotsOnGoalFor": round(29 * (1 + q / 2) * gp), "shotsOnGoalAgainst": round(29 * (1 - q / 2) * gp),
            "shotAttemptsFor": round(58 * (1 + q / 2) * gp), "shotAttemptsAgainst": round(58 * (1 - q / 2) * gp),
            "penaltiesFor": round(rnd.uniform(2.6, 3.6) * gp), "penaltiesAgainst": round(rnd.uniform(2.6, 3.6) * gp)}))
        ratings.append({"team": t, "off_gpg": round(3.05 * (1 + q * 0.8), 3), "def_gpg": round(3.05 * (1 - q * 0.8), 3)})
        for gi, (shots, sv_edge) in enumerate(((420, rnd.uniform(-8, 8)), (150, rnd.uniform(-4, 4)))):
            xg = shots * 0.097
            goalies.append({"name": "%s_G%d" % (t, gi + 1), "team": t, "situation": "all", "games_played": 14 if gi == 0 else 4,
                            "xGoals": round(xg, 2), "goals": round(xg - sv_edge), "ongoal": shots})
        for pi in range(1, 4):
            toi = 20 - pi * 2
            ice = toi * 60 * gp
            cf = 4.8 * toi / 60 * 3 * gp * (1 + q / 2)
            oixg = 3.0 * toi / 60 * gp * (1 + q)
            skaters.append({"name": "%s_F%d" % (t, pi), "team": t, "position": "C", "situation": "all", "games_played": gp,
                            "icetime": ice, "I_F_shotAttempts": round(cf), "I_F_shotsOnGoal": round(cf * 0.52),
                            "I_F_points": round(oixg * 0.7 * 1.0), "OnIce_F_xGoals": round(oixg, 2),
                            "OnIce_F_goals": round(oixg)})
    w(os.path.join(SD, "teams.csv"), teams)
    w(os.path.join(SD, "goalies.csv"), goalies)
    w(os.path.join(SD, "skaters.csv"), skaters)
    w(os.path.join(SD, "ratings.csv"), ratings)
    games = [
        dict(game_id="G1", date="2026-11-15", start_time="19:00 ET", venue="TD Garden", home="BOS", away="TOR",
             home_goalie="BOS_G1", away_goalie="TOR_G1", home_goalie_confirmed=1, away_goalie_confirmed=1,
             home_goalie_is_backup=0, away_goalie_is_backup=0, home_b2b=0, away_b2b=1,
             home_tz_shift=0, away_tz_shift=0, home_lineup_adj=0, away_lineup_adj=-0.08),
        dict(game_id="G2", date="2026-11-15", start_time="22:00 ET", venue="Climate Pledge Arena", home="SEA", away="DET",
             home_goalie="SEA_G2", away_goalie="DET_G1", home_goalie_confirmed=1, away_goalie_confirmed=1,
             home_goalie_is_backup=1, away_goalie_is_backup=0, home_b2b=0, away_b2b=0,
             home_tz_shift=0, away_tz_shift=3, home_lineup_adj=0, away_lineup_adj=0),
        dict(game_id="G3", date="2026-11-15", start_time="20:00 ET", venue="United Center", home="CHI", away="VGK",
             home_goalie="CHI_G1", away_goalie="VGK_G1", home_goalie_confirmed=1, away_goalie_confirmed=0,
             home_goalie_is_backup=0, away_goalie_is_backup=0, home_b2b=0, away_b2b=0,
             home_tz_shift=0, away_tz_shift=2, home_lineup_adj=0, away_lineup_adj=0),
    ]
    w(os.path.join(SD, "games.csv"), games)
    odds = []
    for gid, hml, aml in (("G1", -135, 115), ("G2", 105, -125), ("G3", 150, -175)):
        b = "SampleBook"
        odds += [dict(game_id=gid, market="ML", selection="home", line="", price=hml, book=b),
                 dict(game_id=gid, market="ML", selection="away", line="", price=aml, book=b),
                 dict(game_id=gid, market="ML3", selection="home", line="", price=hml + 150 if hml > 0 else 150, book=b),
                 dict(game_id=gid, market="ML3", selection="draw", line="", price=320, book=b),
                 dict(game_id=gid, market="ML3", selection="away", line="", price=aml + 150 if aml > 0 else 170, book=b),
                 dict(game_id=gid, market="PL", selection="home", line=-1.5, price=210, book=b),
                 dict(game_id=gid, market="PL", selection="away", line=1.5, price=-260, book=b),
                 dict(game_id=gid, market="TOTAL", selection="over", line=6.5, price=110, book=b),
                 dict(game_id=gid, market="TOTAL", selection="under", line=6.5, price=-130, book=b),
                 dict(game_id=gid, market="TOTAL", selection="over", line=6, price=-105, book=b),
                 dict(game_id=gid, market="TOTAL", selection="under", line=6, price=-115, book=b),
                 dict(game_id=gid, market="TT_HOME", selection="over", line=2.5, price=-150, book=b),
                 dict(game_id=gid, market="TT_HOME", selection="under", line=2.5, price=120, book=b),
                 dict(game_id=gid, market="TT_AWAY", selection="over", line=3.5, price=180, book=b),
                 dict(game_id=gid, market="TT_AWAY", selection="under", line=3.5, price=-220, book=b),
                 dict(game_id=gid, market="P1_ML3", selection="home", line="", price=180, book=b),
                 dict(game_id=gid, market="P1_ML3", selection="draw", line="", price=135, book=b),
                 dict(game_id=gid, market="P1_ML3", selection="away", line="", price=230, book=b),
                 dict(game_id=gid, market="P1_TOTAL", selection="over", line=1.5, price=-120, book=b),
                 dict(game_id=gid, market="P1_TOTAL", selection="under", line=1.5, price=100, book=b)]
    w(os.path.join(SD, "odds.csv"), odds)
    props = [
        dict(game_id="G1", player="BOS_F1", team="BOS", opp="TOR", market="SOG", line=2.5, over_price=-140, under_price=115, proj_toi=19.5),
        dict(game_id="G1", player="TOR_F1", team="TOR", opp="BOS", market="SOG", line=3.5, over_price=120, under_price=-145, proj_toi=""),
        dict(game_id="G1", player="BOS_F2", team="BOS", opp="TOR", market="POINTS", line=0.5, over_price=-120, under_price=-105, proj_toi=""),
        dict(game_id="G2", player="SEA_G2", team="SEA", opp="DET", market="SAVES", line=26.5, over_price=-115, under_price=-110, proj_toi=""),
        dict(game_id="G2", player="DET_F1", team="DET", opp="SEA", market="SOG", line=2.5, over_price=-110, under_price=-110, proj_toi=""),
    ]
    w(os.path.join(SD, "props.csv"), props)
    inputs = {k + "_csv": os.path.join("samples", k + ".csv")
              for k in ("teams", "goalies", "skaters", "ratings", "games", "odds", "props")}
    inputs["out_dir"] = "out"
    with open(os.path.join(SD, "inputs.json"), "w") as f:
        json.dump(inputs, f, indent=1)
    return {k: (os.path.join(HERE, v) if k != "out_dir" else os.path.join(HERE, "out")) for k, v in inputs.items()}


def close(a, b, tol=1e-6):
    return abs(a - b) < tol


def main():
    inputs = make_samples()
    res = m.run_card(inputs)
    checks = []
    def ok(name, cond):
        checks.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)
    ok("unconfirmed goalie game G3 skipped", "G3" not in res["projections"])
    ok("G1,G2 projected", set(res["projections"]) == {"G1", "G2"})
    for gid, gp in res["pricers"].items():
        ok(gid + " score matrix sums ~1", close(sum(map(sum, gp.M)), 1.0, 1e-4))
        ok(gid + " 3-way sums to 1", close(sum(gp.reg.values()), 1.0, 1e-4))
        ok(gid + " total dist sums to 1", close(sum(gp.total.values()), 1.0, 1e-4))
        ok(gid + " P1 3-way sums ~1", close(sum(gp.p1.values()), 1.0, 1e-4))
        ph, _, _ = gp.price("ML", "home", 0); pa, _, _ = gp.price("ML", "away", 0)
        ok(gid + " 2-way ML sums to 1", close(ph + pa, 1.0))
        pl_h, pu, _ = gp.price("PL", "home", -1.5); pl_a, pu2, _ = gp.price("PL", "away", 1.5)
        ok(gid + " PL -1.5/+1.5 complementary", close(pl_h + pl_a, 1.0, 1e-6) and pu == 0)
        ok(gid + " PL home -1.5 < ML home", pl_h < ph)
        o, p, _ = gp.price("TOTAL", "over", 6); u, p2, _ = gp.price("TOTAL", "under", 6)
        ok(gid + " integer total o+u+push=1", close(o + u + p, 1.0, 1e-6) and p > 0)
        ok(gid + " empty-net raises mean total", gp.mean(gp.total) > gp.lh + gp.la)
    pr1 = res["projections"]["G1"][0]
    ok("home ice + away b2b favour home in G1", pr1["lam_h"] - pr1["lam_a"] > pr1["base_h"] - pr1["base_a"])
    pr2 = res["projections"]["G2"][0]
    ok("G2 away travel pen 0.10 (3 tz)", close(pr2["away_b2b_travel_pen"], 0.10))
    ok("picks all +blend EV", all(p["blend_ev"] > 0 for p in res["picks"]))
    ok("ranked by blend EV desc", all(a["blend_ev"] >= b["blend_ev"] for a, b in zip(res["picks"], res["picks"][1:])))
    ok("stars in 1..5", all(1 <= p["stars"] <= 5 for p in res["picks"]))
    bad = [p for p in res["picks"] if p["projection"] != "" and
           ((p["selection"] == "under" and float(p["line"]) < p["projection"]) or
            (p["selection"] == "over" and float(p["line"]) > p["projection"]))]
    ok("filter: no contradicting over/under left", not bad)
    ok("filter dropped something", len(res["dropped"]) > 0)
    ok("props priced", any(p["type"] == "prop" for p in res["picks"] + res["dropped"]))
    ok("csv + md written", os.path.getsize(res["csv"]) > 0 and os.path.getsize(res["md"]) > 0)
    # EV math
    ok("EV formula p*dec-1", close(m.ev_from(0.5, 0, 2.1), 0.05))
    ok("no-vig sums to 1", close(sum(m.novig([-110, -110])), 1.0))
    print("\n%d/%d checks passed; picks=%d dropped=%d" % (sum(c for _, c in checks), len(checks),
                                                       len(res["picks"]), len(res["dropped"])))
    return 0 if all(c for _, c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
