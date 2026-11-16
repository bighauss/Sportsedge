import unittest
from models.nfl.team_split_pit_contract import validate, METRICS

def sample():
    rows=[]
    for team in ("LAC","BAL"):
        for split in ("season","last3","venue"):
            rows.append({"team_id":team,"split":split,"games":3,
                         "venue":("away" if team=="LAC" else "home") if split=="venue" else None,
                         "metrics":{m:40.0 if m.endswith("_pct") else 5.0 for m in METRICS}})
    return dict(event_id="LAC-BAL",away_team_id="LAC",home_team_id="BAL",
                source_id="authorized-source",source_sha256="a"*64,
                source_available_utc="2026-11-16T12:00:00Z",
                freeze_utc="2026-11-16T17:00:00Z",
                event_start_utc="2026-11-16T18:00:00Z",rows=rows)

class TestSplitIntake(unittest.TestCase):
    def test_valid_stays_paper(self):
        r=validate(sample())
        self.assertEqual((r["official_counted"],r["approved_stake_u"]),(0,0))
    def test_future_source(self):
        p=sample();p["source_available_utc"]="2026-11-16T17:01:00Z"
        with self.assertRaisesRegex(ValueError,"LOOKAHEAD"):validate(p)
    def test_duplicate_split(self):
        p=sample();p["rows"][1]["split"]="season"
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SPLIT"):validate(p)
    def test_wrong_venue(self):
        p=sample();p["rows"][2]["venue"]="home"
        with self.assertRaisesRegex(ValueError,"VENUE_MISMATCH"):validate(p)
    def test_nan(self):
        p=sample();p["rows"][0]["metrics"]["yards_per_play"]=float("nan")
        with self.assertRaisesRegex(ValueError,"METRIC_INVALID"):validate(p)
    def test_missing_metric(self):
        p=sample();del p["rows"][0]["metrics"]["points_per_game"]
        with self.assertRaisesRegex(ValueError,"METRIC_SCHEMA_INVALID"):validate(p)
    def test_bad_percentage(self):
        p=sample();p["rows"][0]["metrics"]["third_down_pct"]=110
        with self.assertRaisesRegex(ValueError,"PERCENT_OUT_OF_RANGE"):validate(p)
    def test_last3_count(self):
        p=sample();p["rows"][1]["games"]=4
        with self.assertRaisesRegex(ValueError,"LAST3_SAMPLE_INVALID"):validate(p)

if __name__=="__main__":unittest.main()
