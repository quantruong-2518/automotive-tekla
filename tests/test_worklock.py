"""worklock: one writer per work folder (ADR-0011).

The lock is an OS lock (flock on POSIX, msvcrt byte lock on Windows): a second open file in the same
process conflicts with the first, and a child process holding it blocks the parent. Both CI operating
systems run every test here.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from _dxf_fixtures import build_set
from tekla_harness import worklock
from tekla_harness.cli import main
from tekla_harness.intake import run_intake
from tekla_harness.structure import read_structure
from tekla_harness.worklock import (
    HOLDER_FILE,
    LOCK_FILE,
    PART_MODE_WAIT,
    WorkLockBusy,
    WorkLockError,
    lock_wait,
    work_lock,
)

PROJECT = "demo-lock"
HOLDER_SCRIPT = (
    "import os\n"
    "import sys\n"
    "from pathlib import Path\n"
    "from tekla_harness.worklock import work_lock\n"
    "with work_lock(Path(sys.argv[1]), 'holder-test'):\n"
    "    print('ready', os.getpid(), flush=True)\n"
    "    sys.stdin.readline()\n"
)


def snapshot(work: Path) -> dict[str, bytes]:
    """Every file's bytes except the lock file's: its bytes mean nothing, and on Windows a held byte lock
    denies reads through another handle (LockFile remarks)."""
    return {
        p.relative_to(work).as_posix(): p.read_bytes()
        for p in sorted(work.rglob("*"))
        if p.is_file() and p.name != LOCK_FILE
    }


def acquire_eventually(work: Path, seconds: float = 15.0) -> None:
    """Windows may release a dead process's lock with a delay (LockFile remarks): poll, bounded."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            with work_lock(work, "after"):
                return
        except WorkLockBusy:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


@pytest.fixture
def holder(tmp_path):
    """A child process that holds the lock of tmp_path/work until its stdin closes."""
    work = tmp_path / "work"
    work.mkdir()
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLDER_SCRIPT, str(work)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    ready, pid = proc.stdout.readline().split()
    assert ready == "ready"
    yield work, proc, int(pid)  # the pid in the record: on Windows the Popen pid is the venv launcher
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=30)


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("lock")
    (root / "input").mkdir()
    build_set(root / "input", "set.dxf")
    work = root / "work"
    run_intake(root / "input", work, PROJECT)
    assert read_structure(work, root / "input").exit_code == 0
    return work


# --- the lock itself ------------------------------------------------------------------------------


def test_lock_file_is_created_and_survives_release(tmp_path):
    with work_lock(tmp_path, "intake"):
        assert (tmp_path / LOCK_FILE).is_file()
    assert (tmp_path / LOCK_FILE).is_file()  # never deleted (ADR-0011)


def test_holder_record_while_held_and_gone_after(tmp_path):
    with work_lock(tmp_path, "answer"):
        holder = json.loads((tmp_path / HOLDER_FILE).read_text(encoding="utf-8"))
        assert holder["pid"] == os.getpid()
        assert holder["command"] == "answer"
        assert isinstance(holder["host"], str) and holder["host"]
        assert isinstance(holder["started"], str) and holder["started"]
    assert not (tmp_path / HOLDER_FILE).exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_holder_record_names_the_platform(tmp_path):
    with work_lock(tmp_path, "answer"):
        holder = json.loads((tmp_path / HOLDER_FILE).read_text(encoding="utf-8"))
        assert holder["platform"] == sys.platform


def test_holder_record_from_another_platform_refuses_the_lock(tmp_path):
    """WSL flock and Windows byte locks do not see each other (review m1): a live holder record written
    by the other OS is the only trace, so it refuses the lock instead of running beside that writer."""
    other = "win32" if sys.platform != "win32" else "linux"
    record = {"pid": 4242, "host": "h", "command": "marks", "started": "t", "platform": other}
    (tmp_path / HOLDER_FILE).write_text(json.dumps(record), encoding="utf-8")
    ran = []
    with pytest.raises(WorkLockError) as caught, work_lock(tmp_path, "answer"):
        ran.append(True)
    assert not ran and not isinstance(caught.value, WorkLockBusy)
    message = str(caught.value)
    assert caught.value.exit_code == 3 and other in message and HOLDER_FILE in message
    assert json.loads((tmp_path / HOLDER_FILE).read_text(encoding="utf-8")) == record  # not removed
    fd = os.open(tmp_path / LOCK_FILE, os.O_RDWR)  # the refused attempt released the OS lock
    try:
        worklock._lock(fd)
        worklock._unlock(fd)
    finally:
        os.close(fd)


