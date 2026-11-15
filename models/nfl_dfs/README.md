# NFL DFS: DraftKings Showdown Monte Carlo (v1)

**Status:** RESEARCH / PAPER. A DFS projection is never Model_P. Contest EV is **BLOCKED** until a validated ownership feed exists (DFS-lane rule). Parameters are untested starting values until chronological DFS backtests pass.

## What it does
1. `games/<GAME>.json` holds every input that changes the game: market spread/total, pass/rush volume, target shares, catch rate, yards per catch, red-zone TD weights, carry shares, YPC, INT/fumble rates, kicking by distance, DST sacks/turnovers, weather, and the injury active-probability for each player.
2. `showdown_mc.py` approximates a **whole game at the pass/rush-attempt level**, NOT play-by-play or drive-by-drive (default 20,000 sims). There is one shared pace factor plus a scoring factor for each team, so stacks correlate naturally. A passing TD credits both the QB and the receiver. DST points allowed equal the opponent's simulated score.
3. DK scoring is exact, including bonuses and DST tiers.
4. It enumerates **filtered candidate lineups** (CPT + 5 FLEX, at most $50k, both teams) from players above a mean-point floor and with at least $46k spent, then ranks up to 4,000 per objective on shared sims. The reported optimal-lineup rates are conditional on this shortlist, **not** the true best-lineup probability over all DK-legal combinations.

## Audit limitations
The simulator makes passing TDs in a separate step from completed passes, and models defensive takeaways and scoring events approximately. The resulting distribution is research-only and may misstate tails and player correlations. Kicker missed field goals score zero under official DK Showdown rules; the earlier negative-point penalty was a bug fixed by this review. Do not use this model to claim verified DFS profitability or betting value.

## Run
```
python models/nfl_dfs/showdown_mc.py models/nfl_dfs/games/PIT_CIN_2026-11-15.json 20000
python models/nfl_dfs/test_showdown_mc.py
```

## Salaries auto-pull
`fetch_dk_salaries.py` pulls DK's public lobby and draftables JSON into `data/dk_auto/`. The endpoints are unofficial. The fetcher has not been run yet, and the scheduled workflow still needs to be added.

## Sources (PIT@CIN 2026-11-15)
- Odds: SI/BetMGM: CIN -3.5, ML -190/+160, O/U 49.5 (opened 47.5)
- Weather: Sharp Football, mysportsweather, Local12: 42F, calm, dry
- Injuries: SI and the DK CSV status column (Pittman/Iosivas/Hudson/All IR; Freiermuth and Skowronek Q)
- Roles: Rotowire last-4-weeks roles, ESPN/StatsCrew 2026, SI (Burrow 298.3 ypg, 23 TD, 74%)

## Sim result (20k)
PIT 22.0 vs CIN 26.5, total 48.4. CIN wins 57.8%, covers -3.5 at 51.7%, and goes over 49.5 at 45.0%. Paper only.
