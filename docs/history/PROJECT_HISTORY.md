> **Verified status correction (2026-11-15):** PR #1 migrated a 38-file baseline. PR #2 added five synthetic model test suites. PR #3 archived history. PR #5 restored the byte-pinned frozen v5 source and research guards. This document contains historical claims that cannot be independently checked against the old inaccessible repository. No historical betting-edge validation is implied.

# SportsEdge project history and standing rulings

Compiled Nov 15 2026 from working notes and memory. The older `isaacrome21-sys/SportsEdge` repo returned 404 to available access, so old Git commits and code have NOT been verified here. This is a narrative handoff, not a restored or auditable Git history.

## Timeline
- **Early 2026:** FastAPI/Streamlit/SQLAlchemy prototype, then Google Sheets + ChatGPT system: Monte Carlo (25k iterations), v1.9 Auditable Calculation Standard, The Odds API via Apps Script, nine sport modules (MLB, NFL, CFB, NBA, CBB, Tennis, NASCAR, UFC, Golf).
- **Aug–Sept 2026:** Python/GitHub pipeline `isaacrome21-sys/SportsEdge` (public so Actions ran free). 1,213/1,213 tests clean at peak. PRs #77, #200, #203, #213, #218, #219, #223, #224, #230, #311 and the RUN IT lanes (#896, #898, #903).
- **Sept 2026:** Odds API dropped. Isaac sends lines manually (DK only), and Muse captures DK boards.
- **Oct 24–31 2026:** multi-agent work (Claude, ChatGPT, Muse, Grok) through the #2447 relay issue. One evidence ladder for every sport. The 50-pick gate was repealed on Oct 31.
- **Nov 7 2026:** GitHub suspended. SportsEdge rebuilt to run in chat. Isaac screenshots DK boards and says "run it".
- **Nov 9 2026:** shared Google Drive folder + NOTES becomes the relay. `sportsedge_v2.py` is the portable engine of record, with hourly Claude engine work.
- **Nov 11 2026:** adopted frozen **v5** portable engine (SHA-256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f`); candidate v3/v4 testing preceded adoption. "Run it" means every market with an edge, using SportsEdge's own projections.
- **Nov 14 2026:** new public GitHub account `bighauss`.
- **Nov 15 2026:** RUN IT STANDARD v1 (NE@DET Munich), v2 all-sport deep models, then the v2.1 restoration (quarter-Kelly sizing, caps). Repo migrated to `bighauss/Sportsedge`. The owner operates the repo; collaborating assistants contribute with reviewable commits.

## Old-repo architecture (what was built)
- **Promotion ladder:** VALIDATED_MATH → PRODUCTION_LOGIC_PASS → CI_ATTESTED → DEPLOYED. Market state machine: NO_ENGINE → EXPERIMENTAL → VALIDATED_MODEL → READY_FOR_POLICY → OFFICIAL → REVOKED.
- **Independent evidence:** each market has its own evidence. No market inherits another's status (a spread doesn't promote props).
- **Integrity principle:** "Visibly incomplete beats plausibly complete-but-wrong." Pipeline output beats manual analysis.
- **CFB:** market-blind joint-score Monte Carlo. Ridge regression on PPA/success/explosiveness etc. → paired historical residuals → 20k sims with a CFB-specific overtime profile. One distribution prices ML/spread/total.
- **MLB:**
  - 38 markets and a replay policy v1: 180s TTL and 30s skew; book hierarchy Pinnacle→DK→FD→MGM→Caesars; CR1 cluster-robust SEs.
  - Hybrid context autopull (StatsAPI + NWS), fail-closed.
  - NRFI/YRFI polarity verified.
- **NFL:** M2 score-distribution engine. The feature search was exhausted Sept 10 2026 (10/10 attempts did not beat closing lines). 2026 confirmation policy frozen.
- **Devig:** POWER_V1 is authoritative. Above +400, run sensitivity; a spread over 1.0pp blocks the market. No cherry-picking the favorable method.
- **RUN IT Layer A / Layer B:**
  - Layer A is the governed model path. Layer B is market context (splits, RLM, news, social).
  - Market signals can challenge, downgrade, block or trigger a recompute, but never become the model.
- **Portable engine:** `sportsedge_core` + MLB adapter (inning-by-inning NB sim) + football adapter (drive-based, key numbers). `estimate_p` naming.
- **CI rules:**
  - Every workflow-referenced script must exist.
  - Broken workflows are quarantined, never stubbed green.
  - Cron only for PIT-sensitive jobs.

## Standing owner rulings (still in force)
- **Bets:** wanted whenever there's an edge, in every sport, model and market. Recalibration runs in the background and never blocks showing picks.
- **Labels:** no validation/status labels on picks. Rate plays with 1–5 stars, show EV, rank by EV high to low. No 0–100 score on cards.
- **Card format:** NE@DET Munich layout, saved as an image to Photos. Flames on top plays, team mascots/logos, Key Inputs strip.
- **Models:** matchup-driven (unit vs unit). SportsEdge makes its own projections; Torvik, SP+, Sasser and Corbie are cross-checks only.
- **"Run it":** every market with an edge (full game, team totals, halves/quarters, alts, props), not one market.
- **Sport priority:** NFL, MLB, NBA, CFB, CBB, NHL. MLB is in its offseason.
- **Sizing (v2.1, Nov 15):** quarter-Kelly within 0.25–1.5u; 5u/day, 2u/game and 3u/theme caps. This supersedes the Nov 12 "top 8 by EV" daily cap for sizing; the top-8 list remains how picks are surfaced.
- **Pass/kill standard (Nov 10):** judged on beating the closing line, one bet per game per market, thresholds fixed in advance. It does not block daily picks.
- **MANUAL_HOLD (Nov 14):** kept separate from R2 performance. The two records are never combined.
- **Decision rights (Nov 14):** "You do it all, you make decisions, I just say run it." Claude makes the research and engineering calls.
- **Standing goal (Nov 10):** find the 10 largest back-test edges, diagnose why the win probability is so high, fix, and repeat until they're legitimate. Propose fixes and validate on unseen data (see `docs/research/rusty_bill_prompts.md`).
- **Constraints:** free tools only; DraftKings is the only sportsbook account; Isaac works from an iPhone (no computer).

## Agents
- **Claude:** owner of the repo and all lanes; decides, builds, reviews, merges.
- **ChatGPT:** builder/runner; sends changes as PRs.
- **Muse:** DK line capture.
- **Grok:** out since Oct 31.
- **Coordination:** NOTES in the shared Drive folder, plus PRs on GitHub.
