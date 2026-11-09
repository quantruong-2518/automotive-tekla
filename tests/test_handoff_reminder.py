"""SessionStart handoff reminder: open rows of .handoff/INDEX.md reach Claude's context."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import HOOKS, load_hook

INDEX_TEXT = """# Handoff index

Rules
- A session that stops with open work writes `<topic>.md` here and adds one row below.

| File | Work | Status | Next action | Updated |
|---|---|---|---|---|
| [a.md](a.md) | Reading skills | open | PR #4 awaiting merge | 2026-11-07 |
| [b.md](b.md) | Step 3 CLI | done | - | 2026-11-06 |
| [c.md](c.md) | Read cache | blocked | wait for engineer | 2026-11-07 |

Notes after the table | not a row |
"""


@pytest.fixture
def reminder():
    return load_hook("handoff_reminder")


def run_hook(project: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run(
        [sys.executable, str(HOOKS / "handoff_reminder.py")],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_open_rows_skip_closed_ones_and_text_outside_the_table(reminder):
    rows = reminder.open_rows(INDEX_TEXT)
    assert [r["file"] for r in rows] == ["[a.md](a.md)", "[c.md](c.md)"]
    assert rows[1]["status"] == "blocked" and rows[1]["next_action"] == "wait for engineer"


def test_hook_injects_the_rows_and_the_ask_instruction(tmp_path):
    (tmp_path / ".handoff").mkdir()
    (tmp_path / ".handoff" / "INDEX.md").write_text(INDEX_TEXT, encoding="utf-8")
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    text = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Reading skills" in text and "Read cache" in text and "Step 3 CLI" not in text
    assert "AskUserQuestion" in text and "confirms in chat" in text
    assert out["systemMessage"].startswith("2 open handoff(s)")


@pytest.mark.parametrize("content", [None, "# Handoff index\n\n| File | Work | Status |\n|---|---|---|\n"])
def test_no_index_or_no_open_row_prints_nothing(tmp_path, content):
    if content is not None:
        (tmp_path / ".handoff").mkdir()
        (tmp_path / ".handoff" / "INDEX.md").write_text(content, encoding="utf-8")
    proc = run_hook(tmp_path)
    assert proc.returncode == 0 and proc.stdout == ""


def test_a_worktree_finds_the_index_of_its_main_checkout(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=main, check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], cwd=main, check=True)
    (main / ".handoff").mkdir()
    (main / ".handoff" / "INDEX.md").write_text(INDEX_TEXT, encoding="utf-8")
    worktree = tmp_path / "wt"
    subprocess.run([*git, "worktree", "add", "-q", str(worktree)], cwd=main, check=True)
    proc = run_hook(worktree)
    assert proc.returncode == 0
    assert "Reading skills" in json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
