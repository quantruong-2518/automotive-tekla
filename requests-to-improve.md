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
- Open (not in this fix): `dotnet test` of a future `TeklaCore.Tests` project would reach the
  Tekla API outside `builder`; decide in Step 3 how integration tests are allowed to run.
