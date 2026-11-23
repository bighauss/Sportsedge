"""End-to-end test on SYNTHETIC MoneyPuck-shaped samples (fake teams, players, odds).

Run: python3 test_sportsedge_nhl.py   (stdlib only, network off)
Writes samples/ (inputs.json + CSVs), runs the card and checks its rules.
"""
import csv, json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
socket.socket = None  # hard network OFF
import sportsedge_nhl_model as m

SAMPLES = os.path.join(HERE, "samples")
TEAMS = {"AAA": (2.75, 2.35, 0.95), "BBB": (2.45, 2.60, 1.05), "CCC": (2.60, 2.50, 1.00), "DDD": (2.40, 2.70, 1.00)}


def w(name, rows):
    with open(os.path.join(SAMPLES, name), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)


def make_samples():
    os.makedirs(SAMPLES, exist_ok=True)
    gp = 20
    teams, goalies, skaters, ratings = [], [], [], []
    for t, (xgf, xga, pen) in TEAMS.items():
        for sit, ice_pg, f, a in (("5on5", 48 * 60, xgf * 0.8, xga * 0.8), ("5on4", 4.5 * 60, 0.75, 0.05),
                                  ("4on5", 4.5 * 60, 0.05, 0.70), ("all", 60 * 60, xgf, xga)):
            ice = ice_pg * gp
            teams.append(dict(team=t, situation=sit, games_played=gp, iceTime=ice,
                              scoreVenueAdjustedxGoalsFor=round(f * gp, 2),
                              scoreVenueAdjustedxGoalsAgainst=round(a * gp, 2),
                              xGoalsFor=round(f * gp, 2), xGoalsAgainst=round(a * gp, 2),
                              shotsOnGoalFor=round(29 * gp * ice_pg / 3600, 1),
                              shotsOnGoalAgainst=round(28 * gp * ice_pg / 3600, 1),
                              shotAttemptsFor=round(58 * gp * ice_pg / 3600, 1),
                              shotAttemptsAgainst=round(56 * gp * ice_pg / 3600, 1),
                              penaltiesFor=round(3.2 * pen * gp), penaltiesAgainst=round(3.2 / pen * gp)))
        goalies.append(dict(name=f"Goalie {t}1", team=t, situation="all", games_played=15,
                            xGoals=round(xga * 15, 1), goals=round(xga * 15 - (3 if t == "AAA" else -2), 1),
                            ongoal=420))
        goalies.append(dict(name=f"Goalie {t}2", team=t, situation="all", games_played=5,
                            xGoals=round(xga * 5, 1), goals=round(xga * 5 + 2, 1), ongoal=140))
        for i in range(1, 4):
            skaters.append(dict(name=f"Skater {t}{i}", team=t, position="C" if i == 1 else "W", situation="all",
                                games_played=gp, icetime=(19 - i) * 60 * gp, I_F_shotAttempts=5.5 * gp / i,
                                I_F_shotsOnGoal=2.8 * gp / i, I_F_points=0.9 * gp / i,
                                OnIce_F_xGoals=1.2 * gp, OnIce_F_goals=1.3 * gp))
        ratings.append(dict(team=t, off_gpg=round(xgf + 0.3, 2), def_gpg=round(xga + 0.3, 2)))
    games = [
        dict(game_id="N1", date="2026-11-15", start_time="18:00", venue="Arena B", home="BBB", away="AAA",
             home_goalie="Goalie BBB1", away_goalie="Goalie AAA1", home_goalie_confirmed=1, away_goalie_confirmed=1,
             home_goalie_is_backup=0, away_goalie_is_backup=0, home_b2b=1, away_b2b=0,
             home_tz_shift=0, away_tz_shift=2, home_lineup_adj=0, away_lineup_adj=0),
        dict(game_id="N2", date="2026-11-15", start_time="19:00", venue="Arena D", home="DDD", away="CCC",
             home_goalie="Goalie DDD2", away_goalie="Goalie CCC1", home_goalie_confirmed=1, away_goalie_confirmed=1,
             home_goalie_is_backup=1, away_goalie_is_backup=0, home_b2b=0, away_b2b=0,
             home_tz_shift=0, away_tz_shift=0, home_lineup_adj=-0.10, away_lineup_adj=0),
        # unconfirmed goalie -> must be skipped (RUN IT v2.1: unconfirmed starter not actionable)
        dict(game_id="N3", date="2026-11-15", start_time="20:00", venue="Arena C", home="CCC", away="BBB",
             home_goalie="Goalie CCC1", away_goalie="Goalie BBB2", home_goalie_confirmed=1, away_goalie_confirmed=0,
             home_goalie_is_backup=0, away_goalie_is_backup=1, home_b2b=0, away_b2b=0,
             home_tz_shift=0, away_tz_shift=0, home_lineup_adj=0, away_lineup_adj=0)]
    odds = []
    for gid in ("N1", "N2", "N3"):
        for mk, sels, line in (("ML", ("home", "away"), ""), ("TOTAL", ("over", "under"), 6.0),
                               ("TT_HOME", ("over", "under"), 3.0), ("TT_AWAY", ("over", "under"), 2.5),
                               ("P1_TOTAL", ("over", "under"), 1.5)):
            for s in sels:
                odds.append(dict(game_id=gid, market=mk, selection=s, line=line, price=-104, book="DK"))
        odds += [dict(game_id=gid, market="PL", selection="home", line=-1.5, price=180, book="DK"),
                 dict(game_id=gid, market="PL", selection="away", line=1.5, price=-220, book="DK")]
    props = [dict(game_id="N1", player="Skater AAA1", team="AAA", opp="BBB", market="SOG", line=2.5,
                  over_price=-110, under_price=-110, proj_toi=18),
             dict(game_id="N1", player="Skater BBB1", team="BBB", opp="AAA", market="POINTS", line=0.5,
                  over_price=-120, under_price=100, proj_toi=18),
             dict(game_id="N2", player="Goalie DDD2", team="DDD", opp="CCC", market="SAVES", line=26.5,
                  over_price=-110, under_price=-110, proj_toi="")]
    for n, r in (("teams.csv", teams), ("goalies.csv", goalies), ("skaters.csv", skaters),
                 ("ratings.csv", ratings), ("games.csv", games), ("odds.csv", odds), ("props.csv", props)):
        w(n, r)
    inputs = {k + "_csv": os.path.join(SAMPLES, k + ".csv")
              for k in ("teams", "goalies", "skaters", "ratings", "games", "odds", "props")}
    with open(os.path.join(SAMPLES, "inputs.json"), "w") as fh:
        json.dump({**{k: os.path.basename(v) for k, v in inputs.items()}, "out_dir": "out"}, fh, indent=1)
    return inputs


