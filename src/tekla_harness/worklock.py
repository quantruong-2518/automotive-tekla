"""worklock: one writer per work folder (ADR-0011).

Every command that writes a work folder holds an exclusive OS lock on `<work>/.harness.lock` for its whole
run: `fcntl.flock(LOCK_EX | LOCK_NB)` on POSIX (not lockf / fcntl record locks: those belong to the
process, so a second descriptor in the same process would not conflict and closing any descriptor of the
file would drop the lock), `msvcrt.locking(LK_NBLCK)` on byte 0 on Windows.

  * A held lock raises WorkLockBusy (exit 3), naming the holder from `.harness.lock.json` (pid, host,
    command, start time; informational, may be stale or missing). By default it raises at once (wait 0).
    With `wait` seconds (amendment 2026-11-20, part mode) the command retries every 0.2 s until the wait has
    passed, then raises; a wait that ends in success prints one stderr line naming the holder. `lock_wait`
    is the one rule every lock taker uses: HARNESS_LOCK_WAIT, else 60 s when anything exists at
    `parts/manifest.json`, else 0.
  * The OS releases the lock on any process exit, so there is no stale-lock rule. Windows may release a
    terminated process's lock with a delay (LockFile remarks): the message says "retry shortly".
  * Any other lock failure (ENOLCK, EOPNOTSUPP, EINVAL, ...) raises WorkLockError (exit 3): never run
    unlocked, never retried.
  * The lock file is opened without truncation and never deleted. The holder record is removed just before
    unlocking (best effort, reported on stderr).
  * Not reentrant: take it once at command entry (cli.main, run_intake), never in library code; a second
    acquisition in the same process conflicts with the first.
  * WSL and Windows locks do not see each other: use a work folder from one OS. As a best-effort check,
    the holder record names its `platform`, and a record from the other OS refuses the lock (exit 3), never
    after a wait. Two writers starting at the same instant from both OSes can still miss each other.
"""

from __future__ import annotations

import errno
import json
import math
import os
import socket
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tekla_harness.parts import ManifestAccessError, manifest_present

LOCK_FILE = ".harness.lock"
HOLDER_FILE = ".harness.lock.json"
EXIT_ENV = 3
EXIT_USAGE = 2
WAIT_ENV = "HARNESS_LOCK_WAIT"
PART_MODE_WAIT = 60.0  # seconds a command waits in a work folder with anything at parts/manifest.json
RETRY_INTERVAL = 0.2  # seconds between two tries of a held lock

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

    def __init__(self, work: Path, holder: dict[str, Any] | None, waited: float = 0.0) -> None:
        if holder is None:
            who = f"holder unknown ({HOLDER_FILE} missing or unreadable)"
        else:
            who = (
                f"`harness {holder.get('command', '?')}` (pid {holder.get('pid', '?')} on "
                f"{holder.get('host', '?')}, since {holder.get('started', '?')})"
            )
        how = f"waited {waited:g} s, ADR-0011" if waited > 0 else "no waiting, ADR-0011"
        super().__init__(
            f"work folder {work} is in use by another harness command: {who}. Nothing was run or written; "
            f"retry shortly, once that command has finished ({how})"
        )
        self.holder = holder
        self.waited = waited


