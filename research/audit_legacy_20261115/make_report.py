from pathlib import Path
import csv,json,statistics,hashlib
ROOT=Path(__file__).resolve().parent
R=json.load(open(ROOT/'results/audit_metrics.json'))
card=R['results']['original_65_card'];doubted=R['results']['original_10_model_doubted_not_official'];bs=R['results']['game_cluster_bootstrap']
top=list(csv.DictReader(open(ROOT/'results/archived_top20_original_odds_and_projection.csv')))
games=list(csv.DictReader(open(ROOT/'source/nov11_verified_scores.csv')))
scores={r['game']:r for r in games}
from_tab=[]
for r in R['market_disagreement']:
    f=scores[r['game']];at=int(f['away_final'])+int(f['home_final']);am=int(f['home_final'])-int(f['away_final'])
    from_tab.append(dict(r,actual_total=at,actual_margin=am,model_total_abs_err=abs(at-r['total_model']),book_total_abs_err=abs(at-r['total_book']),model_margin_abs_err=abs(am-r['home_margin_projection']),book_margin_abs_err=abs(am-r['book_home_margin'])))
model_total_mae=statistics.mean(r['model_total_abs_err'] for r in from_tab);book_total_mae=statistics.mean(r['book_total_abs_err'] for r in from_tab)
model_margin_mae=statistics.mean(r['model_margin_abs_err'] for r in from_tab);book_margin_mae=statistics.mean(r['book_margin_abs_err'] for r in from_tab)

