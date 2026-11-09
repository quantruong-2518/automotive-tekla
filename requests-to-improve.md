# Requests to improve (RTI)

Improvement log for the harness itself. Each entry: classification, root cause, proposed fix,
regression test, status. Statuses: `proposed` → `approved` → `done` (with version) or `rejected`.

Classification: `reading` · `planning` · `spec` · `build` · `verify` · `report` · `process` · `tooling`.
Severity: `critical` · `major` · `minor`.

---

## RTI-0001 — No drawing inventory or revision control at intake

- Source: flow review, 2026-11-06 (Flow I)
- Classification: process · Severity: critical · Status: **approved** (engineer, 2026-11-06)
- Root cause: step 1 copies files without checking the sheet list, revisions or duplicates.
- Proposed fix: deterministic `inventory` step (hash, sheet no./rev/date from title block,
  compare with drawing list); lock `input/` by hash; a separate "new revision" flow.
- Regression test: fixture set with one missing sheet and two revisions of one sheet →
  both reported as blocking questions.

## RTI-0002 — Confidence assigned per file format instead of per value

- Source: flow review, 2026-11-06 (Flow I)
- Classification: reading · Severity: critical · Status: **approved** (engineer, 2026-11-06; schema support already in v0)
- Root cause: fallback table rates DXF "High" regardless of dimension overrides, mixed scales,
  missing xrefs, units.
- Proposed fix: per-value `provenance` + `confidence` (done in `schemas/common.schema.json`);
  DXF checks for overridden dimension text vs measured value, scale regions, xrefs, `$INSUNITS`.
- Regression test: DXF fixture with an overridden dimension → value flagged, question raised.

## RTI-0003 — Grids and levels reach planning without human confirmation

- Source: flow review, 2026-11-06 (Flow I)
- Classification: process · Severity: critical · Status: **approved** (engineer, 2026-11-06)
- Root cause: grids/levels are extracted inside the large analysis step and flow straight into the plan.
- Proposed fix: deterministic `grids.json` / `levels.json`; mandatory section with a rendered
  grid plan in gate 1.
- Regression test: gate-1 checklist fails if the grid section is missing.

## RTI-0004 — Legacy Vietnamese font encodings (TCVN3/VNI) in DWG/DXF

- Source: flow review, 2026-11-06 (Flow I)
- Classification: reading · Severity: major · Status: **approved** (engineer, 2026-11-06)
- Root cause: text decodes "successfully" into garbage; not detected by the fallback chain.
- Proposed fix: detect encoding from text style font names; convert to Unicode deterministically.
- Regression test: fixture with `.VnTime` text → correct Unicode output.

## RTI-0005 — Write guard blocks reading a file whose name contains `tekla-cli`

- Source: main session, 2026-11-06 (`sed -n 1,40p docs/tekla-cli-contract.md` was denied)
- Classification: tooling · Severity: minor · Status: **done** (Unreleased; engineer approved the fix 2026-11-06)
- Root cause: in a segment whose command word is not on the inert list (`sed`, `python`, …),
  any `tekla-cli` substring counted as an unparsed invocation, so a file name such as
  `tekla-cli-contract.md` was treated as a write. ADR-0004 says data mentions must pass.
- Fix: the mention regex ignores `tekla-cli` followed by `-` or a word character (a longer,
  different name). `sed` stays off the inert list: its `e` command runs shell code.
- Regression test: `tests/test_guard_hook.py` — the denied command and a
  `python … docs/tekla-cli-contract.md` call pass; `sed -n 'e tekla-cli build'` and
  `bash -c 'tekla-cli.cmd build'` stay denied.
- Known limit (unchanged): a heredoc or inline script that contains the bare word `tekla-cli`
  is still denied; write such text with the Edit/Write tools instead.

## RTI-0006 — Write guard does not see the CLI under its default .NET build name

- Source: review of `tekla/api-notes.md`, 2026-11-06
- Classification: tooling · Severity: critical · Status: **done** (Unreleased; approved by the engineer 2026-11-07, both layers; ADR-0007)
- Root cause: the guard recognises only the executable name `tekla-cli(.exe)`. An SDK-style
  `TeklaCli.csproj` builds `TeklaCli.exe` by default, and `dotnet run --project tekla/TeklaCli -- build`
  never names the exe. Today both `TeklaCli.exe build --lot 1` and that `dotnet run` call get
  no decision from the guard, so the main session could write to Tekla.
- Proposed fix: (1) contract: "the executable is named `tekla-cli.exe` (`AssemblyName`
  `tekla-cli`); agents never invoke it through `dotnet run`/`dotnet exec`" (the csproj in
  `tekla/api-notes.md` already sets `AssemblyName`); (2) hook: also treat `teklacli(.exe)`
  and `dotnet run|exec` aimed at the CLI project as invocations (fail closed).
- Regression test: `TeklaCli.exe build --lot 1` and `dotnet run --project tekla/TeklaCli -- build`
  are denied outside `builder`.
- Done: contract names the exe and forbids the dotnet routes; the hook matches `tekla[-_]?cli`
  and denies any `dotnet run|exec|watch` (`tests/test_guard_hook.py`, RTI-0006 cases).
- Follow-up: integration tests that reach the Tekla API outside `builder` → RTI-0007.

## RTI-0007 — Integration tests could write to whatever Tekla model is open

- Source: review of RTI-0006, 2026-11-07
- Classification: tooling · Severity: minor (no Tekla test project exists yet; major once
  Step 3 adds one) · Status: **proposed** (engineer agreed with the direction 2026-11-07; to be
  done when `tekla/` gets its first .NET project)
