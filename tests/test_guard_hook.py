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
    "bash -c 'tekla-cli build --lot 1'",
    "env tekla-cli build --lot 1",
    "FOO=1 tekla-cli build --lot 1",
    "tekla-cli info; bash -c 'tekla-cli build --lot 1'",  # a read must not hide a later write
    'git commit -m "$(tekla-cli build --lot 1)"',  # substitution runs even inside double quotes
    'echo "`tekla-cli build`"',
    "git -c alias.x='!tekla-cli build' x",  # git aliases can run code
    "python -c \"import subprocess; subprocess.run(['tekla-cli', 'build'])\"",
    "sed -n 'e tekla-cli build' x",  # sed `e` runs a shell command: sed is not inert
    "bash -c 'tekla-cli.cmd build'",  # a shim name is still a mention
    # RTI-0006: the .NET project name and dotnet-run routes.
    "TeklaCli.exe build --lot 1",
    r"tekla\TeklaCli\bin\x64\Release\net48\TeklaCli.exe build --lot 1",
    "teklacli update --lot 2",
    "tekla_cli rollback --run-id r1",
    "dotnet run --project tekla/TeklaCli -- build --lot 1",
    "cd tekla/TeklaCli && dotnet run -- build --lot 1",  # no name in the dotnet segment
    "dotnet watch run --project tekla/TeklaCli",
    "dotnet exec bin/tekla-cli.exe build",
    "env dotnet run -- build",
    "dotnet build tekla/TeklaCli && dotnet run --project tekla/TeklaCli -- build",
    "C:/Program Files/dotnet/dotnet.exe run -- build",
    # RTI-0009: a newline separates commands, so an inert first line must not hide a write.
    "cd projects/p\ntekla-cli build --lot 1 --run-id r1 --spec lots/1/spec.json",
    "git status\ntekla-cli build --lot 1",
    "cat notes.md\r\ntekla-cli build --lot 1",
    "cd projects/p && \\\ntekla-cli build --lot 1",  # line continuation
    # PowerShell: a trailing backslash is part of a path, not a continuation.
    "Set-Location C:\\TeklaModels\\proj\\\ntekla-cli build --lot 1",
    "dir projects\\p\\\r\ntekla-cli build --lot 1",
]

# Commands that only mention the tool name as data. They must not be blocked, otherwise the
# main session cannot read the docs or commit work about the tool.
MENTION_ONLY_COMMANDS = [
    "cat docs/tekla-cli-contract.md",
    "grep -rn tekla-cli docs/",
    'git commit -m "docs: contract\n\ntekla-cli build is reserved for the builder"',  # RTI-0009
    'git commit -m "docs: update tekla-cli contract"',
    'git log --grep="tekla-cli"',
    "git diff -- docs/tekla-cli-contract.md",
    'echo "tekla-cli build is reserved for the builder"',
    "Get-Content docs\\tekla-cli-contract.md",
    "cat bin/tekla-cli.exe",  # an exe path used as an argument is not an invocation
    "cat docs/tekla-cli-contract.md | head -20",
    # RTI-0005: a file name that only contains the tool name, after a non-inert command.
    "cd /repo && sed -n 1,40p docs/tekla-cli-contract.md; echo ----; sed -n 1,30p docs/roadmap.md",
    "uv run python -I scripts/check.py docs/tekla-cli-contract.md",
    # RTI-0006: building and reading the CLI project is not running it.
    "dotnet build tekla/TeklaCli/TeklaCli.csproj -c Release",
    "cd tekla/TeklaCli && dotnet restore",
    "dotnet clean tekla/TeklaCli",
    "cat tekla/TeklaCli/Program.cs",
    "ls tekla/TeklaCli/bin",
]

