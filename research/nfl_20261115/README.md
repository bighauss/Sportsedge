# NFL ratings half and roster evidence bridge (Nov 15, 2026)

**PAPER / 0u — synthetic tests and independent-source audit only.** This implementation does not modify frozen v5, any original pregame slate, player history, or historical odds. No wagers or live cards are generated.

The bridge accepts an existing capture CSV, a separate versioned NFL Ridge R1 team ratings file whose SHA256 is supplied explicitly, an optional exact team-map JSON, and an optional per-observation provider+roster evidence JSON. It produces a one-row-per-game ratings-only score report, a player/team-defense identity census and a JSON summary; all outputs stay PAPER/0u. If the actual historical ratings bytes are missing or fail the hash/as-of checks, all projected scores remain blank, rather than being invented. A full player name or truncated prefix is never a validated DK outcome ID. A declared GSIS or provider receipt is only an unverified candidate until independently authenticated.

For a capture CSV:

```sh
python research/nfl_20261115/nfl_ratings_roster_bridge_r1.py --capture /private/capture.csv --output-dir /private/out
python -m unittest discover -s research/nfl_20261115 -p 'test_nfl_ratings_roster_bridge_r1.py' -v
```

For actual numeric ratings scores, add `--ratings /private/nfl_ratings_asof_20261110.csv --ratings-sha256 <observed exact source SHA> --team-map /private/exact_map.json`. Do not reconstruct a stale file after games and claim original point-in-time availability. In this run, 12 synthetic tests passed; no authenticated real ratings input or player binding was promoted.

The screenshots, player quote roster audit, and unverified per-event/price census are **private Drive only**, never published in this public repository. Missing market family or provider quote remains blocked and visible in the separate all-market matrix. GitHub Issue #10 gates A–E still block official betting release.
