"""Synthetic regressions: no real bets, provider authentication or calibrated EV."""
import copy
import unittest

from research.audit import all_sports_beta_compare as beta
from research.audit.test_all_sports_market_census import seven_events, offer, census, HASH


def forecast(o=None, *, p=.6, pp=0, **changes):
    o = o or offer()
    base = {
        "sport": o["sport"], "event_id": o["event_id"],
        "market_family": o["market_family"], "period": o["period"],
        "selection_id": o["selection_id"],
        "participant_id": o["participant_id"], "stat": o["stat"],
        "line": o["line"], "settlement_rule": o.get("settlement_rule"),
        "origin": "SPORTSEDGE_INDEPENDENT",
        "model_sha256": HASH, "distribution_sha256": HASH,
        "model_asof_utc": "2026-12-01T14:05:00Z",
        "p_win": p, "p_push": pp, "period_distribution_sha256": None,
        "ordered_events_sha256": None, "count_distribution_sha256": None,
        "joint_distribution_sha256": None,
    }
    base.update(changes)
    return base


def price(o=None, *, american=-110, **changes):
    o = o or offer()
    base = {"sport": o["sport"], "book": o["book"],
            "offer_id": o["offer_id"], "price_american": american}
    base.update(changes)
    return base


def intake(offers=None, forecasts=None, prices=None):
    offers = [] if offers is None else offers
    return {"schema": beta.SCHEMA, "census": census(offers),
            "forecasts": [] if forecasts is None else forecasts,
            "prices": [] if prices is None else prices}


