"""CBB skew prop challenger: market-blind mean, versioned rows, push-aware EV, no stars."""
import copy, csv, hashlib, os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cbb_prop_skew as S
import sportsedge_cbb_model as M
import test_cbb as T


def rewrite_props(inputs, mutate):
    rows = M.read_csv(inputs["props"]); rows = mutate(copy.deepcopy(rows))
    d = tempfile.mkdtemp(); p = os.path.join(d, "props.csv")
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    return dict(inputs, props=p)


class T1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = T.make_samples()
        cls.res = S.price_props_skew(cls.inputs)

    def test_rows_carry_version_and_sum_to_one(self):
        self.assertTrue(self.res["rows"])
        for r in self.res["rows"]:
            self.assertEqual(r["distribution"], "cbb-prop-skew-v1")
            self.assertAlmostEqual(r["p_win"] + r["p_push"] + r["p_loss"], 1.0, places=12)
            self.assertIsNone(r["stars"]); self.assertEqual(r["approved_stake_u"], 0)

    def test_both_sides_kept_coverage_separate_from_eligibility(self):
        keys = {(r["player"], r["stat"], r["line"]) for r in self.res["rows"]}
        for k in keys:
            sides = {r["side"] for r in self.res["rows"] if (r["player"], r["stat"], r["line"]) == k}
            self.assertEqual(sides, {"over", "under"})
        self.assertTrue(any(not r["eligible"] for r in self.res["rows"]))

    def test_mean_is_market_blind(self):
        def bump(rows):
            for r in rows:
                r["over_price"], r["under_price"] = "-160", "135"
            return rows
        other = S.price_props_skew(rewrite_props(self.inputs, bump))
        m = lambda res: sorted((r["player"], r["side"], r["model_mean"], r["p_win"]) for r in res["rows"])
        self.assertEqual(m(self.res), m(other))

    def test_push_aware_ev(self):
        for r in self.res["rows"]:
            self.assertAlmostEqual(r["raw_ev"], r["p_win"] * (M.am_to_dec(r["price"]) - 1) - r["p_loss"], places=12)

    def test_integer_line_has_push(self):
        def integer(rows):
            rows[0]["line"] = "19"; return rows
        res = S.price_props_skew(rewrite_props(self.inputs, integer))
        r = next(x for x in res["rows"] if x["line"] == 19.0)
        self.assertGreater(r["p_push"], 0.0)

    def test_out_player_withheld_with_reason(self):
        self.assertIn("PLAYER_OUT", [w["reason"] for w in self.res["withheld"]])

    def test_bad_price_withheld_not_crash(self):
        def bad(rows):
            rows[0]["over_price"] = "-110.5"; return rows
        res = S.price_props_skew(rewrite_props(self.inputs, bad))
        self.assertIn("NOT_PRICED", [w["reason"] for w in res["withheld"]])

    def test_pinned_model_untouched(self):
        data = open(M.__file__, "rb").read()
        self.assertEqual(hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(),
                         "8bbe83b7a17d184b3521094b40e00be66ba0f852")


if __name__ == "__main__":
    unittest.main()