def main():
    inputs = make_samples()
    inputs["out_dir"] = tempfile.mkdtemp()
    res = m.run_card(inputs)
    picks, projs = res["picks"], res["projections"]
    # unconfirmed goalie game is not priced
    assert "N1" in projs and "N2" in projs and "N3" not in projs, sorted(projs)
    for gid in ("N1", "N2"):
        gpz = res["pricers"][gid]
        ph, pa = gpz.price("ML", "home", None)[0], gpz.price("ML", "away", None)[0]
        assert abs(ph + pa - 1) < 1e-6, (gid, ph, pa)
        proj = projs[gid][0]
        assert 1.5 < proj["lam_h"] < 4.5 and 1.5 < proj["lam_a"] < 4.5, proj
    # odds math
    assert abs(m.american_to_decimal(-110) - 1.909090909) < 1e-6 and m.american_to_decimal(150) == 2.5
    assert abs(sum(m.novig([-110, -110])) - 1) < 1e-9
    # card rules
    assert picks, "expected some +EV plays on the synthetic slate"
    evs = [p["blend_ev"] for p in picks]
    assert evs == sorted(evs, reverse=True) and all(e > 0 for e in evs)
    for p in picks:
        assert 1 <= p["stars"] <= 5
        if not p.get("push_p"):  # push lines blend on the no-push basis instead
            assert abs(p["blend_p"] - (0.3 * p["model_p"] + 0.7 * p["market_p"])) < 2e-3, p
        if p["projection"] != "" and p["line"] != "":
            assert not m.contradicts(p["selection"], float(p["line"]), float(p["projection"])), p
    rows = list(csv.DictReader(open(res["csv"])))
    assert len(rows) == len(picks)
    md = open(res["md"]).read()
    assert "Game Card" in md and "Prop Card" in md
    # empty-net refit (2026-11-22): 3-goal finals must outweigh 2-goal finals near league scoring,
    # as observed (22.1% vs 18.2% over 285 finals); the old 0.13/0.07 gave 16.8% vs 25.3%.
    gp = m.GamePricer(3.28, 2.98)
    fm = {}
    for d, p in gp.diff.items():
        k = 1 if d == 0 else abs(d)
        fm[k] = fm.get(k, 0) + p
    assert fm[3] > fm[2], fm
    assert 0.38 < fm[1] < 0.47, fm[1]
    assert abs(sum(p for row in gp.M for p in row) - 1) < 1e-9
    print(md)
    print("PASS: %d plays, %d dropped, markets %s" % (len(picks), len(res["dropped"]),
                                                     sorted({p["market"] for p in picks})))


if __name__ == "__main__":
    main()
