# CBB web-stats fallback

Used when `models/cbb/cbb_run_it.py` can't run (it needs the CBB RUN IT workflow + CBBD key).

- `run.py`: Barttorvik 2027 AdjOE/AdjDE/AdjT, league 107.3 eff / 69.3 tempo, HCA 3.0, SD margin 11 / total 16 / team total 10, 50/50 model/no-vig blend. Board = DK 2026-11-23 ~5:44 AM CT.
- `fix.py`: fits a margin scale (k) and total offset to the board, removing the early-season bias that made big dogs grade +EV. Residual disagreements are the plays.
- `card_2026-11-23.txt`: output.

Known gaps: props (no player minutes/usage), neutral-site flags (HCA applied to every listed home team), 5 games with unrated teams.
