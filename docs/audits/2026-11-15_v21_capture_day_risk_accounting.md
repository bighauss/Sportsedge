# Daily v2.1 5-unit exposure accounting — research contract fix
**2026-11-15 · PAPER / 0u**

Binding owner rule 2 is a 5u cap **per Central Time day across all runs and sports**. The standalone risk diagnostics previously compared `risk_date_ct` to the EVENT KICKOFF day. This misdated a Sunday capture of a Monday game as a Monday staking decision, potentially excluding the Sunday exposure from the day's aggregate.

**Fix:** `risk_date_ct` must match the Central-time date of `captured_utc`, the timestamp of the hypothetical staking/quote decision. A Sunday hypothetical wager for Monday counts against Sunday's daily risk allowance. The existing T−90 gate continues to use the game's **actual kickoff**, not the wagering date. The same Central-zone DST conversion applies to quote timestamps independent of UTC midnight. Existing ledger exposure aggregation by `risk_date_ct` remains intact.

Four synthetic tests cover early next-day game captures, wrongly marked game-day risk dates, interaction with an already-used 4.90u capture-day budget, and the local-day/UTC-day boundary. No actual bets are created: all outputs have `approved_stake_u=0`. This adjustment only changes hypothetical sizing diagnostics and leaves frozen v5, capture receipts, historic grades and prices unchanged.

**Preproduction note:** `captured_utc` and `risk_date_ct` are still untrusted caller claims. Independent authenticated receipt timestamps and signed execution-day risk ledgers are required under Issue #10 before real-unit admission.