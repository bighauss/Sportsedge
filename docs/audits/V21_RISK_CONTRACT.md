# RUN IT v2.1 standalone sizing and risk contract

**Nov 15 policy override:** root `RISK_POLICY.md` chooses the stricter verified 1u aggregate game cap. The underlying v2.1 spec remains a historical 2u game cap; this diagnostic implementation is deliberately tighter. All stakes are 0u.

This module is **research-only**; `approved_stake_u` is always **0**, with only a `diagnostic_u` sizing calculation. It does not authenticate DK quotes, establish model skill or change the adopted v5 engine. No wagers or previously archived cards are modified.

`v21_risk_contract.py` implements v2.1 quarter-Kelly on 30% model / 70% independently verified no-vig market probability, the initial 0.25u–1.5u band, LOW-confidence and negative 50-comparable-close half-size modifiers, push-aware win/loss/push Kelly, and the 5u/day (Central Time), 1u/game conservative Nov 15 owner lock, 3u/theme ledger caps. It rejects missing bankroll/unit denomination, quote or model evidence, stale/after-start lines, T−90 locks, unrepriced news, unconfirmed lineups/goalies, crossed projections and underspecified props.

**This is a candidate component rather than a wired production policy gate.** Boolean source-verification flags are claims provided by the caller, **not independent proof**. The CLV observations must be independently authenticated, chronological and comparable within each sport. The code's theme cap is conservative across all supplied ledger records, including prior days; a fully specified production risk period needs separate signoff. The strict field contract does not resolve every sport-specific numeric projection override or produce final public graphics. Those remain open v2.1 implementation requirements.

Test locally: `python research/risk/test_v21_risk_contract.py` (24 synthetic cases).

Every real source/capture, quote availability, forward calibration and per-market evidence gate remains PAPER / 0u until separately satisfied. Never infer a cash wager from a nonzero `diagnostic_u`.
