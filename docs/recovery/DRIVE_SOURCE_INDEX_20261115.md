# Verified high-value Drive recovery index — Nov 15, 2026

This is a selective source index, not a copy of every Drive item. Exact-byte source integrity is stated only when independently reproduced.

| Source | Drive file ID / pointer | Verified local ZIP SHA-256 | GitHub destination / status |
| --- | --- | --- | --- |
| Full baseline bundle (38 files) | `1bapT2Jukizo-a64aBekQCnXEeleLYKSP` | `6bfbba25a35f6312d0e8b856f6527b7cd506020d87386e29a14c714600a0ad22` | PR #1 merged |
| R5 integrated engineering source | `1II-xbSgN0EAuU5Ag-E_EzWBv_axewHCc` | `5ffad3d9a61b629aee8da2f2687f945ad46ab0b9e44a63b404a92535107eeb77` | PR #5 merged: 87 synthetic checks and guards |
| Independent closure source | `1ubZMxVogRSzilwZda8BAweQoZLfTha3L` | `708a0bc27a4e6b40812d337e82ed1ceeadb557b315061b7655cbcc190b8122a1` | Selected portable source in PR #5 |
| Frozen v5 engine | `19nMdTh6TiIqCsOq4fXBTzDfDsJNVCWJO` | Standalone source SHA-256 `72ccaad75b066315f31137f40556321b7057a28119760a6a0b1c2e28da78e02f` | `engine/sportsedge_v5.py` |
| CFB synthetic generator and original fixtures | `1I3pjwMyEcidbQ-O-E0g2qHEZEnWSUDpM`, `10lgrem4DEc-_kB9X7AwoRzLVlDfIGqtf` | Not independently SHA-pinned | PR #2 uses generator; PR #4 has original fixture copies, **not merged** |
| NBA / MLB original synthetic fixture bundles | `1VwQRi3l0ZLIiCcGwXKk5yjjc0t2a8G0X`, `1hDffLZj9QTPgZxchtPuR2EfMr2mQr1dP` | Not independently SHA-pinned | PR #2 synthetic tests; originals remain in Drive |
| RUN IT v2.1 correction | `1TqePW6NrfnUcMTfbED9S5f6YQK7mBADa` | Not independently SHA-pinned | `docs/rules/RUN_IT_V2_1_MANDATORY_RESTORATION.md` baseline |
| Release pointers and open gates | `1NkwNJMBQ0TIXmgucYYluvL8MpRYqHqqL` | Not independently SHA-pinned | Remaining gates listed in audit notes |
| Hourly private logs, complete historical inputs, graded cards, capture and close CSVs, GRIND_QUEUE.md, RELAY_LOG.md | Shared SportsEdge Drive root and NOTES | Mixed; not exhaustively audited | **Not copied** to public GitHub |

## Old GitHub boundary
Prior `isaacrome21-sys/SportsEdge` repository returned 404 through available account access. The narrative in `docs/history/PROJECT_HISTORY.md` is an explicitly **unverified historical reconstruction**; no old Git commits or PRs are asserted to have been imported.
