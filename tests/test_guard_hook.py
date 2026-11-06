"""The Tekla write guard is a safety control: test it like one."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from conftest import HOOKS


def payload(command: str, agent: str | None = None, tool: str = "Bash") -> dict:
    p = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}}
    if agent is not None:
        p["agent_type"] = agent
    return p


def is_denied(decision: dict | None) -> bool:
    return bool(decision) and decision["hookSpecificOutput"]["permissionDecision"] == "deny"


WRITE_COMMANDS = [
    "tekla-cli build --lot 1 --run-id r1 --spec lots/1/spec.json",
    "tekla-cli update --lot 2",
    "tekla-cli rollback --run-id r1",
    "TEKLA-CLI.EXE build --lot 1",
    r"C:\Tools\tekla-cli.exe build --lot 1",
    r'& "C:\Program Files\Harness\tekla-cli.exe" build --lot 1',
    "cd projects/x && tekla-cli build --lot 1",
    "tekla-cli info && tekla-cli build --lot 1",
    "echo $(tekla-cli build --lot 1)",
    "tekla-cli",  # no subcommand: unknown, fail closed
    "tekla-cli delete-everything",  # unknown subcommand: fail closed
    "tekla-cli --lot 1 build",  # option before subcommand: contract violation, fail closed
    'tekla-cli build "unterminated',
]

READ_COMMANDS = [
    "tekla-cli info",
    "tekla-cli validate --spec lots/1/spec.json",
    "tekla-cli query --lot 1",
    "tekla-cli selected",
    "tekla-cli export --lot 1 --out lots/1/export",
    r"C:\Tools\tekla-cli.exe info",
    "uv run pytest",
    "git status",
]


@pytest.mark.parametrize("command", WRITE_COMMANDS)
@pytest.mark.parametrize("agent", [None, "doc-reader", "planner", "verifier", "reporter", "Explore"])
def test_write_denied_outside_builder(guard, command, agent):
    assert is_denied(guard.decide(payload(command, agent)))


@pytest.mark.parametrize("command", WRITE_COMMANDS)
def test_builder_gets_no_decision(guard, command):
    # No decision -> normal permission flow (the `ask` rules) still applies.
    assert guard.decide(payload(command, "builder")) is None


@pytest.mark.parametrize("command", READ_COMMANDS)
@pytest.mark.parametrize("agent", [None, "planner", "verifier"])
def test_reads_pass(guard, command, agent):
    assert guard.decide(payload(command, agent)) is None


def test_powershell_tool_is_guarded(guard):
    assert is_denied(guard.decide(payload("tekla-cli build --lot 1", tool="PowerShell")))


def test_other_tools_ignored(guard):
    p = {"tool_name": "Write", "tool_input": {"file_path": "x", "content": "tekla-cli build"}}
    assert guard.decide(p) is None


def test_reason_names_agent_and_rule(guard):
    reason = guard.decide(payload("tekla-cli build", "planner"))["hookSpecificOutput"][
        "permissionDecisionReason"
    ]
    assert "planner" in reason and "builder" in reason


def test_script_end_to_end():
    """Run the hook exactly as Claude Code does: JSON on stdin, decision on stdout."""
    script = HOOKS / "guard_tekla_write.py"
    denied = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload("tekla-cli build --lot 1")),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"

    allowed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload("tekla-cli build --lot 1", "builder")),
        capture_output=True,
        text=True,
        check=True,
    )
    assert allowed.stdout == ""


def test_script_crashes_on_garbage_input():
    """A crash must be non-zero so `onFailure: block` blocks the call."""
    result = subprocess.run(
        [sys.executable, str(HOOKS / "guard_tekla_write.py")],
        input="not json",
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
