"""Write SYNTHETIC sample inputs for the MLB model test (fake teams, players and odds).

Run: python3 make_samples.py  -> sample_inputs/*.csv
Nothing here is real data. It only exercises code paths.
"""
import csv, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample_inputs")
PITCHES = ["FF", "SI", "FC", "SL", "CU", "CH", "FS"]
TEAMS = ["AAA", "BBB", "CCC", "DDD"]
GAMES = [("G1", "AAA", "BBB", "Park B", "open", 78, 12, "out", 600),
         ("G2", "CCC", "DDD", "Park D", "dome", 72, 0, "none", 5200)]


def w(name, rows):
    with open(os.path.join(OUT, name), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader(); wr.writerows(rows)


def main():
    rnd = random.Random(20261115)
    os.makedirs(OUT, exist_ok=True)
    pitchers, batters, lineups, bullpen, defense = [], [], [], [], []
    for i, t in enumerate(TEAMS):
        usage = [rnd.uniform(5, 30) for _ in PITCHES]; s = sum(usage)
        pitchers.append(dict(
            player_id=f"P{t}", name=f"Starter {t}", team=t, p_throws="RL"[i % 2],
            g=28, gs=28, ip=round(rnd.uniform(150, 185), 1),
            xera=round(rnd.uniform(3.0, 4.9), 2), xwoba=round(rnd.uniform(.280, .335), 3),
            k_percent=round(rnd.uniform(19, 30), 1), bb_percent=round(rnd.uniform(6, 10), 1),
            csw_percent=round(rnd.uniform(26, 32), 1), velo_season=94.5,
            velo_last3=round(94.5 - rnd.uniform(0, 1.2), 1), bf_per_start=round(rnd.uniform(22, 26), 1),
            tto3_xwoba=round(rnd.uniform(.310, .360), 3),
            **{f"usage_{p}": round(u / s * 100, 1) for p, u in zip(PITCHES, usage)},
            **{f"whiff_{p}": round(rnd.uniform(15, 38), 1) for p in PITCHES}))
        for slot in range(1, 10):
            pid = f"B{t}{slot}"
            pa = rnd.randint(380, 650)
            batters.append(dict(
                player_id=pid, name=f"Batter {t}{slot}", team=t, stand="LRS"[slot % 3], pa=pa,
                xwoba=round(rnd.uniform(.290, .380), 3), xslg=round(rnd.uniform(.360, .520), 3),
                barrel_batted_rate=round(rnd.uniform(5, 14), 1), hard_hit_percent=round(rnd.uniform(33, 50), 1),
                bat_speed=round(rnd.uniform(69, 75), 1), k_percent=round(rnd.uniform(15, 28), 1),
                ba=round(rnd.uniform(.230, .295), 3), iso=round(rnd.uniform(.120, .240), 3),
                hr_per_pa=round(rnd.uniform(.020, .055), 3),
                xwoba_vs_L=round(rnd.uniform(.280, .390), 3), xwoba_vs_R=round(rnd.uniform(.280, .390), 3),
                pa_vs_L=int(pa * .3), pa_vs_R=int(pa * .7),
                **{f"xwoba_{p}": round(rnd.uniform(.270, .400), 3) for p in PITCHES}))
            lineups.append(dict(game_id="G1" if t in ("AAA", "BBB") else "G2", team=t, slot=slot, player_id=pid))
        bullpen.append(dict(team=t, ip=round(rnd.uniform(420, 520), 1), xfip=round(rnd.uniform(3.6, 4.6), 2),
                            k_bb_percent=round(rnd.uniform(12, 19), 1), pitches_last3=rnd.choice([60, 95, 140])))
        defense.append(dict(team=t, oaa=rnd.randint(-12, 15), framing_runs=round(rnd.uniform(-6, 8), 1), games=150))
    games = []
    for gid, a, h, park, roof, temp, wind, wdir, alt in GAMES:
        games.append(dict(game_id=gid, date="2026-09-20", away=a, home=h, park=park, start_time="19:05",
                          roof=roof, temp_f=temp, wind_mph=wind, wind_dir=wdir, altitude_ft=alt,
                          umpire="Ump X", ump_runs_per_game=0.15, away_sp_id=f"P{a}", home_sp_id=f"P{h}",
                          away_rating_runs=round(rnd.uniform(4.0, 4.8), 2),
                          home_rating_runs=round(rnd.uniform(4.0, 4.8), 2),
                          away_rest_days=1, home_rest_days=0, away_travel_tz=1, home_travel_tz=0))
    parks = [dict(park="Park B", pf_runs_lhb=103, pf_runs_rhb=101, pf_hr=106),
             dict(park="Park D", pf_runs_lhb=99, pf_runs_rhb=98, pf_hr=96)]
    # Both sides of every market at a light synthetic hold so some sides show +EV.
    odds = []
    for gid, *_ in GAMES:
        for mk, sel_a, sel_b, line_a, line_b in (
                ("ML", "away", "home", "", ""), ("RL", "away", "home", 1.5, -1.5),
                ("TOTAL", "over", "under", 8.5, 8.5), ("TT_AWAY", "over", "under", 4.5, 4.5),
                ("TT_HOME", "over", "under", 4.5, 4.5), ("F5_ML", "away", "home", "", ""),
                ("F5_TOTAL", "over", "under", 4.5, 4.5), ("NRFI", "nrfi", "yrfi", "", "")):
            pa, pb = ((-150, 128) if mk == "RL" else (-102, -102))
            odds.append(dict(game_id=gid, market=mk, selection=sel_a, line=line_a, price=pa))
            odds.append(dict(game_id=gid, market=mk, selection=sel_b, line=line_b, price=pb))
    props = []
    for gid, a, h, *_ in GAMES:
        for t in (a, h):
            props.append(dict(game_id=gid, player_id=f"P{t}", market="K", line=5.5, over_price=-105, under_price=-105))
            props.append(dict(game_id=gid, player_id=f"P{t}", market="OUTS", line=16.5, over_price=-105, under_price=-105))
            for slot in (1, 3, 4):
                pid = f"B{t}{slot}"
                props.append(dict(game_id=gid, player_id=pid, market="HITS", line=0.5, over_price=-160, under_price=135))
                props.append(dict(game_id=gid, player_id=pid, market="TB", line=1.5, over_price=110, under_price=-130))
                props.append(dict(game_id=gid, player_id=pid, market="HR", line=0.5, over_price=420, under_price=-600))
    for n, r in (("games.csv", games), ("pitchers.csv", pitchers), ("batters.csv", batters),
                 ("lineups.csv", lineups), ("bullpen.csv", bullpen), ("parks.csv", parks),
                 ("defense.csv", defense), ("odds.csv", odds), ("prop_odds.csv", props)):
        w(n, r)
    print(f"wrote synthetic samples to {OUT}")


if __name__ == "__main__":
    main()
