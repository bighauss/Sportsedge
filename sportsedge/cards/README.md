# Phone-ready SportsEdge card — Munich format

RESEARCH ONLY. Generates a 1080×1920 dark-neon stadium/turf card with
ranked rows, home/away score projections, total, CT kickoff, price,
research-projected win probability and EV estimate, stars, and a compact
reliability footer. Uses the user's NE@DET Munich layout but does not use
copywritten third-party team artwork unless the owner provides a licensed or
owner-supplied original PNG with exact SHA256. Monogram fallback always works.

Source file is JSON **from the canonical SportsEdge runner**. It is NOT
created by this renderer. Do not put raw private DK book boards, offer
payloads, player IDs, wallets, API keys, or private betting ledgers in the
public repository. A human-approved/private build may render local output.
The renderer cannot independently authenticate the source URL or model
calibration; it cannot turn PAPER/0u into OFFICIAL.

## Usage

From repository root, using an approved **local, private** input JSON:

    python -m sportsedge.cards.phone_card /path/private/card.json /path/private/card.svg

Optional phone-friendly raster:

    python -m pip install cairosvg
    python -m sportsedge.cards.phone_card /path/private/card.json /path/private/card.png

Sample JSON schema (field values below are **illustrative synthetic values**,
not a real wager quote, model recommendation, or event card):

    {
      "release": "PAPER_0U",
      "source": {
        "model_sha256": "INSERT_EXACT_64CHAR_HASH",
        "feature_sha256": "INSERT_EXACT_64CHAR_HASH",
        "frozen_utc": "2026-11-15T12:00:00Z"
      },
      "game": {
        "sport": "NFL",
        "away_name": "Patriots", "away_abbr": "NE",
        "home_name": "Lions", "home_abbr": "DET",
        "venue": "Munich, Germany", "time_ct": "8:30 AM CT",
        "kickoff_utc": "2026-11-15T14:30:00Z",
        "away_projection": 23.6,
        "home_projection": 25.3,
        "total_projection": 48.9
      },
      "plays": [
        {
          "rank": 1, "market": "total", "play": "Example Under 50.5",
          "game_time_ct": "8:30 AM CT",
          "status": "PAPER_0U",
          "price": -105,
          "price_observed_utc": "2026-11-15T13:30:00Z",
          "receipt_id": "REPLACE_WITH_GENUINE_RECEIPT",
          "win_probability": 0.56,
          "projection": 48.9,
          "ev_estimate_pct": 7.8,
          "stars": 3
        }
      ]
    }

The tool validates SHA format; time ordering; consistent score/total;
nonnegative probabilities; sequential ranks sorted by estimated EV;
valid real-sounding American price format; per-offer receipt ID; no
price/EV on blocked/NO DATA rows; and strict escaping of all text.
Logo files, when supplied, must be OWNER_PROVIDED or LICENSED_ASSET,
PNG only, inside the local manifest folder and hash verified.
When missing, team abbreviations are rendered in neon circles.

The artifact has a small non-actionability footer, not a huge PAPER
banner or separate notes. ALL RESEARCH EV fields are model estimates
and not measured returns. Do not use this graphic to solicit actual
stakes while Issue #10 live price/source/calibration gates are open.

## Current integration status

- Synthetic renderer/test suite is in main CI.
- No local/private production board is copied to public GitHub.
- The complete source-to-graphic CI automation is BLOCKED until the
  canonical RUN IT card produces one admitted, hash-verified private JSON
  with actual model/feature/quote receipts.
- Game team logos are optional local verified owner-provided assets.
- PNG uses CairoSVG when installed; SVG uses stdlib only.
- Do not imply "auto-post" to X or place/enter any sportsbook bet.
