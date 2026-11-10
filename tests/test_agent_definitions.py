"""Agent definitions carry safety layer 3 (tool scope): test the frontmatter like one."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import REPO

AGENTS = REPO / ".claude" / "agents"
TIERS = {"opus", "sonnet", "haiku"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
# A bare tool name, optionally with a parenthesised rule such as `Bash(git diff *)`.
TOOL_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\(.*\))?")
SPAWN_TOOL = re.compile(r"(Agent|Task)\b")


def frontmatter(path: Path) -> dict[str, str]:
    """Top-level `key: value` pairs between the leading `---` fences."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", f"{path.name}: no frontmatter"
    end = lines.index("---", 1)
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if line and not line.startswith((" ", "-")) and ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def tools(path: Path) -> list[str]:
    """The `tools` field as a comma-separated scalar; YAML list forms are rejected."""
    value = frontmatter(path).get("tools", "")
    tokens = [t.strip() for t in value.split(",")]
    assert value and all(TOOL_TOKEN.fullmatch(t) for t in tokens), (
        f"{path.name}: tools must be an explicit comma-separated list, got {value!r}"
    )
    return tokens


AGENT_FILES = sorted(AGENTS.glob("*.md"))


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_pins_name_model_effort_and_tools(path: Path) -> None:
    fields = frontmatter(path)
    assert fields.get("name") == path.stem
    assert fields.get("model") in TIERS
    assert fields.get("effort") in EFFORTS
    # Omitting `tools` would inherit every tool, the Agent tool included.
    assert tools(path)


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_no_project_agent_can_spawn_agents(path: Path) -> None:
    # Only the orchestrator dispatches (delegating-work: one orchestrator).
    assert not [t for t in tools(path) if SPAWN_TOOL.match(t)]


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_no_project_agent_widens_permissions(path: Path) -> None:
    assert "permissionMode" not in frontmatter(path)


def test_executor_is_sonnet_medium_and_bounded() -> None:
    fields = frontmatter(AGENTS / "executor.md")
    assert (fields["model"], fields["effort"]) == ("sonnet", "medium")
    assert 0 < int(fields["maxTurns"]) <= 100
    assert 100_000 <= int(fields["autoCompactWindow"]) <= 200_000
    assert "isolation" not in fields  # the orchestrator chooses a worktree per spawn
