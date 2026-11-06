# AGENTS.md — rules for every coding agent in this repository

This file is tool-agnostic. Claude-specific notes live in `CLAUDE.md`.

## Language

- **Reply to the engineer in Vietnamese.** Short conclusion first, then details.
- **Everything committed is English**: code, comments, identifiers, commit messages,
  schemas, docs, skills, agent definitions, log keys.
- Human-facing project deliverables (`questions.md`, `01-analysis.md`, lot and phase
  reports) are written in Vietnamese; their field names, file names and JSON keys stay English.
- Structural terms: use the English term in code; the Vietnamese glossary lives in the
  `structural-drawing-reader` skill (Step 2).

## Non-negotiable principles

1. **Flag problems first.** When reviewing anything, list errors, risks and unverified
   assumptions before anything else, ranked Critical / Major / Minor, each with reason and fix.
2. **Never guess.** Missing or ambiguous → write an open question saying where to check.
   Every value taken from a drawing carries provenance (sheet, revision, location) and confidence.
3. **AI decides, code does.** Prefer deterministic scripts, the C# tool, or built-in Tekla
   features. Use the model only for judgement, interpretation and orchestration.
4. **Model safety.** Work on model copies only. Only the `builder` agent writes to Tekla,
   and only through `tekla-cli`. Tag every object with `LOT`, `RUN_ID`, `SPEC_ID`.
   Back up before each lot.
5. **Gated process.** Do not skip steps. Never open a gate on the engineer's behalf.
6. **Continuous improvement.** Log every defect or piece of feedback in
   `requests-to-improve.md` (classification, root cause, proposed fix, regression test).
7. **Agents propose, humans approve.** Do not change rules, skills or core code without approval.
8. **Be honest about limits.** For Tekla Open API, check `api-notes.md`, the NuGet XML docs or
   Tekla Developer Center before asserting behaviour; say when it may differ by version.
9. **Measure, don't feel.** Judge changes by the benchmark (past projects with answer models).

## Engineering conventions

- Python ≥ 3.12, `src/` layout, managed with `uv`. Lint and format with `ruff`; type-check
  clean under `pyright` basic mode.
- Keep runtime dependencies minimal; justify each new one in the PR description.
- Scripts are deterministic, idempotent, and take paths as arguments. They print
  machine-readable JSON to stdout and diagnostics to stderr. Exit codes: `0` ok,
  `1` validation failure, `2` usage error, `3` environment error.
- Never swallow an error. A fallback is logged (`read-log.json`) and lowers confidence.
- Every JSON artefact validates against a schema in `schemas/`. A schema change bumps its
  `$id` version and adds a CHANGELOG entry.
- Tests: `uv run pytest`. A bug fix ships with a regression test.
- Commits follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`).
- Smallest change that solves the task. No drive-by refactors.

## Where things live

| Need | Location |
|---|---|
| Workflow, lanes, gates | `docs/workflow.md` |
| Agent roles, safety layers | `docs/architecture.md` |
| Build order and current step | `docs/roadmap.md` |
| `tekla-cli` command contract | `docs/tekla-cli-contract.md` |
| Architecture decisions | `docs/decisions/` |
| JSON Schemas | `schemas/` |
| Improvement log | `requests-to-improve.md` |
| Project workspaces (git-ignored) | `projects/<project-id>/` |

## Hard stops

Stop and ask the engineer instead of improvising when:

- a script, skill or `tekla-cli` command the task needs does not exist yet;
- the session is not local to the Tekla machine;
- a drawing value is missing, contradictory, or below the confidence threshold;
- an action would write to a Tekla model outside the `builder` agent.