@pytest.mark.parametrize("platform", [None, "same"])
def test_leftover_holder_record_from_this_platform_is_replaced(tmp_path, platform):
    """A crash on this OS leaves a record behind; this OS's lock already proves it stale."""
    record: dict[str, Any] = {"pid": 4242, "host": "h", "command": "marks", "started": "t"}
    if platform:
        record["platform"] = sys.platform
    (tmp_path / HOLDER_FILE).write_text(json.dumps(record), encoding="utf-8")
    with work_lock(tmp_path, "answer"):
        assert json.loads((tmp_path / HOLDER_FILE).read_text(encoding="utf-8"))["pid"] == os.getpid()
    assert not (tmp_path / HOLDER_FILE).exists()


def test_second_open_in_the_same_process_is_refused(tmp_path):
    ran = []
    with (
        work_lock(tmp_path, "grid-system"),
        pytest.raises(WorkLockBusy) as caught,
        work_lock(tmp_path, "answer"),
    ):
        ran.append(1)
    assert ran == []
    assert caught.value.exit_code == 3
    assert caught.value.holder is not None and caught.value.holder["pid"] == os.getpid()
    message = str(caught.value)
    assert "grid-system" in message and str(os.getpid()) in message and "retry shortly" in message


def test_refused_attempt_keeps_the_holder_lock_and_record(tmp_path):
    with work_lock(tmp_path, "grid-system"):
        with pytest.raises(WorkLockBusy), work_lock(tmp_path, "answer"):
            pass
        holder = json.loads((tmp_path / HOLDER_FILE).read_text(encoding="utf-8"))
        assert holder["command"] == "grid-system"  # the refused one wrote nothing
        with pytest.raises(WorkLockBusy), work_lock(tmp_path, "answer"):
            pass  # still held after the refusal


def test_lock_is_free_again_after_release(tmp_path):
    with work_lock(tmp_path, "a"):
        pass
    with work_lock(tmp_path, "b"):
        pass


def test_lock_is_released_when_the_body_raises(tmp_path):
    with pytest.raises(RuntimeError), work_lock(tmp_path, "a"):
        raise RuntimeError("boom")
    with work_lock(tmp_path, "b"):
        pass
    assert not (tmp_path / HOLDER_FILE).exists()


def test_existing_lock_file_content_is_not_truncated(tmp_path):
    (tmp_path / LOCK_FILE).write_bytes(b"x")
    with work_lock(tmp_path, "a"):
        pass
    assert (tmp_path / LOCK_FILE).read_bytes() == b"x"


def test_busy_without_a_holder_record_says_unknown(tmp_path):
    with work_lock(tmp_path, "a"):
        (tmp_path / HOLDER_FILE).write_text("{not json", encoding="utf-8")
        with pytest.raises(WorkLockBusy) as caught, work_lock(tmp_path, "b"):
            pass
    assert caught.value.holder is None
    assert "unknown" in str(caught.value) and caught.value.exit_code == 3


@pytest.mark.parametrize("code", [errno.ENOLCK, errno.EINVAL, errno.EBADF])
def test_filesystem_without_locks_fails_closed(tmp_path, monkeypatch, code):
    def no_locks(_fd: int) -> None:
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(worklock, "_lock", no_locks)
    ran = []
    with pytest.raises(WorkLockError) as caught, work_lock(tmp_path, "answer"):
        ran.append(1)
    assert ran == [] and not isinstance(caught.value, WorkLockBusy)
    assert caught.value.exit_code == 3 and "unlocked" in str(caught.value)
    assert not (tmp_path / HOLDER_FILE).exists()


@pytest.mark.parametrize(
    "code", [errno.EACCES, errno.EDEADLOCK] if sys.platform == "win32" else [errno.EACCES, errno.EAGAIN]
)
def test_contention_errnos_mean_busy(tmp_path, monkeypatch, code):
    def held(_fd: int) -> None:
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(worklock, "_lock", held)
    with pytest.raises(WorkLockBusy), work_lock(tmp_path, "answer"):
        pass


def test_missing_work_folder_is_an_environment_error(tmp_path):
    with pytest.raises(WorkLockError) as caught, work_lock(tmp_path / "nope", "answer"):
        pass
    assert caught.value.exit_code == 3 and not (tmp_path / "nope").exists()


# --- another process -------------------------------------------------------------------------------


def test_subprocess_holder_blocks_and_is_named(holder):
    work, _, pid = holder
    with pytest.raises(WorkLockBusy) as caught, work_lock(work, "answer"):
        pass
    assert caught.value.holder is not None and caught.value.holder["pid"] == pid
    assert "holder-test" in str(caught.value) and str(pid) in str(caught.value)


def test_subprocess_holder_releases_on_normal_exit(holder):
    work, proc, _ = holder
    assert proc.stdin is not None
    proc.stdin.close()
    assert proc.wait(timeout=30) == 0
    acquire_eventually(work)
    assert (work / LOCK_FILE).is_file() and not (work / HOLDER_FILE).exists()


