"""Synthetic-only regressions for the all-model, all-market census."""
import copy
import json
import unittest

from research.audit import all_sports_market_census as m

HASH = "sha256:" + "a" * 64
KICK = "2026-12-01T18:00:00Z"


def seven_events():
    return [{"sport": sport, "event_id": "event_" + sport, "start_utc": KICK}
            for sport in m.SPORTS]


def offer(sport="NFL", family="ML", *, suffix="1", line="", **overrides):
    base = {
        "sport": sport, "event_id": "event_" + sport,
        "offer_id": "offer_" + sport + "_" + suffix,
        "market_family": family, "period": "FG", "selection_id": "home_" + suffix,
        "participant_id": "", "stat": "", "line": line, "book": "DK",
        "source_observed_utc": "2026-12-01T14:00:00Z",
        "source_captured_utc": "2026-12-01T14:00:01Z",
        "quote_sha256": HASH, "model_sha256": HASH, "close_sha256": None,
        "final_sha256": None, "settlement_rule": "POSTED_RULES",
    }
    base.update(overrides)
    return base


def census(attempts=None, events=None):
    return {"schema": m.SCHEMA,
            "events": seven_events() if events is None else events,
            "attempts": [] if attempts is None else attempts}


class SevenSportMarketTests(unittest.TestCase):
    def test_every_sport_and_family_visible_with_no_supplied_offers(self):
        rep = m.assess(census())
        self.assertEqual({r["sport"] for r in rep["matrix"]}, set(m.SPORTS))
        self.assertEqual(len(rep["matrix"]), sum(len(f) for f in m.FAMILIES.values()))
        self.assertEqual(rep["attempted_outcomes"], 0)
        self.assertTrue(all(r["state"] == "NOT_SUBMITTED_OFFERING_UNKNOWN"
                            for r in rep["matrix"]))
        self.assertFalse(rep["market_universe_complete"])
        self.assertEqual(rep["approved_stake_u"], 0)

    def test_missing_sport_schedule_never_means_not_offered(self):
        rep = m.assess(census(events=seven_events()[:1]))
        pga = next(r for r in rep["matrix"] if r["sport"] == "PGA")
        self.assertEqual(pga["state"], "NO_SCHEDULE_SUPPLIED")
        self.assertEqual(pga["submitted_outcomes"], 0)

    def test_each_native_sport_has_reference_not_asserted_execution(self):
        rep = m.assess(census())
        for row in rep["matrix"]:
            self.assertTrue(row["native_model_reference"].startswith("models/"))
            self.assertFalse(row["model_validated"])
            self.assertTrue(row["model_code_presence_is_not_execution"])
            self.assertEqual(row["five_sport_research_pricer_path"],
                             row["sport"] in m.FIVE_SPORT_RESEARCH_PRICER)

    def test_submitted_all_seven_sports_stay_unverified(self):
        xs = [offer(sport, "ML") if sport != "PGA" else offer(sport, "OUTRIGHT")
              for sport in m.SPORTS]
        r = m.assess(census(xs))
        self.assertEqual(r["attempted_outcomes"], 7)
        self.assertTrue(all(x["status"] == "PAPER_0U_UNVERIFIED"
                            for x in r["attempts"]))
        self.assertTrue(all(not x["source_authenticated"] for x in r["attempts"]))
        self.assertEqual(r["model_releases_certified"], 0)

    def test_missing_settlement_is_blocked_and_explicit_one_retained(self):
        missing = offer()
        del missing["settlement_rule"]
        r = m.assess(census([missing]))
        self.assertIn("MARKET_SETTLEMENT_ID_MISSING", r["attempts"][0]["reasons"])
        valid = m.assess(census([offer(settlement_rule="REGULATION")]))
        self.assertEqual(valid["attempts"][0]["settlement_rule"], "REGULATION")

    def test_alt_ladder_each_rung_separate_and_not_certified(self):
        xs = [
            offer("NFL", "ALTERNATE", suffix="a", line="39.5",
                  participant_id="P123", stat="receiving_yards",
                  selection_id="over"),
            offer("NFL", "ALTERNATE", suffix="b", line="59.5",
                  participant_id="P123", stat="receiving_yards",
                  selection_id="over"),
        ]
        result = m.assess(census(xs))
        self.assertEqual(result["attempted_outcomes"], 2)
        self.assertEqual(next(r for r in result["matrix"] if r["sport"] == "NFL"
                              and r["family"] == "ALTERNATE")["submitted_outcomes"], 2)

    def test_joint_components_unique_and_exact_for_sgp_and_pga(self):
        a = offer(family="SGP", suffix="a", selection_id="yes",
                  joint_leg_ids=["TD_A","REC_OVER"])
        b = offer(family="SGP", suffix="b", selection_id="yes",
                  joint_leg_ids=["TD_A","RUSH_OVER"])
        r = m.assess(census([a,b]))
        self.assertEqual(r["attempted_outcomes"], 2)
        self.assertEqual(r["attempts"][0]["joint_leg_ids"], ["TD_A","REC_OVER"])
        self.assertEqual(r["attempts"][1]["joint_leg_ids"], ["TD_A","RUSH_OVER"])
        missing = m.assess(census([offer("PGA","THREE_BALL")]))
        self.assertIn("JOINT_COMPONENT_IDENTITIES_MISSING",
                      missing["attempts"][0]["reasons"])
        with self.assertRaisesRegex(ValueError,"INVALID_JOINT_LEG_IDENTITIES"):
            m.assess(census([offer(family="SGP",
                                   joint_leg_ids=["TD_A","TD_A"])]))

    def test_non_joint_market_with_unrelated_legs_is_blocked(self):
        r = m.assess(census([offer(joint_leg_ids=["x","y"])]))
        self.assertIn("JOINT_COMPONENTS_ON_SINGLE_MARKET",
                      r["attempts"][0]["reasons"])

    def test_missing_prop_identity_has_reason(self):
        r = m.assess(census([offer(family="PLAYER_PROP")]))
        self.assertIn("PLAYER_ID_NOT_BOUND", r["attempts"][0]["reasons"])
        self.assertIn("PLAYER_STAT_NOT_BOUND", r["attempts"][0]["reasons"])

    def test_missing_all_source_data_does_not_imply_empty_model_edge(self):
        r = m.assess(census([offer(source_observed_utc=None,
                                    source_captured_utc=None,
                                    quote_sha256=None, model_sha256=None)]))
        codes = r["attempts"][0]["reasons"]
        self.assertIn("QUOTE_SOURCE_NOT_ATTESTED", codes)
        self.assertIn("INDEPENDENT_MODEL_RECEIPT_MISSING", codes)
        self.assertIn("CLOSING_QUOTE_NOT_CAPTURED", codes)
        self.assertNotIn("NO_POSITIVE_EV", codes)

    def test_hashes_without_source_are_still_not_certified(self):
        r = m.assess(census([offer(close_sha256=HASH, final_sha256=HASH)]))
        self.assertEqual(r["attempts"][0]["reasons"],
                         ["RECEIPT_METADATA_NOT_INDEPENDENTLY_AUTHENTICATED"])
        self.assertEqual(r["official_counted"], 0)

    def test_postgame_or_reversed_quote_clock_retained_and_flagged(self):
        xs = [offer(suffix="a", source_observed_utc="2026-12-01T19:00:00Z",
                    source_captured_utc="2026-12-01T19:01:00Z"),
              offer(suffix="b", source_observed_utc="2026-12-01T14:30:00Z",
                    source_captured_utc="2026-12-01T14:00:00Z")]
        r = m.assess(census(xs))
        self.assertEqual(r["attempted_outcomes"], 2)
        self.assertTrue(all("QUOTE_CLOCK_NOT_PREGAME" in x["reasons"]
                            for x in r["attempts"]))

    def test_cross_sport_same_event_id_does_not_collide(self):
        es = seven_events()
        es[0]["event_id"] = "shared"
        es[1]["event_id"] = "shared"
        xs = [offer("NFL", event_id="shared"),
              offer("CFB", event_id="shared")]
        self.assertEqual(m.assess(census(xs, es))["attempted_outcomes"], 2)

    def test_an_offer_outside_schedule_is_refused(self):
        with self.assertRaisesRegex(ValueError, "OFFER_OUTSIDE_SUPPLIED_SCHEDULE"):
            m.assess(census([offer(event_id="not_listed")]))

    def test_duplicate_offer_or_exact_outcome_is_refused(self):
        a = offer()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PROVIDER_OFFER_ID"):
            m.assess(census([a, copy.deepcopy(a)]))
        b = offer(suffix="2", selection_id=a["selection_id"])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_EXACT_OUTCOME"):
            m.assess(census([a, b]))

    def test_same_outcome_different_books_is_a_separate_offer(self):
        a = offer()
        b = offer(suffix="2", selection_id=a["selection_id"], book="FD")
        self.assertEqual(m.assess(census([a, b]))["attempted_outcomes"], 2)

    def test_bad_input_is_quarantined_by_exception(self):
        for edits in ({"line": "NaN"}, {"line": "inf"}, {"line": "1e9999"},
                      {"quote_sha256": "fake"}, {"market_family": "BAD"},
                      {"offer_id": ""}, {"period": ""}):
            with self.subTest(edits=edits):
                with self.assertRaises(ValueError):
                    m.assess(census([offer(**edits)]))

    def test_json_duplicate_keys_and_nonfinite_numbers_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            json.loads('{"schema":"a","schema":"b"}', object_pairs_hook=m._pairs)
        with self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
            json.loads('{"x":NaN}', parse_constant=lambda x: (_ for _ in ()).throw(
                ValueError("NONFINITE_JSON:" + x)))


if __name__ == "__main__":
    unittest.main()
