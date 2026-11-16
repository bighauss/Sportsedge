# Gate A — original-source independence research contract

Run `python -m unittest discover -s research/evidence -p 'test_source_lineage_gate.py' -v`.

This is **PAPER / 0u source-claims validation only**, never direct authorization to place bets or claim source authentication. The actual two original book responses, independently observed publication/capture timestamps and permissioned provider credentials must exist outside the public checkout. The function cannot authenticate any signer, document, source clock or provider; source IDs and crosswalk hashes in its arguments are user/caller assertions.

Each of two receipts carries its **own unchanged provider-native** `event_id`, `market_id`, `selection_id`, `opposite_selection_id`. Different original bookmakers normally assign **different native IDs**; their literal strings are NOT matched across books.

A separate independently evidenced cross-provider mapping must establish `canonical_sport`, `canonical_event_id`, `canonical_market_key`, `canonical_period`, `canonical_selection_id` and `canonical_opposite_selection_id`, plus exact posted `line` and kickoff. Both receipts must point to the same declared `crosswalk_source_sha256` (lowercase raw 64-hex) and `crosswalk_observed_utc` (prior to decision). These are a minimal **structural mapping contract**, not proof of crosswalk authenticity. **Do not invent an equivalence or re-label native identifiers to make them match.** No original valid crosswalk → HOLD, do not call the validator or count it as a verified price.

Each original receipt also requires `source_id`, `upstream_operator_id`, `aggregator_id`, `book_id`, `receipt_id`, `raw_sha256`, `observed_utc`, `captured_utc`, `decision_utc`, `kickoff_utc`, `price`, `opposite_price` and `status='OPEN'`. The record must be from before kickoff and no more than 300 seconds old. Structurally identical source/operator/aggregator/book/receipt aliases and identical raw payload digests are rejected. Familiar DK/DraftKings and FD/FanDuel spelling aliases are normalized only for the duplicate-source guard.

The function returns `authenticated=false`, `crosswalk_attested=false`, `approved_stake_u=0` and `PAPER_SOURCE_CLAIMS_ONLY` even with all fields present. In particular, differently named aggregators may still relay the same upstream book: independently attested transport/original source lineage and Issue #10 A–E approval remain mandatory. A local SHA-256 is byte integrity, not a publisher signature, independent clock or source certificate.

No real original odds, provider credentials, wagers, original betting history or forecast files are stored in the public repo. No v5 pricing/models/market weights are changed.
