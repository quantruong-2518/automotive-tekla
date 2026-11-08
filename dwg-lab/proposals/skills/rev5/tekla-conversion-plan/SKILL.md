---
name: tekla-conversion-plan
description: Prepare one planning gate for building the Tekla model from an analysed drawing set — gate 1 plan and risks, gate 2 modelling approach, gate 3 lot sequence — each rule cited with its evidence status and each lot marked buildable or blocked. Use for gate 1–3 preparation or when asked how to convert the drawings to Tekla.
---


# Tekla conversion plan

Owner: `planner`. You plan; the engineer opens each gate; only `builder` builds. **One run =
one gate**: the orchestrator says which (`gate: 1 | 2 | 3`); you write that gate's document and
stop. Rules R1–R17 are the table in `docs/research/tekla-modelling-from-drawings.md` §11; cite
each as `R# (status)` with the status as the table writes it (`cited`, `example`, `practice`,
`proposal`, or a compound such as `cited + practice`, kept whole). Treat `example` and `practice` like `proposal`: the engineer accepts or rejects.

## Inputs

`projects/<id>/01-analysis.md`, `questions.md`; in `work/`: `grid-systems.json` (+ SVGs),
`structure/<file>.levels.json`, `callouts.json`, `marks.json`, `reader-findings.json`,
`answers.json`, `harness status` output; gate 3 also `04-info-matrix.csv`. Tekla facts: `tekla/api-notes.md` (per Tekla version) and the
research note above. Do not re-read drawings: send gaps to `doc-reader` via the orchestrator.

Units: drafting may proceed with unconfirmed units; **no lot is proposed for building** until
the engineer (`answered_by_role: engineer`) has answered every file's units and the selected
grid systems.

## Gate 1 — `02-plan.md`

When `harness status` says `ready_for_gate1: false` (always so while a gate answer is not the
engineer's, `gate1.non_engineer_answers`, as in an eval), the document is a draft: its first
lines are `BẢN NHÁP — gate 1 chưa sẵn sàng` and the `gate1.reasons` with their question ids;
the rest follows as below. A draft calls gate 1 not ready throughout.

Scope (in/out), per file set (`file_set_relation`) and per building when a set holds several
(`separate=` systems); for several buildings, "one Tekla model per building or one model" is an
engineer decision listed here (R13). A file that no selected grid system covers is a scope
decision too: name it, never drop it silently. **Lưới trục và cao độ** (mandatory, RTI-0003):
each selected grid system with coordinate strings (mm only if the system has them), X/Y status,
SVG link; levels table
(confirmed storey levels only, in metres as written; none confirmed → one line saying so with
the question ids); base point/origin (R13). No tool emits the Tekla Z string or the origin
coordinates yet: write them as `chờ công cụ + xác nhận` under the R1 gap. Assumptions, each
tied to a question id or answer; risks Critical / Major / Minor. Lots are a gate-3 decision:
gate 1 lists none. Every scope row, assumption and risk title rests on an allowed entry, a
finding or an answer; a blocked item is named by entry id and font question (`tiêu đề bị chặn
(T…)`, Q-…). A question blocks until the engineer answers it or `gate1.closed` lists it; one
whose answer is in `gate1.non_engineer_answers` is shown answered `(mô phỏng)` and still blocks,
as does every value resting on it. *Done when* every blocking open question is listed with the
scope it blocks.

## Gate 2 — `03-approach.md`

One table each; *done when* every distinct callout, grade, member type and mark prefix in
`callouts.json`/the analysis has a row:
- **Catalog map** — callout → candidate Tekla profile string → `unvalidated` (until
  `tekla-cli validate` exists and passes; R3) — an accepted risk, not a stop. Unverified
  parametric syntax (`PL…`) is a question.
- **Material map** — grade → Tekla material → status. Legacy grades (CI…CIV, A-I…A-IV,
  CCT/XCT) have no official mapping: question.
- **Classes, names, numbering series** (R2, R14) — decided before lot 1.
- **UDAs** — `LOT`, `RUN_ID`, `SPEC_ID`: `special_flag no`, ≤ 19 characters, `unique_attribute`
  vs `attribute`, clash with Tekla Lotting (R15); `tekla/api-notes.md` warns that a copied part
  keeping `RUN_ID` would be deleted by `rollback`. The engineer decides the names.
- **Phases** — one phase per lot, locked after approval (R16, proposal); erection order is
  separate (R10).
- **Connections and rebar** — in or out of scope; components by name and number, only if
  confirmed in the company environment (R6).

## Gate 3 — `05-sequence.md`

Order lots by this tie-break, in order:
1. dependencies (no lot depends on a later one);
2. a small **pilot lot** first that uses every profile, material and class once (proposal), so
   catalog and UDA problems surface early;
3. lots whose members have no open blocking question;
4. lots with open blocking questions held back, listed with their question ids;
5. lot size per R17 (practice): propose a limit with its basis; the engineer decides.

Within that order: grids/levels first (R1, gap below), columns before beams (R4 example),
then beams, bracing, secondary steel (R5 practice), connections after their members (R6),
concrete in R8 order, numbering per lot last (R11), checks per lot (R12).

Each lot: id, scope, member instances (from the matrix), dependencies, blocking questions,
checks, and **buildability**: `tekla-cli` | `engineer manual` | `blocked: <gap>`. Known gaps
today: the spec has no grid/level object (R1), no numbering fields (R2), linear member types
only — no slab, footing, wall, pour or rebar (R8, R9); `tekla-cli` has no copy (R7), numbering,
clash or diagnose command (R11, R12). *Done when* every instance in the matrix is in exactly one
lot or listed out of scope, and every lot has a buildability value.

## Style

Vietnamese, conclusion first, the engineer's words (lưới trục, cao độ, lot, cấu kiện, câu hỏi
chặn); rule ids `R#` and question ids stay as written.

## End

One or two lines: the gate the engineer must open next and what opening it approves. A draft
ends instead with the reasons to clear first, `gate1.non_engineer_answers` included.

## Hard stops

No grid system at all; the orchestrator did not name a gate; a gate's input is stale per
`harness status`. State it and stop.
