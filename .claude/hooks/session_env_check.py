#!/usr/bin/env python3
"""SessionStart hook: tell Claude what this machine can and cannot do.

Plain-text stdout from a SessionStart hook is added to Claude's context.
Never blocks; always exits 0. Stdlib only.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys

MIN_PYTHON = (3, 12)


def report(env: dict[str, str] | None = None, which=shutil.which) -> list[str]:
    env = dict(os.environ) if env is None else env
    lines = ["Environment report (session_env_check):"]
    problems: list[str] = []

    if env.get("CLAUDE_CODE_REMOTE") == "true":
        problems.append(
            "Session is REMOTE (cloud). Tekla is unreachable; do not run project steps that "
            "touch Tekla. Tell the engineer to reopen this repo in a local session."
        )
    system = platform.system()
    lines.append(f"- OS: {system} {platform.release()}")
    if system != "Windows":
        problems.append("Not Windows: Tekla Structures cannot run here (development only).")

    py = sys.version_info
    lines.append(f"- Python: {py.major}.{py.minor}.{py.micro}")
    if (py.major, py.minor) < MIN_PYTHON:
        problems.append(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required.")

    for tool, why in (
        ("uv", "Python environment"),
        ("git", "version control"),
        ("tekla-cli", "Tekla access (built in Step 3)"),
    ):
        path = which(tool)
        lines.append(f"- {tool}: {path or 'NOT FOUND'} ({why})")
        if path is None and tool != "tekla-cli":
            problems.append(f"{tool} not found on PATH.")

    if problems:
        lines.append("Problems:")
        lines.extend(f"  * {p}" for p in problems)
    else:
        lines.append("No blocking problems.")
    return lines


def main() -> int:
    try:
        sys.stdout.write("\n".join(report()) + "\n")
    except Exception as exc:  # never break session start
        sys.stdout.write(f"Environment report failed: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
