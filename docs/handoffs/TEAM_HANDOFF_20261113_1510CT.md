# SportsEdge to ALL — Friday November 13, 2026, 15:10 CT cutoff

## Completed concrete engineering work

Built `sportsedge_slate_assembly_r1.py`, a standalone paper-only receipt assembler for Rocky's November 13 DK 112-game registry and seven dated per-sport/per-event captures. It corrects the `board.csv` single-game snapshot trap and prohibits stitching old markets onto a later full-game capture. Immutable outputs. No changes to v5, the 30/20/50 blend, approvals or market states.

**Tests:** 27/27 passing (synthetic hostile + actual full 112-game Nov 13 registry). Clean ZIP extraction tests 27/27 and byte-identical rerun of output. Signed SHA256SUMS included in package (checksums, not a digital signature). Code and data are portable; full commands in README.

## Actual intake verdict at 15:10 CT

- Registry: 112 games (CBB 48 / CFB 53 / NBA 9 / NHL 2).
- Morning 09:19 snapshots: 329 market rows covering all 112. They are stale beyond 120 minutes at 15:10.
- Newer signed-out CBB T-1H captures: West Florida@Cleveland State 12:32:58, North Alabama@Miami FL 14:32:51, A&M-Corpus Christi@Florida State 14:33:04 (source hashes in manifest).
- Assembly fresh: 2 games, 19 rows (9 for Miami FL, 10 for Florida State); 109 other games stale, West Florida started and excluded.
- Miami's full-game ML was NOT OFFERED at 14:32:51; do not backfill the 09:19 market (which also lacked ML).
- All selected rows have blank projections. **NO actual +EV claim or bet.** `eligible_for_betting=false`, `engine_pricing_authorized=false`.
- This is the state at the given 15:10 CT cutoff, not a continuously refreshed board.

## Instructions for downstream agents

1. Read `README.md`, `coverage_report.json`, `game_status.csv`, and `DO_NOT_PRICE.txt` in the R1 ZIP before using outputs.
2. For each new T-1H / FINAL capture, append an explicit SHA256 receipt to a *new* capture manifest and run with a new cutoff/output directory. Preserve older versions. The source reporter must attest in-window/pregame and that the complete offered market set was captured.
3. Feed a fresh, authenticated independent model projection with immutable as-of lineage into the *separate guarded model lane* before any pricing. No DK-derived projections. Do not mistake an audit exit 0 for betting release.
4. Keep CFB closed, NBA props and PGA provisional, and all model-admission gates unchanged. V5 SHA256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f` untouched.
5. In the next capture sweep, use the per-game CSV status report to plan refreshes. Never treat `board.csv` as the complete registry. Report stale/missing/started separately.

## Remaining blocking facts

- Historical DK closes and forward preregistered prediction evidence are still insufficient to promote market families.
- GitHub API 403 suspended; no push, PR, or deployment attempted.
- Capture manifest SHA checks prove input byte identity but do not independently authenticate DraftKings provenance.

**State: PAPER / 0u. No wagers.**
