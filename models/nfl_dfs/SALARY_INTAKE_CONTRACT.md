# DFS salary intake — subordinate to DFS_SAME_PAGE

Read [`docs/handoffs/DFS_SAME_PAGE.md`](../../docs/handoffs/DFS_SAME_PAGE.md) first.

**Only canonical engine:** `models/nfl_dfs/showdown_mc.py`, default seed **7**.

**Only approved game input:** `models/nfl_dfs/games/PIT_CIN_2026-11-15.json`.

**Only authoritative salary file:** `models/nfl_dfs/data/DKSalaries_PIT_CIN_2026-11-15.csv`, as specified by the game JSON. No generated `dk_auto` file overrides it. `AvgPointsPerGame` is never used in this loader or the SportsEdge DFS projection logic.

**Canonical run** (DO NOT create alternative projections):

```sh
python models/nfl_dfs/showdown_mc.py models/nfl_dfs/games/PIT_CIN_2026-11-15.json 20000
```

The canonical results remain `models/nfl_dfs/out/PIT_CIN_2026-11-15_projections.csv` and `..._lineups.json` from that exact command. Results, salaries, roles, methods and `p_active` can only change through a GitHub commit reviewed against the rulebook. Ownership and contest EV remain **BLOCKED** without real ownership inputs; no guessed ownership.

## This PR's limited scope

- `fetch_dk_salaries.py` is an **unofficial, untrusted, read-only API discovery** path for NFL Showdown salary data. It cannot price football, simulate games or optimize DFS rosters; it does not modify the game JSON, owner CSV or `showdown_mc.py`.
- Numeric DraftKings `rosterSlotId` is **not** presumed to mean captain or flex. It must map to an explicitly named `CPT`/`FLEX` label in the same response; ambiguous or incomplete pairs are refused. All amounts are checked for exact 3:2 captain/flex ratio and unique draftable IDs. Provider schemas/availability are unstable; a blocked response is an expected outcome, not evidence of an offered slate.
- Discovered rows go only to `models/nfl_dfs/data/dk_auto/` with **exclusive-create**, under `QUARANTINED_UNOFFICIAL_DISCOVERY_ONLY`. If they require a canonical salary change, it must be reviewed as an explicit commit to the owner CSV and the game config, not an implicit loader side effect.
- `verify_owner_game` performs a **read-only** cross-check of the existing owner CSV and the versioned game: player name, team, pos, matchup, captain/flex pair ratio, stable IDs and active probability range. The output shows separate exact file SHA256s; it **does not** authenticate that the owner CSV came from the DK website.
- Tests are synthetic/no-network and include a read-only integration against the **actual** owner game, salary file and the existing `showdown_mc.load_salaries`. A `run(cfg,...)` fork, external optimizer, use of DK Avg FP, and alternative salary set are expressly excluded.

Test with:

```sh
python -m unittest discover -s models/nfl_dfs -p 'test_fetch_dk_salaries.py' -v
```

> Current source blobs when authored (2026-11-15): `showdown_mc.py` git blob SHA-1 `af03b3b8b964b4edf933993cd9292c72ff2f092c`, game JSON `06603ad24cae5c340558725b15a20bb1e6ec3b45`, owner salary CSV `da26395713c3f919fca83a494d6b42ea173cd739`. Claude updated the canonical engine after the initial rulebook at commit `f4b7500b1dde7207d745f190580b5d720bfe7ee5` (passing TD logic); the upstream canonical engine/blob above is the latest observed when this loader patch was authored. Other agents may change main; review latest blobs and re-run the canonical command if any of these change. Our loader does not generate or substitute projections.
