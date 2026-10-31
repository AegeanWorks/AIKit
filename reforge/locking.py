"""A per-project advisory lock so one project never runs two Reforge operations at once."""

import os
import time
from contextlib import contextmanager
from pathlib import Path

from reforge.errors import ReforgeError

LOCK_REL = Path(".aikit") / "reforge.run.lock"
# A crashed Reforge must not block a project for ever, but a real audit may run its gates for
# minutes. An hour is far longer than the gate timeout and short enough to recover unattended.
STALE_SECONDS = 3600.0


def lock_path(root: Path) -> Path:
    """The lock inside the audited root itself, resolved so one repository has one lock.

    A relative target (`demo`, `./demo`), a trailing separator and a Windows case variant all
    name the same checkout; resolving first keeps them from creating two locks for one project
    while leaving every other project on its own lock.
    """
    return Path(root).expanduser().resolve() / LOCK_REL


@contextmanager
def run_lock(root: Path, wait_seconds: float = 0.2):
    """Hold the project's run lock; refuse immediately when another process already holds it."""
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    acquired = False
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"{os.getpid()}:{int(time.time())}\n")
                handle.flush()
            acquired = True
            break
        except (FileExistsError, PermissionError):
            # Windows raises EACCES while another process removes its lock; treat it as contention.
            try:
                age = time.time() - path.stat().st_mtime
                if age > STALE_SECONDS:
                    path.unlink()
                    continue
            # hygiene: allow concurrent removal; the retry decides
            except OSError:
                pass
            if time.monotonic() >= deadline:
                owner = ""
                try:
                    owner = path.read_text(encoding="utf-8").strip()
                # hygiene: allow lock-owner text is optional
                except OSError:
                    pass
                raise ReforgeError(
                    f"Another Reforge operation is active in {Path(root)}.",
                    "this project has an audit or repair in progress"
                    + (f" (pid/time {owner})" if owner else "")
                    + "; a second run would interleave state and patches.",
                    "wait for it to finish. If no Reforge process is alive, remove "
                    f"{path} and retry. Other projects use their own locks and are unaffected.",
                )
            time.sleep(0.02)
    try:
        yield
    finally:
        if acquired:
            try:
                path.unlink()
            except OSError:  # hygiene: allow release is best-effort after the operation
                pass
