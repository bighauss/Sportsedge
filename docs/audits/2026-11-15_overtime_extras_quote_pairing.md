# 2026-11-15 — full-game resolution and quote pairing integrity

Research-only repair of two fail-open assumptions in the five-sport market engine.

1. **Incomplete full-game outcome**: the old scenario settlement silently treated a tied regulation score as complete when OT or MLB extra innings were absent. This could contaminate full-game moneyline, spread, team total and total diagnostics. The amended function now refuses absent or logically inconsistent overtime/extra innings; explicit regulation-only and shorter periods remain separate. NBA/CBB/CFB ties remaining after their supplied OT are held. NFL overtime can legitimately end in a tie.
2. **Asynchronous two-sided prices**: the prior pair validator let a primary and opposite quote be separately fresher than five minutes yet observed far apart. A new **conservative, non-promotable research default** enforces <=30-second observation skew; the allowed pair-skew limit must be a positive integer no larger than the existing maximum quote age.

Eleven synthetic regression tests target complete/incomplete NBA/NFL/MLB settlement, post-rule ambiguity, missing-OT propagation into pricing, stale asynchronous paired odds, and valid within-window pairs. All scenario outputs remain PAPER / 0u or BLOCK.

No frozen v5 source, real-market data, game predictions, historical betting record or risk state is changed. No sportsbook authentication, market-specific overtime distribution, chronological calibration, or official bet promotion is established. The 30-second pair window is a conservative research policy requiring independent provider verification before production adoption.
