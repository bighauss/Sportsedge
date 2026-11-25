# CBB player props: matchup distributions, backtest and runner pricing

**Status: RESEARCH. Every output is PAPER_0U, NON_COUNTED, approved_stake_u=0, official_counted=0, with no stars.**
Builds on PR #519 (branch `research/cbb-player-forward-quality-20261124`, head `b2b1e5e3`). This branch starts from that head and leaves the #519 files untouched.

## Layout
- `models/cbb/players/features.py`: point-in-time features from public sportsdataverse (SDV) ESPN player boxes. Uses the #519 two-day lag and eligibility rules. Minutes come from an EWMA blended with the 8-game mean. Per-minute rates are shrunk toward the same athlete's prior-season rate. Also covers team pace, the opponent's allowed per-possession rates, and a missed-last-team-game availability flag. DNP rows are never read as zero lines.
- `models/cbb/players/fit.py`: chronological fit at each forecast origin. Pace and opponent elasticities come from a grid search. Also fits a debias factor, the NB2 dispersion (by moments), and the points/rebounds/assists residual correlation.
- `models/cbb/players/distributions.py` (stdlib): NB/Poisson PMFs, discrete CRPS, correlated combo marginals (moment-matched NB, or a Gaussian copula with NB marginals), push-aware settlement, and uncapped EV.
- `models/cbb/players/model.py`: per-row predictive PMFs for POINTS, REBOUNDS, ASSISTS, THREES, PRA, PR, PA and RA.
- `models/cbb/players/identity.py`: the event match requires exact team names (with `cbb_run_it` aliases) and the exact UTC tip against the ESPN schedule. Player matching uses `sportsedge_cbb_model.resolve_prop_player` (the #292 logic, a read-only import), restricted to the two event teams. A labelled normalized-name pass follows, and it fails closed on ambiguity.
- `models/cbb/players/pricing.py`: the runner interface (`build_context`, `price_board`, `price_row`) plus a CLI.
- `research/cbb_players/backtest.py`: rolling-origin backtest against the #519 benchmark on identical rows.
- `research/cbb_players/PREREGISTRATION.md`: the validation/test split and the selection rule, written before any metric was viewed.

## Runner usage
```python
import sys; sys.path.insert(0, "models/cbb")
from players.pricing import build_context, price_board
ctx = build_context(schedule_parquet=..., season_box=..., prior_season_box=..., prior_schedule_parquet=...)
result = price_board(board_rows, ctx)   # rows: priced dicts or reason-coded rejections
```
CLI: `PYTHONPATH=.:models/cbb python -m players.pricing --board <csv...> --schedule mbb_schedule_2027.parquet --season-box player_box_2027.csv --prior-box player_box_2026.csv --prior-schedule mbb_schedule_2026.parquet --out-dir <dir>`

Data source: `https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_mens_college_basketball_{player_boxscores/player_box,schedules/mbb_schedule}_<season>.{csv,parquet}`. The data isn't committed; the summary JSON records its sha256.

## Nov 25, 2026 DK player rows (outputs/2026-11-25)
Inputs come from main and are not modified:
- `board_2026-11-25_0636CT_pdf_capture.csv`: 310 player rows.
- `board_2026-11-25_0900CT_operator_transcript.csv`: 150 player rows, St Bonaventure @ Belmont.

Pricing rules for these rows:
- All rows are one-sided "N+" milestones, so no de-vig is possible. Implied probabilities include vig.
- Pricing is conditional on the player participating. There's no injury feed, so availability is unverified.
- Features stop at Nov 23 (ET), the validated two-day lag. Box data was retrieved after capture and filtered by game date.
- DK event IDs are not verified here. Event identity comes from the ESPN schedule (exact names plus tip).

Limits:
- The St Bonaventure–Belmont rows stay under the owner's #57 hold. They're priced for research only.
- No historical prop odds exist, so ROI and CLV can't be computed.
