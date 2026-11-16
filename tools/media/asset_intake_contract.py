"""Private media intake preflight for optional rembg/Buzz content workflows."""
import hashlib
from datetime import datetime, timezone

class MediaHold(ValueError):
    pass

ALLOWED = {"image/png", "image/jpeg", "image/webp", "audio/wav", "audio/mpeg"}
MAX_BYTES = 25_000_000

def utc(s):
    if not isinstance(s, str) or not s.endswith("Z"):
        raise MediaHold("UTC_REQUIRED")
    try:
        d = datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError as exc:
        raise MediaHold("UTC_REQUIRED") from exc
    return d.astimezone(timezone.utc)

def preflight(raw, receipt, *, now_utc):
    """Checks only user-authorized media; never uploads, executes models or publishes."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise MediaHold("MEDIA_BYTES_INVALID")
    if not isinstance(receipt, dict):
        raise MediaHold("RECEIPT_INVALID")
    if receipt.get("media_type") not in ALLOWED:
        raise MediaHold("MEDIA_TYPE_NOT_ALLOWED")
    if receipt.get("sha256") != hashlib.sha256(raw).hexdigest():
        raise MediaHold("MEDIA_SHA_MISMATCH")
    if receipt.get("permission") != "OWNER_AUTHORIZED" or receipt.get("publish_approved") is not False:
        raise MediaHold("PERMISSION_OR_PUBLISH_GATE")
    if receipt.get("contains_private_odds") is not False or receipt.get("contains_secrets") is not False:
        raise MediaHold("PRIVATE_DATA_NOT_CLEARED")
    if not isinstance(receipt.get("license"), str) or not receipt["license"].strip():
        raise MediaHold("LICENSE_UNRESOLVED")
    if not isinstance(receipt.get("asset_id"), str) or not receipt["asset_id"].strip():
        raise MediaHold("ASSET_ID_REQUIRED")
    captured, now = utc(receipt.get("captured_utc")), utc(now_utc)
    if captured > now:
        raise MediaHold("FUTURE_CAPTURE")
    if receipt["media_type"] == "image/png" and not raw.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
        raise MediaHold("MEDIA_SIGNATURE_MISMATCH")
    if receipt["media_type"] == "image/jpeg" and not raw.startswith(b"\\xff\\xd8\\xff"):
        raise MediaHold("MEDIA_SIGNATURE_MISMATCH")
    if receipt["media_type"] == "image/webp" and not (raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"):
        raise MediaHold("MEDIA_SIGNATURE_MISMATCH")
    if receipt["media_type"] == "audio/wav" and not (raw.startswith(b"RIFF") and raw[8:12] == b"WAVE"):
        raise MediaHold("MEDIA_SIGNATURE_MISMATCH")
    if receipt["media_type"] == "audio/mpeg" and not (raw.startswith(b"ID3") or raw[:1] == b"\\xff"):
        raise MediaHold("MEDIA_SIGNATURE_MISMATCH")
    return {"status": "PRIVATE_MEDIA_READY_FOR_HUMAN_REVIEW", "publish_approved": False,
            "sha256": receipt["sha256"], "asset_id": receipt["asset_id"],
            "media_type": receipt["media_type"]}
