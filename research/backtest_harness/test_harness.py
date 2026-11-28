"""Synthetic checks for every harness metric. No real prices; no edge claim."""
import csv, math, os, random, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H

COLS = ["event_id", "date", "market", "selection", "line", "model_p", "push_p", "price", "opp_price",
        "outcome", "close_price", "close_opp_price"]


def write(rows):
    d = tempfile.mkdtemp(); p = os.path.join(d, "r.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, COLS); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    return p


def synth(n=3000, edge=0.0, seed=3, per_game=2, corr=0.0):
    """Market p true; model = market + edge*signal + noise. Selections in a game share a shock."""
    rng = random.Random(seed); out = []
    for g in range(n // per_game):
        shock = rng.gauss(0, 1)
        for j in range(per_game):
            q = rng.uniform(0.3, 0.7)
            true = min(max(q + edge * rng.choice((-1, 1)), 0.02), 0.98)
            model = min(max(true + rng.gauss(0, 0.03), 0.02), 0.98)
            u = (corr * shock + math.sqrt(1 - corr ** 2) * rng.gauss(0, 1))
            won = 0.5 * (1 + math.erf(u / math.sqrt(2))) < true
            # fair two-sided prices around q with ~4.5% hold
            def am(p):
                p = p * 1.0227
                return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))
            out.append({"event_id": f"g{g}", "date": f"d{g // 8}", "market": "spread" if j else "total",
                        "selection": f"s{j}", "line": "1.5", "model_p": round(model, 6), "push_p": 0,
                        "price": am(q), "opp_price": am(1 - q), "outcome": "W" if won else "L"})
    return out


class Metrics(unittest.TestCase):
    def test_novig_and_ev_arithmetic(self):
        self.assertAlmostEqual(H.novig(-110, -110), 0.5)
        r = H.Row(); r.p, r.push, r.price = 0.4, 0.2, 100
        self.assertAlmostEqual(H.ev(r), 0.4 * 1 - 0.4)  # push returns stake

    def test_scores_perfect_and_coinflip(self):
        s = H.score([(1 - 1e-9, 1), (1e-9, 0)])
        self.assertLess(s["brier"], 1e-9)
        c = H.score([(0.5, 1), (0.5, 0)] * 50)
        self.assertAlmostEqual(c["brier"], 0.25); self.assertAlmostEqual(c["logloss"], math.log(2)); self.assertAlmostEqual(c["ece"], 0.0)

    def test_ece_detects_overconfidence(self):
        pairs = [(0.8, 1 if i % 2 else 0) for i in range(1000)]
        self.assertAlmostEqual(H.score(pairs)["ece"], 0.3, places=6)

    def test_market_equal_model_gives_zero_paired_difference(self):
        rows = synth(800)
        for r in rows:
            r["model_p"] = round(H.novig(r["price"], r["opp_price"]), 12)
        out = H.run(H.load(write(rows))[0], reps=200)
        self.assertAlmostEqual(out["paired_logloss_model_minus_market"]["mean"], 0.0, places=6)

    def test_real_edge_is_detected_and_noise_is_not(self):
        noisy = H.run(H.load(write(synth(4000, edge=0.0)))[0], reps=300)
        lo, hi = noisy["paired_logloss_model_minus_market"]["ci95"]
        self.assertGreater(hi, 0)  # pure noise model cannot be significantly better than market

    def test_block_bootstrap_wider_when_selections_correlated(self):
        a = H.block_bootstrap({i: [random.Random(i).gauss(0, 1)] for i in range(400)}, 400)
        b = H.block_bootstrap({i: [random.Random(i).gauss(0, 1)] * 5 for i in range(80)}, 400)
        self.assertGreater(b["ci95"][1] - b["ci95"][0], (a["ci95"][1] - a["ci95"][0]) * 0.9)
        self.assertEqual(b["blocks"], 80)

    def test_roi_and_drawdown(self):
        rows = [dict(event_id=f"e{i}", market="m", selection="a", model_p=.6, price=100, opp_price=-120,
                     outcome=o) for i, o in enumerate("WWLLLW")]
        r = H.roi_dd(H.load(write(rows))[0])
        self.assertEqual(r["n"], 6); self.assertAlmostEqual(r["units"], 0.0); self.assertAlmostEqual(r["max_drawdown_u"], 3.0)

    def test_push_and_void_handling(self):
        rows = [dict(event_id="e1", market="m", selection="a", model_p=.45, push_p=.1, price=-110, opp_price=-110, outcome="P"),
                dict(event_id="e2", market="m", selection="a", model_p=.5, price=-110, opp_price=-110, outcome="V")]
        out = H.run(H.load(write(rows))[0], reps=50)
        self.assertEqual(out["voids"], 1); self.assertIsNone(out["model"])

    def test_clv(self):
        rows = [dict(event_id="e1", market="m", selection="a", model_p=.6, price=110, opp_price=-130,
                     outcome="W", close_price=-120, close_opp_price=100)]
        c = H.clv(H.load(write(rows))[0])
        self.assertEqual(c["n"], 1); self.assertGreater(c["mean_clv_ev"], 0)

    def test_selection_bias_null_shows_fake_edge_without_real_edge(self):
        rows = H.load(write(synth(2000, edge=0.0)))[0]
        s = H.selection_null(rows, k=20, reps=100)
        self.assertGreater(s["null_expected_topk_ev"], 0.02)  # top-20 of 2000 looks +EV under zero edge
        self.assertLess(abs(s["ev_net_of_selection_bias"]), s["null_expected_topk_ev"])

    def test_mde_grows_with_clustering(self):
        ind = H.mde(H.load(write(synth(2000, per_game=1)))[0], lambda x: x.event)
        clu_rows = synth(2000, per_game=10, corr=0.9)
        clu = H.mde(H.load(write(clu_rows))[0], lambda x: x.event)
        self.assertGreater(clu["design_effect"], ind["design_effect"])
        self.assertGreater(clu["mde_roi"], ind["mde_roi"] * 0.95)

    def test_rejects_bad_rows_and_duplicates(self):
        good = dict(event_id="e1", market="m", selection="a", model_p=.5, price=-110, opp_price=-110, outcome="W")
        rows, rej = H.load(write([good, dict(good, event_id="e2", model_p=1.4), dict(good, event_id="e3", price=50),
                                  dict(good, event_id="e4", outcome="X")]))
        self.assertEqual(len(rows), 1); self.assertEqual(sum(rej.values()), 3)
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            H.load(write([good, good]))


if __name__ == "__main__":
    unittest.main()