def test_subprocess_holder_killed_releases_the_lock(holder):
    work, proc, _ = holder
    proc.kill()
    proc.wait(timeout=30)
    acquire_eventually(work)  # no stale-lock rule: the OS frees it on any process exit


# --- the CLI ---------------------------------------------------------------------------------------


def run_cli(capsys, *argv: str) -> tuple[int, Any, str]:
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out.strip() else None), cap.err


def writer_argv(work: Path) -> list[list[str]]:
    w = str(work)
    return [
        ["read-structure", w],
        ["callouts", w],
        ["marks", w],
        ["grid-system", w, "--no-svg"],
        ["answer", w, "Q-001", "--text", "x", "--by", "me", "--role", "engineer", "--value", "unit=mm"],
        ["ask", w, "--code", "lock_test", "--where", "here", "--found", "", "--text", "câu hỏi"],
        ["ask", w, "--withdraw", "Q-001", "--reason", "x"],
        [
            "finding",
            "add",
            w,
            "--kind",
            "sheet_class",
            "--file",
            "set.dxf",
            "--entries",
            "T000001",
            "--value",
            "other",
        ],
        ["finding", "withdraw", w, "F-001", "--reason", "x"],
        ["questions-md", w],
    ]


@pytest.mark.parametrize("index", range(10))
def test_every_writer_command_is_refused_while_held(world, capsys, index):
    argv = writer_argv(world)[index]
    before = snapshot(world)
    with work_lock(world, "grid-system"):
        held = snapshot(world)
        code, out, err = run_cli(capsys, *argv)
        assert snapshot(world) == held  # nothing written, the holder record untouched
    assert code == 3 and out is None, (argv, code, err)
    assert "grid-system" in err and str(os.getpid()) in err and "retry shortly" in err
    assert snapshot(world) == before


def test_intake_is_refused_while_held(world, capsys, tmp_path):
    before = snapshot(world)
    with work_lock(world, "answer"):
        code, out, err = run_cli(
            capsys, "intake", str(world.parent / "input"), "--out", str(world), "--project-id", PROJECT
        )
    assert code == 3 and out is None and "answer" in err
    assert snapshot(world) == before


@pytest.mark.parametrize(
    "argv",
    [
        ["status", "{w}"],
        ["list-sheets", "{w}"],
        ["find-text", "{w}", "--contains", "S-"],
        ["finding", "list", "{w}"],
        ["sheet-text", "{w}", "set.dxf", "model#01"],
    ],
)
def test_read_only_commands_run_while_held(world, capsys, argv):
    with work_lock(world, "grid-system"):
        code, out, err = run_cli(capsys, *(a.format(w=world) for a in argv))
    assert code == 0, (argv, err)
    assert out is not None


def test_writer_releases_the_lock_after_it_ran(world, capsys, tmp_path):
    code, _, _ = run_cli(
        capsys,
        "ask",
        str(world),
        "--code",
        "lock_release",
        "--where",
        "w",
        "--found",
        "",
        "--text",
        "câu hỏi",
    )
    assert code == 0
    assert (world / LOCK_FILE).is_file() and not (world / HOLDER_FILE).exists()
    with work_lock(world, "after"):
        pass


def test_writer_on_a_missing_work_folder_keeps_its_usage_error(tmp_path, capsys):
    missing = tmp_path / "missing"
    code, out, err = run_cli(
        capsys, "answer", str(missing), "Q-001", "--text", "x", "--by", "me", "--role", "engineer"
    )
    assert code == 2 and out is None and "not a folder" in err
    assert not missing.exists()


def test_writer_on_a_missing_work_folder_never_runs_unlocked(tmp_path, capsys, monkeypatch):
    """main refuses a locked command whose folder is missing itself (review m3): the command never runs
    without the lock, even if the folder appears between the check and the command's own check."""
    import tekla_harness.cli as cli

    ran = []
    monkeypatch.setattr(cli, "_cmd_answer", lambda args: ran.append(args) or 0)
    parser = cli.build_parser()
    for action in parser._actions:  # re-point the subcommand at the stub
        if isinstance(action, argparse._SubParsersAction):
            action.choices["answer"].set_defaults(func=cli._cmd_answer)
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    code, out, err = run_cli(
        capsys,
        "answer",
        str(tmp_path / "missing"),
        "Q-001",
        "--text",
        "x",
        "--by",
        "me",
        "--role",
        "engineer",
    )
    assert code == 2 and out is None and not ran and "not a folder" in err


def _subcommands() -> dict[str, argparse.ArgumentParser]:
    import tekla_harness.cli as cli

    for action in cli.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("no subcommands")


def test_every_command_is_classified_locked_or_unlocked():
    """A new command must be put on one list on purpose (review m4): writers lock, the rest say why not."""
    import tekla_harness.cli as cli

    lists = [
        set(cli.LOCKED_COMMANDS),
        set(cli.LOCKED_ACTIONS),
        set(cli.SELF_LOCKING_COMMANDS),
        set(cli.UNLOCKED_COMMANDS),
    ]
    for i, a in enumerate(lists):
        for b in lists[i + 1 :]:
            assert not a & b
    assert set(_subcommands()) == set().union(*lists)


