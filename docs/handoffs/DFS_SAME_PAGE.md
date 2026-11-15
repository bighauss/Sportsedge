# DFS: one source of truth (Claude, ChatGPT, Muse)

Every agent must produce identical numbers. Rules:

1. **Engine:** `models/nfl_dfs/showdown_mc.py` only. No private copies, no other optimizer.
2. **Inputs:** `models/nfl_dfs/games/<GAME>.json` only. All lines, roles, injuries and weather live there. To change an input, edit that file in a commit. Never change inputs just in chat.
3. **Salaries:** the owner's DK CSV in `models/nfl_dfs/data/` is authoritative.
4. **Run command (fixed):** `python models/nfl_dfs/showdown_mc.py models/nfl_dfs/games/<GAME>.json 20000` with the built-in seed 7. Same inputs, same seed, same output.
5. **Results:** `models/nfl_dfs/out/<tag>_projections.csv` and `_lineups.json` from that run are the official numbers. Don't post numbers from any other run.
6. **Changes to method:** submit a PR to `showdown_mc.py` with tests. Once merged, everyone uses it.
7. **ChatGPT's loader/tests:** if they're worth keeping, push them into `models/nfl_dfs/` as a PR against this engine, and they get merged into the same pipeline. A separate parallel version is not allowed.
8. **Ownership:** no invented ownership numbers. Contest EV stays BLOCKED until real ownership data exists.

Before lock: update `p_active` in the game JSON from official inactives, re-run, and commit the outputs.
