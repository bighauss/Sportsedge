# Drive archive index (as of Nov 15 2026)

The shared Drive folder `SportsEdge` (root `12uMlp8ALLRk_pC2YalTuVJHTidSQULHn`, NOTES `1BaVdKN-AMSLavZyyJGp8p1Mx7Z_AO335`) holds well over 1,000 files. It stays the archive of record. Open any file at `https://drive.google.com/file/d/<id>/view`.

## In this repo
| Repo path | What |
|---|---|
| `docs/rules/*` | RUN IT v1/v2/addenda/v2.1 (exact Drive copies) |
| `docs/models/*`, `models/*`, `engine/*` | Sport models, tests, `sportsedge_v2.py`, ratings/props v0.2 (exact Drive copies) |
| `docs/handoffs/*` | Nov 13 team handoff |
| `archive/drive/code/` | Original CFB make_samples, NHL test and CBB test from NOTES; r5 alias probe |

## Left on Drive (code, by family; newest revision first)
| Family | Latest file (Drive id) | Notes |
|---|---|---|
| Board admission audit | `sportsedge_board_admission_r10.py` (1wmU5uBNMl80htAYajO6j-OLLoY_yGXyU), test (1-fs6ba7PM9CyiXsBPZYLJnMr_-if_gkz) | r1–r10 on Drive; paper-only legacy-board audit |
| Cross-ID preflight | `sportsedge_cross_id_preflight_r8.py` (1qs64C6lXwXsUTUUh1LNc2sQayKgwCOMR), test (1iaUI3pFayQEAhisbKZbLaxA1eeCTJIVM) | r1–r8 |
| CBB merge / receipt gates | `sportsedge_cbb_merge_gate_r3.py` (1P2LsGsvqeWxQxsej1Te0ZCMlDItuF3ah), `sportsedge_cbb_receipt_gate_r2.py` (1JMJR9gwTBjWSiFu9-fcCOypoS7y6KQYu) | + tests |
| NFL R3 repair candidate | `se_repair_layer_r3_CANDIDATE_CLAUDE_20261114.py` (1a0uUY1blRAbwiqTbJZn7dHTRZsYxDyfa) | needs frozen `se_repair_layer.py` |
| NFL TD shares | `build_nfl_td_shares_v1_1_20261114.py` (1o7hRnqLjjtu5GQ8b11LLKvpS1veV9Bmo) | paper-only nflverse TD shares |
| NFL NegBin totals audit | `nfl_negbin_totals_audit_CLAUDE_20261115.py` (1ETadOf6I3Kr9yxfTTzKPLJlCDNuB8xxe) | audit-only |
| NFL daily lane / run it | `sportsedge_nfl_daily_lane_r5.py` (1mI4sf97DFDbsSSsh7G5wLljUkILBTixU), `sportsedge_run_it_nfl_r1.py` (1PRPg_U8d2gPFxI-7RamOq4Yi0Ix_ATTJ) | + projection recompute / results lineage r1 |
| v5 guarded runner | `sportsedge_guarded_v5_runner_r3.py` (1jmcRyyf5yfOXVzBGGvesjHBZSRo8Tai5) | needs board_guard_r1 + slate_reconciler_r1 |
| Slate assembly | `sportsedge_slate_assembly_r1.py` (1Eor3A0ELuw231bfFTTz4f06jShKzlHJ5) + test | Nov 13 receipt assembler |
| NBA append guard | `sportsedge_nba_append_guard_r3.py` (1mrc9PROMxkQRfqXyJTVtzIztFjI-5aqD) + test | |
| CFB event completeness | `sportsedge_cfb_event_completeness_r5.py` (1xIBzzLVCj9A7f9cvcRa8Lo5q5XFJ8Lq-) + tests r3–r5 | |
| PGA candidate package | `pga_*_candidate_r1.py` (config, features, gate, loader, outcomes, refbt, refmarket, scorer, screen, simulate) + tests | Nov 13 |
| Totals shrink | `test_totals_shrink_CLAUDE.py` (1pxJxb2t3PMm2VZoTU5CttoR12ieSS-xn) | |
| Engine v3 | `sportsedge_v3*.py` | engine of record since Nov 11 (v2 is in `engine/`) |

## Left on Drive (data and logs)
- Hourly `runNNN_*` gate/peer sweeps and finals (run122–run136+).
- Board/close CSV captures and capture markdown.
- FT_R2 / SCENARIO pick receipts, ratings games/priors CSVs.
- Zips (FIXALL_R1, REPAIR_R2, Receipt_Integration_R2, R2_PR_Patch, NFL runners).
- `GRIND_QUEUE.md` (~515 KB) and `RELAY_LOG.md` (~183 KB).
