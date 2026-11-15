# RUN IT STANDARD — every sport, model, market (Isaac ruling Nov 15 2026)

Source run: NE @ DET Munich, 2026-11-15. Apply the same pipeline to every "run it".

## 1. Projection (per team)
- Base: SportsEdge team-ratings model projection (neutral site if neutral; normal home adj otherwise).
- Season stats matchup: team_pts = avg(team PPG, opponent PA/G) (sport-equivalent: runs, goals, points).
- Blend: 50% model + 50% season-stats matchup.

## 2. Adjustments (points, NFL scale — scale proportionally for other sports)
- Injuries/inactives (pull official inactives within 90 min of start):
  - Multiple starting DBs/secondary out -> opponent +1.0
  - Starting C/OL out -> own team -0.5
  - Starting CB out -> opponent +0.5
  - Star skill player out -> own team -1 to -2 (by usage)
- Travel / international / time-zone: -0.25 per team (international); cross-country short week -0.25 to that team.
- Pace: plays/game vs league avg; adjust total proportionally (+/-). Even pace = 0.
- Weather: live forecast only. Wind 15+ mph -1.5 total; heavy rain/snow -1 to -2; dome/roof = 0. Historical averages only -> no adjustment.

## 3. Pricing
- Normal model: NFL margin SD 13.5, total SD 13, team total SD 9.5, 1H = 0.5 x total / SD 9.5.
- EV raw = p * decimal - 1.
- Blended EV = (0.30 model p + 0.70 no-vig market p) -> EV. Show BOTH; rank by EV.
- Never block showing +EV; stars rate strength (blended EV >0 = 4 stars max).

## 4. Props
- Market no-vig implied mean, scaled by (adjusted team projection / market team total) with elasticity:
  yards/receptions 0.6, pass att 0.2, rush att 0.5, completions 0.3, TDs 1.0.
- Normal approx with CV per market (pass yds .28, rec yds .65, rush yds .5, receptions .45, att .15–.3).
- Show raw + blended EV (30/70).

## 5. Filters
- Drop any under whose line is BELOW projection, any over whose line is ABOVE projection.
- Correlated plays (same signal) flagged; don't stack.

## 6. Card (image saved to Photos)
Header (logos, time, venue) / Projection strip / Game Card + Prop Card ranked by EV (price, win %, EV, blended EV, stars, flames) / Key Inputs strip (season stats, pace, injuries, travel, weather). No status/validation labels.
