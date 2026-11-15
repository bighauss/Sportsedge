"""Write SYNTHETIC sample inputs for the CFB model test (fake teams, stats and odds; CFBD field names).

Run: python3 make_samples.py  -> samples/*.json + samples/inputs.json
Game 1: Alpha State (home, strong) vs Beta Tech: away travels 3 time zones on a short week,
        Beta Tech QB out, live forecast wind 18 mph.
Game 2: Delta Mines (home, 6,100 ft) vs Gamma U: Gamma U has 2 DBs out; weather row is not a
        live forecast, so it must be ignored.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "samples")


def side(ppa, sr, expl, ppo, start, havoc, plays, drives):
    return {"plays": plays, "drives": drives, "ppa": ppa, "successRate": sr, "explosiveness": expl,
            "pointsPerOpportunity": ppo, "fieldPosition": {"averageStart": start}, "havoc": {"total": havoc},
            "rushingPlays": {"ppa": ppa - 0.03, "successRate": sr - 0.01, "rate": 0.52},
            "passingPlays": {"ppa": ppa + 0.05, "successRate": sr + 0.01, "rate": 0.48}}


def team(name, conf, off, dfn, games=10):
    return {"team": name, "conference": conf, "games": games, "offense": off, "defense": dfn}


def main():
    os.makedirs(OUT, exist_ok=True)
    advanced = [
        team("Alpha State", "East", side(0.32, 0.48, 1.30, 4.8, 31.0, 0.13, 760, 125),
             side(0.08, 0.38, 1.18, 3.6, 27.5, 0.19, 690, 122)),
        team("Beta Tech", "West", side(0.15, 0.42, 1.22, 4.0, 28.5, 0.16, 700, 120),
             side(0.20, 0.44, 1.26, 4.2, 29.5, 0.15, 720, 124)),
        team("Gamma U", "Mountain", side(0.22, 0.45, 1.25, 4.3, 29.0, 0.15, 730, 123),
             side(0.17, 0.42, 1.24, 4.0, 28.8, 0.16, 710, 121)),
        team("Delta Mines", "Mountain", side(0.25, 0.46, 1.27, 4.5, 30.0, 0.14, 740, 124),
             side(0.12, 0.40, 1.20, 3.8, 28.0, 0.18, 700, 122)),
    ]
    files = {
        "games": [
            {"id": 1001, "season": 2026, "week": 12, "homeTeam": "Alpha State", "awayTeam": "Beta Tech",
             "neutralSite": False, "venue": "Alpha Field", "venueId": 1, "startDate": "2026-11-21T19:30:00Z"},
            {"id": 1002, "season": 2026, "week": 12, "homeTeam": "Delta Mines", "awayTeam": "Gamma U",
             "neutralSite": False, "venue": "Mines Stadium", "venueId": 2, "startDate": "2026-11-21T21:00:00Z"}],
        "advanced": advanced,
        "talent": [{"team": t["team"], "talent": v} for t, v in zip(advanced, (880, 760, 720, 700))],
        "returning": [{"team": t["team"], "percentPPA": v} for t, v in zip(advanced, (0.65, 0.55, 0.60, 0.50))],
        "ratings": [
            {"team": "Alpha State", "rating": 14.0, "offense": {"rating": 9.0}, "defense": {"rating": -5.0}},
            {"team": "Beta Tech", "rating": 2.0, "offense": {"rating": 2.5}, "defense": {"rating": 0.5}},
            {"team": "Gamma U", "rating": 5.0, "offense": {"rating": 3.0}, "defense": {"rating": -2.0}},
            {"team": "Delta Mines", "rating": 6.0, "offense": {"rating": 4.0}, "defense": {"rating": -2.0}}],
        "teams": [
            {"school": "Alpha State", "location": {"timezone": "America/New_York", "elevation": 300}},
            {"school": "Beta Tech", "location": {"timezone": "America/Los_Angeles", "elevation": 150}},
            {"school": "Gamma U", "location": {"timezone": "America/Denver", "elevation": 4500}},
            {"school": "Delta Mines", "location": {"timezone": "America/Denver", "elevation": 6100}}],
        "venues": [{"venue": "Alpha Field", "hfa": 3.0, "elevation_ft": 300},
                   {"venue": "Mines Stadium", "hfa": 2.5, "elevation_ft": 6100}],
        "injuries": [
            {"team": "Beta Tech", "player": "QB Beta", "role": "QB", "status": "OUT"},
            {"team": "Gamma U", "player": "CB One", "role": "DB", "status": "OUT"},
            {"team": "Gamma U", "player": "S Two", "role": "DB", "status": "OUT"}],
        "weather": [
            {"gameId": 1001, "windSpeed": 18, "precipitation_type": "none", "isForecast": True, "roof": "open"},
            {"gameId": 1002, "windSpeed": 22, "precipitation_type": "snow", "isForecast": False, "roof": "open"}],
        "schedule_rest": [{"team": "Beta Tech", "days_rest": 5}, {"team": "Alpha State", "days_rest": 7},
                          {"team": "Gamma U", "days_rest": 7}, {"team": "Delta Mines", "days_rest": 7}],
        "crosscheck": [{"gameId": 1001, "sp_spread": -15.5, "fpi_spread": -14.0},
                       {"gameId": 1002, "sp_spread": -4.0, "fpi_spread": -3.5}],
        "lines": [
            {"homeTeam": "Alpha State", "awayTeam": "Beta Tech",
             "lines": [{"spread": -13.5, "overUnder": 55.5, "homeMoneyline": -600, "awayMoneyline": 430}],
             "spreadHomeOdds": -105, "spreadAwayOdds": -105, "overOdds": -105, "underOdds": -105,
             "homeTT": 34.5, "homeTTOver": -105, "homeTTUnder": -105, "awayTT": 20.5, "awayTTOver": -105,
             "awayTTUnder": -105, "h1Spread": -7.5, "h1HomeOdds": -105, "h1AwayOdds": -105,
             "h1Total": 27.5, "h1Over": -105, "h1Under": -105},
            {"homeTeam": "Delta Mines", "awayTeam": "Gamma U",
             "lines": [{"spread": -3.5, "overUnder": 57.5, "homeMoneyline": -165, "awayMoneyline": 140}],
             "spreadHomeOdds": -105, "spreadAwayOdds": -105, "overOdds": -105, "underOdds": -105,
             "homeTT": 30.5, "homeTTOver": -105, "homeTTUnder": -105, "awayTT": 27.5, "awayTTOver": -105,
             "awayTTUnder": -105}],
        "usage": [
            {"player": "RB Alpha", "team": "Alpha State", "pos": "RB", "market": "rush_yds", "share": 0.48, "eff": 5.6, "games": 10},
            {"player": "WR Alpha", "team": "Alpha State", "pos": "WR", "market": "rec_yds", "share": 0.27, "eff": 13.5, "games": 10},
            {"player": "WR Gamma", "team": "Gamma U", "pos": "WR", "market": "receptions", "share": 0.25, "eff": 0.66, "games": 10}],
        "props": [
            {"gameId": 1001, "player": "RB Alpha", "market": "rush_yds", "line": 92.5, "overOdds": -110, "underOdds": -110},
            {"gameId": 1001, "player": "WR Alpha", "market": "rec_yds", "line": 74.5, "overOdds": -110, "underOdds": -110},
            {"gameId": 1002, "player": "WR Gamma", "market": "receptions", "line": 5.5, "overOdds": -110, "underOdds": -110}],
    }
    for name, rows in files.items():
        with open(os.path.join(OUT, name + ".json"), "w") as fh:
            json.dump(rows, fh, indent=1)
    with open(os.path.join(OUT, "inputs.json"), "w") as fh:
        json.dump({n: n + ".json" for n in files}, fh, indent=1)
    print(f"wrote synthetic samples to {OUT}")


if __name__ == "__main__":
    main()