READ_COMMANDS = [
    "tekla-cli info",
    "tekla-cli validate --spec lots/1/spec.json",
    "tekla-cli query --lot 1",
    "tekla-cli selected",
    "tekla-cli export --lot 1 --out lots/1/export",
    r"C:\Tools\tekla-cli.exe info",
    "TeklaCli.exe query --lot 1",
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


@pytest.mark.parametrize("command", MENTION_ONLY_COMMANDS)
@pytest.mark.parametrize("agent", [None, "planner", "builder"])
def test_mention_only_is_not_blocked(guard, command, agent):
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


@pytest.mark.parametrize("stdin", ["not json", "[1, 2]", '"a string"', "42"])
def test_script_fails_closed_on_bad_input(stdin):
    """Claude Code blocks a tool call only on exit code 2 (other non-zero codes are
    non-blocking errors), so every internal failure must exit exactly 2."""
    result = subprocess.run(
        [sys.executable, str(HOOKS / "guard_tekla_write.py")],
        input=stdin,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "blocking the call" in result.stderr
    assert result.stdout == ""


# RTI-0008: only `harness validate spec` writes a spec validation receipt. The guard denies a
# shell command that could write or delete `*.receipt.json`, for every agent, builder included.
RECEIPT_WRITE_COMMANDS = [
    "echo '{}' > lots/1/spec.json.receipt.json",
    "echo x>lots/1/spec.json.receipt.json",  # redirection without spaces
    "cat forged.json >> lots/1/spec.json.receipt.json",
    "cat forged.json 2> lots/1/spec.json.receipt.json",
    "cat forged.json &> lots/1/spec.json.receipt.json",
    "cd lots/1 && cat > spec.json.receipt.json <<'EOF'\n{}\nEOF",
    "printf '{}' | tee lots/1/spec.json.receipt.json",
    "cp /tmp/forged.json lots/1/spec.json.receipt.json",
    "mv /tmp/forged.json lots/1/spec.json.receipt.json",
    "ln -s /tmp/forged.json lots/1/spec.json.receipt.json",
    "rm lots/1/spec.json.receipt.json",
    "sed -i 's/a/b/' lots/1/spec.json.receipt.json",
    "python -c \"open('lots/1/spec.json.receipt.json', 'w').write('{}')\"",
    "uv run python -c \"open('x.json.receipt.json', 'w')\"",
    "cat $(echo lots/1/spec.json.receipt.json)",  # substitution: never inert
    "Set-Content lots\\1\\spec.json.receipt.json '{}'",
    "Get-Content forged.json | Out-File lots\\1\\spec.json.receipt.json",
    "Copy-Item forged.json lots\\1\\SPEC.JSON.RECEIPT.JSON",
    "cat lots/1/spec.json.receipt.json > lots/2/spec.json.receipt.json",  # second name redirected
    # RTI-0009: a newline separates commands; a reader on line 1 must not cover line 2.
    "cd projects/p/lots/1\ncp /tmp/forged.json spec.json.receipt.json",
    "cat lots/1/spec.json.receipt.json\ncp /tmp/forged.json lots/1/spec.json.receipt.json",
    "Get-Content x.receipt.json\r\nCopy-Item forged.json x.receipt.json",
    "ls lots/1\nrm lots/1/spec.json.receipt.json",
    "cat forged.json > \\\n  lots/1/spec.json.receipt.json",  # line continuation
    "cat forged.json >\\\nlots/1/spec.json.receipt.json",
    "Get-ChildItem lots\\1\\\ncopy-item forged.json lots\\1\\spec.json.receipt.json",
    "dir projects\\p\\\r\nRemove-Item lots\\1\\spec.json.receipt.json",
    # A receipt name piped into a writer, also through grouping and later pipeline stages.
    "ls lots/1/*.receipt.json | xargs -I{} cp forged.json {}",
    "Get-ChildItem lots\\1\\spec.json.receipt.json | Set-Content -Value '{}'",
    "ls lots/*/*.receipt.json | grep lots/1 | xargs -I{} cp forged.json {}",
    "(ls lots/1/*.receipt.json) | xargs -I{} cp forged.json {}",
    "{ ls lots/1/*.receipt.json; } | xargs -I{} cp forged.json {}",
    "(Get-ChildItem lots\\1\\spec.json.receipt.json) | Set-Content -Value '{}'",
    "(ls lots/1/*.receipt.json; true) | xargs rm",
    # `&` inside `2>&1`, `|&`, `>&2` is not a statement end.
    "ls lots/1/*.receipt.json 2>&1 | xargs -I{} cp forged.json {}",
    "ls lots/1/spec.json.receipt.json |& xargs -I{} cp forged.json {}",
    "Get-ChildItem lots\\1\\spec.json.receipt.json 2>&1 | Set-Content -Value '{}'",
    "ls lots/1/spec.json.receipt.json >&2 | xargs rm",
    # git subcommands that are otherwise inert can write a file.
    "git diff --output=lots/1/spec.json.receipt.json",
    "git log -1 --format=%H --output lots/1/spec.json.receipt.json",
    # A reader whose argument runs a command.
    'Test-Path "$(Copy-Item forged.json lots\\1\\spec.json.receipt.json)"',
]

RECEIPT_READ_COMMANDS = [
    "cat lots/1/spec.json.receipt.json",
    "ls lots/1/*.receipt.json",
    "grep sha256 lots/1/spec.json.receipt.json",
    "Get-Content lots\\1\\spec.json.receipt.json",
    'git log --grep=".receipt.json"',
    'git commit -m "docs: explain spec.json.receipt.json"',
    'git commit -m "docs: receipts\n\nspec.json.receipt.json is written by harness"',
    "uv run harness validate spec lots/1/spec.json",  # the one producer of receipts
    "uv run harness validate spec lots/1/spec.json && cat lots/1/spec.json.receipt.json",
    "uv run pytest tests/test_receipt.py",
    "cat schemas/examples/spec-receipt.example.json",
    "cat lots/1/spec.json.receipt.json > /tmp/copy.json",  # reading a receipt into another file
    "cat lots/1/spec.json.receipt.json | jq .sha256",
    "Get-Content lots\\1\\spec.json.receipt.json | ConvertFrom-Json",
    "Get-Content lots\\1\\spec.json.receipt.json | ConvertFrom-Json | Select-Object spec_sha256",
    "Get-Content lots\\1\\spec.json.receipt.json | ConvertFrom-Json | Format-List",
    "cat lots/1/spec.json.receipt.json | jq -r .spec_sha256 | tr -d x",
    "ls lots/1/*.receipt.json; cp a.json b.json",  # a new statement is not fed the receipt
    "ls lots/1/*.receipt.json; ls | xargs echo",
    "cat lots/1/spec.json.receipt.json 2>&1 | head",
    # Existence and comparison checks (builder.md step 1).
    "Test-Path lots\\1\\spec.json.receipt.json",
    "test -f lots/1/spec.json.receipt.json",
    "[ -f lots/1/spec.json.receipt.json ]",
    "stat lots/1/spec.json.receipt.json",
    "jq . lots/1/spec.json.receipt.json",
    "diff lots/1/spec.json.receipt.json lots/2/spec.json.receipt.json",
]


@pytest.mark.parametrize("command", RECEIPT_WRITE_COMMANDS)
@pytest.mark.parametrize("agent", [None, "builder", "doc-reader", "planner"])
@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_receipt_write_denied_for_every_agent(guard, command, agent, tool):
    assert is_denied(guard.decide(payload(command, agent, tool)))


@pytest.mark.parametrize("command", RECEIPT_READ_COMMANDS)
@pytest.mark.parametrize("agent", [None, "builder", "doc-reader"])
def test_receipt_read_passes(guard, command, agent):
    assert guard.decide(payload(command, agent)) is None


def test_receipt_reason_names_the_producer(guard):
    reason = guard.decide(payload("cp a lots/1/spec.json.receipt.json", "builder"))["hookSpecificOutput"][
        "permissionDecisionReason"
    ]
    assert "receipt" in reason and "harness validate spec" in reason


def test_receipt_check_runs_before_the_builder_exemption(guard):
    # A builder command that both runs a CLI write and forges a receipt is denied.
    command = "echo {} > s.json.receipt.json && tekla-cli build --lot 1 --spec s.json"
    assert is_denied(guard.decide(payload(command, "builder")))


def test_receipt_check_in_end_to_end_script():
    result = subprocess.run(
        [sys.executable, str(HOOKS / "guard_tekla_write.py")],
        input=json.dumps(payload("cp a lots/1/spec.json.receipt.json", "builder")),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_settings_deny_edits_of_receipts():
    """The Write/Edit/NotebookEdit tools and Bash redirection targets are blocked by this
    Claude Code deny rule (permissions docs: Edit rules cover every built-in file-editing tool).
    Claude Code enforces it, not pytest: this test only pins that the rule is configured."""
    settings = json.loads((HOOKS.parent / "settings.json").read_text(encoding="utf-8"))
    assert "Edit(**/*.receipt.json)" in settings["permissions"]["deny"]
    assert not any("receipt" in rule for rule in settings["permissions"]["allow"])
