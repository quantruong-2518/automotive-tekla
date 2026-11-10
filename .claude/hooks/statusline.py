#!/usr/bin/env python3
"""Claude Code statusline: model, effort and context tokens, coloured by context freshness.

Two modes, one script:

- `statusline.py` (main): one line for the main session.
- `statusline.py --subagents`: one JSON line `{"id", "content"}` per task for the subagent panel.

Colour by tokens, with the thresholds loaded from `context_guard.py` (same folder) so there is
one source of truth: below WARN green `fresh`, from WARN yellow `warn`, from HANDOFF red
`handoff`. If the thresholds cannot be loaded, tokens are shown uncoloured. Malformed input
prints nothing; always exits 0. Stdlib only, no subprocess calls.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

GUARD_PATH = Path(__file__).resolve().with_name("context_guard.py")

GREEN, YELLOW, RED, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"
DEFAULT_COLUMNS = 120
NO_DATA = "\u2013"  # en dash
ANSI = re.compile(r"(\033\[[0-9;]*m)")


def load_thresholds() -> tuple[int, int] | None:
    """(WARN_TOKENS, HANDOFF_TOKENS) from context_guard.py, or None if unavailable."""
    try:
        spec = importlib.util.spec_from_file_location("context_guard_thresholds", GUARD_PATH)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        warn, handoff = int(module.WARN_TOKENS), int(module.HANDOFF_TOKENS)
    except Exception:
        return None
    return warn, handoff


def _num(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tokens_k(tokens: int) -> str:
    return f"{tokens // 1000}k"


def _window(size: int | None) -> str:
    if size == 1_000_000:
        return "1M"
    return f"{size // 1000}k" if size else "?"


def _badge(tokens: int, window: str | None) -> str:
    limits = load_thresholds()
    count = _tokens_k(tokens) + (f"/{window}" if window else "")
    if limits is None:
        return count
    warn, handoff = limits
    if tokens < warn:
        colour, label = GREEN, "fresh"
    elif tokens < handoff:
        colour, label = YELLOW, "warn"
    else:
        colour, label = RED, "handoff"
    return f"{colour}● {count} {label}{RESET}"


def render_main(data: dict[str, Any]) -> str:
    model = _text(_dict(data.get("model")).get("display_name"))
    if model is None:
        return ""
    effort = _text(_dict(data.get("effort")).get("level")) or "-"
    ctx = _dict(data.get("context_window"))
    tokens = _num(ctx.get("total_input_tokens"))
    window = _window(_num(ctx.get("context_window_size")))
    badge = f"{NO_DATA}/{window}" if tokens is None else _badge(tokens, window)
    parts = [model, effort, badge]
    branch = _text(_dict(data.get("worktree")).get("branch"))
    if branch:
        parts.append(branch)
    return " · ".join(parts)


def _truncate(row: str, columns: int) -> str:
    """Cut to `columns` visible characters (ANSI codes do not count), ending in an ellipsis."""
    if len(ANSI.sub("", row)) <= columns:
        return row
    budget = max(columns - 1, 0)
    out: list[str] = []
    for piece in ANSI.split(row):
        if ANSI.fullmatch(piece):
            out.append(piece)
            continue
        take = piece[:budget]
        out.append(take)
        budget -= len(take)
    result = "".join(out) + "…"
    return result + RESET if "\033" in result else result


def render_subagents(data: dict[str, Any]) -> list[str]:
    columns = _num(data.get("columns")) or DEFAULT_COLUMNS
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return []
    lines: list[str] = []
    for item in tasks:
        if not isinstance(item, dict) or "id" not in item:
            continue
        name = _text(item.get("agentType")) or _text(item.get("name")) or _text(item.get("type"))
        model = (_text(item.get("model")) or "-").removeprefix("claude-")
        effort = _text(item.get("effort")) or "-"
        tokens = _num(item.get("tokenCount"))
        badge = NO_DATA if tokens is None else _badge(tokens, None)
        parts = [name or "?", model, effort, badge]
        description = _text(item.get("description"))
        if description:
            parts.append(description)
        content = _truncate(" · ".join(parts), columns)
        lines.append(json.dumps({"id": item["id"], "content": content}, ensure_ascii=False))
    return lines


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        data = json.loads(sys.stdin.read())
        if not isinstance(data, dict):
            return 0
        subagents = "--subagents" in args
        output = "\n".join(render_subagents(data)) if subagents else render_main(data)
        if output:
            sys.stdout.write(output + "\n")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
