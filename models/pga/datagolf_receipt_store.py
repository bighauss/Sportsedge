"""Write DataGolf capture evidence atomically without storing credentials or URLs."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

def save_capture(receipt, root):
    if not isinstance(receipt, dict):
        raise ValueError("INVALID_RECEIPT")
    raw = receipt.get("raw_bytes")
    if not isinstance(raw, bytes):
        raise ValueError("RAW_BYTES_REQUIRED")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != receipt.get("source_sha256"):
        raise ValueError("SOURCE_HASH_MISMATCH")
    ts = receipt.get("captured_utc")
    if not isinstance(ts, str) or len(ts) != 20 or not ts.endswith("Z"):
        raise ValueError("INVALID_CAPTURE_TIME")
    endpoint = receipt.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.replace("_", "").isalnum():
        raise ValueError("INVALID_ENDPOINT")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("SYMLINK_ROOT_NOT_ALLOWED")
    name = ts.replace(":", "").replace("-", "") + "_" + endpoint + "_" + digest[:16]
    metadata = {"endpoint": endpoint, "captured_utc": ts,
                "source_sha256": digest, "status": "RAW_PROVIDER_CAPTURE_UNVERIFIED",
                "raw_filename": name + ".json"}
    raw_path = root / (name + ".json")
    meta_path = root / (name + ".receipt.json")
    for path, content in ((raw_path, raw), (meta_path, json.dumps(metadata, sort_keys=True).encode())):
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError("CAPTURE_COLLISION")
            continue
        fd, temp = tempfile.mkstemp(prefix=".capture-", dir=root)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists():
                if path.read_bytes() != content:
                    raise ValueError("CAPTURE_COLLISION")
            else:
                os.replace(temp, path)
                temp = None
        finally:
            if temp is not None and os.path.exists(temp):
                os.unlink(temp)
    return {"raw_path": str(raw_path), "receipt_path": str(meta_path),
            "source_sha256": digest, "status": "CAPTURE_STORED_UNVERIFIED"}
