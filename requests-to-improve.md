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
