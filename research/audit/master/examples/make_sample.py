"""Writes synthetic sample_predictions.json for CI/demo. Not real data."""
import json, os, random
rng = random.Random(42); rows = []
for i in range(120):
    p = round(rng.uniform(.48, .66), 3); o = rng.choice([-120, -115, -110, -105, 100, 110, 125])
    day = 1 + i // 8
    rows.append({"pred_id": f"s{i}", "game_id": f"g{i // 3}", "sport": "NFL",
                 "market": rng.choice(["spread", "total", "rec_yds", "receptions"]),
                 "side": rng.choice(["home", "away", "over", "under"]),
                 "player": rng.choice([None, "Player A", "Player B"]), "model_prob": p, "odds": o, "book": "DK",
                 "odds_ts": f"2026-11-{day:02d}T11:50:00-06:00", "pred_ts": f"2026-11-{day:02d}T12:00:00-06:00",
                 "kickoff_ts": f"2026-11-{day:02d}T15:25:00-06:00",
                 "result": "W" if rng.random() < p - .03 else "L", "rule_version": "v1" if day < 10 else "v2",
                 "inputs": [{"name": "season_epa", "value": 0.05, "ts": f"2026-11-{day:02d}T08:00:00-06:00"}]})
json.dump(rows, open(os.path.join(os.path.dirname(__file__), "sample_predictions.json"), "w"))
