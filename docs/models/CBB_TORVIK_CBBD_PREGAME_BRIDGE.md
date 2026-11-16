# CBB Torvik as-of → CBBD exact-ID pregame bridge

RESEARCH ONLY / PAPER 0u. This code does not place bets, change frozen v5, edit past predictions, infer player availability, or claim that locally saved source timestamps are publisher-authenticated.

## Why this exists

- Historical Nov 2026 research notes show 365 Torvik teams, but only 283/365 string-identical names in a prior 364-team SportsEdge name set. Fuzzy matching has real false-positive threats including Kansas vs Kansas City, Virginia vs Virginia Lynchburg, Miami FL vs Miami OH and Georgia Southern missing from prior set. Do NOT use name prefixes or relaxed aliases.
- The candidate research baseline already exists in models/cbb/torvik_point_in_time_baseline.py (PR #122). An independent release-aware score evaluator is in point_in_time_score_walkforward.py (PR #131). CBBD raw games and finals capture landed through PR #145. This bridge connects ONLY a prospectively frozen ratings CSV, explicit human-reviewed CBBD team-ID map, and pre-observed HCA inputs into research expected scores.
- No actual Torvik source adapter, publisher-side publication clock, verified team crosswalk, or HCA calibration is implicitly created by a passing synthetic test.

## Input files and secure source receipt

Create three **private** UTF-8 CSVs outside public GitHub:

1. Ratings (from an authorized T-Rank archive export, e.g., toRvik bart_archive): required headers team,adj_o,adj_d,adj_tempo. Optional date column YYYYMMDD/ISO. All 300+ rows must have exact unique team names and positive finite metrics. Full season ending year passed separately; 2026-27 is season 2027. CSVs sourced from today must NOT be used for predictions frozen on earlier dates.
2. Explicit review-only crosswalk: cbbd_id,cbbd_team_name,torvik_team. CBBD IDs are positive exact integer strings; cbbd_team_name must match the exact provider-supplied homeTeam/awayTeam label in each original CBBD game; torvik_team must match the frozen ratings name exactly. Both provider labels and Torvik targets must be unique (one-to-one). Any mismatch blocks the game, never a fuzzy alias. Unmapped games will be blocked with reason EXACT_CBBD_TO_TORVIK_MAPPING_MISSING. This is a distinct identity dataset, not a substring search.
3. Season-specific measured HCA research: cbbd_id,home_court_points. Every nonneutral home team must have an explicitly recorded HCA points estimate. No default 3 or 3.36 is filled if missing. This HCA coefficient is not deemed calibrated merely by being present.

Save each through the private create-only raw-byte archiver (one per source file):

    cd models/cbb
    python torvik_cbbd_pregame_bridge.py archive-csv --source /private/input/torvik_export.csv --kind TORVIK_RATINGS --season 2027 --private-dir /private/sportsedge/cbb
    python torvik_cbbd_pregame_bridge.py archive-csv --source /private/input/checked_map.csv --kind CBBD_ID_CROSSWALK --season 2027 --private-dir /private/sportsedge/cbb
    python torvik_cbbd_pregame_bridge.py archive-csv --source /private/input/hca.csv --kind HCA_RESEARCH --season 2027 --private-dir /private/sportsedge/cbb

Keep all returned exact raw_path + manifest_path values. The archiver SHA256-checks the exact original file bytes and records the time the **local process observed that file**, NOT an independent Torvik publication timestamp. Do not backdate the local capture clock to fabricate historical evidence. The CSV archiver never fetches data or requires provider credentials; source authorization and true upstream origin are a separate hard gate. Raw/manifest files are create-only and must stay in restricted storage.

You also need the CBBD games raw + manifest paths previously produced by documented, free-tier key-gated capture (see docs/models/CBB_CBBD_PROSPECTIVE_CAPTURE.md). Never hardcode or paste your CBBD_API_KEY into a public repository or chat.

## Run prospective slate research

Use the exact four receipt pairs (CBBD schedule, Torvik ratings, CBBD ID crosswalk, HCA evidence):

    python torvik_cbbd_pregame_bridge.py project \
      --schedule-raw /private/sportsedge/cbb/cbbd_games_exact.raw.json \
      --schedule-manifest /private/sportsedge/cbb/cbbd_games_exact.manifest.json \
      --ratings-raw /private/sportsedge/cbb/torvik_ratings_exact.csv \
      --ratings-manifest /private/sportsedge/cbb/torvik_ratings_exact.manifest.json \
      --map-raw /private/sportsedge/cbb/cbbd_id_crosswalk_exact.csv \
      --map-manifest /private/sportsedge/cbb/cbbd_id_crosswalk_exact.manifest.json \
      --hca-raw /private/sportsedge/cbb/hca_research_exact.csv \
      --hca-manifest /private/sportsedge/cbb/hca_research_exact.manifest.json \
      --output-path /private/sportsedge/cbb/new_pregame_research_board.json

Code checks all original source digests, timestamps, season, rating coverage and exact mapping. The model freeze is the **actual UTC time of running the script**. Current schedule + rating capture must each be within 24 hours of the run, must be earlier than the model freeze, and each game must have status scheduled, explicit non-TBD tipoff, exact CBBD IDs, correct season and tipoff after freeze. Existing finals, games already started, missing crosswalks, missing HCA, corrupted sources and all duplicate CBBD event identities are blocked, not silently omitted.

The output is a **create-only private report**, includes one row for every source event and either research home/away expected scores or an explicit blocking reason. Model code SHA is calculated from the installed baseline code bytes, not invented. Scores and underlying assumptions are UNCALIBRATED and have no fair price or +EV claim, no winning probabilities or betting selections.

## Historical and promotion limitations

The locally supplied Torvik CSV and HCA map are not provider-authenticated even if they carry correct SHA/timestamps. The CBBD live schedule does not prove its current ratings were published before a historical date. For a true 2015-2025 backtest, each exact historical pregame snapshot must be independently attested or else the relevant game must remain BLOCKED. Avoid overcounting known provider aliases, D2/D3 opponents, result corrections, and source duplicates.

No real API key was connected or used in these synthetic tests. A FREE official CBBD account/API key and authenticated pregame odds receipts remain prerequisites for live capture, and issue #10 gates A-E remain strict. The existing hourly SportsEdge engineering task can continue *code/CI* work, but it cannot conjure permitted credentials or legitimately authenticate absent historical receipts.

Run synthetic-only tests from models/cbb:

    python -m unittest -v test_torvik_cbbd_pregame_bridge.py
