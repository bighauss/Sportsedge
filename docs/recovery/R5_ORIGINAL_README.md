# SportsEdge — integrated engineering candidate R5 (2026-11-13)

**Delivery status:** reproducible research workflow, **PAPER / 0u**; NOT a validated or deployed betting system. No wagers, no live feed, and no verified forward +EV.

## Finished this round
- Added a numerically strict NFL source-to-score gate (`sportsedge_nfl_projection_recompute_r1.py`), which blocks fabricated score forecasts even when the source hash matches.
- Added end-to-end results-to-ratings lineage (`sportsedge_nfl_results_lineage_r1.py`): a pinned model file (`a06b8575…`) refits the 136 completed results and exactly regenerates the 32-team ratings SHA `86dd0735…`.
- Added a **one-command NFL research workflow** (`sportsedge_run_it_nfl_r1.py`) for an independently captured DraftKings board, event manifest, and completed results. It fits ratings, projects scores, verifies every lineage step, and invokes the frozen v5 engine through a fail-closed wrapper. It never places wagers or promotes markets.
- Historical WAS @ NYG Nov 12 replay: 13 board rows, 26 priced directions, 0 anchor, exact same historical picks SHA `403d58a3…` as the earlier independent replay. Not precommitted forward evidence.
- Expanded NFL tests: 27 original + 16 recomputation + 13 historical lineage + 8 orchestration = **64 PASS**. NBA 24 PASS, CFB 48 PASS. **136 tests total**, zero failures. All synthetic tests remain synthetic; the NFL 136-game historical and NBA 638-row audits are structural/reproducibility checks.

## Run the historical example

From the extracted `nfl` directory (Python 3.11+, numpy installed):

```bash
python sportsedge_run_it_nfl_r1.py \
  --board fixtures/board_2026-11-12_1808CT_NFL_WAS.csv \
  --slate fixtures/nfl_slate_from_20261112_0901CT_DK_scan.csv \
  --history fixtures/nfl_games_2026_thru_20261109.csv \
  --captured-utc 2026-11-12T18:08:00-06:00 \
  --asof-ct 2026-11-10T00:00:00-06:00 \
  --engine sportsedge_v5.py \
  --model-code sportsedge_nfl_ratings_r1_CLAUDE.py \
  --out demo_r5
```

Output is create-only: if `demo_r5` already exists, choose a new output folder. The `RUN_RECEIPT.json` contains hashes and a research verdict; `guarded_lane/guarded_v5/picks_research.csv` contains the historical research directions. Run every time against new, independently timestamped input snapshots, not the Nov 12 historical fixture.

## Regression tests

```bash
cd nfl
python -m unittest -v test_family_passkill_r1 test_nfl_daily_lane_r1 test_nfl_daily_lane_r2 test_nfl_guarded_path_r3 test_nfl_projection_integrity_r4 test_nfl_results_lineage_r5 test_nfl_run_it_r1
cd ../nba && python -m unittest -v test_nba_append_guard_r3
cd ../cfb && python -m unittest -v test_cfb_event_completeness_r2 test_cfb_event_completeness_r3_recovered test_cfb_event_completeness_r4 test_cfb_event_completeness_r5
```

## What this does not solve

1. GitHub still returned HTTP 403 account suspended, so there is **no merge or deployment**.
2. No automated authenticated DraftKings board / close capture or independent history evidence: `--board` and `--slate` are **supplied inputs**. The R1 results file and metadata are computationally reproduced, not independently authenticated by this gate.
3. No forward precommitted, preregistered closing-price win/loss evidence; no market is promoted. NFL totals backtest improvement was negligible; source has no automatic QB/injury feed or 2024–25 priors.
4. CFB completeness validator R3 is a newly recovered version (not original-byte reproduction); CFB source admission is still withheld. NBA row integrity cannot establish model skill.
5. Market families outside this NFL points-based lane (player props, ATTD, NBA/CBB, CFB, MLB, PGA, etc.) are not magically unlocked by these engineering tests.

SportsEdge engine v5 SHA-256: `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f`; unmodified. Candidate code has no real-bet deployment privileges.
