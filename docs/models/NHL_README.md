# SportsEdge NHL RUN IT model - README (2026-11-15, Claude)

Files: `sportsedge_nhl_model.py` (model), `test_sportsedge_nhl.py` (synthetic samples + end-to-end test), `samples/*.csv` + `samples/inputs.json`.
Python 3.8+ standard library only. No installs, no network. ALL WEIGHTS ARE UNTESTED STARTING VALUES (see the `W` dict at the top of the .py).

## Run
    python3 test_sportsedge_nhl.py                  # builds samples/, runs card, 31 checks
    python3 sportsedge_nhl_model.py samples/inputs.json
Output: `out/nhl_card.csv` (ranked by blended EV) and `out/nhl_card.md` (per-game projection strip, Key Inputs, Game Card + Prop Card, stars, FIRE on 4-5 stars, STACK flags).
Phone-only: any free Python runner (e.g. a free GitHub Actions workflow, Google Colab free tier, or the iOS app "a-Shell"/"Pyto" free tier) can run it; upload the CSVs with the same column names.

## Free data sources
1. **MoneyPuck** (team, goalie, skater season CSVs): https://moneypuck.com/data.htm
   Direct files (current season, replace 2026 with the season start year if different):
   - https://moneypuck.com/moneypuck/playerData/seasonSummary/2026/regular/teams.csv
   - https://moneypuck.com/moneypuck/playerData/seasonSummary/2026/regular/goalies.csv
   - https://moneypuck.com/moneypuck/playerData/seasonSummary/2026/regular/skaters.csv
   Data dictionary is linked on data.htm. Check that `penaltiesFor` means penalties TAKEN; if it means drawn, set `PENALTY_COLS_SWAPPED = True`.
2. **Natural Stat Trick** (cross-check / alternative 5v5 and PP/PK rates): https://www.naturalstattrick.com/teamtable.php
   Set Situation = 5v5 (score & venue adjusted: "Score and Venue Adjusted" rate option), Rate = Per 60, then "CSV (All)" at the bottom. Repeat with Situation = 5v4 and 4v5.
   To use NST instead of MoneyPuck, map its columns into the MoneyPuck `teams.csv` names listed in the .py docstring (xGF -> xGoalsFor, xGA -> xGoalsAgainst, TOI -> iceTime in seconds).
3. **NHL API** (schedule, venue, start time, back-to-backs): https://api-web.nhle.com/v1/schedule/2026-11-15 (any date), https://api-web.nhle.com/v1/club-schedule-season/BOS/now
   B2B = team played the previous day. `*_tz_shift` = time zones crossed since the last game.
4. **DailyFaceoff starting goalies** (confirmed only): https://www.dailyfaceoff.com/starting-goalies/
   Mark `*_goalie_confirmed = 1` only when status is Confirmed; games without both confirmed goalies are skipped. `*_goalie_is_backup = 1` when the confirmed starter is not the usual No. 1.
   Line combinations / injuries for `*_lineup_adj` and prop TOI: https://www.dailyfaceoff.com/teams/
5. **Odds**: type prices from any sportsbook app into `odds.csv` / `props.csv` (both sides of every market).
6. **Ratings**: `ratings.csv` = the existing SportsEdge ratings model output (off_gpg, def_gpg per team).

## Method (RUN IT STANDARD, NHL)
- Matchup goals = 5v5 xGF/60 (team) x xGA/60 (opp) / league x 5v5 minutes + PP xGF/60 x opp PK xGA/60 / league x expected PP opps (from penalty rates) x 1.85 min + 0.12 other-strength. Season stats regressed to league mean with k = 30 games.
- Team goals = 50% ratings model + 50% matchup.
- Adjustments: opposing confirmed goalie GSAx per shot regressed (k = 1500 shots) x expected shots; +0.10 GA if backup; B2B 0.20 goal-diff; travel 0.05 per time zone beyond 1 (cap 0.15); home ice 0.15 goal-diff; manual lineup adj.
- Pricing: Poisson per team, late empty-net (13% when up 1, 7% when up 2), OT/SO winner from strength share shrunk 50% toward even; OT/SO counted as 1 goal in totals/team totals; puck line uses final margin. Period 1 uses 30.5% of goals, no empty-net.
- Markets: ML 2-way, ML3 regulation 3-way, PL, TOTAL (half and whole lines with push), TT_HOME, TT_AWAY, P1_ML3, P1_ML2, P1_TOTAL.
- Props: SOG = TOI x iCF/60 x (SOG/CF) x opp shot-attempt suppression; POINTS = TOI x on-ice xGF/60 x IPP x opp xGA factor; SAVES = opp projected SOG x regressed save% (k = 1500). Each mean is 70% model / 30% market-implied (Poisson mean solved from no-vig over price).
- EV: raw = p x decimal - 1 (pushes refunded); blended uses p_blend = 0.30 model + 0.70 no-vig market. Card keeps blended EV > 0, ranks by blended EV, stars 5/4/3/2/1 at 8%/5%/3%/1.5%/>0.
- Filter: unders with line below projection and overs with line above projection are dropped. Stacks: plays in one game sharing a signal (home_side, away_side, high_scoring, low_scoring) are flagged.

## Limitations (honest)
- Nothing is backtested or calibrated; every weight is a starting guess.
- Independent Poisson ignores score effects and goal correlation; real NHL draws run slightly higher than Poisson gives.
- Saves and SOG use Poisson, which understates variance (overdispersion) - prop EVs are likely overstated.
- Points prop treats on-ice xGF as goals and ignores PP-unit role; IPP regression is a simple k = 20 games.
- Goalie GSAx uses season-only data; no multi-season prior, no fatigue/workload.
- MoneyPuck column meanings (especially penalties) must be confirmed against the live data dictionary.
- The sample odds are made up and deliberately loose, so the sample card shows unrealistically large EVs.
