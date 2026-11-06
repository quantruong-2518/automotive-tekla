# Architecture

## Runtime

One Windows machine with Tekla Structures and a Tekla licence. Claude Code runs as a **local**
session (desktop app *Code* tab or CLI) in this repository. Cloud sessions cannot reach Tekla
and must not be used for project runs ([ADR-0002](decisions/0002-local-claude-code-session.md)).

```
Claude Code (orchestrator, main session)
 ├── doc-reader  ── Python readers ── drawings
 ├── planner     ── tekla-cli info|validate (read-only)
 ├── builder     ── tekla-cli build|update|rollback|export ── Tekla model copy   ← only writer
 ├── verifier    ── tekla-cli query|export, compare scripts
 └── reporter    ── report scripts
```

## Agents

| Agent | Role | Tekla access | Outputs | Suggested model |
|---|---|---|---|---|
| orchestrator | State, commands, delegation, stops at gates | none directly | `project-state.json` | main session |
| `doc-reader` | Read, analyse, matrix, extract spec | none | `01-analysis.md`, `04-info-matrix.csv`, `lots/n/spec.json`, `questions.md` | opus |
| `planner` | Plan, approach, sequence | `info`, `validate` | `02-plan.md`, `03-approach.md`, `05-sequence.md` | opus |
| `builder` | Build, update, roll back per lot | `build`, `update`, `rollback`, `export` | model lot n, build log | sonnet |
| `verifier` | Compare model to spec, independent of builder | `query`, `export` | `lots/n/issues.json` | haiku |
| `reporter` | Lot and phase reports, feedback intake | none | `report.md`, `requests-to-improve.md` | haiku |

Model choices are starting points; the benchmark decides.

## Safety layers

| # | Layer | Enforced by | Failure mode |
|---|---|---|---|
| 1 | Only `builder` runs `tekla-cli` writes | `PreToolUse` hook reading `agent_type` | fails closed (hook exits 2 on any error) |
| 2 | Engineer confirms each write command | `permissions.ask` rules | prompt in main session |
| 3 | Subagent tool scope | `tools` in agent frontmatter | tool absent |
| 4 | Model copy + backup + tags | `tekla-cli` itself (Step 3) | command refuses to run |
| 5 | Gates | orchestrator rules + slash commands (Step 5) | orchestrator stops |

Layers 1–3 exist in Step 0. Layer 4 is specified in [tekla-cli-contract.md](tekla-cli-contract.md)
and built in Step 3. Prompt text is never counted as a safety layer.

## Data artefacts

All JSON artefacts validate against `schemas/`. Every drawing-derived value carries a
`provenance` object (file, sheet, revision, region, method) and a `confidence` level.
Project workspaces live in `projects/<project-id>/` and are git-ignored.
