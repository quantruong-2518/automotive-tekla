---
name: drawing-analysis-report
description: Write the engineer's report on how a drawing set was read — what was received, how each value was obtained, how sure it is, what is missing — as 01-analysis.md, and at gate 3 the information matrix 04-info-matrix.csv. Use after structural-drawing-reader, or when the engineer asks how the drawings were read.
---


# Drawing analysis report

Owner: `doc-reader`, in a fresh dispatch after the reading, so the report is built from the
artefacts rather than from memory of the reading. The engineer must be able to audit every
figure in minutes. You write; you do not re-read the drawings and you raise no questions. Every
number and claim you print names the artefact it comes from. A figure the skill asks for that no
artefact holds is printed as `không có trong artefact`; a gap you notice (a `low` value nobody
asked about, a missing count) goes in §9 under **Chưa hỏi** and in your final message to the
orchestrator, who sends it back to the reader.

## Inputs

In `projects/<id>/work/`: `inventory.json`, `read-log.json`, `structure-summary.json`,
`structure/<file>.{sheets,grids,levels}.json`, `grid-systems.json` (+ SVGs), `callouts.json`,
`marks.json`, `reader-findings.json`, `answers.json`; `uv run harness status projects/<id>/work`
and `uv run harness finding list projects/<id>/work` (stale flags, `summary.by_class`);
`projects/<id>/questions.md` (render it first with `uv run harness questions-md
projects/<id>/work`). Missing `grid-systems.json`, `structure-summary.json` or
`reader-findings.json` → stop: the reading is not done.

## Part A — `projects/<id>/01-analysis.md`

Vietnamese, these sections in order:

1. **Kết luận** — 3–5 lines: can modelling be planned, and what blocks it: the `gate1.reasons`
   count, naming answers not given by the engineer (`gate1.non_engineer_answers`), then
   separately the open blocking questions that block lot specs (callouts, marks).
2. **Vấn đề** — Critical / Major / Minor: reason, where, question id.
3. **Hồ sơ đã nhận** — per file: format, converter, outcome, confidence cap, unit and whether
   it is confirmed, sheet count, changes since last intake.
4. **Bộ bản vẽ** — per file, sheets by class from the `sheet_class` findings (finding id,
   title entry id); sheets without a class with their question id; drawing list status; a file
   with no detected sheet: its `sheets_not_detected` question and the findings on its text.
5. **Cách đã đọc** — the commands run, the converter (version if the read log has it, else
   `không ghi nhận`), fallbacks, how confidence was capped, the method of each value class
   (`dxf_entity`, `derived`, `engineer_answer`, `vision`), and how much text the font gate
   blocked per file (`list-sheets` `files[].blocked_text_count`) with its font question ids, and
   the font rows that decoded cited text (`decoded_by`; stale findings named).
6. **Thông tin chung** — `note_item` and `structural_system` findings: value verbatim, sheet,
   finding id, entry ids, confidence.
7. **Lưới trục và cao độ** — per grid system: labels, spacings, coordinate string (drawing
   units, and mm only where the system has it), evidence counts, flags, SVG link, selection
   and X/Y status; levels: storey levels confirmed or not, `blocked_candidates` by entry id with
   the font question. Everything unanswered is marked `chờ xác nhận`.
8. **Cấu kiện và ký hiệu** — from `marks.json`: mark counts per sheet (`summary.by_sheet`),
   tables (blocked headers and `blocked_columns` named), matched / schedule-only / plan-only
   counts, notation variants, size conflicts with question ids, printed beside the compared /
   not-compared counts (`summary.size_comparisons`); from `callouts.json`: parsed vs unparsed
   counts per reason (`summary.unparsed_by_reason`). No quantities.
9. **Những gì có thể sai** — heuristics relied on, unverified conventions, low-confidence groups
   with counts, single-source grid systems, files read only partially, blocked text.
10. **Câu hỏi mở** — blocking open first, ids as in `questions.md`; then the questions closed by
    another answer, from `gate1.closed` with its reason. A question blocks until the engineer
    answers it or `gate1.closed` lists it, whatever system or file it seems to sit on; an answer
    in `gate1.non_engineer_answers` leaves it blocking gate 1.

*Done when* every number in the report appears in a named artefact, and every `low` or
unconfirmed value carries a question id or is listed under **Chưa hỏi** in §9.

## Part B — `projects/<id>/04-info-matrix.csv` (gate 3, workflow step 7)

One row per member **instance** and field:
`file, sheet, mark, instance_ref, field, value, unit, source_entry, method, confidence, status, question_id`.
`instance_ref` locates the instance (grid ref + level when known, else the text entry id).
Fields: every field `schemas/spec.schema.json` needs for its member type (profile, material,
start, end, rotation…). `status`: `ok` only when confidence ≥ medium and no open question
touches it; `provisional` when low or asked; `missing` when no artefact gives it; `conflict`
when two sources disagree. *Done when* every member instance listed in Part A §8 has a row for
every spec field.

## Style

Conclusion first, short sentences, units always printed. Every topic, title and keyword, headings
and §2/§9 titles included, rests on an allowed entry, a finding or an answer; a blocked item is
written by entry id and font question (`tiêu đề bị chặn (T…)`, Q-…). An answer the engineer
did not give (`gate1.non_engineer_answers`) is printed `(mô phỏng)`. The engineer's words: bản
vẽ, tờ, lưới trục, cao độ, ký hiệu, bảng thống kê, câu hỏi chặn. Tool names appear only as the
command the engineer would run. Print a script's numbers as given; a total appears only when a
script computed it.