def test_cli_fails_closed_without_lock_support(world, capsys, monkeypatch):
    def no_locks(_fd: int) -> None:
        raise OSError(errno.ENOLCK, "No locks available")

    monkeypatch.setattr(worklock, "_lock", no_locks)
    before = snapshot(world)
    code, out, err = run_cli(capsys, "questions-md", str(world))
    assert code == 3 and out is None and "unlocked" in err
    assert snapshot(world) == before


def _save_argv(world: Path) -> list[list[str]]:
    w, inp = str(world), str(world.parent / "input")
    return [
        ["geometry", w, "set.dxf", "--sheet", "model#01", "--input-dir", inp],
        ["contents", w, "set.dxf", "--sheet", "model#01", "--outline-layer", "S-CAP",
         "--circle-layer", "S-PILE", "--input-dir", inp],
    ]  # fmt: skip


@pytest.mark.parametrize("index", range(2))
def test_geometry_and_contents_are_refused_with_save_while_held(world, capsys, index):
    argv = _save_argv(world)[index]
    before = snapshot(world)
    with work_lock(world, "grid-system"):
        code, out, err = run_cli(capsys, *argv, "--save")
    assert code == 3 and out is None, (argv, code, err)
    assert "grid-system" in err and "retry shortly" in err
    assert snapshot(world) == before


@pytest.mark.parametrize("index", range(2))
def test_geometry_and_contents_without_save_run_while_held(world, capsys, index):
    argv = _save_argv(world)[index]
    before = snapshot(world)
    with work_lock(world, "grid-system"):
        code, out, err = run_cli(capsys, *argv)
    assert code == 0, (argv, err)
    assert out is not None
    assert snapshot(world) == before


@pytest.mark.parametrize("index", range(2))
def test_save_locks_only_the_write_and_names_the_command(world, capsys, monkeypatch, index):
    """T24 review 1 (m5, C02): the document is computed without the lock; only the write holds it, as
    `<command> --save`."""
    from tekla_harness import saved_evidence

    argv = _save_argv(world)[index]
    seen: list[dict[str, Any] | None] = []
    real = saved_evidence.work_lock

    @contextlib.contextmanager
    def watching(work: Path, command: str, wait: float = 0.0):
        with real(work, command, wait=wait):
            seen.append(worklock.read_holder(work))
            yield

    monkeypatch.setattr(saved_evidence, "work_lock", watching)
    code, out, err = run_cli(capsys, *argv, "--save")
    assert code == 0 and out is not None, err
    assert [h and h["command"] for h in seen] == [argv[0] + " --save"]
    assert not (world / HOLDER_FILE).exists()  # released after the write


def test_save_after_the_lock_was_taken_by_a_slow_computation_still_works(world, capsys, monkeypatch):
    """The lock is free during the computation: another writer may run and finish meanwhile."""
    from tekla_harness import geometry

    real = geometry.read_geometry
    ran: list[int] = []

    def slow(*args: Any, **kwargs: Any) -> Any:
        with work_lock(world, "answer"):  # a recorder holds and releases the lock in the middle of the run
            ran.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(geometry, "read_geometry", slow)
    code, out, err = run_cli(capsys, *_save_argv(world)[0], "--save")
    assert code == 0 and ran == [1] and out is not None, err


def test_save_into_a_missing_work_folder_is_usage(tmp_path, capsys):
    code, out, err = run_cli(
        capsys, "geometry", str(tmp_path / "nope"), "set.dxf", "--sheet", "model#01", "--save"
    )
    assert code == 2 and out is None and "not a folder" in err


# --- bounded wait (ADR-0011 amendment 2026-11-20) ---------------------------------------------------

WAITED_LINE = re.compile(
    r"lock: waited \d+\.\d s for (harness (?P<command>\S+) \(pid (?P<pid>\d+)\)|unknown holder)"
)
WRITER_SCRIPT = (
    "import sys\n"
    "from tekla_harness.cli import main\n"
    "print('ready', flush=True)\n"
    "sys.stdin.readline()\n"
    "sys.exit(main(sys.argv[1:]))\n"
)


@contextlib.contextmanager
def held_for(work: Path, seconds: float, command: str = "holder-thread"):
    """Hold the lock of `work` in a thread for `seconds`; it is taken before this returns."""
    taken = threading.Event()

    def run() -> None:
        with work_lock(work, command):
            taken.set()
            time.sleep(seconds)

    thread = threading.Thread(target=run)
    thread.start()
    assert taken.wait(10)
    try:
        yield
    finally:
        thread.join(10)


def busy(_fd: int) -> None:
    raise OSError(errno.EACCES, os.strerror(errno.EACCES))  # "held" on POSIX and on Windows


