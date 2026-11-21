"""Publish one complete encrypted NCAA archive from a private workflow directory."""
import argparse
import io
import os
from pathlib import Path
import tarfile
import tempfile

from cryptography.fernet import Fernet


def export(root: Path, target: Path, cipher: Fernet):
    entries = sorted(root.iterdir())
    if not entries:
        raise ValueError("EMPTY_PRIVATE_ARCHIVE")
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode="w") as archive:
        for path in entries:
            if path.is_symlink() or not path.is_file():
                raise ValueError("UNEXPECTED_PRIVATE_ARCHIVE_ENTRY")
            archive.add(path, arcname=path.name, recursive=False)
    ciphertext = cipher.encrypt(bundle.getvalue())
    # Same filesystem, exclusive publication. A failed write leaves no target.
    with tempfile.NamedTemporaryFile(dir=target.parent) as staging:
        staging.write(ciphertext)
        staging.flush()
        os.fsync(staging.fileno())
        os.link(staging.name, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    export(args.root, args.target, Fernet(os.environ["SPORTSEDGE_ARCHIVE_FERNET_KEY"].encode()))
