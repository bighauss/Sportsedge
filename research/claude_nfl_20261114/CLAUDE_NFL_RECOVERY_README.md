# Recovered Claude NFL full-slate model pathways — November 15, 2026

**Research only. All results PAPER / 0u.** No automatic orders, actual verified wagers, graded prospective ROI or frozen v5 formula edits.

## Verified source / file integrity

The source files below are recovered exactly from `NFL_full_slate_runner_R1_1_20261114.zip` and the companion Drive script. Historical archive ZIP SHA256 `ba1513e69894f74f41c091daac26bbff1764904182a704317baceb699ef2a1ce`.

| Public source script | Exact source SHA256 | Status |
| --- | --- | --- |
| `nfl_full_slate.py` | `282f9660636ce5d807e924b345b4ac8756007b8511af37b0231cba5bba54ad49` | Model research runner, not production |
| `se_repair_layer.py` | `300c0938b1c17abfdae62d90dc5f4aa3d71c1c365310bb3809077746eb94d2e0` | **Historical** R2 logit pool, not binding Nov15 v2.1 linear pool |
| `build_nfl_td_shares_v1_1_20261114.py` | `c0816ce737e6b53e8cf8e882ce4e3d6295a9e0b482d19ada95eb60f37b3f0cc5` | Historical offensive TD shares, **not** ATTD probability |
| `reconcile_r2_v21.py` | New, read-only comparison tool | Does not change model |

Frozen v5 engine resides at `engine/sportsedge_v5.py`, SHA-256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f`. No duplicate engine is installed in this directory.

## Projections actually saved

Claude's `FT_R2_picks_2026-11-15_NFL_2229CT_injadj.csv` (private Drive file; SHA256 `700e133f63bd61715a57873e48e452b5c906828d1de87a53593937532bf80be1`) contains **152 selection-direction rows across 13 game identities**. Only six families have actual output: FG spread, FG total, FG moneyline, first-half spread, first-half total, first-half moneyline. It has **no independently priced player props, team totals, ATTD, first TD, 2+ TD, quarter markets or SGP**. The source runner supports some of those families *in code* but requires unverified current ratings/player curves/TD shares/quotes.

The public, sanitized `claude_20261115_model_probability_only_PUBLIC.csv` contains the 152 prior research probabilities **without private market prices, screenshot captures, individual customer data, results or purported bookmaker timestamps**. These are ***not*** freshly generated November 15 predictions or verified first-seen pregame forecasts. Original source and full quote evidence stay in private Drive.

### Independent replay and updated mandatory rule comparison

The R2 historical `se_repair_layer.py` was rerun from input projection columns; all 152 rows reproduced `pooled_p`, `pooled_ev`, `gap_pts`, flags and `r2_keep` **exactly**, with **11 historical R2 keep-flags**. One genuine logic mismatch was identified: **R2 uses logarithmic pooling**, while binding Nov15 owner RUN IT v2.1 specifies **linear probability mixing (0.30 model + 0.70 no-vig market)**. We did not rewrite a frozen historical card. The read-only comparison recomputes the binding formula on all 152 rows, finding **25 positive raw blended-EV diagnostics** (without relaxing any risk gate). The 11 former R2 kept rows remain positive under this diagnostic but are **not verified wagers**. Five legacy keeps were later separately flagged HOLD for unmodeled starter/injury and line movement; the other six are also only PAPER.

### November 15 screenshots and BestBook reconciliation

The user's 11:23–11:26 CT DK screenshot set contains 1,051 cells: 144 FG/1H game lines across 12 future games, 690 touchdown-market prices, and 217 player prop prices. All 907 prop/touchdown labels lacked independently verified player-ID bindings (including 308 visibly truncated). Historic 13th game NE@DET was already live and cannot be recaptured pregame. Direct market family census is stored privately with the screenshots.

BestBook public NFL top-level page retrieved Nov15 listed best prices **across books/exchanges**, not a single canonical sharp-book market or authenticated DraftKings operator quote. Across the 72 full-game DK prices, **52 exact same-line comparisons** were possible and **20 were different lines**. Better prices at another book are **not proof of model edge**, nor permitted DK prices; no coefficient was refit to the current page. Market movement is material, including LAR@ARI O/U dropping from prior 47.5 to 38.5 and MIA@IND from 42.5 to 37.5 (secondary source BetSharp). No authentic provider quote timestamps were supplied by BestBook.

## Unclosed requirements

- Actual pregame bookmaker-bound original two-sided quotes with immutable timestamps, source IDs, prices, player identities, and event starts; public screenshot ≠ authenticated executable offer.
- Frozen roster/availability/injury/QB/goalie/weather as-of inputs, prestart player curves, prospectively confirmed lineup and full independent per-market calibration/CLV.
- Runner's own `--adj` accepts author estimated Seattle −3.5 and Rams −1.5; those are **sensitivity scenarios**, not validated quarterback/receiver correction coefficients. Miami first-start QB wasn't captured in that adjustment file.
- Genuine provider-backed TD-share data (all 32 teams, through week 9) and a calibrated touchdown count model; historical share alone cannot price ATTD/FTD/2+.
- Full v2.1 nine-item policy interface and risk ledger. Per-market action remains 0u. Do not make a selection official to fill daily cards.

## Regression

`python research/claude_nfl_20261114/test_recovery.py` (7 synthetic tests, no internet). The private 152-row replay and BestBook comparison exist in the associated Drive audit ZIP, not in this public GitHub repository.