def test_wait_ends_when_the_holder_releases(holder, capsys):
    work, proc, pid = holder
    assert proc.stdin is not None
    threading.Timer(0.5, proc.stdin.close).start()
    started = time.monotonic()
    with work_lock(work, "answer", wait=3.0):
        elapsed = time.monotonic() - started
        assert 0.3 < elapsed < 2.5
    err = capsys.readouterr().err
    found = WAITED_LINE.search(err)
    assert found is not None, err
    assert found["command"] == "holder-test" and found["pid"] == str(pid)  # the record read at the refusal


def test_wait_names_an_unknown_holder(tmp_path, capsys):
    with held_for(tmp_path, 0.5):
        (tmp_path / HOLDER_FILE).write_text("{not json", encoding="utf-8")
        with work_lock(tmp_path, "answer", wait=3.0):
            pass
    found = WAITED_LINE.search(capsys.readouterr().err)
    assert found is not None and "unknown holder" in found[0]


def test_no_waited_line_when_the_lock_was_free(tmp_path, capsys):
    with work_lock(tmp_path, "answer", wait=3.0):
        pass
    assert "waited" not in capsys.readouterr().err


def test_wait_shorter_than_the_hold_is_refused_and_names_the_seconds(holder):
    work, _, pid = holder
    started = time.monotonic()
    with pytest.raises(WorkLockBusy) as caught, work_lock(work, "answer", wait=0.5):
        pass
    assert 0.45 < time.monotonic() - started < 2.0
    assert caught.value.exit_code == 3 and caught.value.holder is not None
    assert "0.5 s" in str(caught.value) and "retry shortly" in str(caught.value)
    assert "holder-test" in str(caught.value) and str(pid) in str(caught.value)


def test_default_wait_is_zero_and_refuses_at_once(holder):
    work, _, _ = holder
    for call in (lambda: work_lock(work, "answer"), lambda: work_lock(work, "answer", wait=0.0)):
        started = time.monotonic()
        with pytest.raises(WorkLockBusy) as caught, call():
            pass
        assert time.monotonic() - started < 0.5
        assert "waited" not in str(caught.value) and "no waiting" in str(caught.value)


def test_foreign_holder_record_is_refused_without_waiting(tmp_path):
    other = "win32" if sys.platform != "win32" else "linux"
    record = {"pid": 4242, "host": "h", "command": "marks", "started": "t", "platform": other}
    (tmp_path / HOLDER_FILE).write_text(json.dumps(record), encoding="utf-8")
    started = time.monotonic()
    with pytest.raises(WorkLockError) as caught, work_lock(tmp_path, "answer", wait=3.0):
        pass
    assert time.monotonic() - started < 0.5
    assert not isinstance(caught.value, WorkLockBusy) and other in str(caught.value)
    assert json.loads((tmp_path / HOLDER_FILE).read_text(encoding="utf-8")) == record


def test_foreign_record_while_this_os_lock_is_held_is_not_waited_for(tmp_path, monkeypatch):
    other = "win32" if sys.platform != "win32" else "linux"
    record = {"pid": 4242, "host": "h", "command": "marks", "started": "t", "platform": other}
    (tmp_path / HOLDER_FILE).write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(worklock, "_lock", busy)
    started = time.monotonic()
    with pytest.raises(WorkLockError) as caught, work_lock(tmp_path, "answer", wait=3.0):
        pass
    assert time.monotonic() - started < 0.5 and not isinstance(caught.value, WorkLockBusy)
    assert json.loads((tmp_path / HOLDER_FILE).read_text(encoding="utf-8")) == record


@pytest.mark.parametrize("code", [errno.ENOLCK, errno.EINVAL, errno.EBADF])
def test_a_lock_error_other_than_held_is_not_retried(tmp_path, monkeypatch, code):
    calls: list[int] = []

    def no_locks(_fd: int) -> None:
        calls.append(1)
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(worklock, "_lock", no_locks)
    started = time.monotonic()
    with pytest.raises(WorkLockError) as caught, work_lock(tmp_path, "answer", wait=3.0):
        pass
    assert len(calls) == 1 and time.monotonic() - started < 0.5
    assert not isinstance(caught.value, WorkLockBusy) and "unlocked" in str(caught.value)


def test_a_foreign_record_written_during_the_wait_stops_it(tmp_path, monkeypatch):
    other = "win32" if sys.platform != "win32" else "linux"
    record = {"pid": 4242, "host": "h", "command": "marks", "started": "t", "platform": other}
    calls: list[int] = []

    def held_then_foreign(_fd: int) -> None:
        calls.append(1)
        if len(calls) == 2:
            (tmp_path / HOLDER_FILE).write_text(json.dumps(record), encoding="utf-8")
        raise OSError(errno.EACCES, os.strerror(errno.EACCES))

    monkeypatch.setattr(worklock, "_lock", held_then_foreign)
    started = time.monotonic()
    with pytest.raises(WorkLockError) as caught, work_lock(tmp_path, "answer", wait=3.0):
        pass
    assert time.monotonic() - started < 1.0 and not isinstance(caught.value, WorkLockBusy)
    assert len(calls) == 2