def pct(x):return f'{x*100:.1f}%'
def cash(x):return f'{x:+.2f}u'
def trow(cells):return '| '+' | '.join(str(x) for x in cells)+' |'
L=[]
def add(t=''):L.append(t)
add('# SportsEdge — Independent Model Audit, Validation & Forward-Test Package')
add('**As of:** November 14, 2026 (Central). **Research only / PAPER / 0u.** No SportsEdge model, historical prediction, saved line, or qualification rule was modified. All output files are separate derived analyses.')
add('')
add('## Executive findings')
add(f'- **Completed:** 716-row archived historical census analyzed; original 20 largest expected returns independently recomputed. The archived sample is **not point-in-time certified** because row-level source quotes and prediction hashes are missing.')
add(f'- **Completed:** Nov 11 late CBB: 188 priced sides on 96 two-sided market rows; original **65 CARD** selections, separate **10 MODEL-DOUBTED**, and 113 other priced rows. All ten games have independently found final and halftime scores. The historical artifact was created on Drive Nov 11 at 19:34 CT; that is only a file-level signal, not a price receipt for every row.')
add(f'- **Original 65 CARD:** **{card["wins"]}W–{card["losses"]}L**, hypothetical flat 1u **{cash(card["net_units"])} / {pct(card["roi_per_unit"])} ROI**. Mean recorded p **{pct(card["model_mean_p"])}** vs realized hit rate **{pct(card["hit_rate"])}**; Brier **{card["brier"]:.4f}**, log loss **{card["log_loss"]:.4f}**. Ten game clusters: NOT independent 65-event evidence. No execution slips or closing prices. Pre-recorded picks are not evidence of actual wagers.')
add(f'- **Withheld/doubted 10:** {doubted["wins"]}W–{doubted["losses"]}L and hypothetical {cash(doubted["net_units"])}. They **must stay excluded** from CARD/official metrics and must not be added after seeing the results.')
add(f'- **Book overround:** 96 two-sided markets, {R["book_overround"]["min_percent"]:.2f}%–{R["book_overround"]["max_percent"]:.2f}%, zero negative overround pairs. This checks arithmetic, not historical odds availability.')
add('- **EV math audit:** all 188 reproduced to the recorded engine conventions. On 1H ML the engine uses `model_p = P(win | no tie)` and `EV = P(win)*profit − P(loss)`, treating first-half ties as pushes. A naive `model_p*decimal_odds − 1` creates an apparent discrepancy, but is not the correct push-aware formula. This was verified against the archived `sportsedge_v5.py` `emit` path.')
add(f'- **Volatility:** 10-game-cluster bootstrap produces a descriptive **{pct(bs["bootstrap_unit_roi_2p5"])} to {pct(bs["bootstrap_unit_roi_97p5"])}** ROI range. This is not a robust 95% confidence interval with only ten clusters and correlated, multi-market bets.')
add('')
add('## Critical / high-severity findings (ranked by severity, not profit)')
for title,body,proof in [
('CRITICAL 1 — Point-in-time data lineage unverified', 'The 716-row census was assembled after games and lacks row-level quote timestamps, opening/closing quote receipts, model/ruleset hash and each feature as-of timestamp. The Nov 11 board lacks those fields too, although the archived Drive creation time precedes the reported late slate. Player mappings cannot be validated from team-only rows.', 'Signed/immutable per-quote receipts; event ID and kickoff time; model code SHA; source-vintage and feature as-of time; player/team canonical IDs; frozen rule manifest.'),
('CRITICAL 2 — Historical G-18 team-total grading defect', 'In the Nov 9 portable archive, TEAM_TOTAL was matched after TOTAL and graded against the game total. 70 of 496 graded portable rows flip under the corrected dispatch, including seven Washington team-total unders in the top 20. The original census must remain unchanged; only a derived outcome view receives corrections.', 'Independent team-score finals, corrected grader parity tests, old and new grader hashes, full changed-row ledger.'),
('CRITICAL 3 — Defective CBB home-court handoff (Nov 9)', 'The early portable prediction path omitted a documented home-court adjustment. It created exaggerated Rice moneyline/alt-spread confidence and Washington team-total under probabilities. Altering means after seeing results cannot retroactively produce accepted picks.', 'Immutable old projection files, original input feature logs, original HCA coefficient and venue ID, pregame model executable hash, reproduce archived output without altering it.'),
('HIGH 4 — CFB/NBA team-score heuristics assert very large disagreements', 'The largest old claims include Sacramento State ML +217.5% ROI and Sacramento Kings ML +161.9% ROI. The historical audit flagged a wrong QB identity on the CFB source board and large heuristic-versus-book spread mismatches on NBA sides. These are model/identity questions, not proof the book was wrong.', 'Pregame QB/roster evidence, same-time spread/ML, feature source, line movement and independent benchmark, forward calibration.'),
('HIGH 5 — Nov 11 market disagreement vs actual totals', 'Grand Canyon/Cal Poly projected total 162.16 vs DK 181.5; actual 170. Oakland/Boise projected 147.57 vs DK 159.5; actual **190**. Pacific/Long Beach projected 147.97 vs DK 138.5; actual 121. The resulting errors do not identify the optimum model weight; several oversized claims were already in MODEL-DOUBTED.', 'Separate model vs market distributional and calibration evaluation across future slates; save input vintages before games and compare to a proper market baseline.'),
('HIGH 6 — Repeated opinions and cross-market correlation', 'The old top 20 rows represent only seven games; the Nov 11 65 card rows only ten games, with exposure concentrated in single events. Combined totals/team totals/1H bets often share one team-score projection. Counting the rows as independent opportunities inflates precision.', 'Event-level covariance estimated from enough future games; game-cluster bootstrap, same-game exposures and distinct market-family grouping.'),
('HIGH 7 — Probability calibration on Nov 11 card', f"The 65 picks averaged {pct(card['model_mean_p'])} estimated win probability but hit {pct(card['hit_rate'])}. The 65-row Brier was {card['brier']:.4f}. This is a serious warning but is one slate, ten underlying games, and cannot justify a historical refit.", 'Hundreds of frozen qualifying bets from fresh dates, independent events across sports/market families, stable grading and CLV; compare with the sportsbook baseline.'),
('HIGH 8 — Historical result/roster joins are fragile', 'Prior results report a Southern Miss/Jackson State versus Jacksonville State matchup mismatch and an initially wrong Mississippi Valley State fuzzy-match to Mississippi State ratings before repricing on Nov 11. Both are example reasons text-only joins must be rejected without ID receipts.', 'Stable sportsbook event ID, canonical team+player ID, site, roster and box score IDs, strict join cardinality tests; verify each before counting.'),
('MEDIUM 9 — Large EV display can hide execution cost and missing market access', 'Many high EV rows are alternate ladder sides with long odds or restricted market availability. A matched DK book screen and accepted bet size are not proven by a model board line. The Nov 11 record lacks actual fill, offered/accepted state and benchmark closing price.', 'Pregame priced quote receipt, market status/limits, separate execution records, contemporaneous sharp/reference book odds and closing line.')]:
    add(f'### {title}');add(body);add(f'**To verify:** {proof}');add('')
add('## Archived top 20 — original ranking, read-only original EV')
add('**Important:** all 20 are **provisional**, drawn from the postgame-assembled Nov 4/9 census. Odds and model p below are original snapshots, not retroactively corrected. “Audit outcome” is independently interpreted from official finals and documented G-18 correction; no result proves model confidence.')
add(trow(['#','Selection','American','Model p','Book break-even','Raw edge','Original EV','Audit W/L','Severity']))
add(trow(['---:','---','---:','---:','---:','---:','---:','---','---']))
for r in top:
 add(trow([r['archived_rank'],r['game']+' — '+r['pick'],('+' if int(r['american_odds'])>0 else '')+r['american_odds'],pct(float(r['model_p'])),pct(float(r['book_break_even_p'])),f"{100*float(r['raw_probability_edge']):+.1f}pp",pct(float(r['EV_recalculated'])),r['audit_result'],r['severity']]))
