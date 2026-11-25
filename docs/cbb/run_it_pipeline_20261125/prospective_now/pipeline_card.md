# RUN IT CBB — full pipeline research card (2026-11-25)

**PAPER / 0u · NON_COUNTED · research only, not recommendations.** Pipeline cbb-run-it-pipeline-v1 · projection adapter `native_formula_public_replay` · freeze 2026-11-25 11:25 AM CT · card sha `f11bea2d8999`

Board `models/cbb/dk/derived/2026-11-25/runner_board.csv@ed855c58` (sha256 `acdeb2cdd8ef`), provenance **UNAUTHENTICATED_PDF**: not an authenticated DraftKings capture.

> Projection inputs are a PUBLIC ESPN reconstruction (opponent-adjusted efficiencies from box-score possession estimates), NOT the production CBBD ratings. The frozen native formula is unchanged; this run tests the pipeline end to end, not production model quality.
> Venue: ESPN neutral flag only (single source, unverified); production requires CBBD+ESPN agreement.
> Freeze kind: PROSPECTIVE. ESPN data was observed 2026-11-25T17:25:43Z; leakage control uses tip times (prior final assumed available at tip+3h).
> Game ids are ESPN event ids in this replay (production uses CBBD ids).
> CHALLENGER (research): FG1C from models/cbb/fullgame (schedule-adjusted ridge + prior-season prior + recency + verified-venue HCA + chronological de-bias; Student-t residual pricing). Not production; the frozen model stays the default. Hybrid = logit blend at the validation-selected model weight (open: ML 0.125 / spread 0 / total 0.125; at the close validation chose 0 everywhere). Team-total hybrid weight 0.125 is the runner's assumption (not separately validated).
> RESEARCH: half means come from models/cbb/halves (cbb-halves-v1-research), scaled to its fitting research projector, not the production model; its totals ran ~1.1-1.4 points UNDER on the held-out 2026 season; margin/total/period correlation not modelled; half moneylines assume TIE_PUSH (unverified DK rule). Player markets remain NOT_IMPLEMENTED (see coverage).

Views: **FROZEN** (default; frozen native formula), **CHALLENGER** (fullgame FG1C, research), **MARKET** (DK no-vig), **HYBRID** = logit blend of the challenger with the market at the validation-selected model weight (open: ML 0.125, spread 0, total 0.125; at the close validation chose 0 for every market). The hybrid is therefore mostly the market; it is a research view, PAPER/0u, NON_COUNTED, not production-validated. Stars: n/a uncalibrated.

## Projections per game (frozen · challenger · market no-vig · hybrid)

| Tip (CT) | Game | Frozen margin | Frozen total | Chal away | Chal home | Chal margin | Chal total | Mkt margin | Mkt total | Hyb margin | Hyb total | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 11:30 AM CT | Northern Colorado @ Detroit Mercy | -3.1 | 140.1 | 76.2 | 71.7 | -4.5 | 148.0 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 11:31 AM CT | Yale @ Wright State | +13.0 | 136.3 | 68.5 | 75.5 | +7.0 | 144.0 | +6.0 | 137.7 | +6.0 | 138.5 | PROJECTED |
| 12:00 PM CT | Eastern Kentucky @ Miami (OH) | +18.6 | 149.4 | 68.7 | 85.0 | +16.4 | 153.7 | +14.4 | 158.0 | +14.4 | 157.5 | PROJECTED |
| 12:00 PM CT | American International @ Rhode Island | — | — | — | — | — | — | — | — | — | — | PASS GAME_NOT_PROJECTED:UNMAPPED_CBBD_TEAM_ID · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 12:00 PM CT | Southern Utah @ Long Beach State | -1.1 | 168.4 | 76.9 | 79.0 | +2.1 | 155.9 | +1.5 | 150.5 | +1.5 | 151.2 | PROJECTED |
| 12:00 PM CT | Lindenwood @ Stony Brook | +13.6 | 130.6 | 65.8 | 76.9 | +11.1 | 142.8 | +10.6 | 143.7 | +10.6 | 143.6 | PROJECTED |
| 12:30 PM CT | Tulane @ Davidson | +7.4 | 136.1 | 65.4 | 74.4 | +9.0 | 139.8 | +8.6 | 137.0 | +8.6 | 137.4 | PROJECTED |
| 1:00 PM CT | Johnson & Wales @ Brown | — | — | — | — | — | — | — | — | — | — | PASS GAME_NOT_PROJECTED:UNMAPPED_CBBD_TEAM_ID · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 1:00 PM CT | Abilene Christian @ South Dakota State | +14.6 | 145.9 | 64.7 | 76.7 | +12.0 | 141.4 | +7.5 | 142.0 | +7.5 | 142.0 | PROJECTED |
| 1:00 PM CT | Manhattan @ NJIT | +3.8 | 133.7 | 69.6 | 72.7 | +3.2 | 142.3 | +1.6 | 141.0 | +1.6 | 141.2 | PROJECTED |
| 1:00 PM CT | LSU @ Arizona State | -10.7 | 152.9 | 79.1 | 72.8 | -6.3 | 151.9 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 1:00 PM CT | Warner @ North Florida | — | — | — | — | — | — | — | — | — | — | PASS GAME_NOT_PROJECTED:UNMAPPED_CBBD_TEAM_ID · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 1:00 PM CT | Saint Peter's @ Columbia | +23.7 | 110.5 | 55.1 | 73.8 | +18.7 | 128.8 | +14.8 | 125.7 | +14.8 | 126.1 | PROJECTED |
| 1:00 PM CT | Montreat @ Western Carolina | — | — | — | — | — | — | — | — | — | — | PASS GAME_NOT_PROJECTED:UNMAPPED_CBBD_TEAM_ID · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 1:00 PM CT | Grace Christian @ Western Michigan | — | — | — | — | — | — | — | — | — | — | PASS GAME_NOT_PROJECTED:UNMAPPED_CBBD_TEAM_ID · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | +22.9 | 162.0 | 69.6 | 87.4 | +17.7 | 157.0 | +21.4 | 155.5 | +21.4 | 155.7 | PROJECTED |
| 1:30 PM CT | Texas A&M @ Xavier | -7.5 | 163.3 | 85.9 | 77.4 | -8.6 | 163.3 | -5.2 | 169.3 | -5.2 | 168.6 | PROJECTED |
| 1:30 PM CT | Ole Miss @ Arizona | +0.1 | 151.5 | 73.0 | 77.1 | +4.1 | 150.1 | +5.4 | 154.5 | +5.4 | 154.0 | PROJECTED |
| 2:00 PM CT | Jackson State @ Oklahoma State | +31.4 | 167.2 | 65.3 | 96.1 | +30.8 | 161.5 | +34.4 | 160.7 | +34.4 | 160.8 | PROJECTED |
| 2:00 PM CT | SE Louisiana @ North Dakota | +0.4 | 160.4 | 73.9 | 75.9 | +2.1 | 149.8 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 2:00 PM CT | Akron @ App State | -2.4 | 113.6 | 68.7 | 62.9 | -5.8 | 131.6 | -6.4 | 133.0 | -6.4 | 132.8 | PROJECTED |
| 2:30 PM CT | Arkansas State @ Florida International | +6.2 | 176.7 | 81.3 | 84.4 | +3.0 | 165.7 | +1.8 | 173.3 | +1.8 | 172.4 | PROJECTED |
| 3:00 PM CT | Prairie View A&M @ Marshall | +18.0 | 162.6 | 67.1 | 82.3 | +15.2 | 149.4 | +15.4 | 151.5 | +15.4 | 151.2 | PROJECTED |
| 3:00 PM CT | Georgia State @ Florida Gulf Coast | -1.0 | 148.1 | 75.2 | 74.4 | -0.8 | 149.6 | -3.4 | 145.3 | -3.4 | 145.8 | PROJECTED |
| 3:00 PM CT | Princeton @ Liberty | +3.6 | 136.4 | 69.9 | 73.8 | +3.8 | 143.7 | +3.4 | 135.3 | +3.4 | 136.4 | PROJECTED |
| 3:00 PM CT | Grambling @ LSU New Orleans | +0.1 | 169.3 | 72.1 | 78.3 | +6.2 | 150.3 | +3.5 | 152.0 | +3.5 | 151.8 | PROJECTED |
| 3:00 PM CT | Bethesda @ Utah Tech | +54.5 | 182.0 | — | — | — | — | — | — | — | — | PROJECTED · market NO_QUOTE · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 3:30 PM CT | South Carolina @ USC | +14.7 | 149.1 | 69.4 | 80.5 | +11.2 | 149.9 | +10.6 | 147.7 | +10.6 | 148.0 | PROJECTED |
| 4:00 PM CT | Memphis @ Penn State | -5.6 | 170.2 | 83.5 | 79.3 | -4.2 | 162.7 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 4:00 PM CT | Holy Cross @ Dartmouth | +15.7 | 148.8 | 67.1 | 82.3 | +15.1 | 149.4 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 4:00 PM CT | Alcorn State @ Texas State | +31.9 | 148.4 | 58.5 | 86.5 | +28.0 | 145.1 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 4:00 PM CT | Portland State @ UC Riverside | +7.0 | 148.7 | 71.5 | 72.9 | +1.4 | 144.4 | +2.5 | 152.3 | +2.5 | 151.3 | PROJECTED |
| 4:00 PM CT | Southern @ Nebraska | +32.7 | 155.0 | 57.9 | 88.7 | +30.8 | 146.6 | +35.5 | 149.0 | +35.5 | 148.7 | PROJECTED |
| 4:30 PM CT | BYU @ Providence | -4.3 | 153.2 | 82.0 | 74.8 | -7.2 | 156.8 | -3.4 | 154.5 | -3.4 | 154.8 | PROJECTED |
| 5:00 PM CT | UAlbany @ Syracuse | +28.5 | 153.5 | 64.6 | 87.1 | +22.5 | 151.8 | +26.5 | 149.7 | +26.5 | 149.9 | PROJECTED |
| 5:00 PM CT | Bethune-Cookman @ Richmond | +8.3 | 161.1 | 72.8 | 82.6 | +9.8 | 155.4 | +11.8 | 148.5 | +11.8 | 149.4 | PROJECTED |
| 5:00 PM CT | Cal State Northridge @ Weber State | -0.4 | 185.2 | 83.8 | 85.2 | +1.4 | 169.0 | -2.6 | 167.3 | -2.6 | 167.5 | PROJECTED |
| 5:00 PM CT | Kennesaw State @ Charleston | -4.8 | 166.3 | 79.3 | 76.3 | -3.1 | 155.6 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 5:00 PM CT | West Florida @ Northwestern State | +4.5 | 148.4 | — | — | — | — | — | — | — | — | PROJECTED · market NO_QUOTE · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 6:00 PM CT | UConn @ Duke | -2.4 | 148.2 | 72.3 | 72.0 | -0.3 | 144.3 | -2.2 | 147.0 | -2.2 | 146.7 | PROJECTED |
| 6:00 PM CT | Northeastern @ Wisconsin | +12.5 | 158.4 | 71.4 | 88.2 | +16.8 | 159.6 | +19.8 | 156.5 | +19.8 | 156.9 | PROJECTED |
| 6:00 PM CT | Norfolk State @ NC State | +29.4 | 152.0 | 63.9 | 93.0 | +29.1 | 156.9 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 6:00 PM CT | SMU @ Utah State | +3.8 | 176.3 | 81.1 | 86.3 | +5.1 | 167.4 | +4.5 | 167.3 | +4.5 | 167.3 | PROJECTED |
| 6:00 PM CT | Longwood @ George Mason | +13.3 | 146.1 | 65.2 | 79.0 | +13.8 | 144.3 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 6:00 PM CT | St. Thomas @ UNC Wilmington | +0.4 | 177.1 | 79.2 | 81.2 | +2.0 | 160.4 | +6.5 | 156.5 | +6.5 | 157.0 | PROJECTED |
| 6:00 PM CT | Northern Illinois @ SIU Edwardsville | -6.2 | 154.4 | 72.6 | 71.5 | -1.1 | 144.1 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 6:00 PM CT | Bellarmine @ Northern Kentucky | +0.7 | 158.5 | 77.4 | 79.2 | +1.9 | 156.6 | +6.5 | 148.3 | +6.5 | 149.4 | PROJECTED |
| 6:00 PM CT | Case Western Reserve @ Cleveland State | — | — | — | — | — | — | — | — | — | — | PASS GAME_NOT_PROJECTED:UNMAPPED_CBBD_TEAM_ID · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 6:00 PM CT | South Carolina Upstate @ The Citadel | +15.7 | 148.4 | 68.4 | 72.5 | +4.0 | 140.9 | +3.6 | 137.5 | +3.6 | 137.9 | PROJECTED |
| 6:30 PM CT | Wake Forest @ Mississippi State | +5.7 | 152.0 | 74.7 | 75.3 | +0.7 | 150.0 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 7:00 PM CT | Omaha @ UC Davis | +5.9 | 157.2 | 69.9 | 77.0 | +7.1 | 146.9 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 7:00 PM CT | Cal State Bakersfield @ Pepperdine | +13.5 | 170.2 | 74.8 | 82.9 | +8.1 | 157.7 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 7:30 PM CT | Eastern Michigan @ UTEP | -1.2 | 136.8 | 66.3 | 66.3 | +0.1 | 132.6 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 8:00 PM CT | Eastern Washington @ Loyola Marymount | +8.3 | 152.6 | 72.9 | 79.8 | +6.8 | 152.7 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 8:00 PM CT | Mississippi Valley State @ New Mexico | +27.6 | 143.2 | 57.9 | 90.1 | +32.2 | 148.0 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 8:00 PM CT | Northwest Indian @ Montana State | — | — | — | — | — | — | — | — | — | — | PASS GAME_NOT_PROJECTED:UNMAPPED_CBBD_TEAM_ID · CHALLENGER_PASS:CHALLENGER_TEAM_UNRATED |
| 8:30 PM CT | Grand Canyon @ Colorado | -9.2 | 160.8 | 78.7 | 72.7 | -6.0 | 151.4 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 9:00 PM CT | Washington @ VCU | +4.3 | 145.2 | 73.4 | 76.2 | +2.8 | 149.5 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 9:30 PM CT | Pacific @ Jacksonville State | -2.5 | 130.4 | 70.8 | 65.2 | -5.5 | 136.0 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 10:59 PM CT | Stanford @ Saint Louis | +11.3 | 159.7 | 72.5 | 80.7 | +8.2 | 153.2 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 10:59 PM CT | Incarnate Word @ Hawai'i | +16.2 | 136.4 | 62.2 | 78.3 | +16.0 | 140.5 | — | — | — | — | PROJECTED · market NO_QUOTE |
| 11:30 PM CT | Clemson @ Colorado State | -0.1 | 150.1 | 75.6 | 72.6 | -3.0 | 148.2 | — | — | — | — | PROJECTED · market NO_QUOTE |