def test_a_record_without_platform_is_waited_for(tmp_path, monkeypatch):
    record = {"pid": 4242, "host": "h", "command": "marks", "started": "t"}
    (tmp_path / HOLDER_FILE).write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(worklock, "_lock", busy)
    with pytest.raises(WorkLockBusy) as caught, work_lock(tmp_path, "answer", wait=0.5):
        pass
    assert caught.value.waited == 0.5 and caught.value.holder == record


def test_an_error_other_than_held_after_a_wait_stops_the_wait(tmp_path, monkeypatch):
    calls: list[int] = []

    def held_then_broken(_fd: int) -> None:
        calls.append(1)
        code = errno.EACCES if len(calls) == 1 else errno.ENOLCK
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(worklock, "_lock", held_then_broken)
    with pytest.raises(WorkLockError) as caught, work_lock(tmp_path, "answer", wait=3.0):
        pass
    assert len(calls) == 2 and not isinstance(caught.value, WorkLockBusy)


def test_the_wait_retries_every_fifth_of_a_second(tmp_path, monkeypatch):
    calls: list[float] = []

    def always_held(fd: int) -> None:
        calls.append(time.monotonic())
        busy(fd)

    monkeypatch.setattr(worklock, "_lock", always_held)
    with pytest.raises(WorkLockBusy), work_lock(tmp_path, "answer", wait=0.6):
        pass
    assert 3 <= len(calls) <= 6  # about 0, 0.2, 0.4, 0.6
    gaps = [b - a for a, b in itertools.pairwise(calls)]
    assert all(0 < gap < 0.45 for gap in gaps), gaps


def test_the_last_sleep_is_cut_to_the_time_left(tmp_path, monkeypatch):
    """A fake clock: wait 0.5 s sleeps 0.2, 0.2, 0.1 and refuses at 0.5 s, not a full interval later."""
    now = [100.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(worklock, "time", types.SimpleNamespace(monotonic=lambda: now[0], sleep=sleep))
    monkeypatch.setattr(worklock, "_lock", busy)
    with pytest.raises(WorkLockBusy) as caught, work_lock(tmp_path, "answer", wait=0.5):
        pass
    assert sleeps == pytest.approx([0.2, 0.2, 0.1])
    assert caught.value.waited == 0.5 and "0.5 s" in str(caught.value)


def test_the_wait_ends_with_the_lock_when_it_frees_up(tmp_path, monkeypatch, capsys):
    calls: list[int] = []

    def held_twice(fd: int) -> None:
        calls.append(1)
        if len(calls) <= 2:
            busy(fd)

    monkeypatch.setattr(worklock, "_lock", held_twice)
    monkeypatch.setattr(worklock, "_unlock", lambda _fd: None)
    ran: list[int] = []
    with work_lock(tmp_path, "answer", wait=3.0):
        ran.append(1)
    assert ran == [1] and len(calls) == 3
    assert "lock: waited" in capsys.readouterr().err


def ask_argv(work: Path, name: str) -> list[str]:
    return [
        *("ask", str(work), "--code", f"lock_wait_{name}"),
        *("--where", f"here {name}", "--found", "", "--text", f"câu hỏi {name}"),
    ]


def test_two_waiters_on_one_busy_folder_both_write(world, tmp_path):
    work = tmp_path / "work"
    shutil.copytree(world, work)
    env = {**os.environ, "HARNESS_LOCK_WAIT": "30", "PYTHONIOENCODING": "utf-8"}
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", WRITER_SCRIPT, *ask_argv(work, name)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
        )
        for name in ("a", "b")
    ]
    try:
        with work_lock(work, "holder-thread"):
            for proc in procs:  # both are imported and idle: release them while the lock is held
                assert proc.stdout is not None and proc.stdout.readline().strip() == "ready"
            for proc in procs:
                assert proc.stdin is not None
                proc.stdin.write("go\n")
                proc.stdin.flush()
            time.sleep(0.6)
        results = [proc.communicate(timeout=30) for proc in procs]
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=30)
    assert [proc.returncode for proc in procs] == [0, 0], results
    assert all("lock: waited" in err for _, err in results), results
    answers = [json.loads(out) for out, _ in results]
    assert {a["status"] for a in answers} == {"new"} and len({a["id"] for a in answers}) == 2
    registry = (work / "reader-questions.json").read_text(encoding="utf-8")
    assert all(a["key"] in registry for a in answers)  # no lost update
    assert not (work / HOLDER_FILE).exists()


# --- the wait a command uses ------------------------------------------------------------------------


