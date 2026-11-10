#!/usr/bin/env python3
"""UserPromptSubmit and Stop hook: keep the main session's context from growing too large.

Long contexts degrade answer quality and every turn re-reads the whole context (cost). The
context size is read from the last main-chain assistant message in the transcript: input tokens
plus cache creation plus cache read tokens.

- UserPromptSubmit: at or above the warn level, inject a warning; at or above the handoff limit,
  tell Claude to update the handoff file and ask the engineer to type /clear. Never blocks.
- Stop: at or above the handoff limit, block once per session with the same instruction (a
  marker file in the temp dir remembers it); the marker is removed when the context falls back
  below the warn level (after /clear or /compact).

Skips subagents (stdin carries a non-empty `agent_id`). Never blocks otherwise; always exits 0.
Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

# Engineer defaults 2026-11-10, not measured; see docs/research/context-length-quality.md and
# ADR-0014.
WARN_TOKENS = 200_000
HANDOFF_TOKENS = 250_000

CHUNK_BYTES = 4 * 1024 * 1024
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

HANDOFF_TEXT = (
    "Context is {n} tokens, over the handoff limit of 250000 (ADR-0014). Finish only the step "
    "in progress and start no new work. Update the active topic's `.handoff/<topic>.md` and its "
    "row in `.handoff/INDEX.md` of the main checkout: decisions taken, commit SHAs, live agents "
    "and what each owns, the next steps. Then tell the engineer, in Vietnamese, that the "
    "handoff is saved and to type /clear."
)
WARN_TEXT = (
    "Context is {n} tokens (warn level 200000; handoff at 250000, ADR-0014). Do not start a "
    "large new package in this session; keep the active handoff file current."
)


def _usage_total(line: bytes) -> int | None:
    """Token total of one transcript line if it is a main-chain assistant message, else None."""
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get("type") != "assistant" or obj.get("isSidechain"):
        return None
    message = obj.get("message")
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return None
    total = 0
    for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        value = usage.get(key, 0)
        if isinstance(value, int) and not isinstance(value, bool):
            total += value
    return total


def token_count(transcript_path: str) -> int | None:
    """Context size from the last main-chain assistant line, reading the file from its end."""
    try:
        with Path(transcript_path).open("rb") as fh:
            size = fh.seek(0, 2)
            window = CHUNK_BYTES
            while True:
                start = max(0, size - window)
                fh.seek(start)
                data = fh.read(size - start)
                lines = data.split(b"\n")
                if start > 0:
                    lines = lines[1:]  # the first line of the chunk may be cut off
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    total = _usage_total(line)
                    if total is not None:
                        return total
                if start == 0:
                    return None
                window *= 4
    except OSError:
        return None


def _marker(session_id: str) -> Path:
    return Path(tempfile.gettempdir()) / "claude-context-guard" / f"{session_id}.handoff"


def _emit(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data))


def on_user_prompt(tokens: int) -> None:
    if tokens >= HANDOFF_TOKENS:
        message = (
            f"Context {tokens // 1000}k tokens ≥ 250k handoff limit: "
            "Claude updates the handoff file; then type /clear."
        )
        text = HANDOFF_TEXT.format(n=tokens)
    elif tokens >= WARN_TOKENS:
        message = f"Context {tokens // 1000}k tokens ≥ 200k warn level (handoff at 250k)."
        text = WARN_TEXT.format(n=tokens)
    else:
        return
    _emit(
        {
            "systemMessage": message,
            "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text},
        }
    )


def on_stop(tokens: int, session_id: object) -> None:
    if not isinstance(session_id, str) or not SESSION_ID.match(session_id):
        print("context_guard: invalid or missing session_id; never blocking", file=sys.stderr)
        return
    marker = _marker(session_id)
    if tokens < WARN_TOKENS:
        marker.unlink(missing_ok=True)
        return
    if tokens < HANDOFF_TOKENS or marker.exists():
        return
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError as exc:
        print(f"context_guard: cannot create marker, not blocking: {exc}", file=sys.stderr)
        return
    _emit({"decision": "block", "reason": HANDOFF_TEXT.format(n=tokens)})


def main() -> None:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict) or payload.get("agent_id"):
        return
    event = payload.get("hook_event_name")
    if event not in ("UserPromptSubmit", "Stop"):
        return
    if event == "Stop" and payload.get("stop_hook_active"):
        return
    path = payload.get("transcript_path")
    tokens = token_count(path) if isinstance(path, str) else None
    if tokens is None:
        print("context_guard: no usable token count in the transcript", file=sys.stderr)
        return
    if event == "UserPromptSubmit":
        on_user_prompt(tokens)
    else:
        on_stop(tokens, payload.get("session_id"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a hook must never break the session
        print(f"context_guard: {exc}", file=sys.stderr)
    sys.exit(0)