add('')
add('## November 11 external finals, model-versus-book checks')
add(trow(['Game','Final (away-home)','1H (away-home)','Model total','Book total','Actual total','Model–book total','Model–book margin']))
add(trow(['---','---','---','---:','---:','---:','---:','---:']))
for r in from_tab:
 f=scores[r['game']]
 add(trow([r['game'],f['away_final']+'–'+f['home_final'],f['away_1h']+'–'+f['home_1h'],f'{r["total_model"]:.2f}',f'{r["total_book"]:.1f}',r['actual_total'],f'{r["total_model_minus_book_pts"]:+.2f}',f'{r["margin_model_minus_book_pts"]:+.2f}']))
add(f'**Ten-game full-game score-prediction MAE:** model total {model_total_mae:.2f} vs book total {book_total_mae:.2f} points; model home-margin {model_margin_mae:.2f} vs book home-margin {book_margin_mae:.2f}. This is tiny, non-representative, uncalibrated and not a selection of bets. Market “book” values are from the captured DK board. A half-time margin predictor is not reconstructible from the saved full-game means.')
add('')
add('## November 11 original 65-card performance by game')
add(trow(['Game','Picks','W','L','Units','ROI']))
add(trow(['---','---:','---:','---:','---:','---:']))
for g,m in R['results']['original_card_by_game'].items():add(trow([g,m['rows'],m['wins'],m['losses'],cash(m['net_units']),pct(m['roi_per_unit'])]))
add('')
add('## Original 65-card direction and market-family diagnostics')
add(trow(['Direction','N','Win rate','Mean p','Units','ROI']))
add(trow(['---','---:','---:','---:','---:','---:']))
for g,m in R['results']['original_card_by_direction'].items():add(trow([g,m['rows'],pct(m['hit_rate']),pct(m['model_mean_p']),cash(m['net_units']),pct(m['roi_per_unit'])]))
add('')
add(trow(['Market','N','Win rate','Mean p','Units','ROI']))
add(trow(['---','---:','---:','---:','---:','---:']))
for g,m in R['results']['original_card_by_market'].items():add(trow([g,m['rows'],pct(m['hit_rate']),pct(m['model_mean_p']),cash(m['net_units']),pct(m['roi_per_unit'])]))
add('')
add('## Market-disagreement buckets — full-game, like-for-like only')
add('Only 30 of the original 65 selections can be compared with a same-period, same-family parent market line using the preserved full-game projected scores. The 1H and ML markets are excluded; this cannot evaluate all bets, and bucket edges cannot be optimized based on this one slate.')
add(trow(['Abs model–parent gap (points)','N','Mean model p','Actual hit','Flat 1u ROI']))
add(trow(['---','---:','---:','---:','---:']))
for k,m in R['results']['market_disagreement_buckets_fullgame_only'].items():
    add(trow([k,m['rows'],pct(m['model_mean_p']),pct(m['hit_rate']),pct(m['roi_per_unit'])]))
