# NFL player-stat research walk-forward — 15 November 2026

**PAPER / 0u only. No stakes, game picks or approved player probabilities.**

Run: [Real GitHub source and holdout CI](https://github.com/bighauss/Sportsedge/actions/runs/43752259520).
New code: `sportsedge/markets/nfl_player_walkforward_research.py`,
`nfl_player_replay_cli.py`; 13 hostile/synthetic tests plus real-data job.

## Sources and observed study scope

- Original SHA-verified **current** nflverse 2026 weekly player asset:
  `sha256:90befdf33b7dc9e92a840d86a73149b759b601842ff5e86257dc653d34de7cac`
- Original SHA-verified current Next Gen passing:
  `sha256:ff09429b119ebac258205bc2d513f9ebba8a8dc2cd4f778dece64a65dd3ed42f`
- Original SHA-verified current Next Gen rushing:
  `sha256:a14b15fd7aaa1f04c6262f13a96d52969f1607f9f97fb44643b048ae870494ce`
- Original SHA-verified current Next Gen receiving:
  `sha256:1895ce4275d91a20ebad62103bd42f49310dcc2d2c5156f58b37003948d7a7e7`

**Evaluation:** 2026 NFL weeks 5, 6, 7, 8 and 9; for every
observed player/team/stat, model inputs are strictly from weeks **before**
the evaluation week. Requires >=3 prior observed active-role games, with
recent team and historical usage floors. No future-week, week-zero NGS season
aggregates, bookmaker lines or market-implied player means enter features.

**Important:** all four sources are Nov 15-retrieved **retrospective**
releases. There were NO saved, independently authenticated week-5-to-9
pregame source snapshots or roster confirmations in this test, and provider
revisions cannot be excluded. The week-number partition eliminates obvious
same/future-week row leakage in computation but **does not certify genuine
point-in-time publication**. Game absences/byes may be selected based on
whether a scoring box row exists. This is a diagnostic, not a fair fully
unconditional prospective calibration.

## Coverage and missing-player honesty

| Metric | Count |
| --- | ---: |
| Conditional forecasts generated across seven correlated stat families | 2,258 |
| With matching observable actual stat | 1,819 |
| Not gradeable (no matching current-week row) | 439 |
| Available for paired NGS and baseline comparison | 1,388 |
| Number of chronological week holdouts | 5 |

Individual weekly candidate / observed / ungraded counts:
week 5 = 439 / 375 / 64; week 6 = 464 / 350 / 114;
week 7 = 468 / 379 / 89; week 8 = 438 / 350 / 88;
week 9 = 449 / 365 / 84. These **are correlated player-stat rows, not
independent completed bets or independent games**. No grade is assigned
to missing player-week outcomes; there is no invented zero result.

## Source-only forecast benchmarking (lower MAE is better)

Pre-fixed research models (none automatically adopted):

- `LAST_OBSERVED`: last graded historical game value.
- `TRAILING_3_EQUAL`: equal-weight mean of last three eligible prior games.
- `LAG3_EWMA`: earlier/medium/recent weights 0.20/0.30/0.50.
- `LAG3_PLUS_NGS_CANDIDATE`: 65% lag3 EWMA + 35% lagged NGS yards/
  opportunity (or direct count), using prior identical player/team IDs.
  This 35% is **not** a fitted optimal coefficient and should be
  rejected without prospective validation.

| Player stat | Gradeable rows | Last-game MAE | Equal 3 MAE | EWMA MAE | NGS change vs **paired EWMA** |
| --- | ---: | ---: | ---: | ---: | ---: |
| PASS_YDS | 128 | 77.94 yds | 70.72 yds | 70.29 yds | +0.062 yds (worse, n=127) |
| RUSH_YDS | 120 | 35.91 yds | 30.73 yds | 30.60 yds | −0.050 yds (better, n=114) |
| REC_YDS | 441 | 34.27 yds | 28.10 yds | 28.53 yds | −0.005 yds (better, n=302) |
| PASS_ATT | 128 | 9.70 | 8.62 | 8.52 | −0.034 (better, n=127) |
| RUSH_ATT | 120 | 5.53 | 4.68 | 4.70 | +0.027 (worse, n=114) |
| RECEPTIONS | 441 | 2.39 | 1.93 | 1.96 | +0.045 (worse, n=302) |
| TARGETS | 441 | 2.98 | 2.46 | 2.50 | +0.062 (worse, n=302) |

NGS comparison is **paired**, restricted to identical actual player-week
rows where both methods have valid prior player-ID-matched inputs.
Do not compare the unpaired EWMA MAE in column 5 directly to a paired
NGS delta as though the denominators were identical. The total paired
population across all stats is 1,388.

### Quantitative verdict

- EWMA beats **last game only** in all seven families.
- EWMA beats simple equal-three mean on **three of seven** families
  (PASS_YDS, RUSH_YDS, PASS_ATT); equal-three does better on the other four.
- Fixed 35% NGS adjustment beats the *paired* EWMA on **three** of seven
  families (RUSH_YDS, REC_YDS, PASS_ATT), but worsens the other four.
  Magnitudes are tiny compared with the model's existing MAE.
- **No automatic model adoption.** There is no reliable all-market
  probability distribution, calibrated prop over/under curve, contemporaneous
  lineup/role eligibility or authenticated past price receipt here.
- The current candidates are not yet tested against simple market-implied
  probability baselines, no-vig closing prices, production execution quality,
  truly prospective feature freeze timing or correlation-aware SGP labels.
  Never display a +EV or star rating derived from these numbers.

## Implementation and operating constraints

Run from repository root into a private directory with network access:

```bash
python -m unittest sportsedge.markets.test_nfl_player_walkforward_research -v
python -m sportsedge.markets.nfl_player_replay_cli /tmp/private-player-research
```

The scripts verify four original publisher release digests, require canonical
stable GSIS player/team identities, reject duplicates and invalid/unknown
stats, segregate NGS week-zero aggregates, compute only earlier-week
features, compare several plausible baselines on the **same outcomes**,
and keep source bytes outside public GitHub. The output is aggregate
fold-level errors, not identifiable player picks.

### Next hard requirements before actual prospective player-prop forecasting

1. Save original pregame publisher/source snapshots **before the odds and
   kickoff**, including independent receipt and lineup/inactive confirmation.
2. Maintain a timestamped player-team-season identity table and record all
   candidate forecast attempts *including byes/inactives*, pre-kickoff.
3. Preregister folds, stat-specific shrinkage, variance/fat-tail family,
   minimum observations, calibrated over/under thresholds and confidence
   intervals. Compare against trailing-three, market and closes on the
   same held-out population. Correct for correlated props per game/player.
4. Independently capture authorized DraftKings + genuinely independent book
   same-market offers; BestBook is an aggregator comparison, not a distinct
   original sportsbook unless provenance/auth allows it.
5. Only after Issue #10 Gate A–E evidence thresholds, review and explicit
   signed promotion may any real-money model be considered.

**Frozen v5 unchanged. Official counted = 0. Approved stake = 0u.**
