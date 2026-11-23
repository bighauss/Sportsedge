# CBB fallback parameter fit (2026-11-23)

Data: 82 D-I vs D-I finals from CBS scoreboards 11/18-11/21/2026, both teams rated in Barttorvik 2027 (50 campus games, 32 neutral). Neutral = venue not on either campus (Las Vegas, Nassau, St. Thomas USVI, Charleston SC MTE, White Sulphur Springs, Palm Springs, Pensacola, etc.). One game was dropped because Detroit is unrated.

**Leakage:** the Torvik ratings were captured 11/23 and already include these games, so this is in-sample. Residual SDs are a LOWER bound; out-of-sample SDs will be larger. Point-in-time ratings were not available from chat.

| Param | Assumed | Fitted (in-sample) | Used |
|---|---|---|---|
| HCA | 3.0 | 4.50 (se 1.75, n=50) | 3.0 (difference not significant) |
| Margin SD | 11.0 | 11.34 | 11.0 |
| Total SD | 16.0 | 12.78 | 16.0 (in-sample understates) |
| Team-total SD | 10.0 | 8.54 | 10.0 |
| Total bias (actual - proj) | n/a | +3.69 | flag only |
| Margin bias | n/a | -0.86 | none |

Sensitivity: re-running today's card with the fitted values gives the same 7 spread/total plays in the same order, with EV inflated 3-4 points by the tighter SDs. Card unchanged.

Finding to act on: finals ran +3.7 points over the Torvik projection. The board-fitted total offset is only +0.7, so today's UNDER plays (GaSo/NKU, Akron/Wright, UW/BYU) carry extra risk. Recommend a point-in-time walk-forward (`cbb-score-walkforward.yml`) before changing anything.

Reproduce: `python3 fit.py`
