# 0004. Enforce "only builder writes to Tekla" in code

- Status: accepted
- Date: 2026-11-06

## Context

Rule 4 says only the `builder` agent may write to Tekla. Instructions in prompts are not
enforcement. Claude Code `PreToolUse` hooks receive `agent_type` for tool calls made inside
a subagent, and can deny the call.

## Decision

- A project `PreToolUse` hook on `Bash|PowerShell` parses every command for `tekla-cli`
  invocations. Any subcommand not in the read allowlist is a write. A write from any agent
  other than `builder` (including the main session) is denied.
- The hook is set to `onFailure: "block"`: if it crashes or times out, the call is blocked.
- Writes from `builder` still hit a `permissions.ask` rule, so the engineer confirms each one.

## Consequences

- New read-only subcommands must be added to the hook's allowlist with tests.
- Calling Tekla any other way (scripts that load the Tekla API directly) is out of policy;
  code review must reject it. The hook cannot detect indirect invocations such as a variable
  holding the executable name — `tekla-cli`'s own checks (contract rule 1–3) are the backstop.