- Root cause: an external Open API client talks to the first Tekla session started and writes
  to whatever model is open there. A `dotnet test` run of integration tests, by an agent or by
  the engineer, would build test objects into a real project model if one is open. The guard
  hook cannot protect this: it sees only agents, and test runners can be started many ways
  (`dotnet test`, `vstest.console`, Test Explorer, scripts), which ADR-0004 already accepts it
  cannot catch.
- Rejected: extending the hook to deny `dotnet test`. It would block the Tekla-free unit tests
  (most of the code, runnable on Linux CI) or need fragile project-name matching, could still
  be bypassed, would push test runs onto `builder` (wrong role), and would not stop the
  engineer's own runs.
- Proposed fix:
  1. Two test projects: `TeklaCore.Tests` (no Tekla references, runs anywhere and in CI) and
     `TeklaCore.IntegrationTests` (needs a running Tekla).
  2. The integration fixture fails before any write unless the open model path equals the
     declared test model path and that model folder holds a marker file
     (e.g. `.harness-test-model`); same comparison code as contract safety rule 1.
  3. A `permissions.ask` rule for `dotnet test` on the IntegrationTests project, so each run is
     confirmed by the engineer.
- Regression test: with a model open that lacks the marker or has another path, the integration
  fixture fails before any write; `TeklaCore.Tests` builds and runs with no Tekla installed.

## RTI-0008 — An agent can forge a spec validation receipt

- Source: independent design review of slice S1b (ADR-0010 Amendment 1), 2026-11-08
- Classification: safety layer · Severity: minor (the receipt is not a gate; gate approval stays
  with the engineer) · Status: **done** (Unreleased; approved by the engineer 2026-11-08; PR #8, master
  `3307060`; a live check in a new Claude Code session is still to do)
- Root cause: the receipt is a plain JSON file holding the spec's SHA-256. Any agent with file
  write access (`builder` has Write) can create a receipt for a spec that was never validated,
  and the CLI cannot tell. Signing adds nothing while the key sits on the same machine.
- Proposed fix: a Claude Code `permissions.deny` rule for Write and Edit on `**/*.receipt.json`
  (and a guard-hook check for shell redirection into such a file), so only `harness validate spec`
  produces receipts. Check the current permission-rule syntax in the Claude Code docs first.
- Regression test: a hook/permission test where `builder` tries to Write `x.json.receipt.json`
  and is denied, while `uv run harness validate spec` still writes it.
- Related, also needs approval (agent definition): `.claude/agents/builder.md` step 1 runs
  `harness validate spec` right before building, so the agent that writes to Tekla produces its
  own receipt, and the Tekla machine needs Python (ADR-0010 says it should not). Proposed: step 1
  becomes "the receipt exists and matches", checked by `tekla-cli` itself; validation stays with
  the planner/doc-reader before the gate.
- Implemented: settings deny `Edit(**/*.receipt.json)` (Claude Code permissions docs, read
  2026-11-08: Edit rules cover Write, Edit, NotebookEdit and Bash `>`/`>>`/`2>` targets; the
  pattern is anchored at the working directory). `guard_tekla_write.py` denies any shell
  command naming a receipt, or piping one into another command, unless it only reads
  (cat, ls, Test-Path, jq, …) with no redirection into a receipt and no `--output`, for every
  agent. `builder.md` step 1 now only checks that the receipt exists. Tests:
  `tests/test_guard_hook.py` (`test_receipt_*`, `test_settings_deny_edits_of_receipts`); the
  producer side stays covered by `tests/test_receipt.py`. An independent Opus review found the
  newline bypass logged as RTI-0009, fixed on the same branch.
- Remaining limits: this narrows forgery, it does not close it; only an OS-level sandbox would.
  Not seen: a script file that writes a receipt (`uv run python forge.py`), a glob that does
  not spell `.receipt.json`, a directory copy, a path outside the working directory. Nothing
  stops `builder` from running `harness validate spec` itself; `builder.md` no longer asks it
  to. Unverified: whether the `Edit(...)` pattern matches case-insensitively on Windows. The
  Write-tool denial is enforced by Claude Code and is pinned only as configuration in pytest.

## RTI-0009 — Write guard reads a multi-line command as one command

- Source: independent review of RTI-0008, 2026-11-08
- Classification: tooling (safety layer) · Severity: critical · Status: **done**
  (Unreleased; merged by the engineer with RTI-0008 in PR #8, 2026-11-09)
- Root cause: `_split` in `guard_tekla_write.py` let `shlex` treat a newline as whitespace, so
  `cd projects/p` + newline + `tekla-cli build …` became one segment whose command word `cd`
  is inert, and the write passed for any agent. The `Bash(tekla-cli build *)` ask rule still
  prompted, but it does not check which agent runs the command.
- Fix: every newline separates commands like `;`, a bash backslash-newline too (in PowerShell a
  trailing `\` is part of a path, so joining lines would hide the next one; a split bash
  continuation fails closed). Inside quotes a newline stays in its token, so a multi-line
  `git commit -m` is still data. Accepted change: a heredoc body is now read as commands, so a
  heredoc that mentions a CLI write is denied outside `builder` (the commit skill uses `-F`).
- Regression test: `tests/test_guard_hook.py` — newline, CRLF, bash continuation and
  PowerShell trailing-backslash cases in `WRITE_COMMANDS` and `RECEIPT_WRITE_COMMANDS`; a
  multi-line commit message in `MENTION_ONLY_COMMANDS`.
