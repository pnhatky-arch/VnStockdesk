"""Atomic JSON and cross-process locks on Windows and macOS/Linux."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, default=str)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def atomic_csv(path, frame, *, index=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(path.suffix + ".lock"), wait_seconds=10):
        fd, name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
        os.close(fd)
        try:
            frame.to_csv(name, index=index)
            os.replace(name, path)
        finally:
            if os.path.exists(name): os.unlink(name)


@contextmanager
def file_lock(path, wait_seconds=0):
    path = _local_lock_path(Path(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        deadline = time.monotonic() + max(0, float(wait_seconds))
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline: raise
                time.sleep(.025)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _local_lock_path(path):
    """Keep advisory locks off cloud-synchronised filesystems.

    Google Drive can intermittently reject ``flock`` from a Finder-launched
    process even though the underlying data file remains readable/writable.
    A lock is runtime state, not user data, so it belongs in the local runtime
    directory and must never be synchronised between computers.
    """
    resolved = str(path.expanduser().absolute())
    cloud_markers = (
        "/My Drive/",
        "/Drive của tôi/",
        "/Library/CloudStorage/GoogleDrive-",
        "\\My Drive\\",
        "\\Drive của tôi\\",
    )
    if not any(marker.casefold() in resolved.casefold() for marker in cloud_markers):
        return path

    if sys.platform == "darwin":
        runtime_root = Path.home() / "Library/Application Support/VnStockDesk/runtime"
    elif os.name == "nt":
        runtime_root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local")) / "VnStockDesk/runtime"
    else:
        runtime_root = Path(os.getenv("XDG_RUNTIME_DIR", tempfile.gettempdir())) / "vnstockdesk"
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:24]
    return runtime_root / "locks" / f"{digest}.lock"