## Priced markets (ranked by frozen-model paper EV; FG probabilities from the seeded joint simulation, half probabilities from the halves adapter; challenger from fullgame.pricing Student-t residuals)

| # | Tip (CT) | Game | Per | Market | Side | Line | DK odds | p frozen | p push | p chal | p no-vig | p hybrid | Fair (frozen) | EV frozen | EV chal | EV hybrid | Audit flags | Stars | Status | Provenance |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|
| 1 | 6:00 PM CT | Northeastern @ Wisconsin | FG | ML | away | — | +1500 | 0.156 | 0.000 | 0.067 | 0.060 | 0.061 | +540 | +150.0% | +8.0% | -2.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 2 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | TOTAL | over | 156.5 | -110 | 0.890 | 0.000 | 0.602 | 0.500 | 0.513 | -806 | +69.8% | +14.9% | -2.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 3 | 2:00 PM CT | Akron @ App State | FG | TOTAL | under | 132.5 | -105 | 0.856 | 0.000 | 0.528 | 0.489 | 0.494 | -595 | +67.2% | +3.2% | -3.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 4 | 2:00 PM CT | Akron @ App State | FG | ALT_TOTAL | under | 133.5 | -110 | 0.869 | 0.000 | 0.553 | 0.490 | 0.498 | -664 | +65.9% | +5.6% | -5.0% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 5 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | TOTAL | over | 167.5 | -108 | 0.858 | 0.000 | 0.545 | 0.496 | 0.502 | -603 | +65.2% | +5.0% | -3.3% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 6 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | TOTAL | over | 152.5 | -105 | 0.844 | 0.000 | 0.457 | 0.489 | 0.485 | -541 | +64.8% | -10.9% | -5.3% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 7 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | TOTAL | over | 150.5 | -110 | 0.856 | 0.000 | 0.625 | 0.500 | 0.516 | -594 | +63.4% | +19.3% | -1.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 8 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | ALT_TOTAL | over | 155.5 | -125 | 0.900 | 0.000 | 0.625 | 0.520 | 0.534 | -899 | +62.0% | +12.5% | -3.9% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 9 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | ML | away | — | +550 | 0.248 | 0.000 | 0.184 | 0.148 | 0.152 | +303 | +61.3% | +19.5% | -1.4% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 10 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | ALT_SPREAD | home | -4.5 | -104 | 0.822 | 0.000 | 0.483 | 0.473 | 0.473 | -462 | +61.2% | -5.2% | -7.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 11 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | SPREAD | home | -3.5 | -112 | 0.842 | 0.000 | 0.517 | 0.504 | 0.504 | -533 | +59.4% | -2.2% | -4.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 12 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | ML | away | — | +225 | 0.490 | 0.000 | 0.434 | 0.295 | 0.311 | +104 | +59.3% | +40.9% | +1.0% | EV_GT_30_PCT,FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 13 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | ALT_TOTAL | over | 151.5 | -120 | 0.857 | 0.000 | 0.481 | 0.510 | 0.506 | -600 | +57.1% | -11.9% | -7.2% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 14 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | ALT_TOTAL | over | 166.5 | -125 | 0.870 | 0.000 | 0.569 | 0.520 | 0.526 | -670 | +56.6% | +2.4% | -5.2% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 15 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | ALT_TOTAL | over | 149.5 | -125 | 0.868 | 0.000 | 0.648 | 0.520 | 0.537 | -657 | +56.2% | +16.7% | -3.4% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 16 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | ML | away | — | +230 | 0.473 | 0.000 | 0.413 | 0.290 | 0.305 | +112 | +56.0% | +36.3% | +0.5% | EV_GT_30_PCT,FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 17 | 1:00 PM CT | Saint Peter's @ Columbia | FG | TOTAL | under | 125.5 | -108 | 0.808 | 0.000 | 0.426 | 0.496 | 0.487 | -421 | +55.7% | -18.0% | -6.2% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 18 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | TOTAL | under | 143.5 | -108 | 0.773 | 0.000 | 0.509 | 0.496 | 0.497 | -340 | +48.8% | -2.0% | -4.2% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 19 | 1:00 PM CT | Saint Peter's @ Columbia | FG | ALT_TOTAL | under | 126.5 | -125 | 0.824 | 0.000 | 0.450 | 0.520 | 0.512 | -468 | +48.3% | -19.0% | -7.9% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 20 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | TOTAL | over | 148.5 | -110 | 0.772 | 0.000 | 0.659 | 0.500 | 0.521 | -339 | +47.4% | +25.9% | -0.6% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 21 | 1:00 PM CT | Saint Peter's @ Columbia | FG | ALT_SPREAD | home | -15.5 | -103 | 0.747 | 0.000 | 0.631 | 0.471 | 0.471 | -295 | +47.2% | +24.3% | -7.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 22 | 1:30 PM CT | Ole Miss @ Arizona | FG | ML | away | — | +195 | 0.496 | 0.000 | 0.340 | 0.325 | 0.327 | +102 | +46.3% | +0.3% | -3.6% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 23 | 4:00 PM CT | Alcorn State @ Texas State | FG | SPREAD | home | -23.5 | -105 | 0.746 | 0.000 | 0.672 | 0.489 | 0.489 | -294 | +45.7% | +31.2% | -4.5% | EV_GT_30_PCT,FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 24 | 8:00 PM CT | Mississippi Valley State @ New Mexico | FG | SPREAD | away | 36.5 | -112 | 0.763 | 0.000 | 0.626 | 0.504 | 0.504 | -322 | +44.5% | +18.6% | -4.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 25 | 1:00 PM CT | Saint Peter's @ Columbia | FG | SPREAD | home | -14.5 | -115 | 0.772 | 0.000 | 0.663 | 0.511 | 0.511 | -338 | +44.3% | +24.0% | -4.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 26 | 6:00 PM CT | St. Thomas @ UNC Wilmington | 1H | TOTAL | over | 73.5 | -110 | 0.748 | 0.000 | — | 0.490 | 0.554 | -296 | +42.7% | — | +5.8% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 27 | 6:00 PM CT | St. Thomas @ UNC Wilmington | 1H | ML | away | — | +195 | 0.470 | 0.038 | — | 0.319 | 0.348 | +105 | +42.6% | — | +6.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 28 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | TOTAL | over | 137.5 | -110 | 0.746 | 0.000 | 0.590 | 0.500 | 0.511 | -294 | +42.5% | +12.7% | -2.4% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 29 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | ALT_TOTAL | under | 144.5 | -125 | 0.791 | 0.000 | 0.533 | 0.520 | 0.522 | -377 | +42.3% | -4.0% | -6.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 30 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | ALT_TOTAL | over | 147.5 | -125 | 0.790 | 0.000 | 0.682 | 0.520 | 0.541 | -376 | +42.2% | +22.7% | -2.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 31 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | ALT_TOTAL | over | 138.5 | -105 | 0.728 | 0.000 | 0.567 | 0.480 | 0.491 | -267 | +42.1% | +10.6% | -4.2% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 32 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | TOTAL | over | 151.5 | -110 | 0.743 | 0.000 | 0.459 | 0.500 | 0.495 | -289 | +41.8% | -12.4% | -5.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 33 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | 1H | TOTAL | over | 64.5 | -115 | 0.755 | 0.000 | — | 0.500 | 0.564 | -309 | +41.2% | — | +5.4% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 34 | 6:00 PM CT | SMU @ Utah State | FG | ALT_TOTAL | over | 165.5 | -115 | 0.750 | 0.000 | 0.540 | 0.500 | 0.505 | -300 | +40.2% | +0.9% | -5.6% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 35 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | TOTAL | over | 148.5 | -108 | 0.727 | 0.000 | 0.685 | 0.496 | 0.521 | -267 | +40.0% | +32.0% | +0.2% | EV_GT_30_PCT,FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 36 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | ML | home | — | -180 | 0.898 | 0.000 | 0.632 | 0.616 | 0.618 | -877 | +39.6% | -1.7% | -3.8% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 37 | 6:00 PM CT | Northeastern @ Wisconsin | FG | SPREAD | away | 19.5 | -105 | 0.712 | 0.000 | 0.572 | 0.489 | 0.489 | -248 | +39.1% | +11.7% | -4.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 38 | 4:00 PM CT | Alcorn State @ Texas State | FG | ALT_SPREAD | home | -22.5 | -126 | 0.771 | 0.000 | 0.703 | 0.518 | 0.518 | -337 | +38.4% | +26.1% | -7.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 39 | 12:00 PM CT | Southern Utah @ Long Beach State | 1H | TOTAL | over | 69.5 | -125 | 0.766 | 0.000 | — | 0.520 | 0.582 | -328 | +37.9% | — | +4.7% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 40 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | SPREAD | home | -7.5 | -110 | 0.719 | 0.000 | 0.647 | 0.500 | 0.500 | -256 | +37.2% | +23.4% | -4.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 41 | 6:00 PM CT | SMU @ Utah State | FG | TOTAL | over | 167.5 | -108 | 0.712 | 0.000 | 0.490 | 0.496 | 0.495 | -247 | +37.1% | -5.5% | -4.7% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 42 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | ALT_TOTAL | over | 150.5 | -125 | 0.761 | 0.000 | 0.483 | 0.520 | 0.516 | -319 | +37.0% | -13.0% | -7.2% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 43 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | ALT_TOTAL | over | 147.5 | -120 | 0.745 | 0.000 | 0.707 | 0.510 | 0.536 | -292 | +36.6% | +29.6% | -1.7% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 44 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | ALT_SPREAD | home | -8.5 | -104 | 0.692 | 0.000 | 0.615 | 0.473 | 0.473 | -225 | +35.8% | +20.6% | -7.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 45 | 11:31 AM CT | Yale @ Wright State | FG | SPREAD | home | -5.5 | -118 | 0.725 | 0.000 | 0.574 | 0.517 | 0.517 | -263 | +33.9% | +6.1% | -4.4% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 46 | 11:31 AM CT | Yale @ Wright State | FG | ALT_SPREAD | home | -6.5 | -109 | 0.697 | 0.000 | 0.540 | 0.485 | 0.485 | -230 | +33.6% | +3.5% | -7.0% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 47 | 6:00 PM CT | Northeastern @ Wisconsin | FG | ALT_SPREAD | away | 20.5 | -126 | 0.738 | 0.000 | 0.606 | 0.518 | 0.518 | -282 | +32.4% | +8.7% | -7.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 48 | 1:00 PM CT | Saint Peter's @ Columbia | 1H | SPREAD | home | -8.5 | -110 | 0.690 | 0.000 | — | 0.490 | 0.540 | -223 | +31.8% | — | +3.1% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 49 | 2:00 PM CT | Akron @ App State | FG | ML | home | — | +205 | 0.430 | 0.000 | 0.326 | 0.315 | 0.316 | +132 | +31.2% | -0.6% | -3.6% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 50 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | TOTAL | under | 158.5 | -115 | 0.699 | 0.000 | 0.605 | 0.511 | 0.523 | -233 | +30.7% | +13.1% | -2.3% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 51 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | SPREAD | away | 6.5 | -110 | 0.683 | 0.000 | 0.648 | 0.500 | 0.500 | -215 | +30.4% | +23.7% | -4.5% | FROZEN_EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 52 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | ALT_TOTAL | under | 157.5 | -110 | 0.678 | 0.000 | 0.582 | 0.490 | 0.501 | -211 | +29.5% | +11.0% | -4.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 53 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | SPREAD | away | 6.5 | -110 | 0.674 | 0.000 | 0.636 | 0.500 | 0.500 | -207 | +28.8% | +21.4% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 54 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | ALT_SPREAD | away | 5.5 | -104 | 0.654 | 0.000 | 0.616 | 0.473 | 0.473 | -189 | +28.3% | +20.9% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 55 | 1:30 PM CT | Texas A&M @ Xavier | 1H | TOTAL | under | 80.5 | -115 | 0.677 | 0.000 | — | 0.500 | 0.544 | -209 | +26.5% | — | +1.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 56 | 1:30 PM CT | Ole Miss @ Arizona | FG | SPREAD | away | 5.5 | -112 | 0.665 | 0.000 | 0.527 | 0.504 | 0.504 | -198 | +25.8% | -0.3% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 57 | 1:00 PM CT | LSU @ Arizona State | FG | TOTAL | over | 146.5 | -108 | 0.653 | 0.000 | 0.626 | 0.496 | 0.512 | -188 | +25.7% | +20.5% | -1.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 58 | 1:30 PM CT | Ole Miss @ Arizona | FG | ALT_SPREAD | away | 4.5 | -102 | 0.633 | 0.000 | 0.492 | 0.469 | 0.469 | -173 | +25.4% | -2.6% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 59 | 1:00 PM CT | Saint Peter's @ Columbia | 1H | TOTAL | under | 57.5 | -105 | 0.641 | 0.000 | — | 0.480 | 0.520 | -179 | +25.2% | — | +1.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 60 | 1:00 PM CT | Manhattan @ NJIT | FG | TOTAL | under | 141.5 | -115 | 0.668 | 0.000 | 0.488 | 0.511 | 0.508 | -202 | +25.0% | -8.7% | -5.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 61 | 2:30 PM CT | Arkansas State @ Florida International | FG | ML | home | — | -125 | 0.692 | 0.000 | 0.600 | 0.532 | 0.541 | -225 | +24.6% | +8.0% | -2.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 62 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | ALT_SPREAD | away | 7.5 | -131 | 0.706 | 0.000 | 0.668 | 0.527 | 0.527 | -240 | +24.5% | +17.8% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 63 | 4:00 PM CT | Portland State @ UC Riverside | FG | ALT_SPREAD | home | -3.5 | +102 | 0.616 | 0.000 | 0.430 | 0.460 | 0.460 | -160 | +24.4% | -13.2% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 64 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | TOTAL | over | 155.5 | -110 | 0.650 | 0.000 | 0.531 | 0.500 | 0.504 | -186 | +24.1% | +1.3% | -3.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 65 | 4:00 PM CT | Portland State @ UC Riverside | FG | SPREAD | home | -2.5 | -110 | 0.648 | 0.000 | 0.463 | 0.500 | 0.500 | -184 | +23.6% | -11.6% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 66 | 2:30 PM CT | Arkansas State @ Florida International | FG | SPREAD | home | -1.5 | -115 | 0.660 | 0.000 | 0.551 | 0.511 | 0.511 | -194 | +23.5% | +2.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 67 | 1:00 PM CT | Manhattan @ NJIT | FG | ALT_TOTAL | under | 140.5 | -110 | 0.646 | 0.000 | 0.463 | 0.490 | 0.487 | -183 | +23.4% | -11.5% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 68 | 2:00 PM CT | Jackson State @ Oklahoma State | FG | TOTAL | over | 160.5 | -112 | 0.649 | 0.000 | 0.517 | 0.504 | 0.506 | -185 | +22.9% | -2.2% | -4.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 69 | 4:00 PM CT | Holy Cross @ Dartmouth | FG | SPREAD | home | -11.5 | -108 | 0.636 | 0.000 | 0.618 | 0.496 | 0.496 | -175 | +22.5% | +19.1% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 70 | 2:00 PM CT | Jackson State @ Oklahoma State | FG | ALT_TOTAL | over | 161.5 | -105 | 0.627 | 0.000 | 0.492 | 0.480 | 0.481 | -168 | +22.4% | -4.0% | -6.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 71 | 2:30 PM CT | Arkansas State @ Florida International | FG | ALT_SPREAD | home | -2.5 | -105 | 0.627 | 0.000 | 0.517 | 0.475 | 0.475 | -168 | +22.3% | +1.0% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 72 | 4:00 PM CT | Southern @ Nebraska | FG | TOTAL | over | 149.5 | -105 | 0.626 | 0.000 | 0.421 | 0.489 | 0.481 | -167 | +22.1% | -17.8% | -6.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 73 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | SPREAD | home | -14.5 | -108 | 0.633 | 0.000 | 0.561 | 0.496 | 0.496 | -172 | +21.8% | +8.0% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 74 | 11:31 AM CT | Yale @ Wright State | 1H | SPREAD | home | -3.5 | -115 | 0.650 | 0.000 | — | 0.500 | 0.537 | -186 | +21.5% | — | +0.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 75 | 3:30 PM CT | South Carolina @ USC | FG | SPREAD | home | -10.5 | -112 | 0.642 | 0.000 | 0.545 | 0.504 | 0.504 | -179 | +21.5% | +3.1% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 76 | 1:00 PM CT | LSU @ Arizona State | FG | ALT_TOTAL | over | 145.5 | -125 | 0.673 | 0.000 | 0.649 | 0.520 | 0.537 | -206 | +21.1% | +16.8% | -3.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 77 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | ML | away | — | +145 | 0.493 | 0.000 | 0.302 | 0.391 | 0.379 | +103 | +20.9% | -26.0% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 78 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | ALT_TOTAL | over | 154.5 | -125 | 0.670 | 0.000 | 0.555 | 0.520 | 0.525 | -203 | +20.6% | -0.1% | -5.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 79 | 6:00 PM CT | St. Thomas @ UNC Wilmington | 1H | SPREAD | away | 4.5 | -120 | 0.657 | 0.000 | — | 0.510 | 0.547 | -191 | +20.4% | — | +0.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 80 | 3:30 PM CT | South Carolina @ USC | FG | ALT_SPREAD | home | -11.5 | -104 | 0.612 | 0.000 | 0.510 | 0.473 | 0.473 | -157 | +19.9% | -0.0% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 81 | 1:00 PM CT | Abilene Christian @ South Dakota State | 1H | SPREAD | home | -4.5 | -115 | 0.641 | 0.000 | — | 0.500 | 0.535 | -179 | +19.9% | — | +0.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 82 | 2:00 PM CT | Akron @ App State | FG | SPREAD | home | 6.5 | -112 | 0.632 | 0.000 | 0.546 | 0.504 | 0.504 | -172 | +19.6% | +3.3% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 83 | 9:30 PM CT | Pacific @ Jacksonville State | FG | ML | home | — | +185 | 0.419 | 0.000 | 0.320 | 0.336 | 0.334 | +138 | +19.5% | -8.8% | -4.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 84 | 4:00 PM CT | Portland State @ UC Riverside | FG | ML | home | — | -148 | 0.711 | 0.000 | 0.547 | 0.572 | 0.569 | -246 | +19.2% | -8.3% | -4.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 85 | 1:30 PM CT | Texas A&M @ Xavier | FG | TOTAL | under | 169.5 | -112 | 0.629 | 0.000 | 0.655 | 0.504 | 0.524 | -169 | +19.0% | +24.1% | -0.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 86 | 2:00 PM CT | Akron @ App State | FG | ALT_SPREAD | home | 5.5 | -104 | 0.600 | 0.000 | 0.511 | 0.474 | 0.474 | -150 | +17.7% | +0.3% | -7.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 87 | 11:31 AM CT | Yale @ Wright State | FG | ML | home | — | -258 | 0.848 | 0.000 | 0.747 | 0.691 | 0.698 | -559 | +17.7% | +3.6% | -3.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 88 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | ALT_SPREAD | home | -13.5 | -130 | 0.661 | 0.000 | 0.594 | 0.525 | 0.525 | -195 | +16.9% | +5.1% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 89 | 4:00 PM CT | Holy Cross @ Dartmouth | FG | ALT_SPREAD | home | -10.5 | -132 | 0.665 | 0.000 | 0.650 | 0.529 | 0.529 | -198 | +16.8% | +14.2% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 90 | 4:00 PM CT | Southern @ Nebraska | FG | ALT_TOTAL | over | 148.5 | -125 | 0.649 | 0.000 | 0.446 | 0.520 | 0.511 | -185 | +16.7% | -19.8% | -8.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 91 | 9:30 PM CT | Pacific @ Jacksonville State | 1H | ML | home | — | +165 | 0.423 | 0.043 | — | 0.356 | 0.361 | +126 | +16.3% | — | +0.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 92 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | SPREAD | away | 11.5 | -105 | 0.595 | 0.000 | 0.539 | 0.489 | 0.489 | -147 | +16.2% | +5.2% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 93 | 1:30 PM CT | Texas A&M @ Xavier | FG | ALT_TOTAL | under | 168.5 | -110 | 0.606 | 0.000 | 0.633 | 0.490 | 0.508 | -154 | +15.7% | +20.8% | -3.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 94 | 7:00 PM CT | Cal State Bakersfield @ Pepperdine | FG | SPREAD | home | -10.5 | -108 | 0.596 | 0.000 | 0.419 | 0.496 | 0.496 | -148 | +14.8% | -19.4% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 95 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | TOTAL | over | 142.5 | -105 | 0.588 | 0.000 | 0.482 | 0.489 | 0.488 | -143 | +14.8% | -5.8% | -4.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 96 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | ML | home | — | -340 | 0.882 | 0.000 | 0.841 | 0.741 | 0.755 | -747 | +14.1% | +8.8% | -2.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 97 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | SPREAD | home | -10.5 | -112 | 0.602 | 0.000 | 0.519 | 0.504 | 0.504 | -151 | +14.0% | -1.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 98 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | SPREAD | away | 3.5 | -110 | 0.597 | 0.000 | 0.411 | 0.500 | 0.500 | -148 | +13.9% | -21.6% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 99 | 2:00 PM CT | Jackson State @ Oklahoma State | FG | SPREAD | away | 34.5 | -112 | 0.599 | 0.000 | 0.607 | 0.504 | 0.504 | -150 | +13.4% | +14.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 100 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | ALT_SPREAD | away | 12.5 | -125 | 0.627 | 0.000 | 0.573 | 0.516 | 0.516 | -168 | +12.8% | +3.2% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 101 | 5:00 PM CT | UAlbany @ Syracuse | FG | TOTAL | over | 149.5 | -112 | 0.594 | 0.000 | 0.550 | 0.504 | 0.510 | -146 | +12.4% | +4.0% | -3.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 102 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | SPREAD | home | -15.5 | -108 | 0.583 | 0.000 | 0.489 | 0.496 | 0.496 | -140 | +12.3% | -5.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 103 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | ALT_TOTAL | over | 141.5 | -120 | 0.610 | 0.000 | 0.507 | 0.510 | 0.510 | -156 | +11.8% | -7.1% | -6.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 104 | 4:00 PM CT | Southern @ Nebraska | FG | SPREAD | away | 35.5 | -110 | 0.586 | 0.000 | 0.638 | 0.500 | 0.500 | -141 | +11.8% | +21.8% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 105 | 1:00 PM CT | Abilene Christian @ South Dakota State | 1H | TOTAL | over | 65.5 | -120 | 0.609 | 0.000 | — | 0.510 | 0.535 | -156 | +11.7% | — | -1.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 106 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | ALT_SPREAD | home | -11.5 | -104 | 0.568 | 0.000 | 0.486 | 0.473 | 0.473 | -132 | +11.5% | -4.7% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 107 | 1:30 PM CT | Texas A&M @ Xavier | FG | SPREAD | away | -5.5 | -105 | 0.570 | 0.000 | 0.585 | 0.489 | 0.489 | -133 | +11.3% | +14.2% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 108 | 2:30 PM CT | Arkansas State @ Florida International | FG | TOTAL | over | 173.5 | -108 | 0.578 | 0.000 | 0.326 | 0.496 | 0.474 | -137 | +11.3% | -37.2% | -8.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 109 | 2:00 PM CT | Jackson State @ Oklahoma State | FG | ALT_SPREAD | away | 35.5 | -130 | 0.629 | 0.000 | 0.640 | 0.525 | 0.525 | -170 | +11.3% | +13.2% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 110 | 1:00 PM CT | Manhattan @ NJIT | FG | ALT_SPREAD | home | -2.5 | +102 | 0.550 | 0.000 | 0.544 | 0.460 | 0.460 | -122 | +11.0% | +10.0% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 111 | 5:00 PM CT | UAlbany @ Syracuse | FG | ALT_TOTAL | over | 150.5 | -105 | 0.568 | 0.000 | 0.525 | 0.480 | 0.485 | -131 | +10.9% | +2.5% | -5.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 112 | 11:31 AM CT | Yale @ Wright State | 1H | ML | home | — | -238 | 0.757 | 0.031 | — | 0.663 | 0.671 | -357 | +10.6% | — | -1.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 113 | 1:00 PM CT | Manhattan @ NJIT | FG | SPREAD | home | -1.5 | -112 | 0.584 | 0.000 | 0.579 | 0.504 | 0.504 | -141 | +10.6% | +9.6% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 114 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | ML | home | — | +124 | 0.490 | 0.000 | 0.546 | 0.428 | 0.443 | +104 | +9.7% | +22.4% | -0.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 115 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | TOTAL | over | 145.5 | -108 | 0.570 | 0.000 | 0.593 | 0.496 | 0.508 | -132 | +9.7% | +14.2% | -2.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 116 | 9:30 PM CT | Pacific @ Jacksonville State | FG | SPREAD | home | 5.5 | -115 | 0.587 | 0.000 | 0.498 | 0.511 | 0.511 | -142 | +9.7% | -6.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 117 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | ML | away | — | +105 | 0.535 | 0.000 | 0.406 | 0.468 | 0.460 | -115 | +9.6% | -16.7% | -5.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 118 | 1:00 PM CT | Manhattan @ NJIT | FG | ML | home | — | -130 | 0.619 | 0.000 | 0.629 | 0.543 | 0.554 | -162 | +9.5% | +11.3% | -2.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 119 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | ALT_SPREAD | away | 4.5 | -135 | 0.628 | 0.000 | 0.444 | 0.533 | 0.533 | -169 | +9.4% | -22.7% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 120 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | FG | SPREAD | away | -3.5 | -118 | 0.592 | 0.000 | 0.423 | 0.517 | 0.517 | -145 | +9.3% | -21.9% | -4.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 121 | 4:00 PM CT | Southern @ Nebraska | FG | ALT_SPREAD | away | 36.5 | -130 | 0.616 | 0.000 | 0.670 | 0.526 | 0.526 | -161 | +9.0% | +18.6% | -7.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 122 | 4:00 PM CT | Portland State @ UC Riverside | FG | TOTAL | under | 152.5 | -112 | 0.575 | 0.000 | 0.679 | 0.504 | 0.527 | -135 | +8.9% | +28.6% | -0.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 123 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | ALT_SPREAD | home | -14.5 | -131 | 0.615 | 0.000 | 0.522 | 0.527 | 0.527 | -160 | +8.5% | -7.9% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 124 | 2:30 PM CT | Arkansas State @ Florida International | FG | ALT_TOTAL | over | 172.5 | -125 | 0.603 | 0.000 | 0.348 | 0.520 | 0.498 | -152 | +8.5% | -37.4% | -10.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 125 | 1:00 PM CT | Abilene Christian @ South Dakota State | 1H | ML | home | — | -280 | 0.778 | 0.029 | — | 0.696 | 0.701 | -402 | +8.4% | — | -2.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 126 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | FG | ML | away | — | -175 | 0.690 | 0.000 | 0.540 | 0.609 | 0.601 | -222 | +8.4% | -15.2% | -5.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 127 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | SPREAD | away | 1.5 | -110 | 0.568 | 0.000 | 0.457 | 0.500 | 0.500 | -131 | +8.3% | -12.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 128 | 4:00 PM CT | Memphis @ Penn State | FG | SPREAD | away | -3.5 | -115 | 0.578 | 0.000 | 0.502 | 0.511 | 0.511 | -137 | +8.0% | -6.1% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 129 | 4:00 PM CT | Portland State @ UC Riverside | FG | ALT_TOTAL | under | 151.5 | -105 | 0.553 | 0.000 | 0.657 | 0.480 | 0.503 | -124 | +7.9% | +28.3% | -1.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 130 | 5:00 PM CT | UAlbany @ Syracuse | FG | SPREAD | home | -26.5 | -110 | 0.564 | 0.000 | 0.384 | 0.500 | 0.500 | -129 | +7.6% | -26.6% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 131 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | SPREAD | home | 2.5 | -108 | 0.558 | 0.000 | 0.628 | 0.496 | 0.496 | -126 | +7.5% | +21.0% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 132 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | SPREAD | home | 3.5 | -112 | 0.567 | 0.000 | 0.614 | 0.504 | 0.504 | -131 | +7.4% | +16.1% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 133 | 1:30 PM CT | Texas A&M @ Xavier | FG | ALT_SPREAD | away | -4.5 | -128 | 0.603 | 0.000 | 0.619 | 0.522 | 0.522 | -152 | +7.3% | +10.2% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 134 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | ML | home | — | +130 | 0.466 | 0.000 | 0.493 | 0.417 | 0.426 | +115 | +7.1% | +13.4% | -1.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 135 | 4:00 PM CT | Memphis @ Penn State | FG | ML | away | — | -175 | 0.681 | 0.000 | 0.622 | 0.609 | 0.611 | -213 | +7.0% | -2.3% | -4.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 136 | 9:30 PM CT | Pacific @ Jacksonville State | 1H | SPREAD | home | 3.5 | -125 | 0.594 | 0.000 | — | 0.520 | 0.539 | -146 | +6.9% | — | -3.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 137 | 12:00 PM CT | Southern Utah @ Long Beach State | 1H | ML | away | — | +105 | 0.502 | 0.039 | — | 0.459 | 0.457 | -110 | +6.9% | — | -2.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 138 | 6:00 PM CT | Northeastern @ Wisconsin | FG | TOTAL | over | 156.5 | -110 | 0.559 | 0.000 | 0.571 | 0.500 | 0.509 | -127 | +6.8% | +8.9% | -2.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 139 | 1:00 PM CT | Saint Peter's @ Columbia | 1H | ML | home | — | -660 | 0.914 | 0.016 | — | 0.819 | 0.833 | -1296 | +6.8% | — | -2.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 140 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | ALT_TOTAL | over | 144.5 | -125 | 0.592 | 0.000 | 0.617 | 0.520 | 0.533 | -145 | +6.6% | +11.0% | -4.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 141 | 1:30 PM CT | Ole Miss @ Arizona | FG | TOTAL | under | 154.5 | -110 | 0.554 | 0.000 | 0.613 | 0.500 | 0.514 | -124 | +5.8% | +17.0% | -1.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 142 | 1:30 PM CT | Texas A&M @ Xavier | FG | ML | away | — | -218 | 0.724 | 0.000 | 0.756 | 0.657 | 0.671 | -262 | +5.5% | +10.2% | -2.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 143 | 4:00 PM CT | Memphis @ Penn State | FG | ALT_SPREAD | away | -4.5 | -107 | 0.543 | 0.000 | 0.467 | 0.480 | 0.480 | -119 | +5.0% | -9.6% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 144 | 7:00 PM CT | Omaha @ UC Davis | FG | ML | away | — | +230 | 0.318 | 0.000 | 0.275 | 0.290 | 0.289 | +214 | +5.0% | -9.1% | -4.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 145 | 6:00 PM CT | UConn @ Duke | FG | ALT_TOTAL | over | 146.5 | -110 | 0.548 | 0.000 | 0.439 | 0.490 | 0.484 | -121 | +4.7% | -16.1% | -7.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 146 | 6:30 PM CT | Wake Forest @ Mississippi State | FG | ML | home | — | -180 | 0.672 | 0.000 | 0.545 | 0.616 | 0.608 | -205 | +4.6% | -15.2% | -5.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 147 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | SPREAD | home | -21.5 | -108 | 0.542 | 0.000 | 0.392 | 0.496 | 0.496 | -119 | +4.5% | -24.4% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 148 | 6:00 PM CT | Northeastern @ Wisconsin | FG | ALT_TOTAL | over | 157.5 | -105 | 0.535 | 0.000 | 0.546 | 0.480 | 0.488 | -115 | +4.5% | +6.6% | -4.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 149 | 6:30 PM CT | Wake Forest @ Mississippi State | FG | SPREAD | home | -4.5 | -108 | 0.541 | 0.000 | 0.390 | 0.496 | 0.496 | -118 | +4.2% | -24.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 150 | 12:30 PM CT | Tulane @ Davidson | 1H | ML | away | — | +220 | 0.313 | 0.038 | — | 0.294 | 0.291 | +207 | +4.1% | — | -3.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 151 | 1:30 PM CT | Ole Miss @ Arizona | FG | ALT_TOTAL | under | 153.5 | -105 | 0.532 | 0.000 | 0.589 | 0.480 | 0.493 | -114 | +4.0% | +15.0% | -3.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 152 | 1:00 PM CT | Saint Peter's @ Columbia | FG | ML | home | — | -1450 | 0.971 | 0.000 | 0.951 | 0.899 | 0.907 | -3390 | +3.8% | +1.6% | -3.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 153 | 6:00 PM CT | SMU @ Utah State | 1H | ML | away | — | +150 | 0.400 | 0.037 | — | 0.377 | 0.372 | +141 | +3.8% | — | -3.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 154 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | ALT_SPREAD | home | 2.5 | -106 | 0.534 | 0.000 | 0.580 | 0.477 | 0.477 | -115 | +3.7% | +12.7% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 155 | 12:30 PM CT | Tulane @ Davidson | FG | ML | away | — | +275 | 0.277 | 0.000 | 0.202 | 0.256 | 0.249 | +262 | +3.7% | -24.1% | -6.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 156 | 12:00 PM CT | Southern Utah @ Long Beach State | 1H | SPREAD | away | 0.5 | -110 | 0.541 | 0.000 | — | 0.490 | 0.503 | -118 | +3.3% | — | -4.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 157 | 5:00 PM CT | UAlbany @ Syracuse | FG | ALT_SPREAD | home | -27.5 | -106 | 0.531 | 0.000 | 0.352 | 0.477 | 0.477 | -113 | +3.2% | -31.7% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 158 | 3:30 PM CT | South Carolina @ USC | FG | TOTAL | over | 147.5 | -112 | 0.544 | 0.000 | 0.552 | 0.504 | 0.510 | -119 | +3.0% | +4.5% | -3.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 159 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | ALT_SPREAD | home | 3.5 | -135 | 0.592 | 0.000 | 0.660 | 0.533 | 0.533 | -145 | +3.0% | +14.8% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 160 | 1:30 PM CT | Texas A&M @ Xavier | 1H | SPREAD | away | -2.5 | -120 | 0.561 | 0.000 | — | 0.510 | 0.523 | -128 | +2.9% | — | -4.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 161 | 12:30 PM CT | Tulane @ Davidson | FG | SPREAD | away | 8.5 | -108 | 0.534 | 0.000 | 0.462 | 0.496 | 0.496 | -115 | +2.8% | -11.1% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 162 | 6:00 PM CT | UConn @ Duke | FG | TOTAL | over | 147.5 | -105 | 0.525 | 0.000 | 0.415 | 0.489 | 0.480 | -111 | +2.6% | -19.0% | -6.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 163 | 4:30 PM CT | BYU @ Providence | FG | SPREAD | away | -3.5 | -108 | 0.532 | 0.000 | 0.605 | 0.496 | 0.496 | -114 | +2.4% | +16.6% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 164 | 3:00 PM CT | Princeton @ Liberty | FG | TOTAL | over | 135.5 | -108 | 0.531 | 0.000 | 0.688 | 0.496 | 0.521 | -113 | +2.3% | +32.4% | +0.3% | EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 165 | 8:00 PM CT | Eastern Washington @ Loyola Marymount | FG | SPREAD | home | -7.5 | -108 | 0.530 | 0.000 | 0.499 | 0.496 | 0.496 | -113 | +2.1% | -3.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 166 | 3:30 PM CT | South Carolina @ USC | FG | ALT_TOTAL | over | 148.5 | -105 | 0.522 | 0.000 | 0.528 | 0.480 | 0.486 | -109 | +2.0% | +3.0% | -5.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 167 | 4:30 PM CT | BYU @ Providence | FG | ML | away | — | -162 | 0.630 | 0.000 | 0.716 | 0.593 | 0.610 | -171 | +1.9% | +15.8% | -1.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 168 | 11:31 AM CT | Yale @ Wright State | FG | ALT_TOTAL | under | 138.5 | -115 | 0.544 | 0.000 | 0.374 | 0.500 | 0.484 | -120 | +1.8% | -30.2% | -9.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 169 | 6:00 PM CT | SMU @ Utah State | 1H | TOTAL | over | 79.5 | -115 | 0.543 | 0.000 | — | 0.500 | 0.511 | -119 | +1.6% | — | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 170 | 7:00 PM CT | Omaha @ UC Davis | FG | SPREAD | away | 6.5 | -105 | 0.520 | 0.000 | 0.480 | 0.489 | 0.489 | -108 | +1.5% | -6.3% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 171 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | ALT_SPREAD | home | -20.5 | -131 | 0.575 | 0.000 | 0.426 | 0.527 | 0.527 | -136 | +1.5% | -24.8% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 172 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | ML | home | — | -575 | 0.863 | 0.000 | 0.823 | 0.817 | 0.818 | -628 | +1.3% | -3.4% | -4.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 173 | 7:00 PM CT | Cal State Bakersfield @ Pepperdine | FG | ML | home | — | -575 | 0.862 | 0.000 | 0.751 | 0.817 | 0.810 | -625 | +1.2% | -11.9% | -4.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 174 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | ALT_SPREAD | away | 2.5 | -147 | 0.602 | 0.000 | 0.492 | 0.553 | 0.553 | -151 | +1.2% | -17.3% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 175 | 6:00 PM CT | Norfolk State @ NC State | FG | SPREAD | home | -28.5 | -108 | 0.524 | 0.000 | 0.544 | 0.496 | 0.496 | -110 | +1.0% | +4.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 176 | 3:30 PM CT | South Carolina @ USC | FG | ML | home | — | -700 | 0.883 | 0.000 | 0.846 | 0.840 | 0.841 | -754 | +0.9% | -3.3% | -3.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 177 | 4:00 PM CT | Holy Cross @ Dartmouth | FG | ML | home | — | -800 | 0.896 | 0.000 | 0.894 | 0.852 | 0.858 | -866 | +0.9% | +0.6% | -3.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 178 | 4:00 PM CT | Alcorn State @ Texas State | FG | ML | home | — | -8000 | 0.995 | 0.000 | 0.992 | 0.958 | 0.965 | -18592 | +0.7% | +0.4% | -2.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 179 | 11:31 AM CT | Yale @ Wright State | FG | TOTAL | under | 137.5 | -108 | 0.523 | 0.000 | 0.350 | 0.496 | 0.477 | -110 | +0.7% | -32.5% | -8.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 180 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | ML | home | — | -1450 | 0.938 | 0.000 | 0.912 | 0.899 | 0.901 | -1505 | +0.2% | -2.6% | -3.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 181 | 4:30 PM CT | BYU @ Providence | FG | ALT_SPREAD | away | -2.5 | -130 | 0.566 | 0.000 | 0.638 | 0.525 | 0.525 | -130 | +0.1% | +12.9% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 182 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | 1H | SPREAD | away | -2.5 | -115 | 0.534 | 0.000 | — | 0.500 | 0.509 | -115 | -0.1% | — | -4.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 183 | 1:30 PM CT | Texas A&M @ Xavier | 1H | ML | away | — | -195 | 0.636 | 0.036 | — | 0.623 | 0.610 | -194 | -0.1% | — | -4.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 184 | 6:00 PM CT | UConn @ Duke | FG | SPREAD | away | -2.5 | -105 | 0.511 | 0.000 | 0.403 | 0.489 | 0.489 | -104 | -0.2% | -21.4% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 185 | 12:30 PM CT | Tulane @ Davidson | FG | ALT_SPREAD | away | 9.5 | -131 | 0.565 | 0.000 | 0.497 | 0.527 | 0.527 | -130 | -0.3% | -12.4% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 186 | 3:00 PM CT | Princeton @ Liberty | FG | ALT_TOTAL | over | 134.5 | -125 | 0.553 | 0.000 | 0.709 | 0.520 | 0.545 | -124 | -0.5% | +27.6% | -1.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 187 | 10:59 PM CT | Incarnate Word @ Hawai'i | FG | SPREAD | away | 16.5 | -105 | 0.509 | 0.000 | 0.518 | 0.489 | 0.489 | -104 | -0.6% | +1.0% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 188 | 6:00 PM CT | SMU @ Utah State | FG | ML | away | — | +160 | 0.382 | 0.000 | 0.308 | 0.369 | 0.361 | +162 | -0.7% | -19.9% | -6.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 189 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | ML | home | — | -4000 | 0.969 | 0.000 | 0.942 | 0.943 | 0.943 | -3085 | -0.7% | -3.4% | -3.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 190 | 6:00 PM CT | UConn @ Duke | FG | ML | away | — | -142 | 0.582 | 0.000 | 0.489 | 0.563 | 0.554 | -139 | -0.7% | -16.7% | -5.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 191 | 6:00 PM CT | Norfolk State @ NC State | FG | ML | home | — | -50000 | 0.990 | 0.000 | 0.993 | 0.976 | 0.980 | -9704 | -0.8% | -0.5% | -1.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 192 | 5:00 PM CT | UAlbany @ Syracuse | FG | ML | home | — | -50000 | 0.989 | 0.000 | 0.975 | 0.976 | 0.976 | -9032 | -0.9% | -2.3% | -2.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 193 | 11:31 AM CT | Yale @ Wright State | 1H | TOTAL | over | 63.5 | -120 | 0.540 | 0.000 | — | 0.510 | 0.518 | -117 | -1.1% | — | -5.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 194 | 6:30 PM CT | Wake Forest @ Mississippi State | 1H | SPREAD | home | -2.5 | -115 | 0.528 | 0.000 | — | 0.500 | 0.507 | -112 | -1.4% | — | -5.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 195 | 4:00 PM CT | Memphis @ Penn State | 1H | TOTAL | over | 77.5 | -115 | 0.527 | 0.000 | — | 0.500 | 0.507 | -111 | -1.5% | — | -5.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 196 | 6:00 PM CT | SMU @ Utah State | FG | SPREAD | away | 4.5 | -110 | 0.516 | 0.000 | 0.456 | 0.500 | 0.500 | -106 | -1.6% | -12.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 197 | 3:00 PM CT | Princeton @ Liberty | FG | SPREAD | home | -3.5 | -108 | 0.511 | 0.000 | 0.533 | 0.496 | 0.496 | -104 | -1.7% | +2.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 198 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | ML | home | — | -1650 | 0.927 | 0.000 | 0.896 | 0.908 | 0.907 | -1265 | -1.7% | -5.0% | -3.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 199 | 8:00 PM CT | Eastern Washington @ Loyola Marymount | FG | ML | home | — | -325 | 0.751 | 0.000 | 0.742 | 0.734 | 0.735 | -302 | -1.7% | -2.9% | -3.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 200 | 6:30 PM CT | Wake Forest @ Mississippi State | 1H | TOTAL | over | 70.5 | -110 | 0.514 | 0.000 | — | 0.490 | 0.496 | -106 | -1.9% | — | -5.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 201 | 6:00 PM CT | SMU @ Utah State | 1H | SPREAD | away | 2.5 | -110 | 0.513 | 0.000 | — | 0.490 | 0.496 | -105 | -2.1% | — | -5.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 202 | 4:30 PM CT | BYU @ Providence | FG | TOTAL | under | 154.5 | -110 | 0.513 | 0.000 | 0.450 | 0.500 | 0.494 | -105 | -2.1% | -14.1% | -5.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 203 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | 1H | ML | away | — | -188 | 0.613 | 0.038 | — | 0.615 | 0.597 | -175 | -2.3% | — | -4.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 204 | 3:00 PM CT | Princeton @ Liberty | FG | ML | home | — | -170 | 0.614 | 0.000 | 0.651 | 0.604 | 0.610 | -159 | -2.5% | +3.4% | -3.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 205 | 12:30 PM CT | Tulane @ Davidson | FG | TOTAL | under | 137.5 | -115 | 0.521 | 0.000 | 0.449 | 0.511 | 0.503 | -109 | -2.6% | -16.0% | -5.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 206 | 4:00 PM CT | Memphis @ Penn State | 1H | SPREAD | away | -2.5 | -115 | 0.519 | 0.000 | — | 0.500 | 0.505 | -108 | -2.9% | — | -5.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 207 | 12:30 PM CT | Tulane @ Davidson | FG | ALT_TOTAL | under | 136.5 | -105 | 0.497 | 0.000 | 0.425 | 0.480 | 0.473 | +101 | -2.9% | -17.1% | -7.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 208 | 6:30 PM CT | Wake Forest @ Mississippi State | 1H | ML | home | — | -188 | 0.607 | 0.038 | — | 0.615 | 0.596 | -171 | -3.2% | — | -4.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 209 | 3:00 PM CT | Princeton @ Liberty | FG | ALT_SPREAD | home | -2.5 | -131 | 0.547 | 0.000 | 0.568 | 0.527 | 0.527 | -121 | -3.5% | +0.1% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 210 | 10:59 PM CT | Incarnate Word @ Hawai'i | FG | ML | home | — | -1650 | 0.910 | 0.000 | 0.907 | 0.908 | 0.908 | -1007 | -3.5% | -3.8% | -3.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 211 | 6:00 PM CT | UConn @ Duke | FG | ALT_SPREAD | away | -1.5 | -131 | 0.547 | 0.000 | 0.437 | 0.527 | 0.527 | -121 | -3.5% | -23.0% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 212 | 12:30 PM CT | Tulane @ Davidson | 1H | SPREAD | away | 4.5 | -115 | 0.516 | 0.000 | — | 0.500 | 0.504 | -107 | -3.6% | — | -5.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 213 | 6:00 PM CT | UConn @ Duke | 1H | ML | home | — | +114 | 0.429 | 0.041 | — | 0.441 | 0.425 | +124 | -4.1% | — | -5.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 214 | 4:30 PM CT | BYU @ Providence | FG | ALT_TOTAL | under | 153.5 | -105 | 0.491 | 0.000 | 0.425 | 0.480 | 0.473 | +104 | -4.2% | -16.9% | -7.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 215 | 4:00 PM CT | Memphis @ Penn State | 1H | ML | away | — | -188 | 0.595 | 0.037 | — | 0.615 | 0.593 | -162 | -5.1% | — | -5.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 216 | 10:59 PM CT | Incarnate Word @ Hawai'i | FG | ML | away | — | +950 | 0.090 | 0.000 | 0.093 | 0.092 | 0.092 | +1007 | -5.1% | -2.5% | -3.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 217 | 6:00 PM CT | UConn @ Duke | 1H | TOTAL | under | 69.5 | -115 | 0.507 | 0.000 | — | 0.500 | 0.502 | -103 | -5.3% | — | -6.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 218 | 9:30 PM CT | Pacific @ Jacksonville State | 1H | TOTAL | over | 62.5 | -105 | 0.484 | 0.000 | — | 0.480 | 0.481 | +107 | -5.5% | — | -6.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 219 | 6:00 PM CT | SMU @ Utah State | FG | ALT_SPREAD | away | 3.5 | -104 | 0.480 | 0.000 | 0.422 | 0.473 | 0.473 | +108 | -5.8% | -17.3% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 220 | 6:00 PM CT | SMU @ Utah State | FG | ML | home | — | -192 | 0.618 | 0.000 | 0.692 | 0.631 | 0.639 | -162 | -6.0% | +5.2% | -2.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 221 | 12:30 PM CT | Tulane @ Davidson | 1H | TOTAL | under | 64.5 | -115 | 0.502 | 0.000 | — | 0.500 | 0.501 | -101 | -6.1% | — | -6.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 222 | 4:00 PM CT | Memphis @ Penn State | 1H | ML | home | — | +145 | 0.368 | 0.037 | — | 0.385 | 0.370 | +162 | -6.2% | — | -5.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 223 | 6:00 PM CT | UConn @ Duke | 1H | ML | away | — | -145 | 0.530 | 0.041 | — | 0.559 | 0.535 | -124 | -6.3% | — | -5.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 224 | 6:00 PM CT | UConn @ Duke | 1H | SPREAD | home | 1.5 | -120 | 0.511 | 0.000 | — | 0.510 | 0.510 | -104 | -6.4% | — | -6.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 225 | 12:30 PM CT | Tulane @ Davidson | FG | TOTAL | over | 137.5 | -105 | 0.479 | 0.000 | 0.551 | 0.489 | 0.497 | +109 | -6.4% | +7.6% | -3.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 226 | 3:00 PM CT | Princeton @ Liberty | FG | ML | away | — | +142 | 0.386 | 0.000 | 0.349 | 0.396 | 0.390 | +159 | -6.5% | -15.6% | -5.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 227 | 6:00 PM CT | UConn @ Duke | 1H | SPREAD | away | -1.5 | -110 | 0.489 | 0.000 | — | 0.490 | 0.490 | +104 | -6.6% | — | -6.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 228 | 12:30 PM CT | Tulane @ Davidson | FG | ML | home | — | -345 | 0.723 | 0.000 | 0.798 | 0.744 | 0.751 | -262 | -6.7% | +2.9% | -3.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 229 | 12:30 PM CT | Tulane @ Davidson | 1H | TOTAL | over | 64.5 | -115 | 0.498 | 0.000 | — | 0.500 | 0.499 | +101 | -6.9% | — | -6.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 230 | 4:30 PM CT | BYU @ Providence | FG | TOTAL | over | 154.5 | -110 | 0.487 | 0.000 | 0.550 | 0.500 | 0.506 | +105 | -7.0% | +5.0% | -3.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 231 | 9:30 PM CT | Pacific @ Jacksonville State | 1H | TOTAL | under | 62.5 | -125 | 0.516 | 0.000 | — | 0.520 | 0.519 | -107 | -7.1% | — | -6.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 232 | 3:00 PM CT | Princeton @ Liberty | FG | SPREAD | away | 3.5 | -112 | 0.489 | 0.000 | 0.467 | 0.504 | 0.504 | +104 | -7.4% | -11.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 233 | 6:00 PM CT | SMU @ Utah State | FG | SPREAD | home | -4.5 | -110 | 0.484 | 0.000 | 0.544 | 0.500 | 0.500 | +106 | -7.5% | +3.8% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 234 | 6:00 PM CT | UConn @ Duke | 1H | TOTAL | over | 69.5 | -115 | 0.493 | 0.000 | — | 0.500 | 0.498 | +103 | -7.8% | — | -6.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 235 | 7:00 PM CT | Omaha @ UC Davis | FG | ML | home | — | -285 | 0.682 | 0.000 | 0.725 | 0.710 | 0.711 | -214 | -7.9% | -2.1% | -3.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 236 | 6:00 PM CT | UConn @ Duke | FG | ML | home | — | +120 | 0.418 | 0.000 | 0.511 | 0.437 | 0.446 | +139 | -8.1% | +12.5% | -1.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 237 | 10:59 PM CT | Incarnate Word @ Hawai'i | FG | SPREAD | home | -16.5 | -115 | 0.491 | 0.000 | 0.482 | 0.511 | 0.511 | +104 | -8.2% | -9.8% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 238 | 4:30 PM CT | BYU @ Providence | FG | ALT_TOTAL | over | 153.5 | -125 | 0.509 | 0.000 | 0.575 | 0.520 | 0.527 | -104 | -8.3% | +3.4% | -5.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 239 | 6:00 PM CT | SMU @ Utah State | FG | ALT_SPREAD | home | -3.5 | -131 | 0.520 | 0.000 | 0.578 | 0.527 | 0.527 | -108 | -8.3% | +2.0% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 240 | 6:00 PM CT | UConn @ Duke | FG | SPREAD | home | 2.5 | -115 | 0.489 | 0.000 | 0.597 | 0.511 | 0.511 | +104 | -8.6% | +11.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 241 | 6:30 PM CT | Wake Forest @ Mississippi State | 1H | ML | away | — | +145 | 0.355 | 0.038 | — | 0.385 | 0.366 | +171 | -9.3% | — | -6.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 242 | 12:30 PM CT | Tulane @ Davidson | 1H | SPREAD | home | -4.5 | -115 | 0.484 | 0.000 | — | 0.500 | 0.496 | +107 | -9.5% | — | -7.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 243 | 12:30 PM CT | Tulane @ Davidson | FG | ALT_TOTAL | over | 136.5 | -125 | 0.503 | 0.000 | 0.575 | 0.520 | 0.527 | -101 | -9.5% | +3.6% | -5.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 244 | 12:30 PM CT | Tulane @ Davidson | 1H | ML | home | — | -298 | 0.648 | 0.038 | — | 0.706 | 0.671 | -207 | -9.6% | — | -6.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 245 | 11:31 AM CT | Yale @ Wright State | FG | TOTAL | over | 137.5 | -112 | 0.477 | 0.000 | 0.650 | 0.504 | 0.523 | +110 | -9.7% | +22.9% | -1.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 246 | 6:00 PM CT | Norfolk State @ NC State | FG | SPREAD | away | 28.5 | -112 | 0.476 | 0.000 | 0.456 | 0.504 | 0.504 | +110 | -9.9% | -13.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 247 | 4:00 PM CT | Memphis @ Penn State | 1H | SPREAD | home | 2.5 | -115 | 0.481 | 0.000 | — | 0.500 | 0.495 | +108 | -10.2% | — | -7.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 248 | 7:00 PM CT | Omaha @ UC Davis | FG | SPREAD | home | -6.5 | -115 | 0.480 | 0.000 | 0.520 | 0.511 | 0.511 | +108 | -10.3% | -2.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 249 | 8:00 PM CT | Eastern Washington @ Loyola Marymount | FG | ML | away | — | +260 | 0.249 | 0.000 | 0.258 | 0.266 | 0.265 | +302 | -10.5% | -7.2% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 250 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | 1H | ML | home | — | +145 | 0.349 | 0.038 | — | 0.385 | 0.365 | +175 | -10.6% | — | -6.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 251 | 6:00 PM CT | SMU @ Utah State | 1H | SPREAD | home | -2.5 | -120 | 0.487 | 0.000 | — | 0.510 | 0.504 | +105 | -10.7% | — | -7.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 252 | 6:30 PM CT | Wake Forest @ Mississippi State | 1H | TOTAL | under | 70.5 | -120 | 0.486 | 0.000 | — | 0.510 | 0.504 | +106 | -10.9% | — | -7.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 253 | 8:00 PM CT | Eastern Washington @ Loyola Marymount | FG | SPREAD | away | 7.5 | -112 | 0.470 | 0.000 | 0.501 | 0.504 | 0.504 | +113 | -11.1% | -5.2% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 254 | 6:00 PM CT | SMU @ Utah State | 1H | ML | home | — | -195 | 0.563 | 0.037 | — | 0.623 | 0.591 | -141 | -11.2% | — | -6.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 255 | 6:00 PM CT | UConn @ Duke | FG | ALT_SPREAD | home | 1.5 | -104 | 0.453 | 0.000 | 0.563 | 0.473 | 0.473 | +121 | -11.2% | +10.5% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 256 | 3:00 PM CT | Princeton @ Liberty | FG | ALT_SPREAD | away | 2.5 | -104 | 0.453 | 0.000 | 0.432 | 0.473 | 0.473 | +121 | -11.2% | -15.2% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 257 | 6:00 PM CT | UConn @ Duke | FG | TOTAL | under | 147.5 | -115 | 0.475 | 0.000 | 0.585 | 0.511 | 0.520 | +111 | -11.3% | +9.4% | -2.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 258 | 3:00 PM CT | Princeton @ Liberty | FG | TOTAL | under | 135.5 | -112 | 0.469 | 0.000 | 0.312 | 0.504 | 0.479 | +113 | -11.3% | -40.9% | -9.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 259 | 4:30 PM CT | BYU @ Providence | FG | SPREAD | home | 3.5 | -112 | 0.468 | 0.000 | 0.395 | 0.504 | 0.504 | +114 | -11.4% | -25.3% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 260 | 4:00 PM CT | Memphis @ Penn State | 1H | TOTAL | under | 77.5 | -115 | 0.473 | 0.000 | — | 0.500 | 0.493 | +111 | -11.6% | — | -7.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 261 | 6:30 PM CT | Wake Forest @ Mississippi State | 1H | SPREAD | away | 2.5 | -115 | 0.472 | 0.000 | — | 0.500 | 0.493 | +112 | -11.7% | — | -7.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 262 | 12:30 PM CT | Tulane @ Davidson | FG | SPREAD | home | -8.5 | -112 | 0.466 | 0.000 | 0.538 | 0.504 | 0.504 | +115 | -11.8% | +1.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 263 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | ML | away | — | -155 | 0.534 | 0.000 | 0.507 | 0.583 | 0.574 | -115 | -12.1% | -16.6% | -5.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 264 | 11:31 AM CT | Yale @ Wright State | 1H | TOTAL | under | 63.5 | -110 | 0.460 | 0.000 | — | 0.490 | 0.482 | +117 | -12.1% | — | -7.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 265 | 3:30 PM CT | South Carolina @ USC | FG | TOTAL | under | 147.5 | -108 | 0.456 | 0.000 | 0.448 | 0.496 | 0.490 | +119 | -12.2% | -13.8% | -5.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 266 | 3:00 PM CT | Princeton @ Liberty | FG | ALT_TOTAL | under | 134.5 | -105 | 0.447 | 0.000 | 0.291 | 0.480 | 0.455 | +124 | -12.7% | -43.2% | -11.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 267 | 4:30 PM CT | BYU @ Providence | FG | ML | home | — | +136 | 0.370 | 0.000 | 0.284 | 0.407 | 0.390 | +171 | -12.8% | -33.0% | -7.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 268 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | 1H | SPREAD | home | 2.5 | -115 | 0.466 | 0.000 | — | 0.500 | 0.491 | +115 | -12.9% | — | -8.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 269 | 6:30 PM CT | Wake Forest @ Mississippi State | FG | SPREAD | away | 4.5 | -112 | 0.459 | 0.000 | 0.610 | 0.504 | 0.504 | +118 | -13.1% | +15.4% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 270 | 6:00 PM CT | Northeastern @ Wisconsin | FG | ML | home | — | -3600 | 0.844 | 0.000 | 0.933 | 0.940 | 0.939 | -540 | -13.3% | -4.2% | -3.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 271 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | SPREAD | away | 21.5 | -112 | 0.458 | 0.000 | 0.608 | 0.504 | 0.504 | +119 | -13.4% | +15.0% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 272 | 3:30 PM CT | South Carolina @ USC | FG | ALT_TOTAL | under | 148.5 | -125 | 0.478 | 0.000 | 0.472 | 0.520 | 0.514 | +109 | -14.0% | -15.0% | -7.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 273 | 1:30 PM CT | Texas A&M @ Xavier | 1H | ML | home | — | +150 | 0.328 | 0.036 | — | 0.377 | 0.354 | +194 | -14.5% | — | -7.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 274 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | ML | away | — | -148 | 0.510 | 0.000 | 0.454 | 0.572 | 0.557 | -104 | -14.5% | -24.0% | -6.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 275 | 6:00 PM CT | SMU @ Utah State | 1H | TOTAL | under | 79.5 | -115 | 0.457 | 0.000 | — | 0.500 | 0.489 | +119 | -14.6% | — | -8.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 276 | 12:30 PM CT | Tulane @ Davidson | FG | ALT_SPREAD | home | -9.5 | -104 | 0.435 | 0.000 | 0.503 | 0.473 | 0.473 | +130 | -14.7% | -1.2% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 277 | 11:31 AM CT | Yale @ Wright State | FG | ALT_TOTAL | over | 138.5 | -115 | 0.456 | 0.000 | 0.626 | 0.500 | 0.516 | +120 | -14.8% | +17.1% | -3.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 278 | 1:30 PM CT | Ole Miss @ Arizona | FG | TOTAL | over | 154.5 | -110 | 0.446 | 0.000 | 0.387 | 0.500 | 0.486 | +124 | -14.9% | -26.1% | -7.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 279 | 4:30 PM CT | BYU @ Providence | FG | ALT_SPREAD | home | 2.5 | -105 | 0.434 | 0.000 | 0.362 | 0.475 | 0.475 | +130 | -15.2% | -29.4% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 280 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | ML | home | — | -800 | 0.752 | 0.000 | 0.816 | 0.852 | 0.848 | -303 | -15.4% | -8.2% | -4.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 281 | 1:30 PM CT | Ole Miss @ Arizona | FG | ALT_TOTAL | over | 153.5 | -125 | 0.468 | 0.000 | 0.411 | 0.520 | 0.507 | +114 | -15.8% | -26.1% | -8.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 282 | 6:00 PM CT | Northeastern @ Wisconsin | FG | TOTAL | under | 156.5 | -110 | 0.441 | 0.000 | 0.429 | 0.500 | 0.491 | +127 | -15.9% | -18.0% | -6.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 283 | 12:00 PM CT | Southern Utah @ Long Beach State | 1H | SPREAD | home | -0.5 | -120 | 0.459 | 0.000 | — | 0.510 | 0.497 | +118 | -15.9% | — | -8.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 284 | 9:30 PM CT | Pacific @ Jacksonville State | FG | ML | away | — | -225 | 0.581 | 0.000 | 0.680 | 0.664 | 0.666 | -138 | -16.1% | -1.8% | -3.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 285 | 1:30 PM CT | Texas A&M @ Xavier | 1H | SPREAD | home | 2.5 | -110 | 0.439 | 0.000 | — | 0.490 | 0.477 | +128 | -16.2% | — | -8.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 286 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | ML | home | — | -125 | 0.465 | 0.000 | 0.594 | 0.532 | 0.540 | +115 | -16.2% | +6.9% | -2.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 287 | 12:00 PM CT | Southern Utah @ Long Beach State | 1H | ML | home | — | -135 | 0.459 | 0.039 | — | 0.541 | 0.504 | +110 | -16.3% | — | -8.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 288 | 6:00 PM CT | Northeastern @ Wisconsin | FG | ALT_TOTAL | under | 157.5 | -125 | 0.465 | 0.000 | 0.454 | 0.520 | 0.512 | +115 | -16.3% | -18.3% | -7.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 289 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | SPREAD | away | -2.5 | -112 | 0.442 | 0.000 | 0.372 | 0.504 | 0.504 | +126 | -16.4% | -29.6% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 290 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | SPREAD | away | -3.5 | -108 | 0.433 | 0.000 | 0.386 | 0.496 | 0.496 | +131 | -16.7% | -25.6% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 291 | 5:00 PM CT | UAlbany @ Syracuse | FG | SPREAD | away | 26.5 | -110 | 0.436 | 0.000 | 0.616 | 0.500 | 0.500 | +129 | -16.7% | +17.5% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 292 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | ALT_SPREAD | away | 20.5 | -104 | 0.425 | 0.000 | 0.574 | 0.473 | 0.473 | +136 | -16.7% | +12.5% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 293 | 5:00 PM CT | UAlbany @ Syracuse | FG | ALT_SPREAD | away | 27.5 | -129 | 0.469 | 0.000 | 0.648 | 0.523 | 0.523 | +113 | -16.8% | +15.1% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 294 | 6:00 PM CT | UConn @ Duke | FG | ALT_TOTAL | under | 146.5 | -120 | 0.452 | 0.000 | 0.561 | 0.510 | 0.516 | +121 | -17.2% | +2.8% | -5.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 295 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | ALT_SPREAD | away | -2.5 | -129 | 0.466 | 0.000 | 0.420 | 0.523 | 0.523 | +115 | -17.2% | -25.4% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 296 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | ALT_SPREAD | home | -2.5 | +108 | 0.398 | 0.000 | 0.508 | 0.447 | 0.447 | +151 | -17.2% | +5.6% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 297 | 9:30 PM CT | Pacific @ Jacksonville State | 1H | ML | away | — | -215 | 0.535 | 0.043 | — | 0.644 | 0.596 | -126 | -17.4% | — | -8.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 298 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | SPREAD | home | -1.5 | -110 | 0.432 | 0.000 | 0.543 | 0.500 | 0.500 | +131 | -17.4% | +3.6% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 299 | 4:00 PM CT | Memphis @ Penn State | FG | SPREAD | home | 3.5 | -105 | 0.422 | 0.000 | 0.498 | 0.489 | 0.489 | +137 | -17.5% | -2.8% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 300 | 6:30 PM CT | Wake Forest @ Mississippi State | FG | ML | away | — | +150 | 0.328 | 0.000 | 0.455 | 0.384 | 0.392 | +205 | -18.1% | +13.7% | -1.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 301 | 4:00 PM CT | Portland State @ UC Riverside | FG | TOTAL | over | 152.5 | -108 | 0.425 | 0.000 | 0.321 | 0.496 | 0.473 | +135 | -18.2% | -38.2% | -8.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 302 | 4:00 PM CT | Memphis @ Penn State | FG | ALT_SPREAD | home | 4.5 | -127 | 0.457 | 0.000 | 0.533 | 0.520 | 0.520 | +119 | -18.3% | -4.8% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 303 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | TOTAL | under | 145.5 | -112 | 0.430 | 0.000 | 0.407 | 0.504 | 0.492 | +132 | -18.5% | -23.0% | -6.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 304 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | ALT_SPREAD | away | -3.5 | -101 | 0.408 | 0.000 | 0.340 | 0.467 | 0.467 | +145 | -18.7% | -32.3% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 305 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | FG | SPREAD | home | 3.5 | -102 | 0.408 | 0.000 | 0.577 | 0.483 | 0.483 | +145 | -19.1% | +14.3% | -4.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 306 | 9:30 PM CT | Pacific @ Jacksonville State | FG | SPREAD | away | -5.5 | -105 | 0.413 | 0.000 | 0.502 | 0.489 | 0.489 | +142 | -19.3% | -2.0% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 307 | 4:00 PM CT | Portland State @ UC Riverside | FG | ALT_TOTAL | over | 151.5 | -125 | 0.447 | 0.000 | 0.343 | 0.520 | 0.497 | +124 | -19.5% | -38.3% | -10.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 308 | 1:30 PM CT | Texas A&M @ Xavier | FG | SPREAD | home | 5.5 | -115 | 0.430 | 0.000 | 0.415 | 0.511 | 0.511 | +133 | -19.7% | -22.4% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 309 | 1:00 PM CT | Manhattan @ NJIT | FG | ML | away | — | +110 | 0.381 | 0.000 | 0.371 | 0.457 | 0.446 | +162 | -19.9% | -22.1% | -6.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 310 | 1:00 PM CT | Manhattan @ NJIT | FG | SPREAD | away | 1.5 | -108 | 0.416 | 0.000 | 0.421 | 0.496 | 0.496 | +141 | -19.9% | -18.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 311 | 2:30 PM CT | Arkansas State @ Florida International | FG | TOTAL | under | 173.5 | -112 | 0.422 | 0.000 | 0.674 | 0.504 | 0.526 | +137 | -20.1% | +27.6% | -0.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 312 | 2:00 PM CT | Akron @ App State | FG | ML | away | — | -250 | 0.570 | 0.000 | 0.674 | 0.685 | 0.684 | -132 | -20.2% | -5.6% | -4.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 313 | 3:00 PM CT | Georgia State @ Florida Gulf Coast | FG | ALT_TOTAL | under | 144.5 | -105 | 0.408 | 0.000 | 0.383 | 0.480 | 0.467 | +145 | -20.3% | -25.2% | -8.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 314 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | ML | home | — | -175 | 0.507 | 0.000 | 0.698 | 0.609 | 0.621 | -103 | -20.4% | +9.7% | -2.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 315 | 9:30 PM CT | Pacific @ Jacksonville State | 1H | SPREAD | away | -3.5 | -105 | 0.406 | 0.000 | — | 0.480 | 0.461 | +146 | -20.7% | — | -9.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 316 | 4:00 PM CT | Southern @ Nebraska | FG | SPREAD | home | -35.5 | -110 | 0.414 | 0.000 | 0.362 | 0.500 | 0.500 | +141 | -20.9% | -30.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 317 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | SPREAD | away | 15.5 | -112 | 0.417 | 0.000 | 0.511 | 0.504 | 0.504 | +140 | -21.1% | -3.2% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 318 | 5:00 PM CT | UAlbany @ Syracuse | FG | TOTAL | under | 149.5 | -108 | 0.406 | 0.000 | 0.450 | 0.496 | 0.490 | +146 | -21.8% | -13.2% | -5.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 319 | 4:00 PM CT | Memphis @ Penn State | FG | ML | home | — | +145 | 0.319 | 0.000 | 0.378 | 0.391 | 0.389 | +213 | -21.8% | -7.4% | -4.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 320 | 5:00 PM CT | UAlbany @ Syracuse | FG | ALT_TOTAL | under | 150.5 | -125 | 0.432 | 0.000 | 0.475 | 0.520 | 0.515 | +131 | -22.2% | -14.5% | -7.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 321 | 2:30 PM CT | Arkansas State @ Florida International | FG | ALT_TOTAL | under | 172.5 | -105 | 0.397 | 0.000 | 0.652 | 0.480 | 0.502 | +152 | -22.4% | +27.3% | -2.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 322 | 1:00 PM CT | Manhattan @ NJIT | FG | ALT_SPREAD | away | 2.5 | -139 | 0.450 | 0.000 | 0.456 | 0.540 | 0.540 | +122 | -22.6% | -21.7% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 323 | 1:30 PM CT | Texas A&M @ Xavier | FG | ML | home | — | +180 | 0.277 | 0.000 | 0.244 | 0.343 | 0.329 | +262 | -22.6% | -31.6% | -7.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 324 | 1:30 PM CT | Texas A&M @ Xavier | FG | ALT_SPREAD | home | 4.5 | -106 | 0.397 | 0.000 | 0.381 | 0.478 | 0.478 | +152 | -22.8% | -25.9% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 325 | 2:00 PM CT | Jackson State @ Oklahoma State | FG | SPREAD | home | -34.5 | -108 | 0.401 | 0.000 | 0.393 | 0.496 | 0.496 | +150 | -22.8% | -24.3% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 326 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | TOTAL | under | 142.5 | -115 | 0.412 | 0.000 | 0.518 | 0.511 | 0.512 | +143 | -22.9% | -3.2% | -4.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 327 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | SPREAD | home | -3.5 | -110 | 0.403 | 0.000 | 0.589 | 0.500 | 0.500 | +148 | -23.0% | +12.5% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 328 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | ML | away | — | +950 | 0.073 | 0.000 | 0.104 | 0.092 | 0.093 | +1265 | -23.1% | +9.4% | -2.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 329 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | SPREAD | away | 10.5 | -108 | 0.398 | 0.000 | 0.481 | 0.496 | 0.496 | +151 | -23.4% | -7.5% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 330 | 7:00 PM CT | Cal State Bakersfield @ Pepperdine | FG | SPREAD | away | 10.5 | -112 | 0.404 | 0.000 | 0.581 | 0.504 | 0.504 | +148 | -23.6% | +10.0% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 331 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | ALT_SPREAD | away | 11.5 | -131 | 0.432 | 0.000 | 0.514 | 0.527 | 0.527 | +132 | -23.9% | -9.3% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 332 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | FG | ML | home | — | +145 | 0.310 | 0.000 | 0.460 | 0.391 | 0.399 | +222 | -24.0% | +12.7% | -2.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 333 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | SPREAD | home | -11.5 | -115 | 0.405 | 0.000 | 0.461 | 0.511 | 0.511 | +147 | -24.3% | -13.8% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 334 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | ALT_SPREAD | away | 14.5 | -104 | 0.385 | 0.000 | 0.478 | 0.473 | 0.473 | +160 | -24.5% | -6.3% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 335 | 4:00 PM CT | Southern @ Nebraska | FG | ALT_SPREAD | home | -36.5 | -104 | 0.384 | 0.000 | 0.330 | 0.474 | 0.474 | +161 | -24.7% | -35.3% | -7.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 336 | 1:00 PM CT | Abilene Christian @ South Dakota State | 1H | TOTAL | under | 65.5 | -110 | 0.391 | 0.000 | — | 0.490 | 0.465 | +156 | -25.4% | — | -11.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 337 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | ALT_TOTAL | under | 141.5 | -110 | 0.390 | 0.000 | 0.493 | 0.490 | 0.490 | +156 | -25.5% | -5.8% | -6.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 338 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | ALT_SPREAD | home | -4.5 | -101 | 0.372 | 0.000 | 0.556 | 0.467 | 0.467 | +169 | -26.0% | +10.7% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 339 | 2:00 PM CT | Jackson State @ Oklahoma State | FG | ALT_SPREAD | home | -35.5 | -105 | 0.371 | 0.000 | 0.360 | 0.475 | 0.475 | +170 | -27.6% | -29.7% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 340 | 7:00 PM CT | Cal State Bakersfield @ Pepperdine | FG | ML | away | — | +425 | 0.138 | 0.000 | 0.249 | 0.183 | 0.190 | +625 | -27.6% | +30.9% | -0.1% | EV_GT_30_PCT | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 341 | 1:30 PM CT | Texas A&M @ Xavier | FG | ALT_TOTAL | over | 168.5 | -120 | 0.394 | 0.000 | 0.367 | 0.510 | 0.492 | +154 | -27.7% | -32.6% | -9.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 342 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | ML | away | — | +425 | 0.137 | 0.000 | 0.177 | 0.183 | 0.182 | +628 | -27.9% | -6.9% | -4.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 343 | 6:00 PM CT | St. Thomas @ UNC Wilmington | 1H | ML | home | — | -260 | 0.492 | 0.038 | — | 0.681 | 0.614 | -105 | -28.1% | — | -11.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 344 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | ALT_SPREAD | home | -12.5 | -109 | 0.373 | 0.000 | 0.427 | 0.484 | 0.484 | +168 | -28.4% | -18.2% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 345 | 1:30 PM CT | Ole Miss @ Arizona | FG | ML | home | — | -238 | 0.504 | 0.000 | 0.660 | 0.675 | 0.673 | -102 | -28.4% | -6.3% | -4.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 346 | 1:30 PM CT | Texas A&M @ Xavier | FG | TOTAL | over | 169.5 | -108 | 0.371 | 0.000 | 0.345 | 0.496 | 0.476 | +169 | -28.5% | -33.6% | -8.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 347 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | ML | home | — | -285 | 0.527 | 0.000 | 0.587 | 0.710 | 0.695 | -112 | -28.8% | -20.7% | -6.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 348 | 2:00 PM CT | Akron @ App State | FG | SPREAD | away | -6.5 | -108 | 0.368 | 0.000 | 0.454 | 0.496 | 0.496 | +172 | -29.1% | -12.5% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 349 | 2:00 PM CT | Akron @ App State | FG | ALT_SPREAD | away | -5.5 | -130 | 0.400 | 0.000 | 0.489 | 0.526 | 0.526 | +150 | -29.3% | -13.5% | -7.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 350 | 3:30 PM CT | South Carolina @ USC | FG | ML | away | — | +500 | 0.117 | 0.000 | 0.154 | 0.160 | 0.159 | +754 | -29.7% | -7.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 351 | 4:00 PM CT | Southern @ Nebraska | FG | TOTAL | under | 149.5 | -115 | 0.374 | 0.000 | 0.579 | 0.511 | 0.519 | +167 | -30.0% | +8.2% | -2.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 352 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | SPREAD | away | 14.5 | -112 | 0.367 | 0.000 | 0.439 | 0.504 | 0.504 | +172 | -30.4% | -16.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 353 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | ML | home | — | -278 | 0.510 | 0.000 | 0.566 | 0.705 | 0.689 | -104 | -30.7% | -23.0% | -6.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 354 | 3:30 PM CT | South Carolina @ USC | FG | SPREAD | away | 10.5 | -108 | 0.358 | 0.000 | 0.455 | 0.496 | 0.496 | +179 | -31.0% | -12.3% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 355 | 4:00 PM CT | Holy Cross @ Dartmouth | FG | SPREAD | away | 11.5 | -112 | 0.364 | 0.000 | 0.382 | 0.504 | 0.504 | +175 | -31.1% | -27.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 356 | 4:00 PM CT | Southern @ Nebraska | FG | ALT_TOTAL | under | 148.5 | -105 | 0.351 | 0.000 | 0.554 | 0.480 | 0.489 | +185 | -31.4% | +8.3% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 357 | 3:30 PM CT | South Carolina @ USC | FG | ALT_SPREAD | away | 11.5 | -131 | 0.388 | 0.000 | 0.490 | 0.527 | 0.527 | +157 | -31.5% | -13.6% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 358 | 2:00 PM CT | Jackson State @ Oklahoma State | FG | TOTAL | under | 160.5 | -108 | 0.351 | 0.000 | 0.483 | 0.496 | 0.494 | +185 | -32.5% | -6.9% | -4.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 359 | 4:00 PM CT | Holy Cross @ Dartmouth | FG | ML | away | — | +550 | 0.104 | 0.000 | 0.106 | 0.148 | 0.142 | +866 | -32.7% | -31.4% | -8.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 360 | 4:00 PM CT | Portland State @ UC Riverside | FG | SPREAD | away | 2.5 | -110 | 0.352 | 0.000 | 0.537 | 0.500 | 0.500 | +184 | -32.7% | +2.5% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 361 | 2:00 PM CT | Jackson State @ Oklahoma State | FG | ALT_TOTAL | under | 161.5 | -125 | 0.373 | 0.000 | 0.508 | 0.520 | 0.519 | +168 | -32.9% | -8.5% | -6.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 362 | 1:00 PM CT | Abilene Christian @ South Dakota State | 1H | SPREAD | away | 4.5 | -115 | 0.359 | 0.000 | — | 0.500 | 0.465 | +179 | -33.0% | — | -13.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 363 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | TOTAL | under | 155.5 | -110 | 0.350 | 0.000 | 0.469 | 0.500 | 0.496 | +186 | -33.2% | -10.4% | -5.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 364 | 2:30 PM CT | Arkansas State @ Florida International | FG | SPREAD | away | 1.5 | -105 | 0.340 | 0.000 | 0.449 | 0.489 | 0.489 | +194 | -33.7% | -12.3% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 365 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | ALT_SPREAD | away | 13.5 | -105 | 0.339 | 0.000 | 0.406 | 0.475 | 0.475 | +195 | -33.8% | -20.7% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 366 | 4:00 PM CT | Holy Cross @ Dartmouth | FG | ALT_SPREAD | away | 10.5 | -103 | 0.335 | 0.000 | 0.350 | 0.471 | 0.471 | +198 | -33.9% | -31.0% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 367 | 2:30 PM CT | Arkansas State @ Florida International | FG | ALT_SPREAD | away | 2.5 | -130 | 0.373 | 0.000 | 0.483 | 0.525 | 0.525 | +168 | -33.9% | -14.6% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 368 | 4:00 PM CT | Portland State @ UC Riverside | FG | ALT_SPREAD | away | 3.5 | -139 | 0.384 | 0.000 | 0.570 | 0.540 | 0.540 | +160 | -33.9% | -2.0% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 369 | 1:00 PM CT | LSU @ Arizona State | FG | TOTAL | under | 146.5 | -112 | 0.347 | 0.000 | 0.374 | 0.504 | 0.488 | +188 | -34.2% | -29.1% | -7.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 370 | 6:00 PM CT | St. Thomas @ UNC Wilmington | 1H | SPREAD | home | -4.5 | -110 | 0.343 | 0.000 | — | 0.490 | 0.453 | +191 | -34.5% | — | -13.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 371 | 11:31 AM CT | Yale @ Wright State | 1H | SPREAD | away | 3.5 | -115 | 0.350 | 0.000 | — | 0.500 | 0.463 | +186 | -34.5% | — | -13.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 372 | 1:00 PM CT | Manhattan @ NJIT | FG | ALT_TOTAL | over | 140.5 | -120 | 0.354 | 0.000 | 0.537 | 0.510 | 0.513 | +183 | -35.1% | -1.6% | -5.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 373 | 1:00 PM CT | Manhattan @ NJIT | FG | TOTAL | over | 141.5 | -105 | 0.332 | 0.000 | 0.512 | 0.489 | 0.492 | +202 | -35.2% | -0.1% | -3.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 374 | 4:00 PM CT | Portland State @ UC Riverside | FG | ML | away | — | +124 | 0.289 | 0.000 | 0.453 | 0.428 | 0.431 | +246 | -35.3% | +1.4% | -3.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 375 | 1:00 PM CT | Saint Peter's @ Columbia | 1H | TOTAL | over | 57.5 | -125 | 0.359 | 0.000 | — | 0.520 | 0.480 | +179 | -35.4% | — | -13.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 376 | 1:30 PM CT | Ole Miss @ Arizona | FG | SPREAD | home | -5.5 | -108 | 0.335 | 0.000 | 0.473 | 0.496 | 0.496 | +198 | -35.4% | -8.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 377 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | ALT_TOTAL | under | 154.5 | -105 | 0.330 | 0.000 | 0.445 | 0.480 | 0.475 | +203 | -35.6% | -13.2% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 378 | 1:30 PM CT | Ole Miss @ Arizona | FG | ALT_SPREAD | home | -4.5 | -134 | 0.367 | 0.000 | 0.508 | 0.531 | 0.531 | +173 | -36.0% | -11.3% | -7.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 379 | 1:00 PM CT | LSU @ Arizona State | FG | ALT_TOTAL | under | 145.5 | -105 | 0.327 | 0.000 | 0.351 | 0.480 | 0.463 | +206 | -36.1% | -31.4% | -9.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 380 | 2:30 PM CT | Arkansas State @ Florida International | FG | ML | away | — | +105 | 0.308 | 0.000 | 0.400 | 0.468 | 0.459 | +225 | -36.9% | -18.0% | -5.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 381 | 1:00 PM CT | Abilene Christian @ South Dakota State | 1H | ML | away | — | +210 | 0.193 | 0.029 | — | 0.304 | 0.270 | +402 | -37.1% | — | -13.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 382 | 11:31 AM CT | Yale @ Wright State | 1H | ML | away | — | +180 | 0.212 | 0.031 | — | 0.337 | 0.297 | +357 | -37.5% | — | -13.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 383 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | SPREAD | home | -6.5 | -110 | 0.326 | 0.000 | 0.364 | 0.500 | 0.500 | +207 | -37.8% | -30.5% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 384 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | ALT_SPREAD | home | -5.5 | -131 | 0.346 | 0.000 | 0.384 | 0.527 | 0.527 | +189 | -39.0% | -32.4% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 385 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | SPREAD | home | -6.5 | -110 | 0.317 | 0.000 | 0.352 | 0.500 | 0.500 | +215 | -39.5% | -32.8% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 386 | 1:30 PM CT | Texas A&M @ Xavier | 1H | TOTAL | over | 80.5 | -115 | 0.323 | 0.000 | — | 0.500 | 0.456 | +209 | -39.6% | — | -14.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 387 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | ML | away | — | +850 | 0.062 | 0.000 | 0.088 | 0.101 | 0.099 | +1505 | -40.8% | -16.0% | -5.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 388 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | ALT_TOTAL | over | 157.5 | -120 | 0.322 | 0.000 | 0.418 | 0.510 | 0.499 | +211 | -41.0% | -23.3% | -8.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 389 | 12:00 PM CT | Eastern Kentucky @ Miami (OH) | FG | TOTAL | over | 158.5 | -105 | 0.301 | 0.000 | 0.395 | 0.489 | 0.477 | +233 | -41.3% | -22.9% | -6.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 390 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | ALT_SPREAD | home | -7.5 | -104 | 0.294 | 0.000 | 0.332 | 0.473 | 0.473 | +240 | -42.3% | -34.9% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 391 | 1:00 PM CT | Saint Peter's @ Columbia | 1H | SPREAD | away | 8.5 | -120 | 0.310 | 0.000 | — | 0.510 | 0.460 | +223 | -43.3% | — | -15.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 392 | 11:31 AM CT | Yale @ Wright State | FG | ALT_SPREAD | away | 6.5 | -124 | 0.303 | 0.000 | 0.460 | 0.515 | 0.515 | +230 | -45.3% | -16.8% | -7.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 393 | 6:00 PM CT | SMU @ Utah State | FG | TOTAL | under | 167.5 | -112 | 0.288 | 0.000 | 0.510 | 0.504 | 0.505 | +247 | -45.4% | -3.6% | -4.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 394 | 11:31 AM CT | Yale @ Wright State | FG | SPREAD | away | 5.5 | -102 | 0.275 | 0.000 | 0.426 | 0.483 | 0.483 | +263 | -45.5% | -15.6% | -4.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 395 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | ALT_SPREAD | away | 8.5 | -131 | 0.308 | 0.000 | 0.385 | 0.527 | 0.527 | +225 | -45.7% | -32.1% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 396 | 6:00 PM CT | Northeastern @ Wisconsin | FG | SPREAD | home | -19.5 | -115 | 0.288 | 0.000 | 0.428 | 0.511 | 0.511 | +248 | -46.2% | -20.0% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 397 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | SPREAD | away | 7.5 | -110 | 0.281 | 0.000 | 0.353 | 0.500 | 0.500 | +256 | -46.3% | -32.5% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 398 | 1:00 PM CT | Arkansas-Pine Bluff @ South Dakota | FG | ML | away | — | +1600 | 0.031 | 0.000 | 0.058 | 0.057 | 0.057 | +3085 | -46.6% | -1.7% | -3.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 399 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | TOTAL | under | 148.5 | -112 | 0.273 | 0.000 | 0.315 | 0.504 | 0.479 | +267 | -48.4% | -40.4% | -9.2% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 400 | 6:00 PM CT | Northeastern @ Wisconsin | FG | ALT_SPREAD | home | -20.5 | -108 | 0.262 | 0.000 | 0.394 | 0.482 | 0.482 | +282 | -49.6% | -24.1% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 401 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | TOTAL | under | 151.5 | -110 | 0.257 | 0.000 | 0.541 | 0.500 | 0.505 | +289 | -50.9% | +3.3% | -3.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 402 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | ALT_TOTAL | under | 138.5 | -125 | 0.272 | 0.000 | 0.433 | 0.520 | 0.509 | +267 | -51.0% | -22.0% | -8.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 403 | 6:00 PM CT | Bellarmine @ Northern Kentucky | FG | ALT_TOTAL | under | 147.5 | -110 | 0.255 | 0.000 | 0.293 | 0.490 | 0.464 | +292 | -51.3% | -44.0% | -11.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 404 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | TOTAL | under | 137.5 | -110 | 0.254 | 0.000 | 0.410 | 0.500 | 0.489 | +294 | -51.6% | -21.8% | -6.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 405 | 4:00 PM CT | Alcorn State @ Texas State | FG | SPREAD | away | 23.5 | -115 | 0.254 | 0.000 | 0.328 | 0.511 | 0.511 | +294 | -52.5% | -38.7% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 406 | 11:31 AM CT | Yale @ Wright State | FG | ML | away | — | +210 | 0.152 | 0.000 | 0.253 | 0.309 | 0.302 | +559 | -53.0% | -21.5% | -6.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 407 | 6:00 PM CT | SMU @ Utah State | FG | ALT_TOTAL | under | 165.5 | -115 | 0.250 | 0.000 | 0.460 | 0.500 | 0.495 | +300 | -53.2% | -14.0% | -7.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 408 | 3:00 PM CT | Prairie View A&M @ Marshall | FG | ALT_TOTAL | under | 150.5 | -105 | 0.239 | 0.000 | 0.517 | 0.480 | 0.484 | +319 | -53.4% | +0.9% | -5.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 409 | 6:00 PM CT | St. Thomas @ UNC Wilmington | 1H | TOTAL | under | 73.5 | -120 | 0.252 | 0.000 | — | 0.510 | 0.446 | +296 | -53.7% | — | -18.3% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 410 | 6:00 PM CT | Northern Illinois @ SIU Edwardsville | 1H | TOTAL | under | 64.5 | -115 | 0.245 | 0.000 | — | 0.500 | 0.436 | +309 | -54.2% | — | -18.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 411 | 12:00 PM CT | Southern Utah @ Long Beach State | 1H | TOTAL | under | 69.5 | -105 | 0.234 | 0.000 | — | 0.480 | 0.418 | +328 | -54.4% | — | -18.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 412 | 8:00 PM CT | Mississippi Valley State @ New Mexico | FG | SPREAD | home | -36.5 | -108 | 0.237 | 0.000 | 0.374 | 0.496 | 0.496 | +322 | -54.4% | -28.0% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 413 | 5:00 PM CT | UAlbany @ Syracuse | FG | ML | away | — | +4000 | 0.011 | 0.000 | 0.025 | 0.024 | 0.024 | +9032 | -55.1% | +2.6% | -1.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 414 | 1:00 PM CT | Saint Peter's @ Columbia | FG | SPREAD | away | 14.5 | -105 | 0.228 | 0.000 | 0.337 | 0.489 | 0.489 | +338 | -55.4% | -34.2% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 415 | 1:00 PM CT | Saint Peter's @ Columbia | FG | ALT_SPREAD | away | 15.5 | -132 | 0.253 | 0.000 | 0.369 | 0.529 | 0.529 | +295 | -55.6% | -35.1% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 416 | 4:00 PM CT | Alcorn State @ Texas State | FG | ALT_SPREAD | away | 22.5 | -108 | 0.229 | 0.000 | 0.297 | 0.482 | 0.482 | +337 | -56.0% | -42.8% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 417 | 1:00 PM CT | Abilene Christian @ South Dakota State | FG | ML | away | — | +270 | 0.118 | 0.000 | 0.159 | 0.259 | 0.245 | +747 | -56.3% | -41.1% | -9.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 418 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | TOTAL | under | 148.5 | -110 | 0.228 | 0.000 | 0.341 | 0.500 | 0.479 | +339 | -56.5% | -35.0% | -8.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 419 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | TOTAL | over | 143.5 | -112 | 0.227 | 0.000 | 0.491 | 0.504 | 0.503 | +340 | -57.0% | -7.1% | -4.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 420 | 6:00 PM CT | Norfolk State @ NC State | FG | ML | away | — | +4000 | 0.010 | 0.000 | 0.007 | 0.024 | 0.020 | +9704 | -58.2% | -72.8% | -16.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 421 | 5:00 PM CT | Bethune-Cookman @ Richmond | FG | ALT_TOTAL | under | 147.5 | -105 | 0.210 | 0.000 | 0.318 | 0.480 | 0.459 | +376 | -59.0% | -37.9% | -10.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 422 | 12:00 PM CT | Lindenwood @ Stony Brook | FG | ALT_TOTAL | over | 144.5 | -105 | 0.209 | 0.000 | 0.467 | 0.480 | 0.478 | +377 | -59.1% | -8.9% | -6.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 423 | 1:00 PM CT | Saint Peter's @ Columbia | 1H | ML | away | — | +420 | 0.071 | 0.016 | — | 0.181 | 0.151 | +1296 | -61.7% | — | -19.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 424 | 1:00 PM CT | Saint Peter's @ Columbia | FG | TOTAL | over | 125.5 | -112 | 0.192 | 0.000 | 0.574 | 0.504 | 0.513 | +421 | -63.7% | +8.7% | -2.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 425 | 1:00 PM CT | Saint Peter's @ Columbia | FG | ALT_TOTAL | over | 126.5 | -105 | 0.176 | 0.000 | 0.550 | 0.480 | 0.488 | +468 | -65.6% | +7.4% | -4.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 426 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | ALT_SPREAD | away | 4.5 | -131 | 0.178 | 0.000 | 0.517 | 0.527 | 0.527 | +462 | -68.6% | -8.9% | -7.1% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 427 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | SPREAD | away | 3.5 | -108 | 0.158 | 0.000 | 0.483 | 0.496 | 0.496 | +533 | -69.6% | -6.9% | -4.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 428 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | TOTAL | under | 152.5 | -115 | 0.156 | 0.000 | 0.543 | 0.511 | 0.515 | +541 | -70.8% | +1.6% | -3.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 429 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | TOTAL | under | 150.5 | -110 | 0.144 | 0.000 | 0.375 | 0.500 | 0.484 | +594 | -72.5% | -28.4% | -7.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 430 | 3:00 PM CT | Grambling @ LSU New Orleans | FG | ALT_TOTAL | under | 151.5 | -110 | 0.143 | 0.000 | 0.519 | 0.490 | 0.494 | +600 | -72.7% | -0.9% | -5.8% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 431 | 1:00 PM CT | Saint Peter's @ Columbia | FG | ML | away | — | +850 | 0.029 | 0.000 | 0.049 | 0.101 | 0.093 | +3390 | -72.8% | -53.1% | -12.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 432 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | TOTAL | under | 167.5 | -112 | 0.142 | 0.000 | 0.455 | 0.504 | 0.498 | +603 | -73.1% | -13.9% | -5.7% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 433 | 2:00 PM CT | Akron @ App State | FG | TOTAL | over | 132.5 | -115 | 0.144 | 0.000 | 0.472 | 0.511 | 0.506 | +595 | -73.1% | -11.8% | -5.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 434 | 12:00 PM CT | Southern Utah @ Long Beach State | FG | ALT_TOTAL | under | 149.5 | -105 | 0.132 | 0.000 | 0.352 | 0.480 | 0.463 | +657 | -74.2% | -31.3% | -9.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 435 | 6:00 PM CT | South Carolina Upstate @ The Citadel | FG | ML | away | — | +150 | 0.102 | 0.000 | 0.368 | 0.384 | 0.382 | +877 | -74.4% | -8.0% | -4.6% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 436 | 5:00 PM CT | Cal State Northridge @ Weber State | FG | ALT_TOTAL | under | 166.5 | -105 | 0.130 | 0.000 | 0.431 | 0.480 | 0.474 | +670 | -74.6% | -15.8% | -7.5% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 437 | 2:00 PM CT | Akron @ App State | FG | ALT_TOTAL | over | 133.5 | -120 | 0.131 | 0.000 | 0.447 | 0.510 | 0.502 | +664 | -76.0% | -18.1% | -7.9% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 438 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | TOTAL | under | 156.5 | -110 | 0.110 | 0.000 | 0.398 | 0.500 | 0.487 | +806 | -78.9% | -24.0% | -7.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 439 | 6:00 PM CT | St. Thomas @ UNC Wilmington | FG | ALT_TOTAL | under | 155.5 | -105 | 0.100 | 0.000 | 0.375 | 0.480 | 0.466 | +899 | -80.4% | -26.8% | -9.0% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |
| 440 | 4:00 PM CT | Alcorn State @ Texas State | FG | ML | away | — | +2200 | 0.005 | 0.000 | 0.008 | 0.042 | 0.035 | +18592 | -87.7% | -80.5% | -20.4% | — | n/a uncalibrated | PRICED_PAPER/NON_COUNTED | UNAUTHENTICATED_PDF |

