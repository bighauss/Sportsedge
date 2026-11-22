"""Offline synthetic regression tests for research-only NFL last-four pricer."""
import unittest
from datetime import datetime, timedelta, timezone
from research.nfl_beta_last_four import price_beta

NOW = datetime(2026, 11, 22, 15, tzinfo=timezone.utc)
def stamp(offset):
    return (NOW + timedelta(minutes=offset)).isoformat()

def offer(kind="XPLUS", **kw):
    x = dict(event_id="event-1", book="DraftKings", quote_id="q1",
             kind=kind, player_id="p1", stat="rec_yds", threshold=50,
             captured_at_utc=stamp(-1), kickoff_utc=stamp(60),
             model_asof_utc=stamp(-10), source_sha256="sha256:receipt",
             model_sha256="sha256:model", odds_american=150,
             joint_simulation=True)
    x.update(kw)
    return x

def sims(n=1000):
    return [dict(event_id="event-1",
                 players={"p1": {"rec_yds": 60 if i % 2 == 0 else 20,
                                  "receptions": 5 if i % 2 == 0 else 2}},
                 ordered_touchdowns=["p1"] if i % 4 == 0 else ["other"])
            for i in range(n)]

class BetaTests(unittest.TestCase):
    def test_yards_and_receptions_distinct_rungs(self):
        xs = [offer(quote_id="a", threshold=50),
              offer(quote_id="b", stat="receptions", threshold=4)]
        rows = price_beta(sims(), xs, decision_utc=stamp(0))["rows"]
        self.assertEqual([r["beta_probability"] for r in rows], [0.5, 0.5])
        self.assertEqual([r["stake_u"] for r in rows], [0, 0])

    def test_first_td_uses_ordered_events(self):
        row = price_beta(sims(), [offer("FIRST_TD")], decision_utc=stamp(0))["rows"][0]
        self.assertEqual(row["beta_probability"], 0.25)

    def test_sgp_uses_joint_not_independence(self):
        legs = [dict(kind="XPLUS", player_id="p1", stat="rec_yds", threshold=50),
                dict(kind="FIRST_TD", player_id="p1")]
        row = price_beta(sims(), [offer("SGP", legs=legs)], decision_utc=stamp(0))["rows"][0]
        self.assertEqual(row["beta_probability"], 0.25)

    def test_no_first_td_events_is_not_first_scorer(self):
        ss = sims()
        for s in ss:
            s["ordered_touchdowns"] = []
        row = price_beta(ss, [offer("FIRST_TD")], decision_utc=stamp(0))["rows"][0]
        self.assertEqual(row["beta_probability"], 0)
        self.assertIn("EXTREME_MC_ESTIMATE", row["reasons"])

    def test_future_model_is_blocked(self):
        row = price_beta(sims(), [offer(model_asof_utc=stamp(1))],
                         decision_utc=stamp(0))["rows"][0]
        self.assertIsNone(row["beta_ev"])
        self.assertIn("POINT_IN_TIME_OR_KICKOFF_VIOLATION", row["reasons"])

    def test_sgp_requires_joint_attestation(self):
        row = price_beta(sims(), [offer("SGP", joint_simulation=False,
                         legs=[dict(kind="FIRST_TD", player_id="p1"),
                               dict(kind="FIRST_TD", player_id="other")])],
                         decision_utc=stamp(0))["rows"][0]
        self.assertIsNone(row["beta_ev"])

    def test_duplicate_quote_rejected(self):
        with self.assertRaises(ValueError):
            price_beta(sims(), [offer(), offer()], decision_utc=stamp(0))

if __name__ == "__main__":
    unittest.main()
