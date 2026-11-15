# RUN IT STANDARD — addendum: NFL Next Gen Stats (Isaac: "wire it", Nov 15 2026)

## Source (free)
- PRIMARY: nflverse-data GitHub releases, tag `nextgen_stats` — files ngs_<season>_passing.csv, ngs_<season>_receiving.csv, ngs_<season>_rushing.csv (weekly + season rows). Free, public, updated weekly. Pull via GitHub (bighauss repo job or agent with GitHub access).
- FALLBACK: nextgenstats.nfl.com pages are JavaScript-rendered (plain fetch returns no data, verified 08:23 CT) — read them via a browser agent only.
- Use season-to-date + last-4-weeks, weighted 60/40.

## Props: replace market-scaling with usage projections
Player mean = team projected volume x player share x efficiency, then adjusted by opponent.
- Team volume: projected plays (pace) x pass rate -> team targets / rush attempts.
- Receivers: target share + air-yards share (NGS/nflverse) -> targets; yards = targets x catch rate x yards/rec; adjust for avg separation and opponent CB injuries.
- RBs: carry share -> attempts; yards = att x (league YPC + RYOE/att); adjust for 8+ defenders-in-box rate faced.
- QBs: attempts from team pass volume; completions = att x (exp comp% + CPOE); pass yds from aggressiveness/air yards; pressure rate faced vs opponent pressure rate generated.
- TDs: team projected TDs x red-zone/target share.
- Blend: 70% usage projection / 30% market-implied mean (until calibrated); then raw + 30/70 blended EV as standard.

## Team level (sides/totals)
- Add pressure rate allowed vs generated and time to throw as an offense adjustment (+/- up to 1 pt per team).

## Card
Prop Card adds a "Key stat" line per play (e.g. "24% target share, 2.9 sep").