add('These bins are **descriptive** and grouped by a same-market model-vs-DK parent mean; the small, nonmonotonic pattern cannot prove that large edges are bad or good. Preserve the bins and retest on untouched future dates. See `nov11_eligible_fullgame_gap_buckets_per_selection.csv`.')
add('')
add('## Ten candidate input families for future ablation (NOT a predictive ranking)')
add('1. Team pace/possessions, 2. opponent-adjusted offense, 3. opponent-adjusted defense, 4. venue and neutral-site indicator, 5. injury/starter/lineup availability, 6. actual projected player minutes or snaps, 7. player opportunity volume, 8. opponent matchup strength, 9. recent-form features calculated strictly as of prediction time, 10. current same-timestamp book spread/total and bookmaker margin as the benchmark. Every proposed family requires a source timestamp and proof that it existed before kickoff. None has been ranked on this incomplete archive. Sports-specific baselines should be predeclared, trained on previous seasons/weeks and measured on future games only.')
add('')
add('## Reliability bins — no same-slate refit')
add(trow(['Model p range','N','Mean predicted','Observed win rate']))
add(trow(['---','---:','---:','---:']))
for x in R['results']['calibration_by_bin']:add(trow([x['range'],x['n'],pct(x['mean_p']),pct(x['actual_win_rate'])]))
add('The calibration bins are **not independent Bernoulli trials**. Same-game first-half, team total, and total bets share random outcomes; one result can move several bins. See `nov11_reliability_diagram.png`.')
add('')
add('## Applicability of the 16-prompt framework')
add(trow(['Prompt family','Deliverable / completed work','Current limitation']))
add(trow(['---','---','---']))
for a,b,c in [
('Model architecture and predictive variables','`walkforward_research.py`: independent market baseline + fixed-feature ablations. New model not deployed.','No point-in-time sport-specific feature histories here; cannot rank 10 real predictive variables on this sample.'),
('Data quality inspection','Source hashes, 188-row schema, duplicate keys, 96 book overround pairs, 10 finals, missing event/roster quote receipts.','Original source-side identifiers and daily feature as-of records missing.'),
('Player props','Fail-closed player-ID and source-as-of checks plus an explicit pregame-only Poisson count-prop research baseline in `prop_research_baseline.py`; no output without real logs and planned minutes/opportunities.','No historical prop logs, player ID mapped usage/efficiency/attempts or outcomes in these 904 rows.'),
('EV calculator','Raw American implied, no-vig book p, push-aware 1H ML reconciliation, payoff arithmetic.','No accepted bet-slip or independent sharp-book price to estimate execution losses.'),
('Walk-forward specialist','Expanding train-to-future test folds with feature timestamps, label-availability guard, strict event identity, market baseline.','Not executable as real backtest without immutable event-level features.'),
('Model improvement / bias','Team, market, direction, probability bins, game clusters and model–book disagreements (Nov11).','Small sample, no support for formula change.'),
('Performance tracker','65 CARD ledger; 10 DOUBTED ledger separate; 113 other market sides never counted as bets; audit metrics and source hashes.','Only hypothetical flat 1u paper ROI. Settlement timing and CLV missing.'),
('Model automation','`prospective_controls.py validate/evaluate`, source-manifest and check failures; no engine write.','Automatic scheduled ingestion requires authenticated external source and an agreed feed; not started.'),
('Leakage detective','Strict future-as-of rejection, late quotes, retroactive rules, missing hashes and identity checks.','Historical archive not time-certified.'),
('Backtest auditor','Top20 and Nov11 grade recomputation, never qualify bets in hindsight.','716 archived rows not fully prospective; file-level creation times are insufficient for row-level claims.'),
('Probability calibration','Brier, log loss, bins, reliability plot on original 65.','Ten independent game clusters only; no calibration model fit justified.'),
('EV inspection','All 188 arithmetic checked; 96 overround pairs no anomalies.','Line availability and bookmaker execution cannot be independently authenticated.'),
('Market bias hunter','Direction, period, game and market family performance; negative bias evidence flagged not assumed.','No repeated unseen forward period yet.'),
('Correlation analyzer','Game-cluster grouping, exposure counts, cluster bootstrap.','True correlations require repeated joint bets across many games.'),
('Version tracker','Original v5 run note, archive hashes, mandatory future model/ruleset hash and activation time.','Full GitHub version chronology unavailable; connector returned a 403 suspended response.'),
('Stress tester','10,000 game-cluster resamples, unit ROI distribution, uncertainty warning.','Max drawdown not defensible without original sequence/settlement timestamps; only ten games.')]:
 add(trow([a,b,c]))
