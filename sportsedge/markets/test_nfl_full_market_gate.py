"""Synthetic regression tests: NEVER evidence of profitable/live betting."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest

from sportsedge.markets.nfl_full_market_gate import audit

T=datetime(2026,11,15,20,30,tzinfo=timezone.utc)
H="sha256:"+"a"*64
def ts(d): return d.isoformat()
def quote(**kw):
    r=dict(event_id="sea_lv",market_id="total",kind="TOTAL",period="FG",
           side="OVER",line="40.5",odds_american=-108,
           observed_at_utc=ts(T-timedelta(minutes=1)),
           event_start_utc=ts(T+timedelta(minutes=35)),
           source_sha256=H,quote_id="q1",book="DraftKings")
    r.update(kw)
    return r
def model(**kw):
    r=dict(total=42,margin_home=-6.5,
           asof_utc=ts(T-timedelta(hours=2)),source_sha256=H,
           players={"gsis1":{"REC_YDS":dict(mean=68,sd=20,
             asof_utc=ts(T-timedelta(hours=2)),source_sha256=H,
             confirmed_active=True,projected_targets=6)}})
    r.update(kw)
    return {"sea_lv":r}
def run(rows,forecast=None):
    return audit(rows,model() if forecast is None else forecast,decision_utc=ts(T))

class GateTests(unittest.TestCase):
    def test_two_sided_and_no_release(self):
        a=quote(); b=quote(side="UNDER",quote_id="q2",odds_american=-112)
        r=run([a,b])
        self.assertEqual(r["count"],2)
        self.assertEqual(r["approved_stake_u"],0)
        self.assertTrue(all("NO_MATCHED_TWO_SIDED_QUOTE" not in x["reasons"] for x in r["rows"]))
        self.assertTrue(all(x["raw_ev"] is None and x["official_counted"]==0 for x in r["rows"]))
    def test_single_side_blocked(self):
        self.assertIn("NO_MATCHED_TWO_SIDED_QUOTE",run([quote()])["rows"][0]["reasons"])
    def test_large_total_disagreement(self):
        self.assertIn("UNEXPLAINED_TOTAL_MODEL_MARKET_GAP",
                      run([quote()],model(total=46))["rows"][0]["reasons"])
    def test_spread_opposites_normalize_signs(self):
        a=quote(kind="SPREAD",market_id="spread",side="HOME",line="6.5")
        b=quote(kind="SPREAD",market_id="spread",side="AWAY",line="-6.5",quote_id="q2")
        r=run([a,b])
        for x in r["rows"]:
            self.assertNotIn("NO_MATCHED_TWO_SIDED_QUOTE",x["reasons"])
            self.assertNotIn("UNEXPLAINED_MARGIN_MODEL_MARKET_GAP",x["reasons"])
    def test_spread_gap(self):
        self.assertIn("UNEXPLAINED_MARGIN_MODEL_MARKET_GAP",
                      run([quote(kind="SPREAD",side="HOME",line="6.5")],
                          model(margin_home=0))["rows"][0]["reasons"])
    def test_xplus_never_two_sided(self):
        a=quote(kind="PLAYER_PROP_XPLUS",side="YES",line="70",
                player_id="gsis1",player_display="Example",stat="REC_YDS")
        self.assertIn("ONE_SIDED_XPLUS_NO_VIG_PAIR",run([a])["rows"][0]["reasons"])
    def test_truncated_id_not_inferred(self):
        a=quote(kind="PLAYER_PROP_XPLUS",side="YES",line="70",
                player_display="Michael…",stat="REC_YDS")
        reasons=run([a])["rows"][0]["reasons"]
        self.assertIn("PLAYER_ID_UNBOUND",reasons)
        self.assertIn("PLAYER_DISPLAY_TRUNCATED",reasons)
    def test_prop_active_and_volume(self):
        a=quote(kind="PLAYER_PROP",side="OVER",line="50.5",player_id="gsis1",
                stat="REC_YDS")
        f=model()
        p=f["sea_lv"]["players"]["gsis1"]["REC_YDS"]
        p["confirmed_active"]=False;p["projected_targets"]=3
        reasons=run([a],f)["rows"][0]["reasons"]
        self.assertIn("ACTIVE_STATUS_UNVERIFIED",reasons)
        self.assertIn("RECEIVING_TARGET_VOLUME_BELOW_4",reasons)
    def test_td_ordered_event_not_faked(self):
        a=quote(kind="FIRST_TD",side="YES",line="",player_id="gsis1")
        self.assertIn("NO_VALIDATED_ORDERED_TD_EVENT_MODEL",run([a])["rows"][0]["reasons"])
    def test_started_and_stale(self):
        a=quote(event_start_utc=ts(T-timedelta(seconds=1)))
        self.assertIn("EVENT_STARTED_OR_LIVE_PRICE",run([a])["rows"][0]["reasons"])
        b=quote(observed_at_utc=ts(T-timedelta(minutes=6)))
        self.assertIn("STALE_PRICE_RECAPTURE",run([b])["rows"][0]["reasons"])
    def test_future_quote_duplicate(self):
        a=quote(observed_at_utc=ts(T+timedelta(seconds=1)))
        self.assertIn("QUOTE_FROM_FUTURE",run([a])["rows"][0]["reasons"])
        self.assertTrue(all(
            "DUPLICATE_QUOTE_ID" in row["reasons"]
            for row in run([quote(),quote()])["rows"]))
    def test_all_copies_quarantined_independent_of_row_order(self):
        a=quote(quote_id="reused",odds_american=-108)
        b=quote(quote_id="reused",odds_american=-125)
        for raw in ([a,b],[b,a]):
            out=run(raw)["rows"]
            self.assertEqual(len(out),2)
            self.assertTrue(all(
                "DUPLICATE_QUOTE_ID" in item["reasons"]
                and "DUPLICATE_QUOTE_CANNOT_ESTABLISH_TWO_SIDED_PAIR" in item["reasons"]
                for item in out))
            self.assertTrue(all(item["approved_stake_u"]==0 for item in out))

    def test_unique_opposite_never_pairs_with_quarantined_duplicate(self):
        over1=quote(quote_id="q1",odds_american=-108)
        over2=quote(quote_id="q1",odds_american=-130)
        under=quote(quote_id="q2",side="UNDER",odds_american=-112)
        for raw in ([over1,over2,under],[under,over2,over1]):
            out=run(raw)["rows"]
            self.assertEqual(len(out),3)
            self.assertEqual(sum("DUPLICATE_QUOTE_ID" in x["reasons"] for x in out),2)
            unique=next(x for x in out if x["quote_id"]=="q2")
            self.assertIn("NO_MATCHED_TWO_SIDED_QUOTE",unique["reasons"])

    def test_bad_odds_hash_and_threshold(self):
        for changed in (dict(odds_american=-99),dict(source_sha256="not-a-hash"),
                        dict(kind="PLAYER_PROP_XPLUS",side="YES",line="20.5"),
                        dict(kind="PLAYER_PROP_XPLUS",side="OVER",line="20")):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                run([quote(**changed)])
    def test_no_model_never_filled_from_book(self):
        reasons=run([quote()],{})["rows"][0]["reasons"]
        self.assertIn("NO_INDEPENDENT_EVENT_PROJECTION",reasons)
    def test_sgp_never_fake_joint_pricing(self):
        a=quote(kind="SGP",side="YES",line="")
        self.assertIn("SGP_NEEDS_JOINT_EVENT_PROBABILITY_AND_POSTED_PRICE",
                      run([a])["rows"][0]["reasons"])

    def test_half_total_never_compared_to_full_game_total(self):
        a=quote(kind="TOTAL",period="1H",line="20.5")
        reasons=run([a])["rows"][0]["reasons"]
        self.assertIn("NO_INDEPENDENT_PERIOD_PROJECTION",reasons)
        self.assertNotIn("UNEXPLAINED_TOTAL_MODEL_MARKET_GAP",reasons)
    def test_half_has_own_independent_projection(self):
        a=quote(kind="TOTAL",period="1H",line="20.5")
        f=model(periods={"1H":{"total":21,"margin_home":-3}})
        reasons=run([a],f)["rows"][0]["reasons"]
        self.assertNotIn("NO_INDEPENDENT_PERIOD_PROJECTION",reasons)
        self.assertNotIn("UNEXPLAINED_TOTAL_MODEL_MARKET_GAP",reasons)
    def test_team_total_needs_own_team_period_projection(self):
        a=quote(kind="TEAM_TOTAL",period="FG",team_id="LV",line="20.5")
        reasons=run([a])["rows"][0]["reasons"]
        self.assertIn("NO_INDEPENDENT_TEAM_TOTAL_PROJECTION",reasons)
        f=model(team_totals={"FG":{"LV":{"mean":25}}})
        self.assertIn("UNEXPLAINED_TEAM_TOTAL_MODEL_MARKET_GAP",
                      run([a],f)["rows"][0]["reasons"])
    def test_period_player_cannot_reuse_full_game_mean(self):
        a=quote(kind="PLAYER_PROP",period="1H",side="OVER",line="30.5",
                player_id="gsis1",stat="REC_YDS")
        reasons=run([a])["rows"][0]["reasons"]
        self.assertIn("NO_INDEPENDENT_PERIOD_PLAYER_PROJECTION",reasons)
        self.assertIn("INDEPENDENT_PLAYER_FORECAST_MISSING_OR_INVALID",reasons)

if __name__=="__main__":
    unittest.main()
