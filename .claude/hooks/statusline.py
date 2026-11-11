#!/usr/bin/env python3
"""Claude Code statusline: model, effort and context tokens, coloured by context freshness.

Two modes, one script:

- `statusline.py` (main): one line for the main session, same style as the subagent rows:
  `[worktree] opus5.5-high · ● 93k/1M fresh · $4.20 · limit 5%|46% · branch`. `[worktree]` is
  the linked worktree the session works in, `[main]` in the main checkout. The cost is Claude
  Code's own estimate at list price (not the bill). `limit` is the 5-hour then the 7-day rate-limit
  share, shown only when Claude Code sends it, yellow from 70%, red from 90%. A fast-mode session
  gets a ⚡.
- `statusline.py --subagents`: one JSON line `{"id", "content"}` per task for the subagent panel:
  `agent model-effort · ● tokens freshness · $price · task`. The agent name has a fixed colour per
  role. The price is the model's API list price for one million input tokens, not a running cost:
  the panel gives no per-task spend. Prices and costs share one colour.

Colour by tokens, with the thresholds loaded from `context_guard.py` (same folder) so there is
one source of truth: below WARN green `fresh`, from WARN yellow `warn`, from HANDOFF red
`handoff`. If the thresholds cannot be loaded, tokens are shown uncoloured. Malformed input
prints nothing; always exits 0. Stdlib only, no subprocess calls.
"""

from __future__ import annotations

import contextlib
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
DIM = "\033[2m"
SEP = f"{DIM} · {RESET}"
PRICE_COLOUR = "\033[1;38;5;213m"  # pink: money, apart from the freshness colours
WORKTREE_COLOUR = "\033[1;96m"

# Agent name colours: one per role, none of them green/yellow/red (those mean context freshness).
AGENT_COLOURS = {
    "executor": "\033[1;36m",  # cyan
    "doc-reader": "\033[1;34m",  # blue
    "planner": "\033[1;35m",  # magenta
    "builder": "\033[1;38;5;208m",  # orange: the only agent that writes to Tekla
    "verifier": "\033[1;38;5;79m",  # teal
    "reporter": "\033[1;38;5;180m",  # tan
    "general-purpose": "\033[1;37m",  # white
}
DEFAULT_AGENT_COLOUR = "\033[1;90m"  # grey

# API list prices 2026-11, USD per million tokens (input, output); same source as session_cost.py.
# Only the input price is shown.
PRICES = {"opus": (4, 20), "sonnet": (2, 10), "haiku": (0.10, 0.50)}


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


RATE_WARN, RATE_RED = 70, 90


def _rate(window: object) -> str | None:
    used = _dict(window).get("used_percentage")
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        return None
    used = round(used)  # colour what is shown, so "70%" is never uncoloured
    colour = RED if used >= RATE_RED else YELLOW if used >= RATE_WARN else ""
    return f"{colour}{used}%{RESET if colour else ''}"


def _worktree_tag(data: dict[str, Any]) -> str:
    name = _text(_dict(data.get("worktree")).get("name")) or _text(
        _dict(data.get("workspace")).get("git_worktree")
    )
    return f"{WORKTREE_COLOUR}[{name or 'main'}]{RESET} "


def _price(amount: str) -> str:
    return f"{PRICE_COLOUR}{amount}{RESET}"


def _main_model(display_name: str, fast: bool) -> str:
    return display_name.lower().replace(" ", "") + ("\u26a1" if fast else "")


def render_main(data: dict[str, Any]) -> str:
    model = _text(_dict(data.get("model")).get("display_name"))
    if model is None:
        return ""
    effort = _text(_dict(data.get("effort")).get("level")) or "-"
    ctx = _dict(data.get("context_window"))
    tokens = _num(ctx.get("total_input_tokens"))
    window = _window(_num(ctx.get("context_window_size")))
    badge = f"{NO_DATA}/{window}" if tokens is None else _badge(tokens, window)
    parts = [f"{_main_model(model, data.get('fast_mode') is True)}-{effort}", badge]
    spent = _dict(data.get("cost")).get("total_cost_usd")
    if isinstance(spent, (int, float)) and not isinstance(spent, bool):
        parts.append(_price(f"${spent:.2f}"))
    limits = _dict(data.get("rate_limits"))
    shares = [r for r in (_rate(limits.get("five_hour")), _rate(limits.get("seven_day"))) if r]
    if shares:
        parts.append("limit " + "|".join(shares))
    branch = _text(_dict(data.get("worktree")).get("branch"))
    if branch:
        parts.append(branch)
    return _worktree_tag(data) + SEP.join(parts)


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


def _short_model(model: str | None) -> tuple[str, str | None]:
    """('sonnet5.5', '$2') from 'claude-sonnet-5-5'; unknown models keep their id, no price."""
    if model is None:
        return "-", None
    family, _, version = model.removeprefix("claude-").partition("-")
    short = f"{family}{version.replace('-', '.')}" if version else family
    price = PRICES.get(family)
    return short, None if price is None else f"${price[0]:g}"


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
        model, price = _short_model(_text(item.get("model")))
        raw_effort = item.get("effort")
        if isinstance(raw_effort, (int, float)) and not isinstance(raw_effort, bool):
            raw_effort = str(raw_effort)
        effort = {"medium": "med"}.get(raw_effort, raw_effort) if isinstance(raw_effort, str) else None
        tokens = _num(item.get("tokenCount"))
        label = name or "?"
        colour = AGENT_COLOURS.get(label, DEFAULT_AGENT_COLOUR)
        parts = [
            f"{colour}{label}{RESET} {model}-{_text(effort) or '-'}",
            NO_DATA if tokens is None else _badge(tokens, None),
        ]
        if price:
            parts.append(_price(price))
        description = _text(item.get("description"))
        if description:
            parts.append(description)
        content = _truncate(SEP.join(parts), columns)
        lines.append(json.dumps({"id": item["id"], "content": content}, ensure_ascii=False))
    return lines


def _use_utf8_streams() -> None:
    """Claude Code speaks UTF-8 on stdin/stdout; a Windows console defaults to a legacy code page."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):  # not a reconfigurable text stream: leave it as it is
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    _use_utf8_streams()
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
