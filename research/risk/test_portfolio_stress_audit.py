"""Synthetic only; none of these rows are a real SportsEdge wager."""
import copy
import unittest
from portfolio_stress_audit import (audit, american_payout, block_bootstrap,
                                    overlap, peak_to_trough, event_theme_groups, status_summary,
                                    stress_haircut, valid_row)
H = "a" * 64


def row(**changes):
    base = dict(bet_id="synthetic-bet-1",event_id="synthetic-event-1",sport="NFL",
                market_key="NFL:2026-11-15:event-1:FG:ML:home",market="ML",direction="home",
                model_version="v5",rules_version="R1",model_sha256=H,rules_sha256=H,
                universe_sha256=H,universe_complete_claim="TRUE",quote_sha256=H,
                rules_effective_utc="2026-11-10T00:00:00Z",model_asof_utc="2026-11-14T01:00:00Z",
                quote_observed_utc="2026-11-15T16:31:00Z",quote_captured_utc="2026-11-15T16:32:00Z",
                selected_utc="2026-11-15T17:00:00Z",kickoff_utc="2026-11-15T20:00:00Z",
                book="ExampleBook",price_american="+240",stake_units="1",stake_basis="PAPER_FLAT",evaluation_split="OOS",
                result="WIN",settled_utc="2026-11-16T01:00:00Z",settlement_source_a="source-a",
                settlement_source_b="source-b",commission_rate="0",theme_id="sim1")
    base.update(changes)
    return base


class Validation(unittest.TestCase):
    def assert_blocked(self, modified, error):
        result = audit([modified], iterations=100)
        self.assertEqual(result["accepted"], 0)
        self.assertIn(error, result["blocked"][0]["reasons"])

    def test_synthetic_pass_and_paper_status(self):
        r = audit([row()], iterations=100)
        self.assertEqual(r["accepted"], 1)
        self.assertIn("NOT_PROVIDER_AUTHENTICATED",r["status"])

    def test_quote_after_selection(self):
        self.assert_blocked(row(quote_captured_utc="2026-11-15T18:00:00Z"),"LOOKAHEAD_QUOTE_OR_SELECTION")

    def test_quote_after_kickoff(self):
        self.assert_blocked(row(quote_observed_utc="2026-11-15T20:10:00Z"),"LOOKAHEAD_QUOTE_OR_SELECTION")

    def test_rules_after_decision(self):
        self.assert_blocked(row(rules_effective_utc="2026-11-15T20:00:00Z"),"RETROACTIVE_RULE_OR_MODEL")

    def test_model_after_decision(self):
        self.assert_blocked(row(model_asof_utc="2026-11-15T19:00:00Z"),"RETROACTIVE_RULE_OR_MODEL")

    def test_stale_price(self):
        self.assert_blocked(row(quote_observed_utc="2026-11-15T12:00:00Z"),"STALE_QUOTE")

    def test_in_sample_rejected(self):
        self.assert_blocked(row(evaluation_split="TRAIN"),"NOT_OUT_OF_SAMPLE")

    def test_bad_hash(self):
        self.assert_blocked(row(quote_sha256="short"),"INVALID_QUOTE_SHA256")

    def test_missing_universe(self):
        self.assert_blocked(row(universe_complete_claim="FALSE"),"CANDIDATE_UNIVERSE_NOT_CLAIMED_COMPLETE")

    def test_pending_kept_no_profit(self):
        r = row(result="PENDING",settled_utc="",settlement_source_a="",settlement_source_b="")
        a = audit([r], iterations=100)
        self.assertEqual(a["accepted"], 1)
        self.assertIsNone(a["performance"]["roi"])
        self.assertEqual(a["performance"]["pending"], 1)

    def test_inferred_result_rejected(self):
        self.assert_blocked(row(result="LIKELY WIN"),"UNKNOWN_RESULT")

    def test_one_settlement_source(self):
        self.assert_blocked(row(settlement_source_b="source-a"),"SAME_CLAIMED_SETTLEMENT_SOURCE")

    def test_settlement_before_game(self):
        self.assert_blocked(row(settled_utc="2026-11-15T19:00:00Z"),"FINAL_BEFORE_KICKOFF")

    def test_reject_both_duplicates_order_invariant(self):
        a = row(bet_id="same",price_american="+240")
        b = row(bet_id="same",price_american="+380")
        for pair in ((a,b),(b,a)):
            out=audit(pair, iterations=100)
            self.assertEqual(out["accepted"],0)
            self.assertEqual(len(out["blocked"]),2)

    def test_reject_canonical_duplicate_different_ids_and_books(self):
        a=row(bet_id="one")
        b=row(bet_id="two",book="OtherBook")
        out=audit([a,b],iterations=100)
        self.assertEqual(out["accepted"],0)
        self.assertTrue(all("DUPLICATE_CANONICAL_SELECTION_ALL_COPIES" in x["reasons"] for x in out["blocked"]))

    def test_distinct_alt_line_not_duplicate(self):
        a=row()
        b=row(bet_id="two",market_key="NFL:2026-11-15:event-1:FG:spread:+6.5",market="spread")
        out=audit([a,b],iterations=100)
        self.assertEqual(out["accepted"],2)

    def test_paper_flat_rejects_nonflat_risk_weighting(self):
        self.assert_blocked(row(stake_units="2",stake_basis="PAPER_FLAT"),
                            "PAPER_FLAT_REQUIRES_ONE_UNIT")

    def test_invalid_unit_size(self):
        self.assert_blocked(row(stake_units="nan"),"INVALID_STAKE_UNITS")

    def test_invalid_commission(self):
        self.assert_blocked(row(commission_rate="inf"),"INVALID_COMMISSION_RATE")

    def test_central_decision_day_not_game_day(self):
        r=valid_row(row(selected_utc="2026-11-15T17:00:00Z", kickoff_utc="2026-11-16T02:00:00Z", settled_utc="2026-11-16T03:00:00Z"))
        self.assertEqual(r["selected_day_ct"],"2026-11-15")