## Market coverage (every catalogued CBB family has a status or reason code)

| Period | Market | Model | Board rows | Quotes priced | Status | Rejections by reason |
|---|---|---|---:|---:|---|---|
| FG | SPREAD | ACTIVE | 47 | 43 | PRICED_PAPER | ORIENTATION_MISMATCH 1, STARTED_BEFORE_AS_OF 3 |
| FG | ML | ACTIVE | 44 | 40 | PRICED_PAPER | ORIENTATION_MISMATCH 1, STARTED_BEFORE_AS_OF 3 |
| FG | TOTAL | ACTIVE | 45 | 32 | PRICED_PAPER | STARTED_BEFORE_AS_OF 3, TOTALS_ORDER_UNVERIFIED 10 |
| FG | TT_HOME | ACTIVE | 41 | 0 | REJECTED | TOTALS_ORDER_UNVERIFIED 41 |
| FG | TT_AWAY | ACTIVE | 41 | 0 | REJECTED | TOTALS_ORDER_UNVERIFIED 41 |
| FG | ALT_SPREAD | ACTIVE | 38 | 34 | PRICED_PAPER | ORIENTATION_MISMATCH 1, STARTED_BEFORE_AS_OF 3 |
| FG | ALT_TOTAL | ACTIVE | 36 | 32 | PRICED_PAPER | STARTED_BEFORE_AS_OF 3, TOTALS_ORDER_UNVERIFIED 1 |
| 1H | SPREAD | ACTIVE | 15 | 13 | PRICED_PAPER | STARTED_BEFORE_AS_OF 2 |
| 1H | ML | ACTIVE | 15 | 13 | PRICED_PAPER | STARTED_BEFORE_AS_OF 2 |
| 1H | TOTAL | ACTIVE | 15 | 13 | PRICED_PAPER | STARTED_BEFORE_AS_OF 2 |
| 1H | TT_HOME | ACTIVE | 15 | 0 | REJECTED | TOTALS_ORDER_UNVERIFIED 15 |
| 1H | TT_AWAY | ACTIVE | 15 | 0 | REJECTED | TOTALS_ORDER_UNVERIFIED 15 |
| 1H | ALT_SPREAD | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 1H | ALT_TOTAL | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 2H_PREGAME | SPREAD | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 2H_PREGAME | ML | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 2H_PREGAME | TOTAL | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 2H_PREGAME | TT_HOME | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 2H_PREGAME | TT_AWAY | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 2H_PREGAME | ALT_SPREAD | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 2H_PREGAME | ALT_TOTAL | ACTIVE | 0 | 0 | NO_QUOTE | — |
| 2H_HALFTIME_ADJUSTED | SPREAD | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | 0 | 0 | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | — |
| 2H_HALFTIME_ADJUSTED | ML | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | 0 | 0 | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | — |
| 2H_HALFTIME_ADJUSTED | TOTAL | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | 0 | 0 | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | — |
| 2H_HALFTIME_ADJUSTED | TT_HOME | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | 0 | 0 | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | — |
| 2H_HALFTIME_ADJUSTED | TT_AWAY | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | 0 | 0 | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | — |
| 2H_HALFTIME_ADJUSTED | ALT_SPREAD | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | 0 | 0 | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | — |
| 2H_HALFTIME_ADJUSTED | ALT_TOTAL | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | 0 | 0 | NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE | — |
| FG | PLAYER_PTS_OU | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_PTS_AT_LEAST | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_REB_OU | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_REB_AT_LEAST | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_AST_OU | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_AST_AT_LEAST | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_3PM_OU | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_3PM_AT_LEAST | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_PRA_OU | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_PRA_AT_LEAST | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_PR_OU | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_PR_AT_LEAST | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_PA_OU | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_PA_AT_LEAST | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_RA_OU | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |
| FG | PLAYER_RA_AT_LEAST | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | 0 | 0 | NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED | — |

