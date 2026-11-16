"""SportsEdge multi-market RUN IT research intake → existing v2.1 risk receipt gate.

This orchestration deliberately does NOT authorize official cards: even valid
DraftKings 2-sided quotes are not proof of independently authenticated original
bookmaker responses, and another book's quote is not merely DK opposite side.
Each candidate gets the real recovered v2.1 diagnostic + optional evidence
hash-chain record before returning any PAPER-only EV research.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json

from sportsedge.odds.card_gate import gate_candidate
from sportsedge.odds.evidence import DualSourceDecision, PITBinding
from sportsedge.odds.storage import EvidenceChain
from .allmarkets_research import (
    Market, SimulationBatch, PriceReceipt, price_market, _time
)
from .edge_discovery import evaluate_signal, shortlist_signals


@dataclass(frozen=True)
class MarketCandidate:
    market: Market
    dk_quote: PriceReceipt | None
    dk_other_side: PriceReceipt | None
    v21_inputs: dict


def deterministic_decision_id(
    market: Market,
    asof_utc: datetime,
    batch: SimulationBatch,
) -> str:
    identity=json.dumps({
        "market":market.identity(),"asof":_time(asof_utc).isoformat(),
        "model":batch.model_sha256,"features":batch.feature_sha256,
    },sort_keys=True,separators=(",",":")).encode("utf-8")
    return "RESEARCH_"+sha256(identity).hexdigest()


def run_research_board(
    batch: SimulationBatch,
    candidates: tuple[MarketCandidate,...],
    decision_at_utc: datetime,
    *,
    pit: PITBinding | None = None,
    chain: EvidenceChain | None = None,
    ledger=(),
    closing_observations=(),
) -> dict:
    """Every submitted candidate runs the recovered v2.1 guard.

    A missing source or invalid quote gets a visible BLOCK, never imputed price.
    Risk module is called even for rejected candidates to prove zero bypasses.
    """
    now=_time(decision_at_utc)
    if len({x.market.identity() for x in candidates})!=len(candidates):
        raise ValueError("DUPLICATE_BET_ON_SAME_CARD")
    rows=[]
    for c in candidates:
        priced=price_market(batch,c.market,c.dk_quote,c.dk_other_side,now)
        # Preserve the underlying simulated probabilities and book comparison;
        # no EV certification or betting admission is implied by this signal.
        signal=evaluate_signal(priced,c.market,c.dk_quote,c.dk_other_side)
        if signal is not None:
            signal["scenario_spec_sha256"]=batch.scenario_spec_sha256
            signal["scenario_generator_version"]=batch.scenario_generator_version
        dual=DualSourceDecision(
            "BLOCK",("PROVIDER_PROVENANCE_NOT_INDEPENDENTLY_AUTHENTICATED",
                     "SECONDARY_INDEPENDENT_BOOK_NOT_VERIFIED"),
            c.dk_quote.receipt_id if c.dk_quote else None,
            c.dk_other_side.receipt_id if c.dk_other_side else None,
            None)
        # Do not pass trust assertions from external CSV/UI to the risk code.
        x={**c.v21_inputs}
        x["bet_id"]=deterministic_decision_id(c.market,now,batch)
        x["source_receipt_verified"]=False
        x["independent_model_verified"]=False
        guard=gate_candidate(x,dual,pit,None,now,chain=chain,
                             ledger=ledger,closing_observations=closing_observations)
        # The recovered v2.1 gate stores its own contract decision.
        # Preserve original quote SHA/IDs in the *same chain* as a distinct,
        # explicitly unverified source record (never overwrite its report).
        quote_audit_hash=None
        if chain is not None:
            quote_audit_hash=chain.append({
                "decision_id":x["bet_id"]+":QUOTE",
                "asof_utc":now.isoformat(),
                "market_key":list(c.market.identity()),
                "primary_receipt_id":c.dk_quote.receipt_id if c.dk_quote else None,
                "secondary_receipt_id":c.dk_other_side.receipt_id if c.dk_other_side else None,
                "source_payload_hashes":[q.raw_payload_sha256 for q in
                     (c.dk_quote,c.dk_other_side) if q is not None],
                "state":"BLOCK",
                "reason_codes":["QUOTE_HASHES_NOT_PROVIDER_AUTHENTICATION"],
                "pit_status":"UNVERIFIED","v21_status":guard["v21_status"],
                "approved_stake_u":0,"official_counted":0,
            })
        rows.append({
            "market":c.market.identity(),
            "research_state":priced["status"],
            "research_reasons":priced["reasons"],
            "edge_signal":signal,
            "scenario_spec_sha256":batch.scenario_spec_sha256,
            "raw_ev_unverified":priced.get("raw_ev_unverified"),
            "blended_ev_unverified":priced.get("blended_ev_unverified"),
            "guard_state":guard["status"],
            "guard_reasons":guard["reasons"],
            "v21_status":guard["v21_status"],
            "decision_id":x["bet_id"],
            "audit_hash":guard["hash_chain_head"],
            "quote_audit_hash":quote_audit_hash,
            "official_counted":0,"approved_stake_u":0,"card":None,
        })
    return {
        "status":"PAPER_0U_RESEARCH_ONLY",
        "sport":batch.sport,"event_id":batch.event_id,
        "model_sha256":batch.model_sha256,"feature_sha256":batch.feature_sha256,
        "scenario_spec_sha256":batch.scenario_spec_sha256,
        "scenario_generator_version":batch.scenario_generator_version,
        "submitted_candidates":len(candidates),
        "v21_ran_for_all_candidates":True,
        "guard_checked_count":len(rows),
        "evidence_log_requested":chain is not None,
        "research_shortlist":shortlist_signals(
            (i,c.market,rows[i]["edge_signal"]) for i,c in enumerate(candidates)),
        "research_shortlist_is_verified_edges":False,
        "rows":rows,"official_counted":0,"approved_stake_u":0,"card":None,
    }