class WorkLockUsage(WorkLockError):
    """HARNESS_LOCK_WAIT is not a number of seconds >= 0 (exit 2, raised before the lock is touched)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.exit_code = EXIT_USAGE


def lock_wait(work: Path) -> float:
    """Seconds a command waits for the work folder's lock: HARNESS_LOCK_WAIT when set (a number >= 0, else
    WorkLockUsage), else 60 when anything exists at `<work>/parts/manifest.json` (part mode: the shared
    `parts.manifest_present`), else 0. A manifest path that cannot be checked raises WorkLockError
    (exit 3)."""
    text = os.environ.get(WAIT_ENV)
    if text is not None:
        try:
            seconds = float(text)
        except ValueError:
            seconds = math.nan
        if not math.isfinite(seconds) or seconds < 0:
            raise WorkLockUsage(
                f"{WAIT_ENV}={text!r} is not a number of seconds >= 0: nothing was run or written"
            )
        return seconds
    try:
        present = manifest_present(Path(work))
    except ManifestAccessError as exc:
        raise WorkLockError(f"{exc}: nothing was run or written") from exc
    return PART_MODE_WAIT if present else 0.0


def read_holder(work: Path) -> dict[str, Any] | None:
    """The holder record, or None when it is missing or unreadable (it is informational only)."""
    try:
        data = json.loads((Path(work) / HOLDER_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _foreign_holder(work: Path) -> dict[str, Any] | None:
    """A holder record another OS wrote (its `platform` differs from this one), else None.

    WSL flock and Windows byte locks do not see each other on one NTFS folder, so the OS lock just taken
    proves nothing about a writer on the other side; its record is the only trace. A record from this OS,
    or one without a platform, is stale here: this OS's lock was free."""
    holder = read_holder(work)
    if holder is None or holder.get("platform") in (None, sys.platform):
        return None
    return holder


def _foreign_error(work: Path, foreign: dict[str, Any]) -> WorkLockError:
    return WorkLockError(
        f"work folder {work} has a lock holder record from another OS ({foreign.get('platform')}: "
        f"`harness {foreign.get('command', '?')}`, pid {foreign.get('pid', '?')} on "
        f"{foreign.get('host', '?')}, since {foreign.get('started', '?')}). WSL and Windows locks "
        "do not see each other, so nothing was run. Use this work folder from one OS only; if no "
        f"harness command is running there, delete {work / HOLDER_FILE} and retry (ADR-0011)"
    )


def _write_holder(work: Path, command: str) -> None:
    record = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "platform": sys.platform,
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


def _lock_waiting(fd: int, work: Path, path: Path, wait: float) -> tuple[float | None, dict[str, Any] | None]:
    """Take the OS lock, retrying a held one every RETRY_INTERVAL until `wait` seconds have passed.
    Returns (None, None) when the first try succeeded, else the seconds waited and the holder record read
    at the first refusal. An error other than "held" raises WorkLockError at once; a wait that runs out
    raises WorkLockBusy."""
    started = time.monotonic()
    refused = False
    holder: dict[str, Any] | None = None
    while True:
        try:
            _lock(fd)
            return (time.monotonic() - started, holder) if refused else (None, None)
        except OSError as exc:
            if exc.errno not in _BUSY:  # BlockingIOError is EAGAIN / EWOULDBLOCK
                raise WorkLockError(
                    f"cannot lock {path} ({exc}): this filesystem does not support the work-folder lock; "
                    "refusing to write unlocked (ADR-0011). Use a work folder on a local disk"
                ) from exc
            record = read_holder(work)
            if record is not None and record.get("platform") not in (None, sys.platform):
                raise _foreign_error(work, record) from exc  # the other OS's lock is invisible: never wait
            if not refused:
                refused, holder = True, record  # the record of the command we wait for
            remaining = wait - (time.monotonic() - started)
            if remaining <= 0:
                raise WorkLockBusy(work, holder, wait) from exc
            time.sleep(min(RETRY_INTERVAL, remaining))


@contextmanager
def work_lock(work: Path, command: str, wait: float = 0.0) -> Iterator[None]:
    """Hold the work folder's write lock for the body. A held lock is retried for `wait` seconds (0: no
    wait). Raises WorkLockBusy or WorkLockError (exit 3)."""
    work = Path(work)
    path = work / LOCK_FILE
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    except OSError as exc:
        raise WorkLockError(f"cannot open the work-folder lock {path}: {exc}") from exc
    try:
        waited, holder = _lock_waiting(fd, work, path, wait)
        foreign = _foreign_holder(work)
        if foreign is not None:  # leave its record; closing fd below releases our OS lock
            raise _foreign_error(work, foreign)
        if waited is not None:
            who = (
                "unknown holder"
                if holder is None
                else f"harness {holder.get('command', '?')} (pid {holder.get('pid', '?')})"
            )
            print(f"lock: waited {waited:.1f} s for {who}", file=sys.stderr)
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
