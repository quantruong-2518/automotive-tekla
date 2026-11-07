---
name: drawing-analysis-report
description: Write the engineer's report on how a drawing set was read — what was received, how each value was obtained, how sure it is, what is missing — as 01-analysis.md, and at gate 3 the information matrix 04-info-matrix.csv. Use after structural-drawing-reader, or when the engineer asks how the drawings were read.
---

<!-- PROPOSAL rev 2 (2026-11-06, after REVIEW-1): not active until the engineer approves it (AGENTS.md principle 7). -->

# Drawing analysis report

Owner: `doc-reader`, in its own dispatch after the reading (docs/architecture.md). The
engineer must be able to audit every figure in minutes. You write; you do not re-read the
drawings. A figure without an artefact behind it is left out and becomes a question.

## Inputs

In `projects/<id>/work/`: `inventory.json`, `read-log.json`, `structure-summary.json`,
`structure/<file>.{sheets,grids,levels}.json`, `grid-systems.json`, `callouts.json`, the four
`*questions.json`, `answers.json`; `uv run harness status projects/<id>/work`; the reader's
findings with their entry ids. Missing `grid-systems.json` or `structure-summary.json` → stop:
the grid section is mandatory (RTI-0003).

## Part A — `projects/<id>/01-analysis.md`

Vietnamese, these sections in order:

1. **Kết luận** — 3–5 lines: can modelling be planned, and what blocks it (status counts).
2. **Vấn đề** — Critical / Major / Minor: reason, where, question id.
3. **Hồ sơ đã nhận** — per file: format, converter, outcome, confidence cap, unit and whether
   it is confirmed, sheet count (from `structure-summary.json`), changes since last intake.
4. **Cách đã đọc** — the commands actually run, the converter (version if the read log records
   it, else `không ghi nhận`), fallbacks taken, how confidence was capped, and the method of each
   value class (`dxf_entity`, `derived`, `engineer_answer`, `vision`).
5. **Thông tin chung** — codes, grades, cover, laps: value, sheet, entry id, confidence.
6. **Lưới trục và cao độ** — per grid system: labels, spacings, coordinate string (drawing
   units, and mm only if the system has it), evidence counts, flags, link to its SVG, selection
   and X/Y status; levels: storey levels confirmed or not. Everything unanswered is marked
   `chờ xác nhận`.
7. **Cấu kiện và ký hiệu** — mark prefixes with their answered meaning or question id; counts
   per sheet; parsed vs unparsed callouts; schedule matches. No quantities.
8. **Những gì có thể sai** — heuristics relied on, unverified conventions, low-confidence groups
   with counts, single-source grid systems, files read only partially.
9. **Câu hỏi mở** — blocking open first, ids linked to `questions.md`.

*Done when* every number in the report appears in a named artefact, and every `low` or
unconfirmed value carries a question id.

## Part B — `projects/<id>/04-info-matrix.csv` (gate 3, workflow step 7)

One row per member **instance** and field:
`file, sheet, mark, instance_ref, field, value, unit, source_entry, method, confidence, status, question_id`.
`instance_ref` locates the instance (grid ref + level when known, else the text entry id).
Fields: every field `schemas/spec.schema.json` needs for its member type (profile, material,
start, end, rotation…). `status`:
`ok` only when confidence ≥ medium and no open question touches it; `provisional` when low or
asked; `missing` when no artefact gives it; `conflict` when two sources disagree.
*Done when* every member instance listed in Part A §7 has a row for every spec field.

## Style

Conclusion first, short sentences, units always printed. Never round a script's number;
never print a total no script computed.
