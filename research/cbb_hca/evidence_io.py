"""Private no-replace atomic evidence publication; no source authentication claim."""
import hashlib
import os
from pathlib import Path
import tempfile


def atomic_publish(path, raw, *, before_publish=None):
    if type(raw) is not bytes or not raw:
        raise ValueError("NONEMPTY_BYTES_REQUIRED")
    target=Path(os.path.abspath(os.path.expanduser(str(path))))
    repo=Path(__file__).resolve().parents[2]
    for p in (target,target.resolve()):
        if p==repo or repo in p.parents:
            raise ValueError("REPOSITORY_NOT_PRIVATE_STORAGE")
    parent=target.parent
    if parent!=parent.resolve():
        raise ValueError("SYMLINKED_DIRECTORY_FORBIDDEN")
    parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if parent.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_DIRECTORY_REQUIRED")
    temp=None
    try:
        fd,name=tempfile.mkstemp(prefix=".cbb-stage-",dir=parent)
        temp=Path(name)
        with os.fdopen(fd,"wb") as f:
            os.fchmod(f.fileno(),0o600)
            if f.write(raw)!=len(raw):
                raise OSError("SHORT_WRITE")
            f.flush();os.fsync(f.fileno())
        if temp.read_bytes()!=raw:
            raise OSError("STAGED_BYTES_MISMATCH")
        if before_publish is not None:
            before_publish()
        # Same-filesystem hard link publishes complete bytes and fails if the
        # target exists. No rename/replace that could overwrite prior evidence.
        os.link(temp,target,follow_symlinks=False)
        directory_fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
