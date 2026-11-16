# Chronological NFL market baseline evaluation

Run: cd models/nfl_dfs && python test_market_walkforward.py

Input CSV columns:
event_id,market,selection,snapshot_utc,baseline_utc,kickoff_utc,settled_utc,
model_p,baseline_p,outcome,model_sha256,baseline_sha256,baseline_books

Market key should be NFL:<market_type>; each outcome 0/1 must come from an
actual event resolution. Baseline books must be two DIFFERENT independently
observed sources (semicolon-separated), not the two sides of DraftKings alone.
Book names and hashes by themselves do not authenticate a price.

Run: python market_walkforward.py /private/pregame_forecasts.csv --output /private/walkforward.json

For each later forecast, the anchored weight 0,.25,.5,.75,1 is selected using
only the same market's historical rows settled strictly before the forecast.
Until at least 30 settled preceding rows, weight remains zero. Reports model,
baseline, anchor NLL/Brier by market; it never promotes to official, changes
historical forecasts or claims that outside README results were reproduced.
Missing genuine historical frozen rows means no credible empirical conclusion.