class Metrics(unittest.TestCase):
    def test_original_prices_and_fractional_stakes(self):
        w=valid_row(row(stake_units="2",commission_rate=".05",stake_basis="EXECUTED_CLAIM"))
        l=valid_row(row(bet_id="2",result="LOSS",stake_units="3",stake_basis="EXECUTED_CLAIM"))
        p=status_summary([w,l])
        self.assertAlmostEqual(p["net_units"],2*2.4*.95-3)
        self.assertAlmostEqual(p["roi"],(2*2.4*.95-3)/5)

    def test_push_counts_risk_void_does_not(self):
        p=valid_row(row(result="PUSH",stake_units="2",stake_basis="EXECUTED_CLAIM"))
        v=valid_row(row(bet_id="2",result="VOID",stake_units="4",stake_basis="EXECUTED_CLAIM"))
        s=status_summary([p,v])
        self.assertEqual(s["risked_units"],2)
        self.assertEqual(s["roi"],0)
        self.assertEqual(s["pushes"],1)
        self.assertEqual(s["voids"],1)

    def test_american_price_invalid_even_money(self):
        with self.assertRaisesRegex(ValueError,"INVALID_AMERICAN_PRICE"):
            american_payout("-99")

    def test_void_only_games_have_no_bootstrap_evidence(self):
        rows = [valid_row(row(bet_id=str(i),event_id=str(i),result="VOID")) for i in range(30)]
        out = block_bootstrap(rows, iterations=100)
        self.assertEqual(out["blocks"],0)
        self.assertIsNone(out["roi_ci95"])

    def test_game_bootstrap_requires_distinct_games(self):
        rows=[]
        for i in range(100):
            rows.append(valid_row(row(bet_id=str(i),event_id="same-event")))
        self.assertEqual(block_bootstrap(rows, iterations=100)["events"],1)
        self.assertEqual(block_bootstrap(rows, iterations=100)["roi_ci95"],None)

    def test_connected_risk_theme_blocks_cross_game_dependence(self):
        rows = [valid_row(row(bet_id=str(i), event_id=str(i), theme_id="same-weather")) for i in range(30)]
        self.assertEqual(len(event_theme_groups(rows)),30)
        self.assertEqual(len(event_theme_groups(rows,connect_themes=True)),1)
        out = block_bootstrap(rows, iterations=100, connect_themes=True)
        self.assertEqual(out["blocks"],1)
        self.assertIsNone(out["roi_ci95"])

    def test_theme_components_separate_unrelated_games(self):
        rows = [valid_row(row(bet_id=str(i), event_id=str(i), theme_id=f"individual-{i}")) for i in range(30)]
        self.assertEqual(len(event_theme_groups(rows,connect_themes=True)),30)
        out = block_bootstrap(rows, iterations=100, connect_themes=True)
        self.assertEqual(out["blocks"],30)
        self.assertEqual(out["block_method"],"event_or_connected_theme")

    def test_game_bootstrap_30_games(self):
        rows=[]
        for i in range(30):
            rows.append(valid_row(row(bet_id=str(i),event_id=str(i),
                                      result="LOSS" if i%2 else "WIN")))
        b=block_bootstrap(rows,iterations=200,seed=42)
        self.assertEqual(b["events"],30)
        self.assertIn("roi_ci95",b)
        self.assertEqual(b,block_bootstrap(rows,iterations=200,seed=42))

    def test_no_paper_execution_blending_without_notice(self):
        a=row()
        b=row(bet_id="two",event_id="another",stake_basis="EXECUTED_CLAIM")
        result=audit([a,b],iterations=100)
        self.assertEqual(result["stake_basis_counts"],{"PAPER_FLAT":1,"EXECUTED_CLAIM":1})
        self.assertTrue(result["mixed_stake_basis"])
        self.assertIsNone(result["performance"])
        self.assertEqual(result["game_bootstrap"]["status"],"MIXED_STAKE_BASIS_CANNOT_POOL")

    def test_provider_event_ids_do_not_alias_across_sports(self):
        a = row(bet_id="nfl-one", event_id="1234", sport="NFL",
                market_key="NFL:1234:FG:ML:home", theme_id="")
        b = row(bet_id="nba-one", event_id="1234", sport="NBA",
                market_key="NBA:1234:FG:ML:home", theme_id="")
        audit_result = audit([a, b], iterations=100)
        self.assertEqual(audit_result["accepted"], 2)
        self.assertEqual(audit_result["exposure"]["distinct_events"], 2)
        self.assertEqual(set(audit_result["exposure"]["event_stake_units"]), {"NFL:1234", "NBA:1234"})
        parsed = [valid_row(a), valid_row(b)]
        self.assertEqual(len(event_theme_groups(parsed)), 2)
        self.assertEqual(len(event_theme_groups(parsed, connect_themes=True)), 2)

    def test_theme_overlap_and_day_exposure(self):
        a=valid_row(row())
        b=valid_row(row(bet_id="2",event_id="another"))
        expo=overlap([a,b])
        self.assertEqual(expo["theme_overlap"]["sim1"]["count"],2)
        self.assertAlmostEqual(expo["concentration_equivalent_events"],2)

    def test_settled_order_drawdown(self):
        a=valid_row(row(result="LOSS",settled_utc="2026-11-16T01:00:00Z"))
        b=valid_row(row(bet_id="two",result="WIN",settled_utc="2026-11-16T02:00:00Z"))
        dd=peak_to_trough([a,b])
        self.assertEqual(dd["hypothetical_max_drawdown_units"],1)
        self.assertEqual(dd["longest_consecutive_loss_rows"],1)

    def test_payout_haircut_no_magic_execution(self):
        a=valid_row(row(result="WIN"))
        self.assertAlmostEqual(stress_haircut([a],.1)["roi"],2.4*.9)
        self.assertAlmostEqual(stress_haircut([a],.0)["roi"],2.4)

    def test_version_performance_not_retro(self):
        r=audit([row(model_version="v5"),row(bet_id="two",event_id="other",model_version="v6",result="LOSS")], iterations=100)
        self.assertEqual(r["by_model_version"]["v5"]["performance"]["wins"],1)
        self.assertEqual(r["by_model_version"]["v6"]["performance"]["losses"],1)


if __name__ == "__main__":
    unittest.main()