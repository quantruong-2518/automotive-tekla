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

## RTI-0009 — On Windows, an unlocked reader can make a work-folder write fail

- Source: independent review of the tool wave 2 seam (ADR-0011), 2026-11-08
- Classification: tooling · Severity: minor · Status: **proposed**
- Root cause: Python opens files on Windows without delete sharing, so while a read-only command
  (status, sheet-text, find-text) has `answers.json` or the registry open, a writer's
  `os.replace` in `write_text_atomic` fails with `PermissionError`. The registry may already be
  written by then, and `harness answer` catches only `QuestionsError`, so the engineer sees a
  traceback. ADR-0011 leaves readers unlocked by design. The same sharing rule can stop the
  holder record from being removed (a warning only).
- Proposed fix: retry the replace a few times with a short back-off on `PermissionError` on
  Windows; turn a final failure into exit 3 with a "retry" message.
- Regression test: Windows-only test that holds a read handle on the target while
  `write_text_atomic` replaces it; it expects retry, then success, or exit 3 with no traceback.

## RTI-0010 — An agent can declare itself the engineer when it records an answer

- Source: independent review of the tool wave 2 seam, 2026-11-08 (finding M1)
- Classification: safety layer · Severity: major · Status: **proposed** (needs engineer decision)
- Root cause: gate 1 counts only answers recorded with `--role engineer` (tool wave 2, D4), but the
  role is whatever the caller types. Any agent can run `harness answer … --role engineer`, or call
  `record_answer(role="engineer")` from Python, and gate 1 then reports ready on an answer the
  engineer never gave. Until P3, `status` even printed that command, ready to paste, in its reasons.
  The engineer still opens every gate (principle 5), so gate readiness alone does not let an agent
  build, but a wrong "ready" misleads the planner and the engineer.
- What the tools can and cannot do (Claude Code docs, 2026-11-08): a PreToolUse hook sees every
  Bash call that the model or a subagent makes, but not `!` commands typed by the engineer. A hook
  matches command text only, so `sh -c`, a script or a Python call get past it; the permissions
  page says such a rule "isn't a security boundary around the program". A hook cannot tell who
  issued a call.
- Proposed fix (defence in depth, none of it is a boundary on its own):
  1. P3 (tool wave 2): no gate-1 reason or printed command hands an agent `--role engineer`; the
     text says the engineer must answer.
  2. Guard hook: deny any model-issued Bash command that runs `harness answer` with
     `--role engineer`. The engineer records their answers with `! harness answer …` in the
     session, or from their own terminal.
  3. AGENTS.md hard rule: an agent never records an answer as the engineer; simulated answers
     use `--role simulated`.
  4. Later, if needed: engineer answers carry something an agent cannot produce (for example, an
     answer file the engineer edits, checked by hash at gate time).
- Regression test: the guard hook denies `harness answer W Q-1 --text x --by y --role engineer`
  from the model and allows `--role simulated`; a `status` run after a simulated answer prints no
  `--role engineer` command addressed to an agent.
