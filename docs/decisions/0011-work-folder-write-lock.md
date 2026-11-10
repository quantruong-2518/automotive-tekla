# 0011. Work-folder write lock

- Status: proposed
- Date: 2026-11-07
- Decided by: orchestrator default D5 of tool wave 2 (reversible), pending engineer approval

## Context

Every `harness` command that writes a work folder reads `question-registry.json` and
`answers.json`, changes them in memory, then writes them back (questions.py: registry first,
documents after). Two such commands on the same work folder at the same time (two agents, or an
agent and the engineer) can each read the old registry and the second write loses the first
one's question ids or answers. Nothing today stops that. Tool wave 2 adds more writers
(`harness ask --supplement`, file-set answers), so the window grows.

What the operating systems guarantee (primary sources, read 2026-11-07):

- **POSIX `flock(2)`** ([man7 flock(2)](https://man7.org/linux/man-pages/man2/flock.2.html)):
  the lock belongs to the open file description. Duplicates made by `dup(2)` or `fork(2)` share
  it; descriptors from separate `open()` calls "are treated independently by flock()", so a lock
  request through a second descriptor "may be denied by a lock that the calling process has
  already placed via another file descriptor". With `LOCK_NB` a held lock fails with
  `EWOULDBLOCK` ("The file is locked and the LOCK_NB flag was selected"). The lock is released by
  an explicit unlock or "when all such file descriptors have been closed", which includes process
  exit. `ENOLCK`: "The kernel ran out of memory for allocating lock records". Over NFS, Linux
  emulates `flock()` as `fcntl(2)` byte-range locks; over CIFS (Linux 5.5+) locks are mandatory.
- **POSIX record locks (`fcntl`/`lockf`)** ([man7 fcntl_locking(2)](https://man7.org/linux/man-pages/man2/fcntl_locking.2.html),
  "Advisory record locking"): "The record locks described above are associated with the
  process"; "If a process closes any file descriptor referring to a file, then all of the
  process's locks on that file are released"; they "are not inherited by a child created via
  fork(2)". A second descriptor in the same process therefore never conflicts with the first,
  and any library code that opens and closes the lock file silently drops the lock.
- **Python `fcntl.flock`** ([docs.python.org fcntl](https://docs.python.org/3/library/fcntl.html)):
  "Perform the lock operation operation on file descriptor fd … See the Unix manual flock(2) for
  details. (On some systems, this function is emulated using fcntl().) If the flock() call
  fails, an OSError exception is raised." With `LOCK_NB` the `errno` is `EACCES` or `EAGAIN`
  (documented under `lockf`, "for portability, check for both values"); Python maps
  `EAGAIN`/`EWOULDBLOCK` to `BlockingIOError`.
- **Python `msvcrt.locking`** ([docs.python.org msvcrt](https://docs.python.org/3/library/msvcrt.html)):
  "Lock part of a file based on file descriptor fd from the C runtime. Raises OSError on failure.
  The locked region of the file extends from the current file position for nbytes bytes, and may
  continue beyond the end of the file." `LK_NBLCK`: "If the bytes cannot be locked, OSError is
  raised." `LK_LOCK` retries ten times one second apart before failing.
- **CRT `_locking`** ([Microsoft Learn `_locking`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking)):
  "Locking bytes in a file prevents access to those bytes by other processes. All locking or
  unlocking begins at the current position of the file pointer". On failure `errno` is
  `EACCES` ("Locking violation (file already locked or unlocked)"), `EBADF`, `EINVAL`, or
  `EDEADLOCK` (only `_LK_LOCK`/`_LK_RLCK` after 10 attempts). Remarks: "Regions should be locked
  only briefly and should be unlocked before closing a file or exiting the program."
- **Win32 `LockFile`** ([Microsoft Learn LockFile](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfile)),
  which `_locking` is built on: "If the locking process opens the file a second time, it cannot
  access the specified region through this second handle until it unlocks the region." "You can
  lock bytes that are beyond the end of the current file." "If a process terminates with a
  portion of a file locked or closes a file that has outstanding locks, the locks are unlocked by
  the operating system. However, the time it takes for the operating system to unlock these locks
  depends upon available system resources." The delayed-release note is on this page, not on the
  `_locking` page.

## Decision

Every harness command that writes a work folder takes an exclusive OS lock on
`work/.harness.lock` (flock on POSIX, msvcrt byte lock on Windows) for its whole run. A held lock
means exit 3 with the holder read from `.harness.lock.json`; there is no waiting and no timeout.
The OS frees the lock on any process exit, so there is no stale-lock rule. The lock file is never
deleted. Read-only commands do not lock. A filesystem without lock support fails closed (exit 3).
Locks do not cross the WSL/Windows boundary; a work folder is used from one OS. One project runs
one writer at a time; projects run in parallel.

Details:

1. **Mechanism.** POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`; `BlockingIOError` (or `EACCES`,
   `EAGAIN`) means held. Not `lockf`/`fcntl` record locks: they are per process, so a second
   descriptor in the same process would not conflict and closing any descriptor of the file would
   drop the lock. Windows: `msvcrt.locking(fd, LK_NBLCK, 1)` on byte 0 (seek to 0 first, also
   before `LK_UNLCK`); `OSError` with `EACCES` (or `EDEADLOCK`) means held. Byte 0 may lie beyond
   the end of the empty lock file, which both `_locking` and `LockFile` allow.
2. **Fail closed.** Any other `OSError` from the lock call (`ENOLCK`, `EOPNOTSUPP`, `EINVAL`, …)
   is exit 3 with its own message; the command never runs unlocked.
3. **Holder record.** After acquiring, the holder writes `.harness.lock.json` (pid, host,
   platform, command name, start time; never argv, which holds absolute paths). A refused command reads it
   for its message; it is informational and may be stale or missing. The holder removes it just
   before unlocking (best effort, reported on stderr when it fails), so a finished command leaves
   no file a work-folder snapshot would see. The lock file itself is opened without truncation and
   never deleted: deleting it would let a later process lock a new inode while an older one still
   holds the old one. A record whose `platform` is another OS's (`win32` vs `linux`) refuses the
   lock with exit 3 even though this OS's lock was free: it is the only trace of a writer on the
   other side of the WSL/Windows boundary. The message says to delete the record when nothing runs
   there. A record from this OS, or one without a platform, is stale and is replaced.
4. **Not reentrant.** The lock is taken once, at command entry: in `cli.main` for read-structure,
   callouts, marks, grid-system, answer, ask, finding add/withdraw and questions-md, and inside
   `run_intake` after its usage checks (and after creating the work folder). Library functions
   never take it: a second acquisition in the same process conflicts with the first (flock and
   LockFile both treat a second open independently).
5. **Not locked:** status, list-sheets, sheet-text, find-text, finding list, dimensions (read
   only), and the path-based tools (validate, detect, dwg2dxf, read-dxf, extract-*, env-check):
   they write only where `--out` / `--out-dir` / `--cache-dir` point and never touch the registry
   or answers, even when that path lies inside a work folder. `cli.UNLOCKED_COMMANDS` lists them; a
   test fails when a subcommand is on no list. A locked command whose work folder does not exist is
   refused by `cli.main` with exit 2 before it runs, so it never runs unlocked.
6. **Contention message.** Exit 3, naming the holder, with "retry shortly": on Windows the OS may
   release the lock of a terminated process with a delay (LockFile remarks). The `_locking`
   advice to lock "only briefly" is about blocking other readers of the locked bytes; nobody reads
   byte 0 of the lock file, so holding it for a command's run is harmless, and the lock is
   unlocked explicitly before the file is closed.

## Consequences

- Two writers on one work folder can no longer interleave their registry and answers writes; the
  second one stops at once with exit 3 and the first one's command name and pid.
- Agents running in parallel must use different work folders (projects), or wait and retry.
- A work folder on a filesystem without locks (some network shares) cannot be written; the error
  says so.
- A work folder shared between WSL and Windows is only protected on a best-effort basis: WSL's
  Linux `flock` and the Windows byte lock do not see each other (checked on a WSL2 /mnt/c drvfs
  mount, 2026-11-08), so only the holder record's `platform` (decision 3) stops the second writer,
  and two writers starting at the same instant can still miss each other. Use one OS per work folder.
- On Windows, an unlocked reader (status, sheet-text) that has a work-folder file open can make a
  writer's atomic replace of that file fail (Python opens files without delete sharing). This is
  older than this ADR and is tracked in `requests-to-improve.md`.
- `.harness.lock` stays in every written work folder (empty, harmless).
- Tests: in-process second descriptor and a subprocess holder, on both CI operating systems
  (`tests/test_worklock.py`).
