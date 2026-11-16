import unittest
from models.nfl.qb_efficiency_pit_contract import validate

def row():
    return dict(event_id="nfl-1",qb_id="qb-1",team_id="A",opponent_id="B",
                season=2026,dropbacks=160,epa_per_dropback=0.12,
                source_sha256="a"*64,source_available_utc="2026-11-15T20:00:00Z",
                feature_freeze_utc="2026-11-16T17:00:00Z",
                event_start_utc="2026-11-16T18:00:00Z",source_name="authorized-pbp")

class TestQBIntake(unittest.TestCase):
    def test_research_only(self):
        result=validate([row()])
        self.assertEqual((result["status"],result["approved_stake_u"]),("PAPER_0U_QB_RESEARCH",0))
    def test_100_vs_150_threshold(self):
        r=row();r["dropbacks"]=120
        self.assertFalse(validate([r])["rows"][0]["eligible_for_threshold_analysis"])
        self.assertTrue(validate([r],minimum_dropbacks=100)["rows"][0]["eligible_for_threshold_analysis"])
    def test_reject_future_source(self):
        r=row();r["source_available_utc"]="2026-11-16T17:01:00Z"
        with self.assertRaisesRegex(ValueError,"LOOKAHEAD"):validate([r])
    def test_reject_nan(self):
        r=row();r["epa_per_dropback"]=float("nan")
        with self.assertRaisesRegex(ValueError,"EPA_INVALID"):validate([r])
    def test_reject_unlicensed_pff(self):
        r=row();r["pff_offensive_grade"]=89.1
        with self.assertRaisesRegex(ValueError,"PFF_AUTHORIZATION_REQUIRED"):validate([r])
    def test_pff_requires_source_hash(self):
        r=row();r.update(pff_offensive_grade=89.1,pff_use_authorized=True,
                         pff_available_utc="2026-11-15T20:00:00Z")
        with self.assertRaisesRegex(ValueError,"PFF_SOURCE_HASH_REQUIRED"):validate([r])
    def test_pff_future(self):
        r=row();r.update(pff_offensive_grade=89.1,pff_use_authorized=True,
                         pff_source_sha256="b"*64,pff_available_utc="2026-11-16T17:01:00Z")
        with self.assertRaisesRegex(ValueError,"PFF_LOOKAHEAD"):validate([r])
    def test_duplicate_qb_event(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_QB_EVENT"):validate([row(),row()])

if __name__=="__main__":unittest.main()
