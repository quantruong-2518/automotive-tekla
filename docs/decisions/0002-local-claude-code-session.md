# 0002. Run the harness in a local Claude Code session on the Tekla machine

- Status: accepted
- Date: 2026-11-06

## Context

Tekla Open API only talks to a Tekla Structures instance running on the same Windows machine.
Claude Code can run locally (CLI, desktop app *Code* tab) or in cloud sessions. The chat app
cannot run subagents, hooks or local executables.

## Decision

- Project runs use Claude Code in a **local** session on the Tekla machine. The desktop app
  *Code* tab is the default interface for the engineer; the CLI is equivalent.
- Benchmarks and regression runs use non-interactive Claude Code (`claude -p`) on the same machine.
- The Claude chat app is used for design discussion and external reports only.
- `tekla-cli` is called as a shell command, not wrapped as an MCP server, until multi-machine use is needed.
- Computer use is never used to operate Tekla.

## Consequences

- A `SessionStart` hook warns when the session is remote or `tekla-cli` is missing.
- Plugins declared in `.claude/settings.json` do not load in cloud sessions; this is acceptable.
