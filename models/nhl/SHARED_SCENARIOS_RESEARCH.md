# NHL shared shot-goal-goalie-save simulation — research only

This isolated candidate consumes existing sportsedge_nhl_model.py projected home and away shots and goals. It does not modify the incumbent NHL ratings model, game card, betting EV or any DFS lineup. No provider fantasy-point averages, paid data, book prices or fabricated player usage are used.

Each modeled regulation period simulates team shots and assigns every shot either a goal or the opposing goalie save, always conserving SOG = goals + goalie saves. Team period score, goalie save counts and first-period and regulation winner distributions come from the SAME simulated games. Random seed and all parameters are deterministic.

Requirements: confirmed starting goalies for both teams, source SHA-256, model SHA-256, UTC feature freeze preceding kickoff, explicitly supplied period shares (sum=1) and pace dispersion. Coefficients are unvalidated until backtested on genuine source-frozen historical games. No default tuned proportions or model EV.

BLOCKED intentionally: full-game moneyline, totals and team totals (no OT/shootout events); full-game goalie saves (no OT shots), skater SOG/points/assists, DraftKings DFS (no player shot allocation), and SGP (no verified prices/joint event calibration).

Tests: run python -m unittest test_nhl_shared_scenarios.py from models/nhl. Existing NHL synthetic tests remain in CI. Passing software tests is NOT evidence of +EV or profitability.

Next: real source-pinned starting goalie receipts; independent chronological fitting of period shot shares, shooting and goalie statistics; team-shared simulation of OT, then player shot events linked to precise roster IDs before connecting props and DFS. PAPER/0u. No wagers.
