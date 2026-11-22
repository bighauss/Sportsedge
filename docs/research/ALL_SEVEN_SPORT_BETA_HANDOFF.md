# Seven-sport, all-market beta research handoff — 2026-11-22

This is a **reproducible architecture milestone**, not a claim of actual betting readiness. Models do not become authenticated by being named in the repository. Today's open gaps include private original sportsbook offers, source publication and capture clocks, player-team identification, empirical player/period/joint distributions, prospective history, and independent closing quotes.

## What runs on main / in research

| Sport | Native model reference in code | Existing pricing status | Additional proof required |
|---|---|---|---|
| NFL | `models/nfl/score_walkforward_pit.py` and frozen v3/v5 research lanes | Five-sport research price path for supported identities only | #440 all-attempt denominator, #442 reviewed results, original odds, player-minute/opportunity, TD-order/2+ counts and joint SGP |
| CFB | `models/cfb/sportsedge_cfb_model.py` | Five-sport research path, source dependent | #405/#407 verified source intake and end-to-end execution, #433 neutral flags, player IDs, period/TD distribution |
| CBB | `models/cbb/sportsedge_cbb_model.py` | Five-sport research path; quality quarantine | #443 neutral/HCA, points/possessions baseline, injuries, period and OT rules, independent props and first-basket |
| NBA | `models/nba/sportsedge_nba_model.py` | Five-sport research path, not attested | PIT roster and minutes, individual stat distributions, quarter/half, first-basket and joint correlations |
| MLB | `models/mlb/sportsedge_mlb_model.py` | Five-sport research path, not attested | Confirmed pitchers/lineups, #446 duplicate-key fix, innings/F5 posted settlement, real pitch/hit/HR/NRFI distributions |
| NHL | `models/nhl/sportsedge_nhl_model.py` | Native NHL research only; **not five-sport-priced** | Original goalie and skater roster, xG/shot/save distributions, periods, first-goal ordering, joint markets |
| PGA | `models/pga/tournament_sim.py` | Native PGA/DataGolf research only; **not five-sport-priced** | Authenticated field/tee times, strokes and hole distributions, cuts/ties, outrights, 3-balls, matchup/round joint markets |

### All-market output contract

Every expected event and **every provider-offered exact outcome**, including each alt rung, period, selection, sportsbook and settlement rule, needs its own registered row. Source-backed missing markets must be tagged `NOT_OFFERED` only when an authenticated provider inventory proves absence; `NOT_SUBMITTED_OFFERING_UNKNOWN` is not the same thing. No submitted family is treated as zero opportunities without a quote and a model.

A separate chronological independently derived SportsEdge forecast (with model, feature and distribution SHA and pregame source evidence) is matched to the same exact outcome. A separate price receipt with the same event, posted market terms and settlement rule is matched to that forecast; p(win), p(push), p(loss) must be from the distribution, **not sportsbook-implied probability or projection–line difference**. A joint bet requires its own joint distribution and posted joint price. Reject a generic team-total fallback as a substitute for player props.

### Execution stages

1. **Full universe:** `research.audit.all_sports_market_census` validates seven sports and every listed family, preserves attempted offers and exact identity, and records every missing source, quote, close and result.
2. **Research beta candidate comparison:** `research.audit.all_sports_beta_compare` matches exact market forecast with an individual offered price and calculates EV per unit, including pushes, only when required model-distribution fingerprints are supplied. Every result is explicitly `bet_eligible=false`, `official_counted=0`, `approved_stake_u=0` and `certified_positive_ev=false`. Submitted hash strings alone are **not source authentication**.
3. **Private real pregame source capture:** Supply original provider bytes, permitted publication clocks, independent team/player data and canonical IDs, original DK/BESTBOOK quotes, and each source's receipt. Reconcile the entire original event and offer denominator.
4. **Independent calibration:** Walk-forward score, player, period, ordered count and joint distributions, paired market-only baselines on the *same* outcomes, Brier/log loss/reliability, bootstrap game-cluster uncertainty, no hidden exclusions, and genuine CLV from independent matched closes. No retrospective rule promotions.
5. **Official promotion** is a separate owner/risk-governance process requiring gates A–E per sport **and market**, before any official +EV claim or unit stake. Neither this handoff nor synthetic GitHub tests performs it.

### Safe offline reproducibility

```sh
python -m unittest research.audit.test_all_sports_market_census research.audit.test_all_sports_beta_compare -v
python -m unittest research.audit.master.test_master_audit -v
python -m research.audit.all_sports_market_census /private/normalized_market_census.json --out /private/market_census_report.json
python -m research.audit.all_sports_beta_compare /private/normalized_beta_input.json --out /private/beta_comparison_report.json
```

Only use private files in an authorized environment. The public GitHub workflow runs **synthetic tests**; never commit provider originals, credentials, screenshots or real private lines as fixtures. The report input must match schemas in the modules. No automatic API calls, stake sizing, bet placement, public wager publishing or official grading exists in this research handoff.

Tracking: [#445](https://github.com/bighauss/Sportsedge/issues/445). Agent coordination: [#57](https://github.com/bighauss/Sportsedge/issues/57).
