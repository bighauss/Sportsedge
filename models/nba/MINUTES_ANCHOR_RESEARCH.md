# NBA minutes + sharp-market anchor (PAPER)

Run: cd models/nba && python test_minutes_candidate.py && python test_anchor_evaluator.py

Minutes input requires an ORIGINAL SHA256-matched CSV of historical prior
regulation-only game logs. Columns: game_id,game_utc,player_id,team,minutes,
is_regulation. A separate pre-tipoff JSON manifest provides logs_path
(relative), logs_sha256, captured_at_utc, tipoff_utc, and players array
{player_id,team,status} with explicit ACTIVE or OUT. At least eight active
players/team and three previous games/player; unknown availability is blocked.
A capped weighted allocation conserves exactly 240 regulation player-minutes
per team. It is an unvalidated deterministic candidate, NOT Claude's live NBA
engine or an injury/pace model.

Separate anchor_evaluator.py consumes frozen history with event_id,market
(NBA:PTS, etc),selection,snapshot_utc,baseline_utc,tipoff_utc,final_utc,
model_p,market_p,result,model_sha256,baseline_sha256,baseline_books (two
independent source names). No baseline or result may arrive after the
prediction. Weights are selected only on earlier SETTLED games. Reports NLL
and Brier versus market; no positive-edge or accuracy claim without actual
archived independent data. Do not infer correlations for PRA from mean sums.
