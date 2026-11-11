#!/usr/bin/env python3
"""PreToolUse guard: executor stays on the execution tier; generic spawns name a model.

Reads the Claude Code hook payload on stdin. When an Agent (older Claude Code: Task) call
spawns `executor`, an explicit `model` outside EXECUTOR_MODELS or an explicit `effort` in
BANNED_EFFORTS is denied. A missing model or effort is allowed: the agent's frontmatter
(sonnet, medium) then applies. A generic agent (GENERIC_AGENTS; a missing or blank
`subagent_type` counts as general-purpose) spawned without a non-empty `model` is denied,
because it would inherit the session's model. Agent names match after strip() and lower().
Every other subagent and every other tool is not touched.

Exit 0 with no output  -> no decision; the normal permission flow applies.
Exit 0 with JSON deny  -> the tool call is blocked and the reason is shown to Claude.
Exit 2                 -> blocking error. Any crash (bad stdin, unexpected payload) exits 2,
                          so the guard fails closed by itself. A non-zero exit other than 2
                          would NOT block.
Stdlib only, so it runs before the project environment exists.
"""

from __future__ import annotations

import json
import sys

AGENT_TOOLS = frozenset({"Agent", "Task"})
GUARDED_AGENT = "executor"
EXECUTOR_MODELS = frozenset({"sonnet", "haiku"})
BANNED_EFFORTS = frozenset({"xhigh", "max"})
GENERIC_AGENTS = frozenset({"general-purpose", "claude"})


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def decide(payload: dict) -> dict | None:
    """Return a PreToolUse deny decision, or None for no decision."""
    if payload.get("tool_name") not in AGENT_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise ValueError(f"tool_input must be a JSON object, got {type(tool_input).__name__}")
    agent = tool_input.get("subagent_type")
    if agent is not None and not isinstance(agent, str):
        raise ValueError(f"subagent_type must be a string, got {type(agent).__name__}")
    agent = (agent or "").strip().lower() or "general-purpose"
    if agent in GENERIC_AGENTS:
        model = tool_input.get("model")
        if model is not None and not isinstance(model, str):
            raise ValueError(f"model must be a string, got {type(model).__name__}")
        if model is not None and model.strip():
            return None
        return _deny(
            f"Blocked: a {agent} spawn without `model` inherits the session's model. "
            "Set `model` (and effort) on every spawn: sonnet or haiku for execution, opus "
            "only for judgement work (delegating-work skill)."
        )
    if agent != GUARDED_AGENT:
        return None
    problems: list[str] = []
    model = tool_input.get("model")
    if model is not None:
        if not isinstance(model, str):
            raise ValueError(f"model must be a string, got {type(model).__name__}")
        if model.strip().lower() not in EXECUTOR_MODELS:
            problems.append(f"model={model}")
    effort = tool_input.get("effort")
    if effort is not None:
        if not isinstance(effort, str):
            raise ValueError(f"effort must be a string, got {type(effort).__name__}")
        if effort.strip().lower() in BANNED_EFFORTS:
            problems.append(f"effort={effort}")
    if not problems:
        return None
    return _deny(
        f"Blocked: {GUARDED_AGENT} runs execution packages on sonnet or haiku at "
        f"low/medium/high effort (got {', '.join(problems)}). Judgement work (planning, "
        "review, diagnosis) belongs to the orchestrator or a review agent; if the package "
        "seems to need Opus, decompose it further (delegating-work §2)."
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError(f"hook payload must be a JSON object, got {type(payload).__name__}")
        decision = decide(payload)
    except Exception as exc:  # fail closed: exit 2 is the only non-zero code that blocks
        sys.stderr.write(f"guard_agent_tier: internal error, blocking the call: {exc!r}\n")
        return 2
    if decision is not None:
        sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
