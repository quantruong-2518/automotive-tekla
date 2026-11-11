"""The agent tier guard keeps `executor` on the execution tier and generic agents on a set model."""

from __future__ import annotations

import json
import subprocess
import sys
from types import ModuleType

import pytest

from conftest import HOOKS, load_hook


@pytest.fixture
def tier() -> ModuleType:
    return load_hook("guard_agent_tier")


def payload(subagent: str = "executor", tool: str = "Agent", **tool_input: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"subagent_type": subagent, "prompt": "do it", **tool_input},
    }


def is_denied(decision: dict | None) -> bool:
    return bool(decision) and decision["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("model", ["opus", "fable", "OPUS", "claude-opus-4", ""])
def test_executor_on_a_higher_model_is_denied(tier, model):
    assert is_denied(tier.decide(payload(model=model)))


@pytest.mark.parametrize("model", ["sonnet", "haiku"])
def test_executor_on_execution_models_is_allowed(tier, model):
    assert tier.decide(payload(model=model)) is None


def test_executor_without_model_or_effort_is_allowed(tier):
    assert tier.decide(payload()) is None


@pytest.mark.parametrize("effort", ["xhigh", "max"])
def test_executor_at_top_effort_is_denied(tier, effort):
    assert is_denied(tier.decide(payload(model="sonnet", effort=effort)))
    assert is_denied(tier.decide(payload(effort=effort)))


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_executor_at_normal_effort_is_allowed(tier, effort):
    assert tier.decide(payload(model="sonnet", effort=effort)) is None


def test_other_subagent_is_not_touched(tier):
    assert tier.decide(payload("planner", model="opus", effort="max")) is None


def test_fork_without_model_is_not_touched(tier):
    assert tier.decide(payload("fork")) is None


def test_general_purpose_without_model_is_denied(tier):
    assert is_denied(tier.decide(payload("general-purpose")))
    assert is_denied(tier.decide({"tool_name": "Agent", "tool_input": {"prompt": "x"}}))


@pytest.mark.parametrize("agent", ["general-purpose", "claude"])
@pytest.mark.parametrize("model", ["", "  "])
def test_generic_agent_with_blank_model_is_denied(tier, agent, model):
    assert is_denied(tier.decide(payload(agent, model=model)))


def test_claude_agent_without_model_is_denied(tier):
    assert is_denied(tier.decide(payload("claude")))


@pytest.mark.parametrize("agent", ["planner", "doc-reader", "builder", "verifier", "Explore"])
def test_named_agent_without_model_is_not_touched(tier, agent):
    assert tier.decide(payload(agent)) is None


@pytest.mark.parametrize("agent", ["general-purpose", "claude", " Claude "])
@pytest.mark.parametrize("model", ["sonnet", "haiku", "opus"])
def test_generic_agent_with_a_model_is_allowed(tier, agent, model):
    assert tier.decide(payload(agent, model=model)) is None


def test_missing_subagent_type_counts_as_general_purpose(tier):
    with_model = {"tool_name": "Agent", "tool_input": {"prompt": "x", "model": "sonnet"}}
    assert tier.decide(with_model) is None
    for blank in (None, "", " "):
        spawn = {"tool_name": "Agent", "tool_input": {"prompt": "x", "subagent_type": blank}}
        assert is_denied(tier.decide(spawn))


def test_task_tool_name_is_guarded_for_generic(tier):
    assert is_denied(tier.decide(payload("general-purpose", tool="Task")))
    assert tier.decide(payload("general-purpose", tool="Task", model="haiku")) is None


def test_generic_reason_names_the_rule(tier):
    reason = tier.decide(payload("general-purpose"))["hookSpecificOutput"]["permissionDecisionReason"]
    assert "inherits" in reason and "delegating-work" in reason and "general-purpose" in reason


def test_generic_agent_with_non_string_model_raises(tier):
    bad = {"tool_name": "Agent", "tool_input": {"subagent_type": "general-purpose", "model": ["opus"]}}
    with pytest.raises(ValueError):
        tier.decide(bad)


@pytest.mark.parametrize("name", ["General-Purpose", " general-purpose ", "Claude"])
def test_generic_agent_name_is_matched_loosely(tier, name):
    assert is_denied(tier.decide(payload(name)))


def test_task_tool_name_is_handled(tier):
    assert is_denied(tier.decide(payload(tool="Task", model="opus")))
    assert tier.decide(payload(tool="Task", model="sonnet")) is None


def test_other_tools_are_ignored(tier):
    assert tier.decide(payload(tool="Bash", model="opus")) is None


def test_reason_names_the_offender_and_the_rule(tier):
    reason = tier.decide(payload(model="opus"))["hookSpecificOutput"]["permissionDecisionReason"]
    assert "model=opus" in reason and "sonnet" in reason and "delegating-work" in reason


def test_script_end_to_end():
    script = HOOKS / "guard_agent_tier.py"
    denied = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload(model="opus")),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    allowed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload(model="sonnet")),
        capture_output=True,
        text=True,
        check=True,
    )
    assert allowed.stdout == ""


@pytest.mark.parametrize(
    "stdin",
    [
        "not json",
        "[1, 2]",
        '"a string"',
        "42",
        '{"tool_name": "Agent", "tool_input": "x"}',
        '{"tool_name": "Agent", "tool_input": [1]}',
        '{"tool_name": "Agent", "tool_input": {"subagent_type": "executor", "model": ["opus"]}}',
        '{"tool_name": "Agent", "tool_input": {"subagent_type": 123, "model": "sonnet"}}',
        '{"tool_name": "Agent", "tool_input": {"subagent_type": ["general-purpose"]}}',
    ],
)
def test_script_fails_closed_on_bad_input(stdin):
    result = subprocess.run(
        [sys.executable, str(HOOKS / "guard_agent_tier.py")],
        input=stdin,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "blocking the call" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("name", ["Executor", " executor "])
def test_executor_name_is_matched_loosely(tier, name):
    assert is_denied(tier.decide(payload(name, model="opus")))


@pytest.mark.parametrize("bad", [123, ["general-purpose"], [], 0, False, {}])
def test_non_string_subagent_type_raises(tier, bad):
    spawn = {"tool_name": "Agent", "tool_input": {"subagent_type": bad, "model": "sonnet"}}
    with pytest.raises(ValueError):
        tier.decide(spawn)