## Rejection census

| Stage | Reason code | Rows |
|---|---|---:|
| validate | ORIENTATION_MISMATCH | 3 |
| validate | STARTED_BEFORE_AS_OF | 21 |
| validate | TOTALS_ORDER_UNVERIFIED | 123 |

## Audit

- EV>30%: 51 of 440 priced sides (2 at +300 or longer). Flagged, not capped.
- Orientation: spread/ML inconsistent rejected 0; home/away mismatch rejected 3; ladder monotonicity violations 4.
- Bias: model−market home margin 0.866 (mean abs 3.783), total 2.776 over 31 games; +EV selections fav/dog 78/103 (p 0.0631), over/under 46/20 (p 0.0014); flags ['OVER_UNDER_IMBALANCE'].
- Leakage: prior finals 1111, latest prior tip 2026-11-25T06:00:00Z, flags none.
- Consistency: sim vs closed-form max |Δp| 0.0192 {'ALT_SPREAD': 0.0192, 'ALT_TOTAL': 0.0162, 'ML': 0.0079, 'SPREAD': 0.0163, 'TOTAL': 0.0173}; joint team SD 10.55 vs cbb_pricing closed-form 12.021; implied home/away score corr 0.298.
- Pins: models/cbb/cbbd_frozen_final_join.py MATCH; models/cbb/sportsedge_cbb_model.py DRIFT; models/cbb/torvik_cbbd_pregame_bridge.py MATCH
- Provenance: {'UNAUTHENTICATED_PDF': 367}; authenticated rows 0.

## Grade

Not graded in this run.
