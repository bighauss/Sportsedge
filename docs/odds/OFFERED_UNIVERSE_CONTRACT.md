# Original offered-universe research census (Gate A, not certification)

`research.odds.offered_universe_contract.census(original_bytes, manifest, rows)` enforces that a caller supplies every claimed original offer, including excluded and suspended rows, with stable exact sport/event/market/period/participant/side/line/settlement identity and a nonempty reason for every exclusion. It verifies local byte SHA, chronology and count consistency. No dropped losers, no hidden unclassified rows, no auto-betting.

**Crucial limitations:** The original offer count is **caller-declared**; this module does not parse provider bytes to establish the actual denominator, authenticate transport, verify provider permissions, prove canonical IDs, or attest independent bookmaker origin. A malicious or incomplete manifest can still pass if its internal claims agree. Genuine Gate A requires a separately authenticated parser/inventory and private original-byte custody; independent review of that mapping is mandatory. Original bytes must never be committed to public GitHub. Synthetic fixtures are not evidence of real source completeness.

Always PAPER/0u; frozen v5 and RISK_POLICY.md untouched. Applies to NFL, CFB, CBB, NBA, MLB, NHL, PGA, without certifying any market family.
