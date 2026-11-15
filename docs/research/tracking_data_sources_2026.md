Yes — this is one of the highest-leverage areas to formalize. Your current rules already lean on the best available free/public sources for each sport, but coverage quality and “tracking-level” depth vary a lot. Here’s the realistic 2026 picture for Statcast / Next Gen equivalents (player-tracking, expected stats, process metrics) and what to lock in.
Current Best Free / Public Tracking & Advanced Layers
Sport
Closest to Statcast / Next Gen
Primary Free Sources
What You Actually Get
Gaps / Notes
MLB
Statcast (best in class)
Baseball Savant, pybaseball / baseballr, FanGraphs
Exit velo, launch angle, barrel%, xwOBA/xBA/xSLG, bat speed (2024+), sprint speed, OAA, framing, pitch movement/spin, CSW, whiff
Gold standard. Fully public, pitch-level, nightly updates. Your rules already use the right pieces.
NFL
Next Gen Stats
nflverse (load_nextgen_stats), NFL.com/Trends, EndzoneAPI (free tier), PFR advanced
Target share, air yards, separation, CPOE, RYOR, pressure rate, route classification 2.0 (2026), run scheme classification, player tracking (10x/sec)
Excellent and improving. nflverse updates nightly. New 2026 run-game + route models are useful. Snap counts + participation also available.
CFB
No true player tracking
CollegeFootballData (CFBD) + cfbfastR / sportsdataverse
EPA/PPA, success rate, explosiveness, havoc, SP+/FPI/Elo cross-checks, talent/returning production
Closest you get is high-quality EPA + success metrics. No public player-tracking (GPS is mostly team-only). Stick with CFBD as primary; SP+/FPI only as cross-check (as you already do).
NBA
Second Spectrum / NBA tracking
nba_api (stats.nba.com), Cleaning the Glass (limited free), Basketball-Reference, pbpstats
Tracking: speed, distance, touches, drives, contested shots, hustle stats, lineup net ratings, four factors, ORtg/DRtg
Official tracking exists but is less open than MLB/NFL. nba_api gives most of what is publicly released. On/off and minutes redistribution (your current approach) remain essential.
CBB
No real tracking
BartTorvik (primary), KenPom (paid/limited), sportsdataverse / hoopR
Adjusted O/D, tempo, four factors, 3P% regression, player on/off-ish
BartTorvik is still the clear free public standard. No player-tracking equivalent. Your “barttorvik adjusted O/D × tempo + hard 3P regression” is correct.
NHL
MoneyPuck + Natural Stat Trick
MoneyPuck (downloadable shot/xG data), Natural Stat Trick, NHL Edge (limited public)
5v5 xGF/xGA per 60, shot quality, high-danger chances, goalie xG, Corsi/Fenwick, PP/PK
MoneyPuck is the closest thing to a public Statcast for hockey (shot-level with expected goals). Confirm goalies only (your rule) is still critical because backup/starter swings are large.
Recommended Additions to the Ruleset
	1	Explicit primary source hierarchy per sport (so the process is reproducible and never invents numbers):
	◦	MLB → Baseball Savant / Statcast first, FanGraphs second.
	◦	NFL → nflverse Next Gen + EPA (nflfastR) first, PFR advanced second.
	◦	CFB → CFBD / cfbfastR EPA + success + havoc first; SP+/FPI only as sanity check.
	◦	NBA → nba_api tracking + lineup data + Cleaning the Glass-style four factors when available.
	◦	CBB → BartTorvik only for adjusted efficiency/tempo.
	◦	NHL → MoneyPuck xG first, Natural Stat Trick for possession splits, confirmed goalie only.
	2	Minimum sample / regression rules already exist — keep them tight:
	◦	You already regress toward league average until meaningful sample sizes. That is correct. Do not override with small-sample tracking numbers (e.g., early-season CPOE or barrel%).
	3	Props-specific tracking usage:
	◦	NFL: target share + air yards + separation + CPOE for receiving; RYOR + yards before contact for rushing.
	◦	MLB: barrel% / xwOBA vs pitch type + platoon for hitters; CSW / whiff / stuff for pitcher K props.
	◦	NHL: individual xG + ice time + high-danger share for points/SOG.
	◦	NBA: touches / time of possession / contested rate when available, otherwise usage × efficiency × opponent DRtg.
	4	What not to chase:
	◦	Do not wait for or invent player-tracking in CFB or CBB — it does not exist publicly at usable scale.
	◦	Avoid paid-only tracking (PFF charting, full Second Spectrum dumps, etc.) unless you later decide to add a paid data budget. Your current free stack is already strong enough for +EV work.
Practical Next Step for SportsEdge
Add a short “Tracking / Advanced Data” subsection under INPUTS that lists the primary free source + fallback for each sport, and a rule: “If the primary tracking/expected metric is missing or below the sport’s regression threshold, fall back to the season-long efficiency number and widen the uncertainty band (or skip the play).”
This keeps the system honest, reproducible, and aligned with what is actually available in 2026. Your existing sport-specific sections are already pointed at the right sources — they just need to be made explicit and hierarchical so nothing drifts.
