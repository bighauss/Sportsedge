# SportsEdge: independent projection for every market (PAPER-only contract)

Owner directive, 2026-11-16: **RUN IT means our own projected outcomes and distributions for every sport, player, period, and market**; the bookmaker is the comparison, never the forecast. This is a target architecture, **not a claim that all models or authenticated data are finished**.

## Required end-to-end chain

1. Freeze source-permitted **pregame statistics, rosters, injury/lineup news, venue, schedule, and weather** with content hashes and actual *source publication* timestamps. Never use the closing board, later results, or an external service's finished probability as a SportsEdge feature.
2. Produce SportsEdge's own **team and player expected outcomes** using a versioned, reproducible model. Save team scores, pace/opportunities, player minutes/usage/rates, starting lineup/goalie and measured uncertainty. Keep external projections (Torvik, vendor picks, aggregators) as **reference comparators**, not as our own model.
3. Fit **walk-forward** marginal and joint distributions from historical pregame data. Periods must have independent paths (halves/quarters, innings/periods/rounds). First event, 2+ event, 3-ball, matchups, SGP and correlated props require appropriate ordered/count/joint outcomes — no mechanical full-game percentages.
4. Produce projected win / loss / push probability for an **exact** event, market, side, line, period, player, settlement rule and frozen roster binding. Maintain the complete attempted market census with explicit `NO_MODEL`, `NO_ROSTER`, `NO_DISTRIBUTION`, `NO_AUTHENTICATED_PRICE`, etc.
5. Only **after** a model forecast exists, compare to independently authenticated original sportsbook offers (including original source/observation/receipt clocks and matching no-vig opposite). Distinguish **research disagreement** from calibrated, independently verified +EV and genuine CLV. Uncertified: **PAPER / 0u**.

## Seven-sport implementation inventory (not acceptance claims)

| Sport | Our own required event forecast | Additional paths before all markets work |
| --- | --- | --- |
| NFL | Opponent-adjusted EPA + QB, pace, drives, scores; roster-bound targets/attempts | All passing/rushing/receiving props; quarter/half paths; TD counts/order; SGP joint model |
| CFB | Opponent-adjusted offense/defense, possessions, injuries, scores | Player props, early periods, TD event/SGP joint model |
| CBB | Own possession/efficiency/matchup team + player forecasts; Torvik/CBBD as *inputs or comparator*, not sole answer | Historical empirical half paths, roster/minutes/usage props, first basket, SGP, OT settlement |
| NBA | Independent pace, efficiency, minutes, usage, team and player stats | All points/rebounds/assists/3PM/PRA/defensive props, quarter/half paths, first basket, joint SGP |
| MLB | Confirmed starters and lineups, plate appearances, pitching/batting event model | F5/1IN, NRFI/YRFI, K/outs/hits/TB/HR/RBI/etc, joint correlated markets |
| NHL | Frozen xG/chances, goalie identity, team score and player shot/event rates | Periods, saves, player shots/points/goals, first goal, SGP — currently no five-sport pricing adapter |
| PGA | Field-bound strokes gained / hole / round distributions | Outrights, finishing positions, cuts, rounds, 3-ball/matchups, leaders, birdie/bogey and DFS; no generic five-sport pricer |

Current code includes five-sport `projection_bridge.py`, `projection_distribution.py`, `allmarkets_research.py`, plus separate NHL and PGA research modules. Existing paths **do not** establish seven-sport independent model coverage, validated distributions, source authentication or official emission.

## New independent forecast *metadata* gate

`sportsedge/markets/independent_projection_gate.py` deliberately does **not** manufacture scores or probabilities. It audits each supplied projection receipt:

- `market`: sport, event_id, family, period, settlement_id, and exact player_id/team_id/stat when applicable.
- `forecast`: `origin=SPORTSEDGE_INDEPENDENT`, model/feature/distribution SHA256, frozen/generated/start UTC clocks, feature source kind/hash/published UTC, `p_win` and `p_push`; optionally projected_mean.
- Non-FG markets additionally need a period distribution fingerprint; first events ordered stream; 2+ events count distribution; correlated markets joint distribution; props must match a **separate** frozen player→team roster map.
- `audit_projection(...)` labels missing or anchor-only forecasts **BLOCK**. Any structurally valid own-model **assertion** remains `PAPER_0U_MODEL_PROJECTION_UNVERIFIED`: the metadata is not upstream authentication or calibration.
- `census(...)` retains all submitted rows, including rejected ones, and reports explicit gap counts. The module never reads betting prices, claims true edges, changes risk or writes to the frozen engine.

**Important integration gap:** the Nov 16 `operative_run_20261116_runit` artifact has not been independently fetched or audited by this PR. The gate is a standalone checked contract, **not yet connected** to that card emitter. Next PR must wire it to RUN IT without converting blocked/anchor rows into stars or independently modeled EV, and register the seven-sport per-market coverage matrix. Separate model/validation work remains under #239; original odds A–E gates under #10.

## Near-term order of work

1. Preserve Tonight's 369-side full census; tag the 43 rows by independent score/prop/period/joint model provenance, and *quarantine* the large CBB model-vs-market disagreement rows until recomputed against PIT inputs.
2. Fix roster identity on NBA/NHL prop feeds from an authorized independently timestamped roster; no guessed team names, no synthetic market lines.
3. Feed independent NFL + NBA player event rates into the same game-level simulations as sides/totals; give NHL/PGA explicit independent sport-native research adapters rather than synthetic five-sport substitutions.
4. Walk-forward fit the score, half/quarter, player, touchdown-order and joint tails, preserve all rejected wagers and compare to simple/market-only baselines.
5. Promote **each market separately** only after original quotes, calibration, PIT and issue #10 A–E evidence; no 43-paper-play card becomes official by declaration.

Software tests here use synthetic fixtures only. They cannot verify a provider's original bytes, private feature freezes, or real-world predictive calibration.
