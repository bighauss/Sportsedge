"""Synthetic regression tests for same-draw MLB player/inning research."""
import copy
import unittest

from models.mlb import shared_inning_sim as sim


def profiles():
    rates = {"OUT":.69,"BB":.08,"1B":.16,"2B":.04,"3B":.01,"HR":.02}
    return {side:[{"player_id":side[0]+str(i),"rates":dict(rates)}
                  for i in range(1,10)] for side in ("away","home")}


class SharedInningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = sim.simulate("SYNTH",profiles(),draws=160,seed=2026)

    def test_seed_and_hash_determinism(self):
        a=sim.simulate("SYNTH",profiles(),draws=30,seed=77)
        b=sim.simulate("SYNTH",profiles(),draws=30,seed=77)
        c=sim.simulate("SYNTH",profiles(),draws=30,seed=78)
        self.assertEqual(a["scenario_sha256"],b["scenario_sha256"])
        self.assertNotEqual(a["scenario_sha256"],c["scenario_sha256"])
        self.assertEqual(a["scenarios"],b["scenarios"])

    def test_same_draw_f5_and_first_inning_consistency(self):
        for d in self.samples["scenarios"]:
            self.assertLessEqual(d["first_away"],d["f5_away"])
            self.assertLessEqual(d["first_home"],d["f5_home"])
            self.assertLessEqual(d["f5_away"],d["away"])
            self.assertLessEqual(d["f5_home"],d["home"])
            self.assertGreaterEqual(d["innings"],9)
            self.assertEqual(sum(s["HITS"] for s in d["players"].values()),
                             sum(s["HITS"] for s in d["players"].values()))
            for p in d["players"].values():
                self.assertGreaterEqual(p["TB"],p["HITS"])
                self.assertGreaterEqual(p["HITS"],p["HR"])
        self.assertEqual(self.samples["official_counted"],0)

    def test_nrfi_yrfi_exact_complement(self):
        a=sim.settle(self.samples,"NRFI","nrfi")
        b=sim.settle(self.samples,"NRFI","yrfi")
        self.assertEqual(a["wins"],b["losses"])
        self.assertEqual(b["wins"],a["losses"])
        self.assertEqual(a["pushes"],0)
        self.assertEqual(a["scenario_sha256"],b["scenario_sha256"])

    def test_f5_moneyline_tie_push_and_opposite_symmetry(self):
        a=sim.settle(self.samples,"F5_ML","away")
        h=sim.settle(self.samples,"F5_ML","home")
        self.assertEqual(a["wins"],h["losses"])
        self.assertEqual(a["losses"],h["wins"])
        self.assertEqual(a["pushes"],h["pushes"])
        self.assertEqual(a["wins"]+a["losses"]+a["pushes"],self.samples["draws"])

    def test_integer_total_push_and_half_line_no_push(self):
        a=sim.settle(self.samples,"F5_TOTAL","over",5)
        b=sim.settle(self.samples,"F5_TOTAL","under",5)
        self.assertEqual(a["wins"],b["losses"])
        self.assertEqual(a["losses"],b["wins"])
        self.assertEqual(a["pushes"],b["pushes"])
        self.assertEqual(sim.settle(self.samples,"F5_TOTAL","over",5.5)["pushes"],0)

    def test_player_props_use_own_same_draw(self):
        pid="a1"
        for market,line in (("HITS",.5),("TB",1.5),("HR",.5)):
            a=sim.settle(self.samples,market,"over",line,player_id=pid)
            b=sim.settle(self.samples,market,"under",line,player_id=pid)
            self.assertEqual(a["wins"],b["losses"])
            self.assertEqual(a["losses"],b["wins"])
            self.assertEqual(a["scenario_sha256"],self.samples["scenario_sha256"])
        x=sim.settle(self.samples,"HITS","over",.5,player_id="absent")
        self.assertEqual(x["status"],"NO_FORECAST")

    def test_unresolved_extras_never_renormalized(self):
        d=copy.deepcopy(self.samples)
        d["unresolved_extra_innings"]=1
        g=sim.settle(d,"ML","away")
        self.assertEqual(g["status"],"UNRESOLVED_MARKET")
        self.assertNotIn("p_win",g)
        self.assertEqual(sim.settle(d,"F5_ML","away")["status"],"SIMULATED_RESEARCH")

    def test_unsupported_and_bad_source(self):
        self.assertEqual(sim.settle(self.samples,"PITCHER_K","over",5.5)["status"],"NO_FORECAST")
        with self.assertRaisesRegex(sim.NoForecast,"DUPLICATE_PLAYER_ID"):
            x=profiles();x["home"][0]["player_id"]=x["away"][0]["player_id"]
            sim.simulate("x",x,draws=2)
        with self.assertRaisesRegex(sim.NoForecast,"INVALID_PA_RATES"):
            x=profiles();x["home"][0]["rates"]["OUT"]=-.1
            sim.simulate("x",x,draws=2)
        with self.assertRaisesRegex(sim.NoForecast,"INVALID_SIM_CONTROL"):
            sim.simulate("x",profiles(),draws=0)

    def test_raw_ev_does_not_invent_benchmark(self):
        inp={"odds":[{"game_id":"SYNTH","market":"F5_TOTAL","selection":"over",
                      "line":"5.5","price":"-110","book":"DK"},
                     {"game_id":"SYNTH","market":"F5_TOTAL","selection":"under",
                      "line":"5.5","price":"-110","book":"DK"}],
             "prop_odds":[{"game_id":"SYNTH","player_id":"a1","market":"HITS",
                           "line":".5","over_price":"-150","under_price":"125"}]}
        rows=sim._offered(self.samples,inp,{"game_id":"SYNTH"})
        self.assertEqual(len(rows),4)
        self.assertTrue(all(x["status"]=="RESEARCH_RAW_EV_ONLY" for x in rows))
        self.assertTrue(all(x["no_vig"] is None and x["blended_ev"] is None for x in rows))
        self.assertTrue(all(x["official_counted"]==0 for x in rows))
        self.assertEqual(rows[0]["scenario_sha256"] if "scenario_sha256" in rows[0] else None,None)

    def test_rates_fail_closed_and_flag_league_walk_fallback(self):
        r,assumed=sim._rates({"ba":".255","iso":".180","hr_per_pa":".025"})
        self.assertTrue(assumed)
        self.assertAlmostEqual(sum(r.values()),1)
        with self.assertRaisesRegex(sim.NoForecast,"INCONSISTENT"):
            sim._rates({"ba":".15","iso":".01","hr_per_pa":".12"})

    def test_native_loader_projector_bridge_synthetic(self):
        from models.mlb import sportsedge_mlb_model as native, make_samples
        make_samples.main()
        inp=native.load_inputs(make_samples.OUT)
        # Make synthetic test-rate components internally coherent; never touch live inputs.
        for b in inp["batters"].values():
            b["iso"]="0.230";b["hr_per_pa"]="0.025"
        original=copy.deepcopy(inp["odds"])
        result=sim.run_research(inp,draws=8,seed=24)
        self.assertEqual(result["game_count"],2)
        self.assertEqual(len(result["games"]),2)
        self.assertTrue(all(g["status"]=="SIMULATED_RESEARCH" for g in result["games"]))
        self.assertTrue(all(g["n_sims"]==8 for g in result["games"]))
        self.assertEqual(original,inp["odds"])
        self.assertTrue(all(g["census"].get("NO_FORECAST",0)>0 for g in result["games"]))
        self.assertFalse(result["no_vig_verified"])

    def test_native_missing_starter_kept_in_denominator(self):
        from models.mlb import sportsedge_mlb_model as native, make_samples
        make_samples.main()
        inp=native.load_inputs(make_samples.OUT)
        inp["games"][0]["away_sp_id"]="absent"
        r=sim.run_research(inp,draws=2,seed=7)
        self.assertEqual(r["game_count"],2)
        self.assertEqual(r["games"][0]["status"],"NO_FORECAST")
        self.assertTrue(r["games"][0]["offers"])


if __name__=="__main__":
    unittest.main()
