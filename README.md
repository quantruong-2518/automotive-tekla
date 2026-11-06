# Tekla AI Harness

A multi-agent harness that reads structural steel drawings, plans the modelling work,
builds the model in Tekla Structures lot by lot, verifies it against the drawings,
reports, and improves itself from engineer feedback.

> **AI decides, code does, the engineer signs off.**
> Agents interpret drawings and propose; deterministic code converts, validates and
> writes to Tekla; a human approves every gate.

| | |
|---|---|
| Status | **v0 — Step 0 (foundation).** No drawing reader and no Tekla connection yet. |
| Runtime | Claude Code (desktop app *Code* tab), **local session** on the Windows machine that runs Tekla |
| Languages | Python 3.12 (tooling, readers, checks) · C# / .NET Framework 4.8 (`TeklaCore`, `tekla-cli`, from Step 3) |
| Agent replies | Vietnamese. Everything committed to this repo is English (see [ADR-0003](docs/decisions/0003-language-policy.md)). |

## How it works

```
drawings ─► read & analyse ─► plan ─► [lot loop: extract spec ─► build ─► verify ─► report] ─► phase report
   (DWG/DXF/PDF/XLSX)   doc-reader     planner      doc-reader    builder   verifier   reporter
                                  gates 1–3                                   gate 4        gate 5
engineer feedback ─► requests-to-improve.md ─► /improve (gate 6) ─► better tools for the next project
```

Full flow, lanes and gates: [docs/workflow.md](docs/workflow.md).
Agent roles and safety layers: [docs/architecture.md](docs/architecture.md).
Build order: [docs/roadmap.md](docs/roadmap.md).

## Repository layout

```
.claude/
  settings.json        Shared Claude Code config: language, permissions, hooks, plugins
  agents/              The five subagents (doc-reader, planner, builder, verifier, reporter)
  hooks/               Deterministic guards (Tekla write guard, session environment check)
docs/                  Workflow, architecture, roadmap, tekla-cli contract, ADRs
schemas/               JSON Schemas (spec, project-state, read-log) + valid examples
src/tekla_harness/     Python package: schema validation, environment check, CLI
tests/                 pytest suite (schemas, hooks, CLI)
tekla/                 TeklaCore + tekla-cli (C#) — Step 3, placeholder for now
benchmark/             Benchmark protocol; datasets live outside git
projects/              Per-project workspaces — git-ignored (client data never enters git)
scripts/setup.ps1      One-shot Windows bootstrap
requests-to-improve.md Improvement log (RTI) for the harness itself
```

## Quick start (Windows)

Prerequisites: Git for Windows, Python 3.12, [uv](https://docs.astral.sh/uv/), Claude Code
(desktop app or CLI). Node.js is optional (only for the Python language server fallback).

```powershell
git clone <your-remote> tekla-ai-harness
cd tekla-ai-harness
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

`setup.ps1` installs the Python environment, pre-commit hooks, language servers, and the
project's Claude Code plugins. Then open the folder in the Claude desktop app → **Code** tab
→ **local** session (never a cloud session: Tekla is only reachable on this machine).

Developer commands:

```powershell
uv run pytest                     # tests
uv run ruff check . ; uv run ruff format --check .
uv run harness env-check          # is this machine ready?
uv run harness validate spec schemas/examples/spec.example.json
```

## Safety model (summary)

1. Work only on a **copy** of a Tekla model; back up before every lot.
2. Only the `builder` subagent may run write commands of `tekla-cli`
   (enforced by `.claude/hooks/guard_tekla_write.py`, not by prompt text).
3. Every object written carries `LOT`, `RUN_ID` and `SPEC_ID` user-defined attributes.
4. Every gate waits for the engineer. The orchestrator never opens a gate itself.

## Plugins

Enabled for this project in `.claude/settings.json` (install once per machine via `setup.ps1`):

| Plugin | Why |
|---|---|
| `andrej-karpathy-skills@karpathy-skills` | Coding discipline: think first, simplicity, surgical diffs, verifiable goals |
| `pyright-lsp@claude-plugins-official` | Type diagnostics on every Python edit |
| `csharp-lsp@claude-plugins-official` | Diagnostics for `TeklaCore` (active from Step 3) |

## License

Proprietary — see [LICENSE](LICENSE).
