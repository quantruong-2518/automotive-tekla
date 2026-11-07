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
- The hook fails closed by itself: any internal error (bad stdin, unexpected payload) exits
  with code 2, the blocking exit code. It does not rely on a settings field (see Amendment).
- Commands that only mention `tekla-cli` as data (`cat docs/tekla-cli-contract.md`,
  `git commit -m "..."`, `grep`) are allowed. A segment is skipped only if its command word
  is on a short inert list and the command has no `$(` or backtick substitution.
- Writes from `builder` still hit a `permissions.ask` rule, so the engineer confirms each one.

## Amendment (2026-11-06, review)

- The first version relied on `onFailure: "block"`. That field is not in the Claude Code hooks
  documentation we checked, and a crash exited with code 1, which Claude Code treats as a
  non-blocking error. The field was removed; the script now exits 2 on any failure.
- The first version blocked every command containing the text `tekla-cli`, including reading
  its own contract. It now parses per command segment (see Decision).
- Still unverified: the hook timeout behaviour (a timeout is probably non-blocking). The script
  is tiny and has no I/O besides stdin; re-check the docs before relying on it.
- Still unverified until the first real builder run: that `agent_type` is present in the
  payload of tool calls made inside the `builder` subagent. If it is missing, the builder is
  denied (safe), and the fix is in the hook, not in the agent prompt.
- RTI-0005: a longer name such as `tekla-cli-contract.md` is not a mention of the tool, so
  reading it with a non-inert command (`sed`, `python`) is allowed.
- RTI-0006 (ADR-0007): the .NET project name (`TeklaCli.exe`, `teklacli`, `tekla_cli`) is
  recognised as the CLI, and every `dotnet run|exec|watch` counts as a write, since it can start
  the CLI without naming it. `dotnet build|restore|clean` and `cd`/`pushd` are inert.

## Consequences

- New read-only subcommands must be added to the hook's allowlist with tests.
- Calling Tekla any other way (scripts that load the Tekla API directly) is out of policy;
  code review must reject it. The hook cannot detect indirect invocations such as a variable
  holding the executable name — `tekla-cli`'s own checks (contract rule 1–3) are the backstop.
