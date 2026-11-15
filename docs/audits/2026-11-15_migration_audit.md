# SportsEdge migration audit — 2026-11-15

## Baseline and test evidence
- PR #1 merged the SHA-256 pinned 38-file full Drive archive into main (merge 6a63ac3).
- Extracted baseline passed local Python compileall. CFB test lacked samples/inputs.json, NBA test lacked G1 CSVs, MLB card was empty because sample_inputs/ had not been included. The remaining 5 MLB unit tests passed.
- Located original (previously omitted) synthetic fixtures and original NHL/CBB test scripts in Drive. Recovered them without editing core pricing code.

| Suite | Local outcome after restoring original synthetic fixtures |
| --- | --- |
| CFB | Passed; 2 simulated games, 15 synthetic selections |
| NBA | Passed; 2 simulated games, 14 synthetic selections |
| MLB | 6 of 6 tests passed; 6 synthetic selections |
| NHL | 31 of 31 checks passed; 8 synthetic selections |
| CBB | Passed; 2 simulated games, 5 synthetic selections |

These are regression tests, not evidence of model accuracy, forward betting edge, CLV, approved model states, or stake eligibility.

## Outstanding critical gates
1. **P0, engine identity.** v5 with documented SHA-256 72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f remains in Drive. Repository v2 is not the adopted v5 engine of record.
2. **P0, live-data provenance.** No authenticated capture receipts, immutable event mapping, lineup/goalie verification, no-vig independent quotes, or chronological as-of audits were migrated. A data-source adapter is not a complete verified capture pipeline.
3. **P0, actionability.** Standalone models use untested weights. v2.1 quarter-Kelly and 5u/2u/3u risk caps, 90-minute locks, 50-comparable-close CLV triggers, prop minima, and audit footers are documented but unverified as executable gates. Every run stays PAPER / 0u.
4. **P1, runner dependencies.** The guarded v5 runner requires board guard and slate reconciler modules missing from baseline. Locate originals and test exact hashes before integration. Do not stub them green.
5. **P1, evidence.** Tests do not include out-of-sample calibration, leakage controls, live book reconciliation, true joint SGP probabilities, or cluster-aware stakes. Implement independent checks on locked snapshots.
6. **P1, CI.** Python compilation and synthetic suites have been configured in GitHub Actions. Remote status must be checked from the actual PR run; local success does not imply CI passed.

## Ruleset alignment
The Nov 15 mandatory RUN IT v2.1 restoration already specifies nine core requirements. Do not weaken them or introduce an arbitrary EV floor to force test cards. Remaining work is enforcing the written requirements with versioned contract tests, timestamp/source receipts, a cross-sport exposure ledger, market identity deduplication, CLV matching, and chronological evaluations.

## Release boundary
No historical bets/cards were rewritten; no wager was placed; the verified v5 engine remains unchanged. Synthetic tests do not authorize an OFFICIAL state. Continue PAPER / 0u until market-specific promotion gates pass.