add('')
add('## Prospective recommendations — proposals, NOT approved modifications')
add('1. **Versioned source contracts** (P0). Store each quote with sportsbook, event/market/player IDs, `captured_at_utc`, `prediction_at_utc`, `feature_asof_utc`, kickoff, model SHA, frozen rule SHA and receipt hash. Fail closed on missing fields. Test using synthetic late/duplicated/stale snapshots, then a seven-day shadow run. Never backfill a new receipt as if it existed before kickoff.')
add('2. **Historical outcome repair in a parallel view** (P0). Leave `census.json` and original cards byte-identical; export `grade_corrected` beside `grade_of_record` with exact event-score and grader version. Regression-test G-18 with Washington Under 82.5 and ordinary full-game Under 82.5 as contrasting cases.')
add('3. **Separated first-half model and game-total model checks** (P0). Save actual first-half forecast distribution *before* games and audit on new weeks. The Nov 11 1H rows cannot be reconstructed from the full-game projection mean alone.')
add('4. **Large edge quarantine candidate** (P1). Compare pregame projection inputs with independently captured same-time market parent spread/total, and tag gaps for review. Do **not** tune the threshold to the Nov 4/9/11 failures; preregister gap buckets (0–3, 3–6, 6–10, >10 points) and report calibration/ROI forward by bucket without altering the old cards.')
add('5. **Roster, starter, neutral site and aliases** (P1). Require stable IDs; reject fuzzy text match on a live selection unless explicitly confirmed from point-in-time source. Keep a complete reject log. Use prospective fixture tests involving Mississippi Valley State vs Mississippi State, venue flips, and wrong player teams.')
add('6. **Separate validation by sport and market** (P1). For each use expanding walk-forward folds and a timestamp-matched no-vig market baseline, out-of-sample Brier/log loss and raw ROI. Keep an untouched holdout period for a single preregistered promotion verdict. Do not pool CBB and NFL parameter targets.')
add('7. **Evaluation with realistic execution** (P1). Require actual fill/accepted odds (or mark “theoretical”), stake, available line limits, best-market and DK benchmark, push/commission logic and closing-price evidence. Report theoretical/filled counts separately; do not infer CLV from the win/loss result.')
add('8. **Correlation-robust forward tracking** (P1). Print per-game and per-selection ROI, group bets by common projection/injury/team/game script, and bootstrap whole games. Add exposure limits only after prospective testing under a preregistered risk policy. Do not delete duplicates silently.')
add('9. **Feature ablation, baselines and props research** (P2). Try simpler, measurable inputs first; compare a frozen market baseline, a simple feature model, then one removal group at a time on future folds. For player props require actual roster IDs, projected minutes/snaps, opportunities, efficiency, opponent and residual distributions. No missing-input projection is allowed.')
add('10. **Automation and governance** (P2). Run the no-write validator on every capture, save read-only report outputs and hashes, and alert on stale/late data and unidentified players. Production promotion requires separate owner approval; the existing hourly SportsEdge workflow should consume reports, not be duplicated by a conflicting new scheduler.')
add('')
add('## No in-sample refit or retrospective leakage')
add('All diagnostics and source-score joins were performed *after* selections were frozen; they change only the audit view. No production calibration constants, lineup assumptions, thresholds, stake rule, historical probability, qualification status or model artifact were changed. No calibration parameter is fitted here. Original CARD 65 and MODEL-DOUBTED 10 remain in their original buckets even if their outcomes contradict the model.')
add('')
add('## Provenance and known data limitations')
add('- Original Drive `census.json`: https://drive.google.com/file/d/1yI_2CA52Y9-LcI2kpnFkzGk6BmNXRhTq/view')
add('- Original 188-row Nov 11 CSV: https://drive.google.com/file/d/1x-sC8kLvOoKnZL5WP8PDbmmU-RyaBCID/view')
add('- Original 96-market Nov 11 board: https://drive.google.com/file/d/1s_guYIfk_8o6QfZR0nkFMcgti3J8H4om/view')
add('- Original Nov 11 card and doubted categories: https://drive.google.com/file/d/1tSPOPxP988zFTZOF1HGPOBHEIaZKU-bu/view')
add('- Nov 11 late-run source note (version, captures, alias correction): https://drive.google.com/file/d/1Mo5vYZtl1VYddfln3nkn5jgvsPPR_nR1/view')
add('- Independent earlier archive audit: https://drive.google.com/file/d/1rtnA0xV5DIcVgRlV2mzHHWqo58C4Mqou/view')
add('- Nov 11 scoreboard with finals and 1H splits: https://www.warrennolan.com/basketball/2027/scores-live?date=2026-11-11&type=All+Games')
add('- Separate original run-it card final grading note: https://drive.google.com/file/d/1uLs9FYr-vGgo9YoOAh2T6sBSPE7ew4Ly/view (not merged because source game identity anomaly and missing independent player-prop verification).')
add('')
add('## Runbook')
add('```bash')
add('python independent_audit.py --input-dir source --output-dir results')
add('python make_charts.py')
add('python -m unittest -v test_independent_audit.py')
add('python prospective_controls.py example-schema')
add('python prospective_controls.py validate /path/to/frozen_pregame_snapshots.csv')
add('python walkforward_research.py /path/to/frozen_event_features.csv pace,efficiency,injury 150 20')
add('```')
add('**Never run `walkforward_research.py` on the existing 716+188 data as though they contained historical raw features.** The feature matrix and outcome-availability timestamps are not there. Do not treat predicted probabilities as trainable inputs for the model they are validating.')
(ROOT/'INDEPENDENT_AUDIT_REPORT.md').write_text('\n\n'.join(L)+'\n',encoding='utf-8')
print('report',len(L), (ROOT/'INDEPENDENT_AUDIT_REPORT.md').stat().st_size)
