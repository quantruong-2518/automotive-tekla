---
name: commit
description: Split working-tree changes into logical commits and write English commit messages that another agent can understand from `git log` alone. Use whenever you are about to run `git commit` in this repository, or when asked to commit, split, or describe changes.
---

# Commit

Goal: a later agent runs `git log --format='%h %s' -30` and knows what happened. If it greps
for an id (`git log --grep RTI-0002`), it finds every commit that touched that item.
Everything in a commit message is English.

## 1. Look before you stage

```bash
git status --short
git diff            # unstaged
git diff --staged   # already staged
```

- Stage only changes you made in this task. If a file changed and you did not change it
  (another session, the engineer), leave it out and say so. Never "tidy up" by committing it.
- Never stage project data: `projects/`, `benchmark/data/`, drawings, models, `.env`.

## 2. Split into commits

One commit = one reason to change. Test: can you write the subject without "and"?

Keep together in the **same** commit:
- code + the tests that prove it;
- `pyproject.toml` + `uv.lock`;
- a schema change + its `$id` bump + `SCHEMA_NAMES` + `CHANGELOG.md` entry + updated examples;
- a hook change + its tests + the ADR/doc lines that describe that hook's behaviour;
- a `CHANGELOG.md` entry + the change it describes.

Put in **separate** commits:
- an engineer decision (RTI status, ADR, roadmap) before the code that implements it;
- a bug fix apart from a feature, even in the same file area;
- a refactor or formatting pass apart from a behaviour change;
- a new dependency in the commit that first uses it, never in an unrelated one.

Every commit must pass the checks on its own (section 4), so `git bisect` stays useful.
Order commits so that this holds: decision → infrastructure → feature → docs that depend on it.

If one file mixes two reasons and you cannot separate the hunks safely (interactive
`git add -p` is not available here), commit them together and name both in the body. Do not
rewrite the file to fake a split.

Stage by explicit path: `git add path/a path/b`. Not `git add -A` or `git add .`.

## 3. Message format

```
<type>(<scope>): <imperative summary, lower case, no period, max 72 chars>

Why: <one or two lines: the problem or decision that caused this change>

- <what changed, as behaviour, one bullet per point>
- <name the command, flag, schema field or rule, not the file list>

Verify: <exact command that proves it, e.g. uv run pytest tests/test_convert.py>
Unverified: <what is assumed but not proven; omit the line if nothing>
Refs: <RTI-0002, ADR-0005, Q-014; omit the line if none>
Co-Authored-By: <attribution line from the current system instructions>
```

- **type**: `feat` new behaviour · `fix` wrong behaviour corrected · `docs` docs, ADRs, RTIs ·
  `test` tests only · `refactor` no behaviour change · `chore` config, deps, CI, plugins.
- **scope** (one word, from this list; add a new one only if none fits): `guard`, `env-check`,
  `detect`, `readlog`, `convert`, `dxf`, `cli`, `schemas`, `agents`, `skills`, `hooks`,
  `settings`, `ci`, `deps`, `workflow`, `roadmap`, `adr`, `rti`, `tekla-cli`.
- Breaking change to a schema, CLI output or `tekla-cli` contract: `feat(schemas)!: …`, and a
  `BREAKING CHANGE: <what callers must do>` line before `Refs:`.
- Anything that changes a safety layer (guard hook, permissions, `tekla-cli` safety rules,
  gates) adds `Safety: <what is now allowed or blocked that was not before>`.
- Subject says what the repo now does, not what you did: `fix(convert): treat truncated DXF
  output as a failed attempt`, not `fix bug` or `update convert.py`.
- Body bullets describe behaviour. The diff already lists files; repeat a path only if the
  reader needs it to find the change.
- Keep the labels exactly (`Why:`, `Verify:`, `Unverified:`, `Refs:`, `Safety:`). They are
  what a reading agent greps for.

## 4. Before each commit

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q
```

If a check fails, fix it or stop and report. Never `--no-verify`, never commit red.

## 5. Commit

Write the message through a quoted heredoc so nothing is expanded:

```bash
git add src/tekla_harness/convert.py tests/test_convert.py
git commit -F - <<'EOF'
fix(convert): treat truncated DXF output as a failed attempt

Why: ezdxf raises StopIteration on a truncated file, which crashed the
whole dwg2dxf command instead of falling back to the next converter.

- Any exception while opening the converter output now becomes a failed
  attempt with the exception type in its error, then the chain continues.
- New fake-converter cases: binary and truncated output.

Verify: uv run pytest tests/test_convert.py
Refs: ADR-0005
Co-Authored-By: <attribution line>
EOF
```

- No backticks or `$(` anywhere in the message: the guard hook treats them as command
  substitution and blocks the whole command if the text also mentions the Tekla CLI.
- `git commit` is an `ask` rule: the engineer confirms each one. Do not try to avoid the prompt.
- Do not push, amend a pushed commit, or rewrite history unless the engineer asks.
- After committing, show `git log --oneline -<n>` for the commits you made, plus anything
  you left unstaged and why.

## Reading history (for the next agent)

```bash
git log --format='%h %s' -30             # what happened, one line each
git log --grep 'RTI-0002' --format='%h %s'
git log --grep '^Unverified:' --format='%h %s'   # open assumptions
git log --grep '^Safety:' --format='%h %s'       # safety-layer changes
git show --stat <hash>                   # files of one commit
```
