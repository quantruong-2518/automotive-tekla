# Workflow v0

Status: design, not built. Source of truth for the flow; the Vietnamese visual version is the
project artifact "Luồng Tekla AI Harness". Items marked **(proposed)** come from the flow
review of 2026-11-06 and are not approved yet.

## Lanes

| Lane | Who | Does |
|---|---|---|
| Engineer | Human | Supplies drawings, answers questions, approves every gate, owns the result |
| Orchestrator | Claude Code main session | Holds state, runs commands, delegates, stops at every gate |
| Agents | Subagents | Interpret, plan, classify, explain, write reports and questions |
| Code | Python scripts, `TeklaCore` | Convert, extract, validate, build, export, compare, benchmark |
| Tekla | Tekla Structures via Open API | Only reached through `tekla-cli` |

## Inputs and fallback chain

A failure at one step moves to the next, is logged in `read-log.json`, and lowers confidence.
No silent failures.

| Format | Primary → fallback | Base confidence |
|---|---|---|
| `.dwg` | ODA File Converter → DXF → LibreDWG `dwg2dxf` → render to PDF/image → ask engineer for DXF/PDF | High |
| `.dxf` | ezdxf (grids, text, dims, blocks, layers) → broken SHX text: render region, read with vision → open question | High |
| `.pdf` vector | PyMuPDF (text with coordinates, vectors) → no text layer: render 300–400 dpi tiles, vision → open question | Medium |
| `.pdf` scan, image | Render, tile → vision → every value marked low confidence | Low |
| `.docx`, `.xlsx` | Read text and tables → cross-check against drawings → conflicts become questions | High |

**(proposed)** Confidence is recorded **per value**, not per format (`schemas/common.schema.json`).
**(proposed)** DXF checks: overridden dimension text vs measured value, multiple scales in model
space, missing xrefs, `$INSUNITS`, legacy Vietnamese encodings (TCVN3/VNI).

## Steps

### I. Intake and reading
1. **Hand over drawings** — engineer copies files to `input/`, runs `/new-project`.
   → `project-state.json`
   - **(proposed) 1b. Inventory** — code: hash files, read sheet no./revision/date from title
     blocks, compare with the drawing list, detect format per page and font encoding.
     → `00-inventory.csv` + blocking questions.
2. **Read files with fallback** — `detect_input`, `dwg_to_dxf`, `read_dxf`, `read_pdf`,
   `render_tiles`. → `read-log.json`
3. **Expert analysis** — sheet list, general notes, structural system, grids, levels,
   members, anomalies; `crosscheck` spans and grid counts across sheets.
   → `01-analysis.md`, `questions.md`
   - **(proposed)** split into 3a deterministic extraction (`grids.json`, `levels.json`,
     `schedules.json`) and 3b AI analysis per sheet group.

### II. Planning
4. **Plan** — scope, risks, assumptions; Tekla `info`, `validate` (read-only). → `02-plan.md`
5. **Gate 1: plan review** — `/approve` or `/revise`. **(proposed)** grids and levels are a
   mandatory section of this review.
6. **Gate 2: approach** — lot split, name/class conventions, components. → `03-approach.md`
7. **Gate 3: information matrix (if gaps)** — member × field × source sheet × status.
   → `04-info-matrix.csv`
8. **Sequence** — lot order. → `05-sequence.md`

### III. Lot loop (9–13 for n = 1…N; verifier checks lot n while builder builds lot n+1)
9. **Extract lot n** — every value with source sheet and confidence; `validate_spec`,
   `selfcheck`, `profile_map`. → `lots/n/spec.json`
10. **Build lot n** — hook: backup, permission check; one `tekla-cli build` per lot, tags
    `LOT`/`RUN_ID`/`SPEC_ID`, single commit. → model, log
11. **Verify lot n** — export CSV + IFC; `compare_report`, `compare_ifc`; classify issues;
    critical issues → `rollback`/`update`; hook blocks the next lot while critical issues remain.
    → `lots/n/issues.json`
12. **Lot report** — `build_report`. → `lots/n/report.md`
13. **Gate 4: 3D check** — engineer selects wrong members in Tekla, `/approve` or `/feedback`;
    `tekla-cli selected` reads the selection; feedback is tied to GUID, lot, `SPEC_ID`.

### IV. Close and improve
14. **Gate 5: phase report** → `phase-report.md`
15. **Record feedback** — classification, root cause, proposal → `requests-to-improve.md`
16. **Gate 6: `/improve`** — group RTIs by root cause; propose fixes to skills, `lessons.md`,
    `TeklaCore`; regression tests + `run_benchmark`; engineer approves and tags a version.

The tool never edits its own rules.
