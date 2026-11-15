# Issue #10 — Offline dual-source source-to-card contracts

**State:** Engineering candidate. **Every output is PAPER / 0u.** No auto-wagering, wallet, bookmaker API, valid +EV claim, OFFICIAL card, or promotion record is implemented.

## Implemented

- `sportsedge/odds/evidence.py`: strict identity contract (sport, event, market, period, side, line, team, player, stat, settlement), raw American odds validation, UTC clock order, 90-second live / 300-second pregame age, same-underlying-book block, PIT feature freeze, strict open/take/close definition and odds-to-implied-probability movement.
- `sportsedge/odds/adapters.py`: offline parser for a **known authorized export schema**, hashing the exact original bytes and rejecting duplicate JSON keys. Not a live or authenticated source connector. Never put API tokens/sessions in receipts.
- `sportsedge/odds/storage.py`: append-only local hash chain with restricted fields, duplicate decision ID guard, deterministic hashes and verification. Tamper-evident **only when the head hash is independently anchored**; it is not cryptographically signed, WORM, or fully immutable.
- `sportsedge/odds/card_gate.py`: calls the recovered v2.1 risk diagnostic for every candidate, forcibly treats source/model verification as **unverified**, binds dual-source+PIT flags, optionally records a hash-chain log and always returns `card=None`, `approved_stake_u=0`, `official_counted=0`.
- `sportsedge/odds/test_issue10_offline.py`: synthetic normalizer, fake authentication, stale quote, event-start, mismatch, PIT lookahead, CLV, evidence-tamper and card gate tests.

Test: `python -m unittest sportsedge.odds.test_issue10_offline -v` (stdlib Python 3.12+, from repository root).

## BestBook.app policy

BestBook is an odds aggregator and research/comparison app; its public app listing does not constitute a documented, licensed developer API. The adapter is **disabled for automatic extraction** until the user supplies legitimate export/API documentation and authorization. An authorized raw export can be parsed only after its field schema and upstream original bookmaker are validated.

**BestBook displaying DraftKings is not independent of DraftKings.** A *separately authenticated FanDuel/Circa/etc.* offer compared against a DK offer can be an independent source, subject to exact event/market identities and verified mappings. Two book names in one aggregator response may still depend on a single collection path, so the code cannot independently certify provider authenticity.

Do not invent URLs, API response schemas, auth signatures, last-updated timestamps, opening odds, or prices; no cookie scraping / hidden-endpoint reverse engineering. No real sportsbook web access is performed by these scripts.

## What remains before any promotion

1. Obtain legitimate documented primary DK and independent secondary (potentially BestBook, with upstream provenance) source permissions/transport; capture raw response bytes privately with trusted external observation timestamp and signature/attestation.
2. Version and verify source-specific IDs and settlement rules (no fuzzy matching); prove both offers genuinely existed at decision time. The present `market_mapping_verified` flag is **a caller claim only** and never causes promotion.
3. Bind real player/team PIT features to approved source hashes; implement complete 5-gate run audit across all sports and markets.
4. Establish chronological calibration, genuine close triples and independently audited v2.1 end-to-end controls. Follow Issue #10's 5-day / 200-settlement / 100-card requirements, then require signed owner promotion.

No historical cards, engine formulas or v5 SHA modified. All recovered v5 modules remain unchanged.