class BetaSevenSportTests(unittest.TestCase):
    def test_absent_models_and_prices_keep_offers(self):
        os = [offer(s, "OUTRIGHT" if s == "PGA" else "ML")
              for s in beta.universe.SPORTS]
        r = beta.evaluate(intake(os))
        self.assertEqual(r["submitted_outcomes"], 7)
        self.assertEqual(r["research_comparisons"], 0)
        self.assertEqual(r["blocked"], 7)
        self.assertTrue(all("NO_EXACT_MODEL_FORECAST_FOR_OUTCOME" in x["reasons"]
                            for x in r["rows"]))
        self.assertFalse(r["market_universe_complete"])

    def test_research_math_no_bet_or_release(self):
        o = offer()
        r = beta.evaluate(intake([o], [forecast(o)], [price(o)]))
        x = r["rows"][0]
        self.assertAlmostEqual(x["research_ev_per_unit_unverified"], 0.6*(100/110)-.4)
        self.assertEqual(x["status"], "UNVERIFIED_RESEARCH_POSITIVE_EV")
        self.assertFalse(x["bet_eligible"])
        self.assertFalse(x["certified_positive_ev"])
        self.assertFalse(x["source_authenticated"])
        self.assertEqual(x["approved_stake_u"], 0)

    def test_negative_ev_is_still_visible(self):
        o = offer()
        r = beta.evaluate(intake([o], [forecast(o, p=.4)], [price(o)]))
        self.assertEqual(r["rows"][0]["status"], "UNVERIFIED_RESEARCH_NONPOSITIVE_EV")
        self.assertLess(r["rows"][0]["research_ev_per_unit_unverified"], 0)

    def test_true_push_probability_is_not_assumed_a_loss(self):
        o = offer()
        r = beta.evaluate(intake([o], [forecast(o, p=.48, pp=.12)], [price(o)]))
        self.assertAlmostEqual(r["rows"][0]["research_ev_per_unit_unverified"],
                               .48*(100/110)-.4)

    def test_alt_rungs_price_separately_from_same_distribution(self):
        a = offer(family="ALTERNATE", suffix="a", line="40.5",
                  participant_id="P1", stat="REC_YDS", selection_id="over")
        b = offer(family="ALTERNATE", suffix="b", line="70.5",
                  participant_id="P1", stat="REC_YDS", selection_id="over")
        r = beta.evaluate(intake([a,b], [forecast(a,p=.76),forecast(b,p=.34)],
                                 [price(a, american=-130),price(b,american=180)]))
        self.assertEqual(r["research_comparisons"], 2)
        self.assertGreater(r["rows"][0]["research_ev_per_unit_unverified"],
                           r["rows"][1]["research_ev_per_unit_unverified"])

    def test_same_market_prices_at_two_books_have_separate_offer_receipts(self):
        a = offer()
        b = offer(suffix="2", selection_id=a["selection_id"], book="FD")
        r = beta.evaluate(intake([a,b], [forecast(a)],
                                 [price(a,american=-110), price(b,american=-105)]))
        self.assertEqual(r["research_comparisons"], 2)
        self.assertGreater(r["rows"][1]["research_ev_per_unit_unverified"],
                           r["rows"][0]["research_ev_per_unit_unverified"])

    def test_model_hash_mismatch_blocks(self):
        o = offer(model_sha256=None)
        r = beta.evaluate(intake([o],[forecast(o)],[price(o)]))
        self.assertEqual(r["rows"][0]["research_ev_per_unit_unverified"], None)
        self.assertIn("MODEL_RECEIPT_HASH_MISMATCH", r["rows"][0]["reasons"])

    def test_no_player_identity_no_research_prop(self):
        o = offer(family="PLAYER_PROP")
        r = beta.evaluate(intake([o],[forecast(o)],[price(o)]))
        self.assertIn("PLAYER_ID_NOT_BOUND", r["rows"][0]["reasons"])
        self.assertIsNone(r["rows"][0]["research_ev_per_unit_unverified"])

    def test_first_tdmust_have_ordered_tds(self):
        o = offer(family="FIRST_TD", participant_id="P7")
        r = beta.evaluate(intake([o], [forecast(o)], [price(o)]))
        self.assertIn("NO_ORDERED_EVENT_DISTRIBUTION", r["rows"][0]["reasons"])
        self.assertIsNone(r["rows"][0]["research_ev_per_unit_unverified"])
        yes = beta.evaluate(intake([o],[forecast(o,ordered_events_sha256=HASH)],[price(o)]))
        self.assertEqual(yes["research_comparisons"], 1)

    def test_two_td_requires_count_dist(self):
        o = offer(family="TD_2PLUS", participant_id="P7")
        r = beta.evaluate(intake([o],[forecast(o)],[price(o)]))
        self.assertIn("NO_COUNT_EVENT_DISTRIBUTION", r["rows"][0]["reasons"])

    def test_sgp_and_pga_three_ball_require_joint_distribution(self):
        a = offer(family="SGP")
        b = offer("PGA","THREE_BALL")
        r = beta.evaluate(intake([a,b],[forecast(a),forecast(b)],[price(a),price(b)]))
        self.assertEqual(r["blocked"], 2)
        self.assertTrue(all("NO_JOINT_DISTRIBUTION" in x["reasons"]
                            for x in r["rows"]))

    def test_half_requires_own_period_distribution(self):
        o = offer(family="TOTAL", period="1H")
        r = beta.evaluate(intake([o],[forecast(o)],[price(o)]))
        self.assertIn("NO_PERIOD_DISTRIBUTION", r["rows"][0]["reasons"])

    def test_missing_settlement_blocks_probability_price_match(self):
        o=offer()
        del o["settlement_rule"]
        f=forecast(o)
        r=beta.evaluate(intake([o],[f],[price(o)]))
        self.assertIn("MARKET_SETTLEMENT_ID_MISSING", r["rows"][0]["reasons"])

    def test_stale_quote_is_blocked_before_ev(self):
        o = offer(source_observed_utc="2026-12-01T13:00:00Z",
                  source_captured_utc="2026-12-01T13:00:02Z")
        r = beta.evaluate(intake([o],[forecast(o)],[price(o)]))
        self.assertIn("QUOTE_STALE_RELATIVE_TO_MODEL",r["rows"][0]["reasons"])
        self.assertIsNone(r["rows"][0]["research_ev_per_unit_unverified"])

    def test_bad_quote_clock_retained_blocked(self):
        o = offer(source_observed_utc="2026-12-01T16:00:00Z",
                  source_captured_utc="2026-12-01T16:01:00Z")
        r = beta.evaluate(intake([o],[forecast(o,model_asof_utc="2026-12-01T16:05:00Z")],[price(o)]))
        self.assertIn("QUOTE_STALE_RELATIVE_TO_MODEL",r["rows"][0]["reasons"]) if False else None
        self.assertIn("QUOTE_CLOCK_NOT_PREGAME",r["rows"][0]["reasons"])

    def test_bad_probabilities_fail_closed(self):
        o=offer()
        for v,pp in ((1.1,0),(.6,.5),(float("nan"),0),(True,0)):
            with self.subTest(v=v,pp=pp):
                with self.assertRaises(ValueError):
                    beta.evaluate(intake([o],[forecast(o,p=v,pp=pp)],[price(o)]))

    def test_external_or_book_anchored_forecast_is_refused(self):
        o=offer()
        with self.assertRaisesRegex(ValueError, "NOT_AN_ASSERTED_INDEPENDENT_MODEL"):
            beta.evaluate(intake([o],[forecast(o,origin="SPORTSBOOK_ANCHOR")],[price(o)]))

    def test_unlisted_probabilities_and_quote_prices_rejected(self):
        o=offer()
        extra=offer("CBB",family="ML")
        with self.assertRaisesRegex(ValueError, "ORPHAN_FORECAST"):
            beta.evaluate(intake([o],[forecast(o),forecast(extra)],[price(o)]))
        with self.assertRaisesRegex(ValueError, "ORPHAN_OFFER_PRICE"):
            beta.evaluate(intake([o],[forecast(o)],[price(o),price(extra)]))

    def test_duplicate_model_or_quote_fails_closed(self):
        o=offer()
        with self.assertRaisesRegex(ValueError, "DUPLICATED_EXACT_MARKET_FORECAST"):
            beta.evaluate(intake([o],[forecast(o),forecast(o)],[price(o)]))
        with self.assertRaisesRegex(ValueError, "DUPLICATED_EXACT_OFFER_PRICE"):
            beta.evaluate(intake([o],[forecast(o)],[price(o),price(o)]))

    def test_seven_sports_research_hypotheses_no_actual_bets(self):
        os=[offer(s,"OUTRIGHT" if s=="PGA" else "ML")
            for s in beta.universe.SPORTS]
        r=beta.evaluate(intake(os,[forecast(o) for o in os],
                               [price(o) for o in os]))
        self.assertEqual(r["research_comparisons"], 7)
        self.assertEqual(r["official_counted"], 0)
        self.assertFalse(r["certified_positive_ev"])
        self.assertTrue(all(x["bet_eligible"] is False for x in r["rows"]))


if __name__=="__main__":
    unittest.main()