def test_lock_wait_is_zero_without_a_manifest_or_variable(tmp_path):
    assert lock_wait(tmp_path) == 0.0


def test_lock_wait_is_sixty_seconds_with_a_parts_manifest(tmp_path):
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "manifest.json").write_text("{}", encoding="utf-8")
    assert lock_wait(tmp_path) == 60.0


@pytest.mark.parametrize("where", ["manifest.json", "parts/other.json"])
def test_lock_wait_looks_only_at_the_parts_manifest_path(tmp_path, where):
    path = tmp_path / where
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    assert lock_wait(tmp_path) == 0.0


def test_lock_wait_is_zero_when_parts_is_a_regular_file(tmp_path):
    (tmp_path / "parts").write_text("not a folder", encoding="utf-8")
    assert lock_wait(tmp_path) == 0.0


def test_lock_wait_is_sixty_seconds_for_a_directory_at_the_manifest_path(tmp_path):
    (tmp_path / "parts" / "manifest.json").mkdir(parents=True)  # present, so part mode (the shared rule)
    assert lock_wait(tmp_path) == PART_MODE_WAIT


def test_lock_wait_is_sixty_seconds_for_a_dangling_symlink_at_the_manifest_path(tmp_path):
    (tmp_path / "parts").mkdir()
    try:
        (tmp_path / "parts" / "manifest.json").symlink_to(tmp_path / "nowhere.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not permitted here")
    assert lock_wait(tmp_path) == PART_MODE_WAIT


needs_permissions = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 does not stop this user (Windows or root)",
)


@contextlib.contextmanager
def no_access(path: Path) -> Iterator[None]:
    path.chmod(0o000)
    try:
        yield
    finally:
        path.chmod(0o755)


@needs_permissions
def test_lock_wait_stops_when_the_manifest_path_cannot_be_checked(tmp_path):
    (tmp_path / "parts").mkdir()
    with no_access(tmp_path / "parts"), pytest.raises(WorkLockError, match=r"parts/manifest\.json") as caught:
        lock_wait(tmp_path)
    assert caught.value.exit_code == 3 and not isinstance(caught.value, WorkLockBusy)
    assert "nothing was run or written" in str(caught.value)


@needs_permissions
def test_a_command_in_a_folder_with_an_unreadable_parts_folder_exits_3_and_writes_nothing(
    world, tmp_path, capsys
):
    work = tmp_path / "work"
    shutil.copytree(world, work)
    (work / "parts").mkdir()
    with no_access(work / "parts"):
        assert main(["questions-md", str(work)]) == 3
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err and "parts/manifest.json" in captured.err
    assert captured.out == "" and not (tmp_path / "questions.md").exists()


@needs_permissions
def test_the_variable_wins_so_an_unreadable_parts_folder_is_not_looked_at(tmp_path, monkeypatch):
    (tmp_path / "parts").mkdir()
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "3")
    with no_access(tmp_path / "parts"):
        assert lock_wait(tmp_path) == 3.0


@pytest.mark.parametrize(("text", "seconds"), [("2.5", 2.5), ("0", 0.0), ("7", 7.0), (" 1 ", 1.0)])
def test_lock_wait_takes_the_variable(tmp_path, monkeypatch, text, seconds):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", text)
    assert lock_wait(tmp_path) == seconds


def test_the_variable_wins_over_the_manifest(tmp_path, monkeypatch):
    (tmp_path / "parts").mkdir()
    (tmp_path / "parts" / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "0")
    assert lock_wait(tmp_path) == 0.0
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "5")
    assert lock_wait(tmp_path) == 5.0


@pytest.mark.parametrize("text", ["abc", "-1", "-0.5", "nan", "inf", "", " ", "1s"])
def test_lock_wait_rejects_a_bad_variable_as_usage(tmp_path, monkeypatch, text):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", text)
    with pytest.raises(WorkLockError) as caught:
        lock_wait(tmp_path)
    assert caught.value.exit_code == 2 and "HARNESS_LOCK_WAIT" in str(caught.value)


def test_a_bad_variable_is_exit_2_before_the_lock_is_touched(world, capsys, monkeypatch):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "soon")
    before = snapshot(world)
    started = time.monotonic()
    with work_lock(world, "grid-system"):  # held: a command that touched the lock would be exit 3
        code, out, err = run_cli(capsys, "questions-md", str(world))
        code_save, _, err_save = run_cli(capsys, *_save_argv(world)[0], "--save")
        code_intake, _, err_intake = run_cli(
            capsys, "intake", str(world.parent / "input"), "--out", str(world), "--project-id", PROJECT
        )
    assert time.monotonic() - started < 1.0
    assert (code, code_save, code_intake) == (2, 2, 2), (err, err_save, err_intake)
    assert out is None and "HARNESS_LOCK_WAIT" in err and "HARNESS_LOCK_WAIT" in err_save
    assert "HARNESS_LOCK_WAIT" in err_intake
    assert snapshot(world) == before


