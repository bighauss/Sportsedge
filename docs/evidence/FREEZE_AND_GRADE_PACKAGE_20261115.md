# SportsEdge seven-sport prefreeze and first chronological grade register — 2026-11-15 CT

**Status: PAPER / 0u. No sport is officially frozen for betting; no A–E package has been closed.** This is a reproducible **code pin + already-recorded research-grade consolidation**. It is not a newly backdated prediction record or an authenticated market backtest.

## Truth Gate baseline

- Baseline Git HEAD before this preparation: `d9399409a86d63346b7fe0597c415fd406fd97fe`.
- Original portable v5 unchanged: SHA-256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f`.
- Source-code Git blob identities (all seven sport research paths) pinned in `research/freezes/frozen_baselines_20261115.json`. Verify locally using `python research/freezes/verify_code_freezes.py`.
- The blob digests are NOT model forecast hashes, data authentication or proof of historical point-in-time observation. The exact final integrated PR commit becomes a separate baseline once accepted; this file intentionally pins the source bytes from the inspected starting branch, rather than claiming an unverified future commit SHA.
- **No verified original DK / independent bookmaker quote file, take/close triple, or bookmaker credential/permission evidence was found attached to these freezes.** Production Odds API is forbidden by current owner instructions, and the existing free-aggregator adapter is research-only.

## Track B prefreeze truth matrix

| Sport | Code identity pinned | Required model/data pieces still missing before a real freeze | Next forward-only test |
| --- | --- | --- | --- |
| NFL | EPA ridge and chronological score-conversion Python SHA pins; v5 engine still separately pinned | Genuine pre-kickoff EPA ratings and opponent-adjusted snapshots, calibrated discrete score/key-number probabilities, lineup/QB/weather and player/TD distributions; quoted full market inventory | Freeze next untouched NFL slate with independent raw, source time and original forecasts before kickoff; grade later with official finals |
| CBB | CBB model, Torvik/CBBD bridge, final join code pinned, **not frozen** | Original Nov 9 496-priced-side `picks.csv` and source/score receipts missing; G-18 not original-byte reproduced; team crosswalk, as-of Torvik, measured HCA, actual player minutes | Register future 2026-27 season slate IDs and new pre-tip frozen board only from authentic capture, then join original CBBD finals |
| CFB | Standalone model code pinned | Historical as-of team EPA/efficiency, QB/injury/pace/weather, validation and offered-market archive | Next untouched weekend game set, all offered markets visible |
| NBA | Standalone model code pinned | Observed real minutes/lineup, usage and tail distributions, sportsbook props, external injury status | Timestamp next untouched schedule and minute/rotation assumptions |
| MLB | Standalone model code pinned | Pregame starter and lineups, bullpen order/availability, true Statcast as-of and pitch/hitter odds | Freeze next real in-season slate, not a November nonexistent MLB game |
| NHL | Standalone model code pinned **only**; NOT integrated into central pricing kernel | Code integration/settlement equivalence first; verified starter goalies, xG/TOI/prop tails | Test NHL full-game and goalie markets only after central kernel equivalence |
| PGA | Tournament simulator pinned | Authorized DataGolf connection, original tournament field, tee times, withdrawal/cut/dead-heat rules, observed market | Freeze next actually observed field once DataGolf scope is approved |

CBB and NHL are explicitly **PREFREEZE**, regardless of SHA pins, until their hard dependencies are satisfied. Other sport pins are equally not certification or calibrated full-slate models. No data or weights fabricated.

## Track C — first NFL chronological research grade package

Existing independently inspectable research **aggregate** in repository at `nfl/audit/nfl_backtest_results_2026-11-15.json`, accompanied by `nfl/audit/AUDIT_NFL_2026-11-15.md`. Those are prior recorded studies, not evidence this PR reran 98 games. The original event-level 98 source predictions and original pre-game book snapshots are not attached to this package.

| Pre-existing 2026 NFL diagnostic | Value |
| --- | ---: |
| Chronologically partitioned scored games (Oct 4–Nov 15) | 98 |
| Earlier training games / later test games | 45 / 53 |
| Train-period margin scaling slope | 0.480 |
| Test-period margin slope | 2.631 |
| Test margin MAE before/after proposed multiplier | 11.555 / 12.205 points (proposed scaling **worse**) |
| Test total MAE model / league-mean baseline | 10.663 / 10.537 points (model **worse**) |
| Point-margin model near pick'em (within 3) | 67 of 98 |
| Nov 15 modeled spread MAE vs DK spread (10-game retrospective report) | 10.99 vs 9.45 points; not a verified matched original sportsbook quote archive |
| Nov 15 model totals MAE vs market (retrospective report) | 10.31 vs 9.70 points |

The reported Nov 15 19 selected positions graded **8–11 / −3.63 units on a hypothetical flat 1u baseline**. That is neither authentic original-sized-stake ROI nor a released, timestamped official card, and may contain correlated decisions. **Do not import those 19 as 19 independently validated bets.** A research v2.2 candidate's 6-point market-gap HOLD was reported to reduce this same-day count to 9 (4–5 / −1.35 flat hypothetical units); one-day post-hoc comparison is not adoption evidence.

Additional strictly lag-row partitioned NFL player-stat study `docs/audits/2026-11-15_nfl_player_walkforward_real_research.md`: 2026 weeks 5–9, 2,258 conditional candidate stat rows, 1,819 gradeable, 439 ungraded; 1,388 paired NGS comparisons. **Those publisher files were fetched Nov 15 after the study weeks, so this is retrospective reconstruction, not an authenticated historical source freeze.** No player-prop betting probabilities or matched market/close CLV are established.

### Columns required before next genuine market grade

Each frozen event/market row must preserve:
`sport, event_id, provider_event_id, source_observed_utc, source_captured_utc, model_code_sha256, model_artifact_sha256, forecast_asof_utc, kickoff_utc, market, period, side, line, p_model, projected_score_or_stat, price_american_take, original_quote_sha256, closing_price_american, closing_quote_sha256, final_result, settlement_state, probability_error, clv, inclusion_reason, approved_stake_u=0, official_counted=0`.

Unavailable data stays **null with explicit reason**; never backfill a price, outcome, or forecast from the present-day board. Event-level scoring error is not the same as bookmaker ROI, EV or CLV. No false confidence intervals on unverified correlated positions.

## CBB November 9 forensic status and forward preregistration

- Original `board.csv` Drive revision `0Bz5GGyFPXJYyTGFSZ3dlZzlIMW8vY0pmVHNldlZxdXVMT3hvPQ` (Drive file ID `1Kqqneaz-fvCfSF2z8eOm6z7d468KRHSh`) contains 248 *two-sided board* rows, not 496 historical pick-side engine outputs.
- Original `CARD_2026-11-09_LATE_CBB_CHATGPT.md` (Drive ID `1SG4rLd9C-lb7cvxMglDje-3ebqbdriUj`) has 150 CARD + 59 DOUBTED (209) selections with original board matches. It does not resolve the full 496-side denominator.
- Historic G-18 bug: total before team-total dispatch; original grader revision predates corrected revision. Retrospective census yielded **70 changed labels** among **496 reconstructed sides**, not authenticated exact original `picks.csv` replay. Original `run7_finals.json` raw bytes and hashes also missing.
- [PR #175](https://github.com/bighauss/Sportsedge/pull/175) **merged**; it requires CBBD original raw response bytes plus manifest for any CBB finals join. This is a local integrity proof, not provider authentication.
- Future CBB forward-set start: **PREREGISTERED, 0 genuine predictions yet**, season ending **2027**. Each real next-game board must freeze before tip, preserve blocked and unpriced games, require strict team IDs, original Torvik/CBBD bytes, contemporaneous timestamps, observed source/venue HCA, roster availability, pre-tip projection artifact hash; later official full-game (incl. OT) finals join through the merged CBBD tool; evaluate only as-of prior released results. No qualification retroactively inferred from November 9.

## All-market Gate A–E acceptance (each market separately)

A: independent authenticated original DK + secondary book receipt, exact offered inventory, UTC original/capture clocks, full eligible core/prop/alternate catalogue.  
B: independent as-of team/player inputs and stable IDs, no future data.  
C: exact frozen code + weights/config + original pre-event output and chronological evaluation against same-event benchmarks.  
D: genuine matched original take/closing-line triple and calibrated, reproducible prospective holdouts.  
E: duplicate, void/push/settlement and aggregate risk audit, signed Truth Gate, independent release approval.

**No market passes any official release here**. A hash registry or synthetic completeness check must never be conflated with real data authentication or official emissions. Keep grade sidecars separate from the original forecasts, never overwrite, and begin with future events only.
