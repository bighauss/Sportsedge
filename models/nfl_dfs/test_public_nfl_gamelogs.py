"""Unit tests verify provider FP can be corrupted without changing features."""
import unittest
import public_nfl_gamelogs as g

HEAD = "Date,Player,Team,Opp,Pos,Season,Receptions,Rec Yards,Rec TD,Rush Yards,Rush TD,Pass Yards,Pass TD,INT Thrown,Fumbles Lost,2-Pt Conversions,FD Pts,Games Ago\n"
ROWS = (
    "2026-11-01,Joe Burrow,CIN,PIT,QB,2026,0,0,0,16,0,322,3,1,0,0,999999,1\n"
    "2026-11-08,Joe Burrow,CIN,ATL,QB,2026,0,0,0,5,0,300,2,0,0,0,-99,2\n"
    "2026-11-15,Joe Burrow,CIN,PIT,QB,2026,0,0,0,999,10,999,10,0,0,0,999,0\n"
    "2026-11-08,Ja'Marr Chase,CIN,ATL,WR,2026,8,123,1,0,0,0,0,0,0,0,999,1\n"
    "2026-11-08,Jaylen Warren,PIT,CIN,RB,2026,4,37,0,88,1,0,0,0,0,0,999,1\n"
)


class RawLogTests(unittest.TestCase):
    def test_cutoff_and_raw_feature_only(self):
        rows = g.parse_records((HEAD+ROWS).encode(), kickoff_date="2026-11-15")
        self.assertEqual(len(rows), 4)
        features = g.player_features(rows)
        self.assertEqual(features["Joe Burrow"]["Pass Yards"], 311)
        self.assertEqual(features["Ja'Marr Chase"]["Receptions"], 8)
        self.assertNotIn("FD Pts", str(features))
        self.assertNotIn("AvgPointsPerGame", str(features))
        self.assertEqual(len(features), 3)

    def test_corrupted_provider_points_irrelevant(self):
        a = g.player_features(g.parse_records((HEAD+ROWS).encode(), kickoff_date="2026-11-15"))
        b = g.player_features(g.parse_records((HEAD+ROWS.replace("999999", "-8000").replace("-99", "999")).encode(), kickoff_date="2026-11-15"))
        self.assertEqual(a, b)

    def test_duplicates_fail(self):
        x = ROWS.splitlines(keepends=True)[0]
        with self.assertRaises(g.SourceError):
            g.parse_records((HEAD+x+x).encode(), kickoff_date="2026-11-15")

    def test_invalid_stat_fails(self):
        with self.assertRaises(g.SourceError):
            g.parse_records((HEAD+ROWS.replace("322,3", "NaN,3")).encode(), kickoff_date="2026-11-15")

    def test_requires_raw_columns(self):
        with self.assertRaises(g.SourceError):
            g.parse_records(b"Date,Player,FD Pts\n2026-11-01,Joe Burrow,22\n", kickoff_date="2026-11-15")


if __name__ == "__main__":
    unittest.main()
