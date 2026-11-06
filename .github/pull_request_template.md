## What and why

<!-- One or two sentences. Link RTI ids if this changes the harness itself (skills, agents, hooks, schemas, TeklaCore). -->

RTI: <!-- RTI-000X or n/a -->

## Risks (Critical / Major / Minor)

-

## Checklist

- [ ] Smallest change that solves the task; no drive-by refactors
- [ ] Tests added or updated; a bug fix includes a regression test
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pytest` pass
- [ ] Schema change: `$id` version bumped, example updated, CHANGELOG entry
- [ ] Harness change: benchmark run attached, no metric worse
- [ ] No client data, models or secrets in the diff
