"""Synthetic audit-only tests: never claim fixtures are historical correlations."""
import csv
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).parent))
from prop_joint_correlation import audit, REQ, JOINT_REQ


def write(path, cols, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        out = csv.DictWriter(handle, fieldnames=cols)
        out.writeheader()
        out.writerows(rows)


def prediction(event, leg, result="WIN", *, asof="2026-11-20T18:00:00Z",
               stat="PTS", mode="PROJECTION", team="A",
               result_source="OFFICIAL_PLAYER_BOX_SCORE"):
    return dict(event_id=event, sport="NBA", event_start_utc="2026-11-20T20:00:00Z",
                snapshot_id="s", asof_utc=asof, leg_id=leg, player_id=leg,
                team_id=team, stat=stat, side="OVER", period="FG",
                line="10.5", predicted_p="0.5", result=result,
                result_source=result_source, model_mode=mode)


class TestJointPropAudit(unittest.TestCase):
    def test_header_only_explicit_zero(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            write(d/"p.csv", list(REQ)+["model_mode"], [])
            summary=audit(d/"p.csv", None, d/"output", iterations=100)
            self.assertEqual(summary["input_rows"], 0)
            self.assertEqual(summary["pair_rows"], 0)

    def test_joint_brier_same_pairs_and_no_team_proxy(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            outcomes=[("WIN","WIN"),("WIN","LOSS"),("LOSS","WIN"),
                      ("LOSS","LOSS"),("WIN","WIN")]
            rows=[]
            for i, (a, b) in enumerate(outcomes):
                rows.extend((prediction(str(i),"A",a),
                             prediction(str(i),"B",b,stat="AST")))
            rows.append(prediction("late","A",asof="2026-11-20T20:01:00Z"))
            rows.append(prediction("proxy","A",result_source="TEAM_PROXY"))
            write(d/"p.csv", list(REQ)+["model_mode"], rows)
            frozen=[dict(event_id=str(i),snapshot_id="s",leg_id_a="A",leg_id_b="B",
                         asof_utc="2026-11-20T18:00:00Z",joint_p="0.35")
                    for i in range(5)]
            frozen.append(dict(event_id="0",snapshot_id="s",leg_id_a="A",
                               leg_id_b="MISSING",asof_utc="2026-11-20T18:00:00Z",
                               joint_p="0.2"))
            write(d/"j.csv",JOINT_REQ,frozen)
            report=audit(d/"p.csv",d/"j.csv",d/"out",iterations=120)
            self.assertEqual(report["pair_rows"],5)
            self.assertEqual(report["frozen_joint_matched_pair_rows"],5)
            self.assertEqual(report["exclusion_counts"]["NON_PREGAME_OR_AT_START"],1)
            self.assertEqual(report["exclusion_counts"]["NOT_INDEPENDENT_PLAYER_SETTLEMENT"],1)
            self.assertEqual(report["exclusion_counts"]["UNMATCHED_OR_INVALID_JOINT_PAIR"],1)
            with (d/"out"/"relationships.csv").open() as handle:
                r=list(csv.DictReader(handle))[0]
            self.assertAlmostEqual(float(r["observed_cothit_rate"]),0.4)
            self.assertAlmostEqual(float(r["expected_cothit_independence"]),0.25)
            self.assertAlmostEqual(float(r["independence_brier_joint_matched_subset"]),0.2625)
            self.assertAlmostEqual(float(r["frozen_joint_brier_matched_subset"]),0.2425)
            self.assertEqual(r["flag"],"SMALL_SAMPLE_EXPLORATORY")

    def test_malformed_csv_fails_closed(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            headers=",".join(REQ)+",Player_ID"
            (d/"bad.csv").write_text(headers+"\n"+",".join(["x"]*len(REQ))+",x\n")
            with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_BLANK_COLUMN"):
                audit(d/"bad.csv",None,d/"out",iterations=100)
            (d/"bad.csv").write_text(",".join(REQ)+"\n"+"x,short\n")
            with self.assertRaisesRegex(ValueError,"RAGGED_OR_EMPTY_ROW"):
                audit(d/"bad.csv",None,d/"out",iterations=100)

    def test_anchor_and_reused_event_id_quarantined(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            anchor=[prediction("a","A",mode="ANCHOR"),
                    prediction("a","B",stat="AST",mode="ANCHOR")]
            write(d/"p.csv",list(REQ)+["model_mode"],anchor)
            report=audit(d/"p.csv",None,d/"out",iterations=100)
            self.assertEqual(report["pair_rows"],0)
            self.assertEqual(report["exclusion_counts"]["NON_INDEPENDENT_MODEL_MODE"],2)
            original=[prediction("same","A"),prediction("same","B",stat="AST")]
            revised=[{**x,"snapshot_id":"later","event_start_utc":"2026-11-21T20:00:00Z"}
                     for x in original]
            write(d/"p.csv",list(REQ)+["model_mode"],original+revised)
            report=audit(d/"p.csv",None,d/"out2",iterations=100)
            self.assertEqual(report["pair_rows"],0)
            self.assertEqual(report["exclusion_counts"]["EVENT_ID_REUSED_FOR_DIFFERENT_GAME"],4)

    def test_duplicate_frozen_joint_all_copies_quarantined_order_independently(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            legs=[prediction("G1","A"),prediction("G1","B",stat="AST")]
            write(d/"p.csv",list(REQ)+["model_mode"],legs)
            for probs in (("0.2","0.4"),("0.3","0.3")):
                for flipped in (False, True):
                    with self.subTest(probs=probs,flipped=flipped):
                        joints=[dict(event_id="G1",snapshot_id="s",
                                    leg_id_a="A",leg_id_b="B",
                                    asof_utc="2026-11-20T18:00:00Z",
                                    joint_p=p) for p in probs]
                        if flipped:
                            joints.reverse()
                        write(d/"j.csv",JOINT_REQ,joints)
                        sub=d/("out_"+str(probs[0])+str(probs[1])+
                               ("r" if flipped else "f"))
                        result=audit(d/"p.csv",d/"j.csv",sub,iterations=100)
                        self.assertEqual(result["pair_rows"],1)
                        self.assertEqual(result["frozen_joint_matched_pair_rows"],0)
                        self.assertEqual(
                            result["exclusion_counts"]["DUPLICATE_FROZEN_JOINT_PAIR_ALL_COPIES"],2)
                        with (sub/"pair_rows.csv").open() as handle:
                            rows=list(csv.DictReader(handle))
                        self.assertEqual(rows[0]["p_joint_frozen"],"")

    def test_player_team_conflict_across_snapshots_quarantines_entire_event(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            original=[prediction("G1","A",team="TEAM1"),
                      prediction("G1","B",stat="AST",team="TEAM1")]
            changed=[dict(x,snapshot_id="later",
                          asof_utc="2026-11-20T18:30:00Z",
                          team_id=("TEAM2" if x["player_id"]=="A" else "TEAM1"))
                     for x in original]
            for flipped in (False,True):
                write(d/"p.csv",list(REQ)+["model_mode"],
                      changed+original if flipped else original+changed)
                result=audit(d/"p.csv",None,d/("reversed" if flipped else "normal"),iterations=100)
                self.assertEqual(result["pair_rows"],0)
                self.assertEqual(result["snapshot_groups_valid"],0)
                self.assertEqual(
                    result["exclusion_counts"]["PLAYER_ID_CROSS_SNAPSHOT_TEAM_CONFLICT"],4)

    def test_missing_model_mode_does_not_count_as_independent_forecast(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            legs=[prediction("G1","A",mode=""),
                  prediction("G1","B",stat="AST",mode="")]
            write(d/"p.csv",list(REQ)+["model_mode"],legs)
            result=audit(d/"p.csv",None,d/"out",iterations=100)
            self.assertEqual(result["pair_rows"],0)
            self.assertEqual(result["accepted_rows_before_snapshot_checks"],0)
            self.assertEqual(result["exclusion_counts"]["NON_INDEPENDENT_MODEL_MODE"],2)

    def test_structural_threshold_not_statistical_covariance(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            a=prediction("struct","A")
            b={**prediction("struct","A"),"leg_id":"B","line":"15.5"}
            write(d/"p.csv",list(REQ)+["model_mode"],[a,b])
            report=audit(d/"p.csv",None,d/"out",iterations=100)
            self.assertEqual(report["pair_rows"],1)
            with (d/"out"/"relationships.csv").open() as handle:
                r=list(csv.DictReader(handle))[0]
            self.assertEqual(r["flag"],"STRUCTURAL_NOT_STATISTICAL_EVIDENCE")


if __name__=="__main__":
    unittest.main()
