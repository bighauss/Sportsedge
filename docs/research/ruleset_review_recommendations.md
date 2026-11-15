What’s strong already
Your ruleset is unusually complete for a multi-sport system: clear data discipline (no invented numbers, skip if missing), explicit projection blend + regression schedule, dual EV (raw + market-blended), correlation flagging, sport-specific adjustments that actually matter (EPA/success, on/off, goalie confirmation, Statcast pitch-type, weather thresholds, altitude/B2B/rest), SD filters, and a grading loop with CLV. The card layout is practical.
Highest-value additions / fixes
	1	Unit sizing & risk controls (biggest gap) Flat 1u is simple but leaves edge on the table and creates uneven exposure. Add:
	◦	Fractional Kelly (or half-Kelly) using blended EV and a conservative variance estimate, capped (e.g. 0.5–1.5u max).
	◦	Hard daily / weekly exposure limits and max correlated exposure (same game or same side of a total).
	◦	Explicit “no chase” and stop rules after a losing streak or when CLV turns consistently negative.
	2	Minimum edge + confidence gates Showing every +EV is fine for analysis, but for actionable cards add:
	◦	Soft floor (e.g. raw EV ≥ 2–3% or blended ≥ 1.5%) that can be tuned per sport/market after grading data accumulates.
	◦	Confidence band around the projection (or at least a simple “high / medium / low” based on sample size, injury uncertainty, and weather volatility). Drop or demote low-confidence +EV plays.
	3	Correlation & portfolio construction You already flag same-outcome stacking. Extend it:
	◦	Same-game correlation matrix (or simple rules: ML + team total, spread + total, player prop + team total).
	◦	Cross-game limits when multiple plays ride the same weather, travel, or public-fade theme.
	◦	Explicit rule for same-game parlays only when the joint EV still clears the floor after correlation adjustment.
	4	Data & timing discipline
	◦	Cutoff times: latest acceptable injury/lineup/goalie confirmation and weather update before a card is locked.
	◦	Primary free sources list (and fallbacks) so the process is reproducible: e.g. CFBD + SP+/FPI cross-check, MoneyPuck + Natural Stat Trick, Statcast + FanGraphs, BartTorvik, Next Gen Stats / PFR, official injury reports + confirmed lineups.
	◦	Explicit “stale price” rule: if the DK number moves materially after the card is built, re-price or kill the play.
	5	Closing-line and market-efficiency tracking You already grade CLV. Make it first-class:
	◦	Track CLV by sport, market, and book (DK vs Pinnacle/Circa when available).
	◦	Flag systematic over/under-performance vs the close; use it to retune the 30/70 blend weight and the regression schedules.
	◦	Optional: simple public-betting % or ticket% vs money% when free sources exist (helps identify soft spots).
	6	Model hygiene & retuning process “Retune after 100+ graded plays” is good. Add structure:
	◦	Separate calibration (probability → actual win rate) from edge estimation.
	◦	Keep a hold-out or rolling out-of-sample window so retunes don’t overfit the recent sample.
	◦	Log every weight change with the evidence that justified it.
	◦	Periodic full back-test of the current rule set on prior seasons (or at least prior 1–2 years) before promoting changes.
	7	Sport-specific gaps worth filling
	◦	NFL/CFB: Explicit days-rest differential and short-week effects beyond the current international/cross-country notes. Pressure rate and OL health already good; add a simple “pass-rush win rate vs protection” interaction for totals and sacks props.
	◦	NBA: Minutes redistribution rules are there; add a hard cap on usage spikes for players stepping into larger roles (regression is usually strong).
	◦	CBB: 3P% regression is correctly aggressive; consider a conference-strength or non-conference schedule adjustment early in the season.
	◦	NHL: Confirmed goalies only is correct. Add a small “goalie confirmation late” penalty or wider uncertainty band when the starter is not locked until morning of.
	◦	MLB: Strong Statcast foundation. Explicitly handle bullpen chains and leverage situations for team totals and late-inning props; umpire tendencies are already noted—keep them secondary to the pitcher/batter matchup.
	8	Props-specific refinements
	◦	Volume floors (minimum projected attempts/targets/shots/minutes) so you don’t bet tiny-sample noise.
	◦	Opponent-adjusted efficiency that is not just team D but positional or scheme matchups when the data exists.
	◦	Clear separation between “core” props (high volume, liquid) and speculative ones; different EV floors or star thresholds.
	9	Operational / output rules
	◦	Version the rule set (date + short hash) on every card so graded results can be mapped back to the exact logic used.
	◦	Explicit “kill criteria” after the card is published (major injury news, weather shift, line move past the projection, etc.).
	◦	Simple audit trail: which free sources were used, what was missing, and why any game was skipped.
Lower priority but still useful
	•	Referee/umpire impact scores where reliable free data exists (more material in MLB and somewhat in NFL).
	•	Altitude / travel interaction terms beyond the current fixed adjustments.
	•	A lightweight “market consensus” check (average of 2–3 sharp books) solely for the no-vig win% component of blended EV.
	•	Tracking of push rates and half-point effects on key numbers.
Suggested immediate next steps
	1	Add fractional-Kelly (or fixed fractional) sizing + daily exposure caps.
	2	Introduce a soft EV floor and a simple confidence tag.
	3	Formalize the retune process and CLV-by-market tracking.
	4	Lock source list + cutoff times so every card is reproducible.
Your current skeleton is already better than most public systems. The biggest ROI is turning “every +EV” into a risk-controlled, calibrated portfolio and making the feedback loop (grading → weight change → next card) fully explicit and versioned.
