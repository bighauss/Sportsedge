# Nov 25 afternoon owner capture — research replay

PAPER/0u, NON_COUNTED. Supersedes the morning quote board for overlapping research contracts only; preserve both snapshots. Capture was 15:47:43–15:48:46 CT, based on the printed server timestamps. Upload time 15:49:24 CT is the retrospective decision cutoff, not a claim that this run executed at that time.

## Sources
- 3.47.44 PM: FG team totals, 66 two-sided contracts.
- 3.47.52 PM: first-half game lines, 87 contracts.
- 3.48.01 PM: first-half team totals, 48 contracts.
- 3.48.48 PM: FG game lines, 97 contracts (two missing ML pairs).
- 3.48.16/26/32/38 PM: 105 points, 78 threes, 100 rebounds, 87 assists milestone yes prices. No opposite prices or stable player identities on source pages; held pending independent player projection and event-scoped identity.
- Board blob 290e2225c031dbeaf300313e1b584ad0519441c2.
- Projection table blob 46426e5a5b45fcd6fa3f914d082623d795a7ba74 at #537 head 63a4230, frozen 11:25 CT. Public reconstruction, not fresh CBBD.
- Historical TRAIN residual SD table blob e7da962a093e871e4fa5fbb00286405e1a85618a at #538 head 0518a7d3.
- H1 coefficients blob aab8c4f3005890cc48e08d47c0f3e4326287339d at #537.

## Method and limitations
298 two-sided contracts captured from parsed text; no DK event IDs invented. 269 contracts / 538 selections repriced in a separate retrospective calculation from archived projections. 29 H1 ML contracts held for unresolved tie settlement. No new independent production forecast was executed. Full-game means use archived FG1 challenger where present, otherwise reconstructed native means; SD uses corresponding TRAIN residual SD (2019–2021). Normal marginal approximation, not the original Student-t challenger or joint score simulator. For FG moneyline condition on non-tie regulation (approximation to overtime). First-half means, SD and empirical team marginal shapes use the research H1 base variants and archived native scores. All prices are half-point lines except ML. Explicit team-total order is preserved, game identity matched by team aliases and source tip labels; source event IDs and player IDs are absent. No portfolio correlation model, calibration, ROI, CLV, or official stakes. Transcription is a candidate, not independently verified row by row; parsed source text was used. No raw PDF bytes stored in repo.

Nine weights, independent share 100/87.5/75/62.5/50/37.5/25/12.5/0 percent, linear blend with two-sided no-vig probabilities. EV = p*net payout - (1-p), no push for priced contracts. Counts at >=1%: 178,167,154,142,123,87,43,2,0. These are sensitivity counts, NOT backtest returns; #538's separate rolling-origin close-proxy evaluation selected market-only for all full-game families, and cannot validate opening or half markets. No selected weight is promoted. Preserve all research rows, including negative EV.

Freshness is an advisory for owner research boards, not a reason to replace them with earlier uploads. Capture-time evidence and manual provenance are separate. Never use started games in a live delivery; replay remains historical. Raw source access and independently captured provider IDs remain necessary for production acceptance.
