# SportsEdge Moonshot Lab — NFL v0.1

An offline, mobile-friendly **DraftKings Football Moonshot research tool**. This is **not** a betting bot, an odds feed, a validated pricing engine, or an official DraftKings product. No picks are authorized; all analysis remains **PAPER / 0u**.

## What works now

- Manual play-by-play wager tracker: qualifying rushes/passes, yardage increments, first downs, offensive touchdowns, score and 10th-play bonuses, incomplete/turnover loss, pre-start void, end-of-half settlement, cashout, nullified plays.
- Target payout cap and stake/payout accounting, action undo, JSON log export.
- Historical CSV importer with duplicate-ID validation and a retrospective payoff table for chosen targets, including 95% Wilson bounds on observed hit rates.
- Pure JavaScript rule engine, **15 unit tests**, no dependencies or login, no network calls.

## Start

Open `index.html` in a desktop browser with `engine.js` alongside it. For phones, host the two files together on HTTPS (e.g. GitHub Pages). `moonshot_lab_standalone.html` is a single-file option where supported by the local file viewer.

Run tests with Node.js:

```bash
node engine.test.js
```

## Historical CSV format

```csv
round_id,game,date,final_x,end_type,source,captured_at
```

`round_id` must uniquely identify the **actual DK round**, across games and halves. `final_x` is the **maximum achieved multiplier** before the next designated failure or half-end, not the target offered or a payout on your own bet. `end_type` must be `incomplete`, `turnover`, `half_end` or `void`. Use `final_x=0` for void. `game`, `date`, `source`, and `captured_at` are strongly recommended provenance fields.

**Important:** A historical round with a 5x peak does not prove DK actually offered a 5x target in that round. The retrospective payout table therefore models a hypothetical fixed target offered on every recorded eligible round. This is *not* a forecast, bet recommendation, real-market EV, or an execution-realistic backtest. Representative sampling and pre-round offer capture are required to move beyond PAPER.

## Research-to-production gates

1. Record immutable DK game, period, pre-round target options, stake, timestamp, selection status, market label and jurisdiction.
2. Record official play-by-play event IDs, snapped field position, teams, accepted/declined penalty, yards, first down, touchdown, incompletion/turnover, scoring bonus and action count. Track cancellations and late stat corrections.
3. Validate individual action transitions, 10th/15th action bonus boundary, second-score bonus, zero-yard completions, kneels, special-teams bonus, third-party event feed semantics, red-zone restart and half-end partial settlement against actual DraftKings receipts. In v0.1 the bonus applies on the threshold event itself; confirm that timing.
4. Build an independent, time-frozen, offense/play type/clock/score/field-position model with historical walk-forward calibration and holdout tests. Never learn from the target price itself as a substitute for a predictive model.
5. Compare predicted **conditional payout distribution** to the **actually offered** target and optional cash-out quotes with realistic timing, sensitivity, and confidence intervals. Require materially robust edge after model uncertainty. Keep everything 0u until validated.
6. Never auto-place bets or auto-cash-out; manual confirmation only. Respect local law and DK terms.

## Official rules source

DraftKings support: https://support.draftkings.com/dk/en-us/football-moonshot-overview?id=kb_article_view&sysparm_article=KB0012395

Some edge-case semantics are ambiguous in the public overview. Live DK rules and settlements take precedence over this research implementation. The current implementation assumes *credited positive rushes/completions* accumulate the displayed 0.2x bonus, while all official rushes and completed passes increment the qualifying play count; unusual negative/zero-yard and penalty plays require receipt validation.