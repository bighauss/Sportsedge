import tempfile
import unittest
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from research.sportsleader.venue_baseline import evaluate

class VenueBaselineTests(unittest.TestCase):
    def test_prior_only_and_neutral(self):
        rows = []
        for i, (season, neutral, margin) in enumerate([
            (2022, False, 4), (2022, True, 100),
            (2023, False, 10), (2023, True, 8),
            (2024, False, 20)]):
            rows.append(dict(game_id=i, season=season, completed=True,
                             neutral_site=neutral, home_score=100+margin, away_score=100))
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)/"games.parquet"
            pq.write_table(pa.Table.from_pylist(rows), p)
            results = evaluate([p])["results"]
            by_key = {(r["season"],r["neutral"]):r for r in results}
            self.assertEqual(by_key[2023,False]["prediction"],4)
            self.assertEqual(by_key[2023,True]["prediction"],0)
            self.assertEqual(by_key[2024,False]["prediction"],7)
            with self.assertRaises(ValueError):
                evaluate([p,p])
