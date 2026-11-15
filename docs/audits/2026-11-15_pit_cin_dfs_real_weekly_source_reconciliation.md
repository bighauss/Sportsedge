# PIT@CIN DFS real nflverse source confrontation — Nov 15, 2026

**Status: RESEARCH ONLY / no lineup promotion.** This is a source/schema and
pre-kickoff historical-feature comparison, not a historical backtest, certified
win probability, sportsbook EV, or independently authenticated injury/roster
receipt.

## Source provenance
- Archived public nflverse GitHub release captured **2026-11-15 22:19:56 UTC**
  (before scheduled PIT@CIN kickoff 2026-11-16 01:20 UTC).
- Archived original ZIP on private Drive is
  `nflverse_forward_raw_capture_20261115_run43768677042.zip`;
  original archive SHA-256:
  `3a88b5af7e774018ab3481c77873abbe82fe551d6e732bd88abc011e737add67`.
- `NFL_WEEKLY_2026` compressed source SHA-256:
  `379dd8008d9e1d9d6c2994df2ee2fcfc04da1cf4ad47c8198a6e8798ea9ca860`,
  10,105 player-week rows overall. Source: [nflverse nflverse-data](https://github.com/nflverse/nflverse-data), attribution per provider license.
- PIT/CIN regular-season historical records through week 9: **553 player-week rows**;
  PIT most recent five game weeks 8/7/6/5/4 (171 rows),
  CIN most recent five 9/8/7/5/4 (169 rows).
- Verified published weekly stat columns include `passing_interceptions`
  but **not** `interceptions`. PR #62 repairs the mismatch in our builder.

## Independent team volume cross-check

All values below are raw prior-five-game averages or per-pass rates from the
authentic pregame-captured public weekly file, compared with the manually set
game JSON already on main. They are **not** independent next-game calibrated
predictions and cannot be substituted directly into the live card.

| Team | Metric | Archived last-five | Hand-set JSON | Difference |
|---|---|---:|---:|---:|
| PIT | Pass attempts/game | 35.000 | 33.5 | +1.500 |
| PIT | Rush attempts/game | 25.200 | 25.5 | -0.300 |
| PIT | Pass TD/game | 1.800 | 1.5 | +0.300 |
| PIT | Rush TD/game | 0.800 | 1.0 | -0.200 |
| PIT | INT/pass | 0.0229 | 0.0240 | -0.0011 |
| CIN | Pass attempts/game | 38.600 | 38.5 | +0.100 |
| CIN | Rush attempts/game | 21.800 | 24.5 | -2.700 |
| CIN | Pass TD/game | 3.400 | 2.35 | +1.050 |
| CIN | Rush TD/game | 0.800 | 0.85 | -0.050 |
| CIN | INT/pass | 0.0259 | 0.0160 | +0.0099 |

**Top observed target shares in five-game windows** (not projected 2026-W10
share): PIT DK Metcalf 24.5%, Germie Bernard 20.2%, Jaylen Warren 13.5%,
Pat Freiermuth 12.9%, Darnell Washington 12.3%.
CIN Ja'Marr Chase 25.7%, Tee Higgins 23.5%, Chase Brown 17.1%,
Dohnte Meyers 10.2%, Mike Gesicki 8.6%.

**Top observed carry shares**: PIT Jaylen Warren 64.3%, Rico Dowdle 24.6%;
CIN Chase Brown 49.5%, Samaje Perine 33.0%, Joe Burrow 13.8%.
CIN Chase Brown's observed 49.5% differs meaningfully from the hand-set
64% rushing weight; before adopting, independently validate current
starter/goal-line role and injury-related changes.

## Identity and admission check
- Uploaded full owner DK Showdown CSV used for **identity comparison only**:
  50 non-kicker/non-DST distinct FLEX entries; **30 exact** source matches
  by display name+team+position; **20 not exact**. This does *not* imply those
  20 are inactive, nor are unverified aliases accepted.
- Among the current *modeled* 25 non-K/DST names in canonical game JSON,
  **22 exact**, **3 unresolved by strict literal match**:
  `Lew Nichols` vs source `Lew Nichols III`;
  `Mitch Tinsley` vs source `Mitchell Tinsley`;
  `Marquez Valdes-Scantling` is not observed as PIT player in the
  archived 2026 weekly file (a same-name appearance on another team is
  **not** a PIT identity receipt).
- Player ID mapping remains fail-closed until all modeled role/GSIS
  joins are supported by a team/roster-source receipt. No fuzzy assignment
  or invented 0-opportunity projections.
- Source capture lacks current authoritative inactives, confirmed starting
  groups and independent contest ownership. The current hand-set market
  assumptions are not model ground truth, and no new official lineups
  have been generated from this source audit.

This report may be used to construct future as-of, source-verified event
research inputs; it is **not** a verified PIT@CIN slate release.
