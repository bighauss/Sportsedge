import unittest

import key_number_margin as K


class KeyNumbers(unittest.TestCase):
    def test_pmf_sums_to_one_and_keeps_shape_without_weights(self):
        p = K.pmf(2.5)
        self.assertAlmostEqual(sum(p.values()), 1, 9)
        self.assertAlmostEqual(p[3] / p[4], K.N.pdf((3 - 2.5) / 13.5) / K.N.pdf((4 - 2.5) / 13.5), 2)

    def test_weights_raise_key_mass(self):
        w = {3: 2.8, 7: 2.3}
        self.assertGreater(K.pmf(3, weights=w)[3], 2 * K.pmf(3)[3])

    def test_fit_recovers_heavy_three_and_never_below_one(self):
        margins = [3] * 15 + [-3] * 5 + [1, 2, 4, 5, 6, 8, 10, 13, 14, 17, 21] * 7
        w = K.fit_weights(margins)
        self.assertGreater(w[3], 2.0)
        self.assertGreaterEqual(w[7], 1.0)
        self.assertEqual(K.fit_weights([]), {})

    def test_cover_push_on_integer_only(self):
        w, p, l = K.cover(3.0, -3)
        self.assertGreater(p, 0)
        self.assertAlmostEqual(w + p + l, 1)
        w2, p2, _ = K.cover(3.0, -2.5)
        self.assertEqual(p2, 0)

    def test_half_point_across_three_worth_more_with_keys(self):
        w = {3: 2.8, 7: 2.3}
        plain = K.cover(3, -2.5)[0] - K.cover(3, -3.5)[0]
        keyed = K.cover(3, -2.5, weights=w)[0] - K.cover(3, -3.5, weights=w)[0]
        self.assertGreater(keyed, 2 * plain)

    def test_ev_push_refund(self):
        self.assertAlmostEqual(K.ev(0.5, 0.05, -110), 0.004545, 5)

    def test_log_loss_prefers_weighted_on_key_heavy_data(self):
        data = [(3, 0.0)] * 10 + [(-3, 0.0)] * 5 + [(k, 0.0) for k in (1, 4, 6, 10, -8, 14, -2, 17)]
        w = K.fit_weights([m for m, _ in data])
        self.assertLess(K.log_loss(data, weights=w), K.log_loss(data))


    def test_nan_inf_and_sd_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(value=str(value)):
                with self.assertRaisesRegex(ValueError, "INVALID_MEAN"):
                    K.pmf(value)
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(sd=str(value)):
                with self.assertRaisesRegex(ValueError, "INVALID_SD"):
                    K.pmf(2, sd=value)
        with self.assertRaisesRegex(ValueError, "MARGIN_DISTRIBUTION_UNSUPPORTED"):
            K.pmf(100000, sd=.01)

    def test_key_weights_fail_closed_on_invalid_values(self):
        bad = ({3: float("nan")}, {7: float("inf")}, {3: -1}, {3: .5},
               {2: 2.0}, {True: 2.0}, [3], {"3": 2})
        for weights in bad:
            with self.subTest(weights=str(weights)):
                with self.assertRaises(ValueError):
                    K.pmf(3, weights=weights)

    def test_integer_margin_and_strict_key_inputs(self):
        for margins in ([True], [1.5], [71], [float("nan")]):
            with self.subTest(margins=str(margins)):
                with self.assertRaisesRegex(ValueError, "INVALID_FINAL_MARGIN"):
                    K.fit_weights(margins)
        with self.assertRaisesRegex(ValueError, "KEY_LIST_INVALID"):
            K.fit_weights([3], keys=(3, 3))
        self.assertEqual(K.fit_weights([3, 7]), K.fit_weights([3, 7]))

    def test_pit_asof_cutoff_includes_only_observed_completed_finals(self):
        src = [{"event_id": "event1", "margin": 3,
                "completed_utc": "2026-11-01T02:00:00Z",
                "result_observed_utc": "2026-11-01T02:05:00Z"},
               {"event_id": "event2", "margin": 7,
                "completed_utc": "2026-11-08T02:00:00Z",
                "result_observed_utc": "2026-11-08T02:10:00Z"}]
        result = K.fit_weights_asof(src, asof_utc="2026-11-15T19:00:00Z")
        self.assertEqual(result["eligible_events"], 2)
        self.assertEqual(result["weights"], K.fit_weights([3, 7]))
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["model_released"])

    def test_pit_refuses_lookahead_and_missing_or_duplicate_event(self):
        base = {"event_id": "evt", "margin": 3,
                "completed_utc": "2026-11-14T20:00:00Z",
                "result_observed_utc": "2026-11-15T19:00:00Z"}
        cutoff = "2026-11-15T19:00:00Z"
        with self.assertRaisesRegex(ValueError, "PIT_RESULT_NOT_AVAILABLE_BEFORE_ASOF"):
            K.fit_weights_asof([base], asof_utc=cutoff)
        with self.assertRaisesRegex(ValueError, "PIT_DUPLICATE_EVENT_ID"):
            K.fit_weights_asof([base, base], asof_utc="2026-11-16T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "PIT_SOURCE_SCHEMA_INVALID"):
            K.fit_weights_asof([{"event_id": "evt", "margin": 3}],
                               asof_utc="2026-11-16T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "UTC_Z_REQUIRED"):
            K.fit_weights_asof([base], asof_utc="2026-11-16T00:00:00")
        with self.assertRaisesRegex(ValueError, "PIT_RESULT_NOT_AVAILABLE_BEFORE_ASOF"):
            K.fit_weights_asof([dict(base, result_observed_utc="2026-11-14T19:00:00Z")],
                               asof_utc="2026-11-16T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "PIT_RECORDS_REQUIRED"):
            K.fit_weights_asof([], asof_utc="2026-11-16T00:00:00Z")

    def test_ev_rejects_invalid_odds_probability_and_empty_score(self):
        for price in (0, 99, -99, True, -0.5, 100001, None):
            with self.subTest(price=str(price)):
                with self.assertRaisesRegex(ValueError, "INVALID_AMERICAN_ODDS"):
                    K.ev(.50, 0., price)
        for win, push in ((float("nan"), 0), (.5, float("inf")),
                          (-.1, 0), (.95, .10), (True, .1)):
            with self.subTest(pair=(win, push)):
                with self.assertRaises(ValueError):
                    K.ev(win, push, -110)
        with self.assertRaisesRegex(ValueError, "EVALUATION_ROWS_REQUIRED"):
            K.log_loss([])
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_SPREAD_LINE"):
            K.cover(0, -2.25)
        with self.assertRaisesRegex(ValueError, "INVALID_SPREAD_LINE"):
            K.cover(0, float("nan"))

if __name__ == "__main__":
    unittest.main()
