# Optional open-source creative tools — SportsEdge / Audit Trail Docs

Owner phone-first. Evaluate **rembg** for local background removal of owner-licensed graphics, and **Buzz** for local speech transcription and caption drafts. Open WebUI can be evaluated separately as a private research UI; LibreTranslate only when multilingual output is needed. FinceptTerminal is not a verified sports data source and must not be wired into betting markets.

No installation, runtime, external API authorization or asset processing is claimed by this PR. Verify each upstream project's current license, model-weight license, device/runtime needs and security posture before deployment. Server-side execution would require an authorized private runner; GitHub Actions must not upload user media to public logs/artifacts.

`tools/media/asset_intake_contract.py` enforces original media SHA, basic format signature, owner permission, explicit license and local timestamp consistency, with a hard publish-approval false gate. It does not authenticate ownership, inspect image contents, perform antivirus scanning or establish legal rights. Human review is required before publication.

Never include sportsbook receipts, credentials, personal records or unpublished picks in public graphics, commits or CI artifacts. Frozen v5, risk policy and Issue #10 remain untouched; all sports research PAPER/0u.
