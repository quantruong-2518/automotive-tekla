# Skill drafts — review 1 (2026-11-06) and resolution plan

Independent Opus review of the four drafts. Verdict: **none ready**. Each finding is mapped to
the change that resolves it; tooling items must land before the skill text is rewritten.

## Tooling (code) — must exist first

| Finding | Resolution | Status |
|---|---|---|
| C1 question ids positional; answers bind to ids | stable `key` per question = code + fingerprint of sorted refs; `answers.json` (schema) keyed by `key`; rerun re-maps answers, re-asks when refs changed | planned (after structure fixes land: intake.py/structure.py busy) |
| C2 no tool for one sheet's text, no member/callout extractor | `sheet_text.py` (list_sheets, sheet_text) + `callouts.py` (verified patterns only, practice marks `low`, prefix-meaning questions) | in progress |
| M3 provenance.sheet = detector id, file absolute | file made input-relative (structure fix D9); sheet: reader rule detector id → printed number via answers | D9 in progress; mapping rule planned |
| M4 no project grid consolidation, no mm rescale | `grid-system`: choose master families per view group with evidence, rescale to mm only from a units answer | planned |
| M5 levels not classified storey/local | storey selection question + heights only between storeys (structure fix D6) | in progress |
| M14 no drawing-list search, no changed-input diff | drawing-list detection or blocking question; intake diffs sha256 vs previous inventory and invalidates answers on changed files | planned |
| M6 no members artefact/schema | `callouts.json` is the members-candidate artefact | in progress |

## Skill text — rewrite after tooling

| Finding | Resolution |
|---|---|
| M1 env-check is the wrong gate | drop it; intake exit 3 is the converter stop |
| M2 wrong artefact paths | use `work/structure/<file>.*.json`, `structure-summary.json`, `structure-questions.json` |
| M7 info matrix keyed by mark | one row per instance (mark + grid ref/level), `file` column, `ok` only if ≥ medium and no open question |
| M8 ownership/timing | analysis report owned by doc-reader (separate dispatch); info matrix at gate 3 per workflow.md, or amend workflow (engineer decides) |
| M9 plan collapses gates | `gate` argument: write only that gate's document, then stop |
| M10/M11 §11 labels, buildability, tie-break | cite `R# (status)`; buildability column (`tekla-cli` / `manual` / `blocked: gap`); ordered tie-break with a pilot lot |
| M12/M13 units and validate contradictions | drafting allowed, building blocked; pre-Step-3 catalog items `unvalidated` = risk to accept |
| M15 unit gate too early | run read-structure right after intake; its spacings go into the units question; interpretation gated on units |
| M16 routing to unapproved lab notes | route only to `docs/research/*`; promote needed checklist items there first |
| M17 no eval | run each skill end-to-end on the e2e sample with `skill-creator` before approval |
| m1–m16 | applied during the rewrite (rename `takeoff-report` → `drawing-analysis-report`, trim descriptions, done-when for every plan step, one question format, project layout alignment, agent definitions name their skills) |
