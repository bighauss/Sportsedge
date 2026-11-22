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


if __name__ == "__main__":
    unittest.main()
