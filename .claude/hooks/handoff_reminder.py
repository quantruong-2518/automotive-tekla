#!/usr/bin/env python3
"""SessionStart hook: remind a new session of the open multi-session handoffs.

Open work that spans sessions is recorded in `.handoff/INDEX.md` of the MAIN checkout (excluded
from git, shared by every worktree): one table row per topic. While any row is open, every new
session must first ask the engineer which handoff to resume, and a row is removed only after the
engineer confirms in chat that its topic is cleared. This hook makes that deterministic: it
reads the table and injects the open rows plus that instruction into Claude's context, and shows
the engineer a one-line notice.

Registered for the `startup` and `clear` sources only (a fresh start), not `resume` or `compact`.
Never blocks; always exits 0. Stdlib only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

INDEX = Path(".handoff") / "INDEX.md"
COLUMNS = ("file", "work", "status", "next_action", "updated")
CLOSED = {"done", "cleared", "closed"}


def find_index(project_dir: Path) -> Path | None:
    """`.handoff/INDEX.md` in the project dir, else in the main checkout of a worktree."""
    direct = project_dir / INDEX
    if direct.is_file():
        return direct
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not common:
        return None
    candidate = Path(common).parent / INDEX
    return candidate if candidate.is_file() else None


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def open_rows(text: str) -> list[dict[str, str]]:
    """Rows of the first table whose first header cell is `File`, minus closed ones."""
    rows: list[dict[str, str]] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                break
            continue
        cells = _cells(stripped)
        if not in_table:
            in_table = bool(cells) and cells[0].lower() == "file"
            continue
        if set("".join(cells)) <= set("-: "):
            continue  # the separator row
        row = dict(zip(COLUMNS, cells + [""] * (len(COLUMNS) - len(cells)), strict=False))
        if row["status"].lower() not in CLOSED:
            rows.append(row)
    return rows


def context(rows: list[dict[str, str]], index: Path) -> str:
    listed = "\n".join(
        f"- {r['file']}: {r['work']} (status {r['status'] or 'unknown'}; next: {r['next_action'] or '-'}; "
        f"updated {r['updated'] or '-'})"
        for r in rows
    )
    return (
        f"Open multi-session handoffs in {index}:\n{listed}\n\n"
        "Before any other work in this session, ask the engineer (AskUserQuestion, in Vietnamese) which "
        "handoff to resume, one option per row above, plus 'something else'. Read the chosen handoff "
        "file before acting and keep it updated as you go. A row and its file are removed only after the "
        "engineer confirms in chat that the topic is cleared; until then this question is asked again at "
        "the start of every new session."
    )


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    index = find_index(project_dir)
    if index is None:
        return 0
    try:
        rows = open_rows(index.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return 0
    if not rows:
        return 0
    out = {
        "systemMessage": f"{len(rows)} open handoff(s) in .handoff/INDEX.md: Claude asks which to resume.",
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context(rows, index)},
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # a reminder must never break session start
        sys.exit(0)
