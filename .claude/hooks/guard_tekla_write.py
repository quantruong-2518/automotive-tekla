#!/usr/bin/env python3
"""PreToolUse guard: only the `builder` subagent may run tekla-cli write commands.

Reads the Claude Code hook payload on stdin. For Bash/PowerShell calls it finds every
`tekla-cli` invocation in the command. Any subcommand outside READ_SUBCOMMANDS is a
write (fail closed). A write from any agent other than `builder` is denied.

Exit 0 with no output  -> no decision; the normal permission flow applies.
Exit 0 with JSON deny  -> the tool call is blocked and the reason is shown to Claude.
Stdlib only, so it runs before the project environment exists.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

WRITER_AGENT = "builder"
READ_SUBCOMMANDS = frozenset(
    {"info", "validate", "query", "selected", "export", "version", "help", "--help", "-h", "--version"}
)
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

# Executable name: tekla-cli or tekla-cli.exe, optionally with a Windows or POSIX path.
_EXE = re.compile(r"(?:^|[\\/])tekla-cli(?:\.exe)?$", re.IGNORECASE)
# Mentions of tekla-cli that the tokenizer might miss (e.g. inside $(...) or & "...").
_MENTION = re.compile(r"tekla-cli", re.IGNORECASE)
# Shell operators that start a new simple command.
_SEPARATORS = frozenset({";", "&&", "||", "|", "&", "(", ")", "{", "}", "`", "$("})


def _split(command: str) -> list[str]:
    """Tokenize loosely across bash and PowerShell; never raise."""
    spaced = re.sub(r"(\$\(|&&|\|\||[;|&(){}`])", r" \1 ", command)
    try:
        lexer = shlex.shlex(spaced, posix=True, punctuation_chars=False)
        lexer.whitespace_split = True
        lexer.commenters = ""
        lexer.escape = ""  # keep Windows backslashes in paths
        return list(lexer)
    except ValueError:  # unbalanced quotes
        return [t.strip("\"'") for t in spaced.split()]


def find_subcommands(command: str) -> list[str | None]:
    """Return the subcommand of each tekla-cli invocation (None if missing)."""
    tokens = _split(command)
    found: list[str | None] = []
    for i, tok in enumerate(tokens):
        if not _EXE.search(tok):
            continue
        sub = None
        for nxt in tokens[i + 1 :]:
            if nxt in _SEPARATORS:
                break
            if nxt.startswith("-") and nxt.lower() not in READ_SUBCOMMANDS:
                continue  # global option before the subcommand
            sub = nxt.lower()
            break
        found.append(sub)
    if not found and _MENTION.search(command):
        found.append("<unparsed>")  # mentioned but not parseable: treat as write
    return found


def decide(payload: dict) -> dict | None:
    """Return a PreToolUse deny decision, or None for no decision."""
    if payload.get("tool_name") not in SHELL_TOOLS:
        return None
    command = str((payload.get("tool_input") or {}).get("command") or "")
    writes = [s for s in find_subcommands(command) if s is None or s not in READ_SUBCOMMANDS]
    if not writes:
        return None
    agent = payload.get("agent_type") or "main session"
    if agent == WRITER_AGENT:
        return None
    shown = ", ".join(s or "<none>" for s in writes)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked: tekla-cli write command ({shown}) from '{agent}'. "
                f"Only the '{WRITER_AGENT}' subagent may write to Tekla. "
                "Delegate this lot to the builder agent, or use a read subcommand "
                f"({', '.join(sorted(s for s in READ_SUBCOMMANDS if not s.startswith('-')))})."
            ),
        }
    }


def main() -> int:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    decision = decide(payload)
    if decision is not None:
        sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
