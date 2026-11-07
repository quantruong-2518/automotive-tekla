# Contributing

## Workflow

1. Branch from `master`, one branch per task: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`,
   `chore/<topic>`. Never commit on `master`. Parallel agent sessions each use their own git
   worktree under `.claude/worktrees/`.
2. Make the smallest change that solves the task. Add or update tests.
3. Run locally: `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest`.
4. Commit with Conventional Commits (`.claude/skills/commit/SKILL.md`). Push the branch and open
   a PR into `master` using the template (`gh pr create --base master --fill` or the GitHub MCP).
5. Merge only after review and green CI (Linux and Windows).

## Changes to the harness itself (skills, agents, hooks, schemas, TeklaCore)

These follow the improvement loop (gate 6), not ad-hoc edits:

1. An entry exists in `requests-to-improve.md` (classification, root cause, fix, regression test).
2. The PR links the RTI id(s).
3. The regression test and the benchmark run pass, and **no metric gets worse**.
4. The engineer approves. Release tag: `vX.Y` with the benchmark score in the tag message.

Agents may draft these PRs. Agents never merge them.

## Architecture decisions

Record any decision that is hard to reverse as an ADR in `docs/decisions/`
(copy the format of `0001`). Never edit an accepted ADR; supersede it with a new one.

## Data

Client drawings, models and benchmark datasets never enter git. `projects/` and
`benchmark/data/` are ignored. Use synthetic fixtures under `tests/fixtures/` for tests.
