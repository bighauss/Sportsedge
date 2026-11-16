# Private media preflight CLI (no third-party service)

For a trusted private Linux/macOS runner with Python 3.12 and authorized owner-owned asset, store asset and JSON receipt **outside the public checkout** with mode 0600. Use `python -m tools.media.private_asset_cli --asset /private/asset.png --receipt /private/receipt.json`. The CLI reads files locally with no-follow, verifies basic media signature, SHA-256, permission/license claims, privacy flags and capture time. It prints only a compact result, no file paths or media content, and never publishes.

Receipt schema: `asset_id`, `media_type`, `sha256`, `permission: OWNER_AUTHORIZED`, `publish_approved: false`, `contains_private_odds: false`, `contains_secrets: false`, `license`, `captured_utc` (UTC Z). Claim fields are not independently verified rights. This is NOT a content sanitizer, malware scan or provider authorization. Use only on a trusted runner, with private parent directories and without GitHub Actions artifact uploads.

No rembg/Buzz installed by this PR. A later separate integration may invoke a pinned, license-reviewed local model **after** preflight and human approval; no auto-posting.
