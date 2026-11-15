"""Synthetic source-to-research-card v2.1 integration acceptance."""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sportsedge.markets.test_allmarkets_research import D,batch,mk,quote
from sportsedge.markets.run_it_research import (
    MarketCandidate,run_research_board,deterministic_decision_id,
)
from sportsedge.odds.storage import EvidenceChain


class TestFullGate(unittest.TestCase):
    def test_every_candidate_gets_v21_and_quote_hash_audit(self):
        game=batch()
        a=mk()
        b=mk(selection="AWAY",line="3.5")
        candidate=MarketCandidate(a,quote(a),
            quote(b,receipt="r2",quote_id="q2"),
            {"sport":"NFL","source_receipt_verified":True,
             "independent_model_verified":True})
        with TemporaryDirectory() as d:
            store=EvidenceChain(Path(d))
            out=run_research_board(game,(candidate,),D,chain=store)
            self.assertEqual(out["status"],"PAPER_0U_RESEARCH_ONLY")
            self.assertEqual(out["submitted_candidates"],1)
            self.assertIsNone(out["card"])
            self.assertEqual(out["rows"][0]["research_state"],"PAPER_0U")
            self.assertEqual(out["rows"][0]["guard_state"],"BLOCK")
            self.assertIn("PROVIDER_PROVENANCE_NOT_INDEPENDENTLY_AUTHENTICATED",
                          out["rows"][0]["guard_reasons"])
            self.assertEqual(store.verify()[0],2)
            self.assertEqual(out["rows"][0]["official_counted"],0)
            self.assertIsNotNone(out["rows"][0]["quote_audit_hash"])

    def test_unpriced_candidate_still_gets_v21_contract_check(self):
        game=batch()
        candidate=MarketCandidate(mk(),None,None,{"sport":"NFL"})
        out=run_research_board(game,(candidate,),D)
        self.assertEqual(out["rows"][0]["research_state"],"BLOCK")
        self.assertEqual(out["rows"][0]["guard_state"],"BLOCK")
        self.assertEqual(out["rows"][0]["approved_stake_u"],0)

    def test_same_selection_twice_rejected_before_card(self):
        game=batch(); m=mk()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_BET_ON_SAME_CARD"):
            run_research_board(game,(MarketCandidate(m,None,None,{}),
                                      MarketCandidate(m,None,None,{})),D)

    def test_replay_same_decision_id_fails_closed(self):
        game=batch();m=mk()
        candidate=MarketCandidate(m,None,None,{"sport":"NFL"})
        with TemporaryDirectory() as d:
            store=EvidenceChain(Path(d))
            run_research_board(game,(candidate,),D,chain=store)
            with self.assertRaisesRegex(ValueError,"DECISION_ID_REUSED"):
                run_research_board(game,(candidate,),D,chain=store)


if __name__=="__main__":
    unittest.main()
