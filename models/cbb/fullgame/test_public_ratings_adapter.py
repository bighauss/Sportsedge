"""Offline unit tests for non-destructive AdjustedFit public ratings adapter (PAPER/0u)."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from fullgame import public_ratings_adapter as PRA  # noqa: E402


def _g(gid, day, h, a, hp, ap, site="HOME_VERIFIED", poss=70.0, hd1=True, ad1=True):
    return {"game_id": str(gid), "date": day, "home": str(h), "away": str(a),
            "home_points": hp, "away_points": ap, "possessions": poss,
            "site": site, "home_d1": hd1, "away_d1": ad1}


class PublicRatingsAdapterTest(unittest.TestCase):
    def test_sparse_graph_does_not_collapse_like_kcore(self):
        # Every team has only 1-2 games: iterative min_games>=3 k-core would drop 100% of games.
        games = [
            _g(1, "2026-11-05", "10", "20", 78, 70),
            _g(2, "2026-11-08", "20", "30", 72, 68),
            _g(3, "2026-11-10", "10", "999", 99, 41, ad1=False),
        ]
        d1_set = {"10", "20", "30", "40"}
        prev_final = ({"10": (5.0, -3.0, 1.0), "20": (1.0, 0.0, 0.0),
                       "30": (-2.0, 2.0, -1.0), "40": (3.0, -1.0, 0.5)}, 105.0, 69.0, 3.8)
        body, diag = PRA.fit_public_adjusted_ratings(
            games, season=2027, as_of_date="2026-11-25", d1_set=d1_set,
            prev_final=prev_final, hca_prior=3.8,
        )
        rows = {str(r["teamId"]): r for r in json.loads(body)}
        self.assertTrue(diag["iterative_pruning_disabled"])
        self.assertEqual(diag["usable"], 2)
        self.assertEqual(diag["dropped_non_d1"], 1)
        self.assertEqual(diag["rated_teams"], 4)
        self.assertEqual(rows["40"]["n_games"], 0)
        self.assertGreater(rows["40"]["netRating"], 0.0)
        self.assertNotIn("999", rows)

    def test_empty_without_prior_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "RATINGS_INSUFFICIENT_SAMPLE"):
            PRA.fit_public_adjusted_ratings([], season=2027, as_of_date="2026-11-25")


if __name__ == "__main__":
    unittest.main()
