# Issue #10 current-evidence streak fixes — November 15, 2026

In the initial structural threshold auditor, Gate C used a COUNT of any three clean registered calibration cycles, allowing the newest cycle to have leakage while the gate remained structurally green. The five-day gate used the LONGEST clean calendar-day run in the entire manifest, and only considered successful cards; this hid later failures and ignored failed runs on a date when at least one other card succeeded.

**Repaired:** Gate C requires the most recent three evaluation cycles to be registered before their window, non-overlapping, and zero-leakage; it reports the historical count separately. The five-day gate requires every submitted run on each of the latest consecutive Central-time dates to be price/guard clean, and the streak must end on the most recent reported day. Any later bad run resets it to zero; no historical best streak can silently substitute.

Five deterministic negative/positive synthetic tests reproduce the false positives and ensure the stronger semantics. The new metric is STILL only a *reported* calendar streak, not external evidence of every slate having been monitored. All output continues to force `release_certified=false`, `approved_stake_u=0`, `official_counted=0`, `externally_certified=false`.

No changes to original 2026 prices, real bettor account data, frozen v5 engine, historical cards, calibration coefficients, or Issue #10's externally attested release standard.