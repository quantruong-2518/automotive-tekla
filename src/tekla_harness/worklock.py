"""worklock: one writer per work folder (ADR-0011).

Every command that writes a work folder holds an exclusive OS lock on `<work>/.harness.lock` for its whole
run: `fcntl.flock(LOCK_EX | LOCK_NB)` on POSIX (not lockf / fcntl record locks: those belong to the
process, so a second descriptor in the same process would not conflict and closing any descriptor of the
file would drop the lock), `msvcrt.locking(LK_NBLCK)` on byte 0 on Windows.

  * A held lock raises WorkLockBusy (exit 3) at once, naming the holder from `.harness.lock.json` (pid,
    host, command, start time; informational, may be stale or missing). No waiting, no timeout.
  * The OS releases the lock on any process exit, so there is no stale-lock rule. Windows may release a
    terminated process's lock with a delay (LockFile remarks): the message says "retry shortly".
  * Any other lock failure (ENOLCK, EOPNOTSUPP, EINVAL, ...) raises WorkLockError (exit 3): never run
    unlocked.
  * The lock file is opened without truncation and never deleted. The holder record is removed just before
    unlocking (best effort, reported on stderr).
  * Not reentrant: take it once at command entry (cli.main, run_intake), never in library code; a second
    acquisition in the same process conflicts with the first.
  * WSL and Windows locks do not see each other: use a work folder from one OS.
"""

from __future__ import annotations

import errno
import json
import os
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOCK_FILE = ".harness.lock"
HOLDER_FILE = ".harness.lock.json"
EXIT_ENV = 3

if sys.platform == "win32":
    import msvcrt

    _BUSY = frozenset({errno.EACCES, errno.EDEADLOCK})

    def _lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)  # the region starts at the current position
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    _BUSY = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK})

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class WorkLockError(Exception):
    """The work folder cannot be locked; `exit_code` is the CLI exit code (3, environment)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.exit_code = EXIT_ENV


class WorkLockBusy(WorkLockError):
    """Another harness command holds the work folder's lock. `holder`: its record, None when unreadable."""

    def __init__(self, work: Path, holder: dict[str, Any] | None) -> None:
        if holder is None:
            who = f"holder unknown ({HOLDER_FILE} missing or unreadable)"
        else:
            who = (
                f"`harness {holder.get('command', '?')}` (pid {holder.get('pid', '?')} on "
                f"{holder.get('host', '?')}, since {holder.get('started', '?')})"
            )
        super().__init__(
            f"work folder {work} is in use by another harness command: {who}. Nothing was run or written; "
            "retry shortly, once that command has finished (no waiting, ADR-0011)"
        )
        self.holder = holder


def read_holder(work: Path) -> dict[str, Any] | None:
    """The holder record, or None when it is missing or unreadable (it is informational only)."""
    try:
        data = json.loads((Path(work) / HOLDER_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_holder(work: Path, command: str) -> None:
    record = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "command": command,
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    path = work / HOLDER_FILE
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(record) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:  # informational: a refused contender then reports the holder as unknown
        print(f"warning: cannot write the lock holder record {path}: {exc}", file=sys.stderr)


def _remove_holder(work: Path) -> None:
    try:
        (work / HOLDER_FILE).unlink(missing_ok=True)
    except OSError as exc:
        print(f"warning: cannot remove the lock holder record {work / HOLDER_FILE}: {exc}", file=sys.stderr)


@contextmanager
def work_lock(work: Path, command: str) -> Iterator[None]:
    """Hold the work folder's write lock for the body. Raises WorkLockBusy or WorkLockError (exit 3)."""
    work = Path(work)
    path = work / LOCK_FILE
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    except OSError as exc:
        raise WorkLockError(f"cannot open the work-folder lock {path}: {exc}") from exc
    try:
        try:
            _lock(fd)
        except OSError as exc:
            if exc.errno in _BUSY:  # BlockingIOError is EAGAIN / EWOULDBLOCK
                raise WorkLockBusy(work, read_holder(work)) from exc
            raise WorkLockError(
                f"cannot lock {path} ({exc}): this filesystem does not support the work-folder lock; "
                "refusing to write unlocked (ADR-0011). Use a work folder on a local disk"
            ) from exc
        try:
            _write_holder(work, command)
            yield
        finally:
            _remove_holder(work)
            try:
                _unlock(fd)
            except OSError as exc:  # closing the descriptor below releases it anyway
                print(f"warning: cannot unlock {path} explicitly: {exc}", file=sys.stderr)
    finally:
        os.close(fd)
