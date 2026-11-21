# CFB manual injury file (phone-editable)

No free programmatic CFB injury feed is usable (ESPN's college-football injuries endpoints
return empty lists; CFBD has no injury endpoint). So injuries come from this folder.

In the GitHub app: add `models/cfb/injuries/<YYYY-MM-DD>.json` (copy `EXAMPLE.json`, which uses
placeholder names), then run **CFB RUN IT** with `injuries_path` set to that file.

- `reviewed_utc`: when you checked (UTC). Older than 6 h -> card says INJURY_REVIEW_STALE.
- `teams_reviewed`: every team you checked, **even if it has no injuries**. Teams on the
  card that are not listed show `INJURY_COVERAGE_PARTIAL` / "injury coverage missing".
- `injuries[]`: `team`, `player`, `position`, `status` (OUT / DOUBTFUL / QUESTIONABLE / PROBABLE),
  optional `starter` (true/false), optional `source` note.
- Only `OUT` is applied. Role comes from position: QB -> QB; WR/RB/TE -> STAR_SKILL only with
  `"starter": true`; OL/OT/OG/C -> OL; CB/S/DB -> DB; anything else is listed, not applied.
- This file overrides any injury rows in the lines intake. Each card note shows the source.