def test_a_bad_variable_creates_no_intake_folder(world, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "soon")
    out = tmp_path / "new" / "w"
    code, printed, err = run_cli(
        capsys, "intake", str(world.parent / "input"), "--out", str(out), "--project-id", PROJECT
    )
    assert code == 2 and printed is None and "HARNESS_LOCK_WAIT" in err and "Traceback" not in err
    assert not (tmp_path / "new").exists()


def test_a_bad_variable_does_not_stop_a_read_only_command(world, capsys, monkeypatch):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "soon")
    code, out, _ = run_cli(capsys, "status", str(world))
    assert code == 0 and out is not None


# --- every lock taker uses the wait -----------------------------------------------------------------


def test_cli_main_waits_for_a_held_lock(world, capsys, monkeypatch):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "3")
    with held_for(world, 0.6, "grid-system"):
        code, _, err = run_cli(capsys, "questions-md", str(world))
    assert code == 0, err
    found = WAITED_LINE.search(err)
    assert found is not None and found["command"] == "grid-system"


def test_cli_main_gives_up_after_the_wait(world, capsys, monkeypatch):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "0.4")
    before = snapshot(world)
    with held_for(world, 1.0, "grid-system"):
        code, out, err = run_cli(capsys, "questions-md", str(world))
    assert code == 3 and out is None and "0.4 s" in err and "grid-system" in err and "retry shortly" in err
    assert snapshot(world) == before


def test_intake_waits_for_a_held_lock(world, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "3")
    out_dir = tmp_path / "intake-work"
    out_dir.mkdir()
    with held_for(out_dir, 0.6, "answer"):
        code, out, err = run_cli(
            capsys, "intake", str(world.parent / "input"), "--out", str(out_dir), "--project-id", PROJECT
        )
    assert code == 0 and out is not None, err
    assert "lock: waited" in err and (out_dir / "inventory.json").is_file()


def test_intake_in_a_part_mode_folder_waits_without_the_variable(world, capsys, tmp_path):
    work = tmp_path / "w"
    (work / "parts").mkdir(parents=True)
    (work / "parts" / "manifest.json").write_text("{}", encoding="utf-8")
    with held_for(work, 0.6, "answer"):
        code, out, err = run_cli(
            capsys, "intake", str(world.parent / "input"), "--out", str(work), "--project-id", PROJECT
        )
    assert code == 0 and out is not None and "lock: waited" in err, err


def test_save_waits_for_a_held_lock(world, capsys, monkeypatch):
    monkeypatch.setenv("HARNESS_LOCK_WAIT", "3")
    with held_for(world, 0.6, "answer"):
        code, out, err = run_cli(capsys, *_save_argv(world)[0], "--save")
    assert code == 0 and out is not None, err
    assert "lock: waited" in err


def test_a_part_mode_folder_waits_without_the_variable(world, capsys, tmp_path):
    work = tmp_path / "work"
    shutil.copytree(world, work)
    shutil.copytree(
        world.parent / "input", tmp_path / "input"
    )  # `geometry` finds the drawing beside the work folder
    (work / "parts").mkdir()
    (work / "parts" / "manifest.json").write_text("{}", encoding="utf-8")
    with held_for(work, 0.6, "grid-system"):
        code, _, err = run_cli(capsys, "questions-md", str(work))
        assert code == 0 and "lock: waited" in err, err
    with held_for(work, 0.6, "grid-system"):
        code, _, err = run_cli(capsys, *_save_argv(work)[0], "--save")
    assert code == 0 and "lock: waited" in err, err


def test_receipt_is_a_locked_action(tmp_path, capsys, monkeypatch):
    """`part receipt` writes a work folder, so it takes the lock (and waits 60 s in part mode, E1); the two
    readers of `part` stay unlocked. Held lock: the receipt is refused before it runs."""
    import tekla_harness.cli as cli

    assert cli.LOCKED_ACTIONS["part"] == frozenset({"receipt", "conflicts", "spotcheck", "answer-key"})
    parser = cli.build_parser()
    receipt = parser.parse_args(["part", "receipt", "W", "--part", "scout", "--kind", "checked"])
    assert cli._lock_target(receipt) == Path("W")
    for action in ("check", "manifest-check"):
        argv = ["part", action, "W", *(["--part", "scout"] if action == "check" else [])]
        assert cli._lock_target(parser.parse_args(argv)) is None
    monkeypatch.setenv(worklock.WAIT_ENV, "0")
    with work_lock(tmp_path, "holder-test"):
        code, out, err = run_cli(
            capsys, "part", "receipt", str(tmp_path), "--part", "scout", "--kind", "checked"
        )
    assert code == 3 and out is None and "holder-test" in err
    assert not (tmp_path / "parts").exists()
