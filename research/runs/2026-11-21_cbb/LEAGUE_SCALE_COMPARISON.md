# CBB league-scale comparison (2026-11-21 slate)

**Status: proposed, needs validation. Not yet adopted for official cards.**

## Source snapshot
- `torvik_2027_slate.csv`: Torvik 2027 `team_results.csv` (barttorvik.com/2027_team_results.csv), fetched 2026-11-21 about 07:45 CT. It holds adjoe, adjde and adj_t for the 102 teams on the 51-game DK slate. `dk` = DraftKings display name.
- The DK lines are screenshots captured 07:33 to 07:34 CT on 11/21 (full game, 1st half, team totals).
- The four-factor columns were not captured, so every projection used the ratings leg only.
- Venue: every game is treated as a home game except California Baptist vs Loyola Marymount, which is at Acrisure Arena in Palm Desert (neutral site, per the LMU schedule). Other Feast Week neutral sites have **not** been audited yet.

## Controlled comparison (same snapshot, same DK lines, only LEAGUE oe/tempo changed)
| Constants | n | mean(model total - DK total) | sd | games projected over DK | mean(model margin - DK spread) |
|---|---|---|---|---|---|
| old 105.0 / 67.5 | 51 | **+7.88** | 3.62 | 50 of 51 | +0.20 |
| new 107.0 / 69.0 | 51 | **+1.65** | 3.63 | 34 of 51 | +0.13 |

With the old constants, 50 of 51 totals came out over the market, which is a scale error rather than signal. The new values come from the D-I scale, not from fitting to DraftKings: the mean of (adjoe+adjde)/2 is 106.96 and the mean adj_t is 69.41 across the snapshot. That snapshot is weighted toward low-major teams, so these numbers are a proxy. The proper source is `league_from_teams()` run on the **full** Torvik file of 300+ teams; the function refuses partial files. Margins barely change, because the constants scale both teams the same way.

## Still open before adoption
1. Rerun `league_from_teams()` on a complete 360+ team snapshot, then pin and timestamp it.
2. Check calibration on graded games (old vs new), not just the gap to the market.
3. Audit neutral-site venues for every game on the slate.
4. Capture the four-factor columns so the matchup leg can run.
