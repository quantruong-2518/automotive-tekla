"""worklock: one writer per work folder (ADR-0011).

The lock is an OS lock (flock on POSIX, msvcrt byte lock on Windows): a second open file in the same
process conflicts with the first, and a child process holding it blocks the parent. Both CI operating
systems run every test here.
"""

from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from _dxf_fixtures import build_set
from tekla_harness import worklock
from tekla_harness.cli import main
from tekla_harness.intake import run_intake
from tekla_harness.structure import read_structure
from tekla_harness.worklock import HOLDER_FILE, LOCK_FILE, WorkLockBusy, WorkLockError, work_lock

PROJECT = "demo-lock"
HOLDER_SCRIPT = (
    "import sys\n"
    "from pathlib import Path\n"
    "from tekla_harness.worklock import work_lock\n"
    "with work_lock(Path(sys.argv[1]), 'holder-test'):\n"
    "    print('ready', flush=True)\n"
    "    sys.stdin.readline()\n"
)


def snapshot(work: Path) -> dict[str, bytes]:
    return {p.relative_to(work).as_posix(): p.read_bytes() for p in sorted(work.rglob("*")) if p.is_file()}


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
    assert proc.stdout is not None and proc.stdout.readline().strip() == "ready"
    yield work, proc
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


@pytest.mark.parametrize("code", [errno.EACCES, errno.EAGAIN])
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
    work, proc = holder
    with pytest.raises(WorkLockBusy) as caught, work_lock(work, "answer"):
        pass
    assert caught.value.holder is not None and caught.value.holder["pid"] == proc.pid
    assert "holder-test" in str(caught.value) and str(proc.pid) in str(caught.value)


def test_subprocess_holder_releases_on_normal_exit(holder):
    work, proc = holder
    assert proc.stdin is not None
    proc.stdin.close()
    assert proc.wait(timeout=30) == 0
    acquire_eventually(work)
    assert (work / LOCK_FILE).is_file() and not (work / HOLDER_FILE).exists()


def test_subprocess_holder_killed_releases_the_lock(holder):
    work, proc = holder
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
        ["answer", w, "Q-001", "--text", "x", "--by", "me", "--value", "unit=mm"],
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
    code, out, err = run_cli(capsys, "answer", str(missing), "Q-001", "--text", "x", "--by", "me")
    assert code == 2 and out is None and "not a folder" in err
    assert not missing.exists()


def test_cli_fails_closed_without_lock_support(world, capsys, monkeypatch):
    def no_locks(_fd: int) -> None:
        raise OSError(errno.ENOLCK, "No locks available")

    monkeypatch.setattr(worklock, "_lock", no_locks)
    before = snapshot(world)
    code, out, err = run_cli(capsys, "questions-md", str(world))
    assert code == 3 and out is None and "unlocked" in err
    assert snapshot(world) == before
