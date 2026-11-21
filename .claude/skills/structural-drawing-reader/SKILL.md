---
name: structural-drawing-reader
description: Expert reading of a structural drawing set after drawing-intake. Use whenever the engineer asks what a drawing set or sheet shows (đọc bản vẽ, tổng quan công trình, khối nhà, phân loại các tờ, mặt bằng móng, chi tiết cột, loại móng), which levels are storey levels and which are local (cao độ tầng, cao độ cục bộ), which grid axes the project uses (lưới trục), what the general notes specify (mác bê tông, thép, lớp bảo vệ), whether marks on plans match the schedule (ký hiệu cấu kiện, bảng thống kê), how a steel factory building is framed (nhà xưởng, khung kèo, xà gồ, chân cột, bu lông neo, móng cọc), to analyse a drawing set in projects/<id> for a Tekla model, or when dispatched to review such a reading.
---

<!-- PROPOSAL rev 11 — not live. The live skill is .claude/skills/structural-drawing-reader (rev 10). -->

# Structural drawing reader

Read the set as a structural engineer does: the whole works before any member, the load path before any mark, every value met twice before
it is trusted. Scripts measure (text from the index, sizes and counts from `geometry`/`contents`; a `render` image only checks a count,
never gives a number or text); you interpret. An interpretation is a **claim** (a finding with its evidence) or a question; the report
prints nothing else.

`P` = `projects/<id>`, `W` = `P/work`, `I` = `P/input`, `PT` = `W/parts/<part>`. Commands and fallbacks: [tools.md](tools.md); read it once
before your first command. Every command here means the harness invocation that tools.md's first paragraph defines.

## Roles

A reading runs **part by part**: the scout cuts the set into parts, each part is read, checked, reviewed and locked alone, the assembler
joins them ([part-mode.md](part-mode.md): stages, manifest, brief, dispatch, lock).
- **Scout** (`doc-reader`): phases 0–1 for the whole set; writes the manifest, records only `--part scout`, no member value. Context 150k.
- **Part reader** (`doc-reader`): phases 2–4 for one part, from its brief. Records `--part <own part>`, writes `PT/values.json` and
  `PT/notes.md`, never another part; an input part is cited, never re-recorded. Context 200k: print no whole artefact (tools.md § Reading).
- **Part reviewer** (a fresh dispatch that saw nothing of the part): [review-rubric.md](review-rubric.md) only.
- **Assembler** (`doc-reader`): phases 5–6 across the locked parts, as part `all-assembly`.
- **Orchestrator**: dispatches every agent, records every receipt (`reopened` too), runs `part conflicts` after each
  `checked` receipt and again before assembly, then the review round and loop of [improvement-loop.md](improvement-loop.md) (it picks
  each `--seed`). Only the engineer answers questions and opens gates.

## Seen, unread, absent

Every statement about the drawings is one of three, and says which:

- **seen** — allowed, printed entries say it, or a measured finding's `G-` ids counted it; you cite their ids.
- **unread** — nothing reached the content: blocked text, text that does not print, a table or insert the tools did not open, a file with no
  detected sheet, a producer that returned nothing. Give the count, the reason and the question id; `unread` says nothing about the content.
- **absent** — you searched for it and record the search: `searched: "<q1>","<q2>" | scope: <file>, <sheets | all + unassigned> | hits: 0 |
  blocked_in_scope: <n> | not_printed_hits: <n from the --include-hidden rerun> | unassigned_searched: yes | unassigned_assigned: yes`.
  Search every term accented and unaccented (tools.md T10); `part check` reports a missing twin (`search_unaccented`). With
  `blocked_in_scope` above 0 the statement is `unread`: `không thấy trong chữ đọc được; N mục bị chặn (Q-…)`. With `not_printed_hits` above
  0 it is not `absent`: quote the hits `không in (T…)` (E16). Blocked entries on named sheets: search the others one by one; `absent` there,
  `unread` on the blocked ones.

**Text outside every frame** is read before any "no rows", "schedule unread" or `absent`: the scout assigns each cluster to the nearest
frame (method § Phase 0, E10) and the manifest gives every cluster to one part. A producer's empty result (no grid system, no schedule,
`plan_only`, `matched: 0`) is `unread` until your own search makes it `seen` or `absent` (terms: reading-method.md § Search terms).

## Claims

A finding is a claim with its evidence: `--value` the claim, `--entries` the entries it rests on, `--confidence` at most the extractor's
(`high` comes only from an engineer answer; a `measured` finding: tools.md § Measured findings), and for every kind except `note_item` a `--note` in this form:

`node: <tree id> | basis: two_sources | single_source | alt: <the strongest other reading> — ruled out by <entry id or check> | alt: none
after <check run>`

- `two_sources` = two sheets, or two kinds of evidence (text and dimension, plan and schedule); for `sheet_class`, the title-block title
  plus one in-frame heading or schedule header of the same subject. `part check` counts two different (kind, file, sheet) keys, not your `basis`.
- `single_source` → `--confidence low` (not a `measured` finding: tools.md § Measured findings). Every `low` finding has a `--question`
  asking its value (a font question alone does not count); all `single_source` sheet classes of a file share one question.
- A `measured` finding cites `--source`/`--items` (the `G-` ids of one member type) and a `--claim` per number (recipe: tools.md § Measured
  findings and § Recording; form: reading-method § Recording forms).
- An alternative nothing rules out is no claim: ask one question that states both readings.
- Every `note_item` `--note` starts `block: <node id>`; for topic `other` it continues `; topic: <name>`.

Evidence no kind fits (level or datum text, grid, mark, blocks, rows, units): the forms in reading-method.md § Recording forms, never a bent
kind. A K line or a `values.json` row cites `F-…`, `Q-…`, `T…`, `G-…` ids, an artefact pointer, or both.

## Done when, by tool

Code computes done-when; no phase card is written. The scout runs `harness part manifest-check W` to exit 0, a part reader `harness part
check W --part <id>` to exit 0, the assembler the same on `all-assembly`. Fix a problem where it sits, in `values.json` or the findings;
`input_invalid` names a tool-written file to regenerate (`grid-systems.json` too), not a row. `PT/notes.md` (form: [part-mode.md](part-mode.md) § Brief) holds scope,
unread and absent lines with question ids, tool gaps, `needs:` lines. `W/reading-record.md` holds the scout's two tables, **Reach** and
**Breakdown**, edited in place (English keys, drawing text verbatim); the assembler sets each node's coverage. A number a phase needs names
its command and JSON field path ([reading-method.md](reading-method.md) § Required counts). Rework is a new `part check` and review round.

## Phases

Before each phase read its section in [reading-method.md](reading-method.md). A situation no phase fits: its row in
[edge-cases.md](edge-cases.md).

**0. Reach — what can be read at all (scout).** `harness status W` (every producer `fresh`; a stale one is rerun first), `list-sheets`,
`inventory.json`, `read-log.json`, one `geometry --save` call per file (tools.md). Fill the Reach table: per file and sheet `readable |
blocked N of M (Q-font) | no sheet | near-empty (no text, no geometry) | partial conversion`, and one row `U<n>` per cluster of text outside
every frame, with nearest frame and gap.
*Done when* every file, sheet and cluster has a reach value; each but `readable`/`assigned` names a question id.

**1. Orient — what the works are (scout).** Class every sheet (`sheet_class`, title entry cited; values in method § Phase 1; a plan also by
its `geometry` layers). Reconcile the drawing list with the sheets both ways; record revision and issue status per sheet from its title
block, never an abbreviation table (`revision_from_table`). State the works: use, blocks, disciplines drawn, storeys, a first reading of the
structural system, the load path from roof to ground with the sheets showing each link. Build the **breakdown tree** (works → block → part →
member group), every sheet in one node, a coverage per node: `seen | titled | unread | absent | unclear`. Raise one blocking
`reader_breakdown_confirm` question showing the tree. Then write `W/parts/manifest.json` ([part-mode.md](part-mode.md) § Manifest), each
sheet's block placed by title, grid origin and number series together.
*Done when* every sheet has a class or a question and sits in one node; every list-versus-sheet difference has a question; every block and
load-path link has a node; the confirm question is raised; `part manifest-check` exits 0.

**2. Rules — what applies everywhere (part `all-notes-materials`; a member part for notes on its own sheets).** General notes, legend,
abbreviations, typical details, and notes printed on any drawing sheet (a pile-head concrete on a detail): one verbatim `note_item` per
topic in the method's topic list, per block. A cited standard keeps its edition (E27: a superseded or yearless one is a non-blocking
question, never mapped).
*Done when* every topic, for every block, is `seen` (finding), `unread` (count, Q-id) or `absent` (search record).

**3. Frame — grids, levels, orientation (part `all-grid-levels`).** Runs on a file once its units are answered (`part manifest-check`
reports `unit_unanswered` or `unit_answer_unread` until then); otherwise stop after phase 2 for that file and say so in `notes.md`. Per
block node: its grid system and selection status; whether RC and steel sheets show the same axes; the datum (`±0.000` against the absolute
level); storey and reference levels against local ones; the foundation levels the tree needs; the relative position of the blocks (a
blocking question when no site plan places them). The engineer selects systems and storey levels; you bring the evidence (producer
questions: method § Phase 3). A grid row cites the finding and the grid system; the system backs no number. A spacing with
`grid-systems.json` status `dimension_agrees` or `dimension_measured` needs no question (the second is recorded `printed, default text`,
normal confidence only when a whole number of millimetres, else asked); `dimension_differs` and `no_dimension` raise one.
*Done when* every block names its grid system with an answer or open question ids, and every level a leaf needs is a row at the extractor's
confidence or sits in a question.

**4. Members — along the load path, from the ground up (one member part).** One `values.json` row per mark × field: size, thickness or
depth, count on plan and in schedule, piles per member, levels, axes, each with its entry, finding or `G-` ids, or a question id (a value
read off another quantity is never the size). Sizes, counts and marks per type come from `contents` and `marks.json`, render-checked (method
§ Phase 4). A hand sum that uses another part's rows lists that part as an input in the manifest, else `cite_foreign_part`. **Trace** each
section and detail reference from the plan to its target and back; C2–C10 of the method (§ Phase 6) run here, on the part's sheets. Steel frames,
bases, bolts: [steel-industrial.md](steel-industrial.md); rebar, schedules, grades: [conventions.md](conventions.md).
*Done when* every manifest sheet has a row or a finding of its part (an unreadable sheet gets an `unread` row citing its question), every mark of `marks.json` on them that fits `marks_regex` has a row,
every `schedule_only` and `plan_only` mark is explained by a finding or a question, every section or detail heading belongs to a row or one
orphan question, and `part check` exits 0.

**5. Reason — would an engineer sign this reading? (assembler.)** Answer key claims K1–K14 of the method, each `claimed` (finding ids,
basis, alternative ruled out), `question` (ids) or `unread`; then every surprise (a base with no foundation, a schedule row no plan shows).
*Done when* K1–K14 each have a line with ids, every `claimed` line names its ruled-out alternative, every surprise has a question.

**6. Analyse — is it enough to plan a model? (assembler.)** First `harness status W --verify` and `harness part check` on every `locked` part: name each part with `check_failed: true` or `input_check_failed` to the
orchestrator and stop (only the orchestrator records `part receipt --kind reopened --reason "part check: <check_codes>"`, and never for a part with `check_error`: see part-mode.md § Lock and reopen); one that `harness status` reads
`reopened` or `stale_input` goes back, by the orchestrator, through `reopened`, `checked`, `reviewed`, `locked`. Then, from `part chain`
per block (a plan count conflicts across parts only on one shared sheet; sums across sheets are yours) and the `part conflicts` questions, run
C1, C11 (which axes and bays carry what) and C12 (counts per block) of the method on every block; each mismatch is a `cross_check` finding
citing both entries, or one entry plus a saved `contents` document, with its question (`--part all-assembly`). Rank the problems Critical /
Major / Minor in `all-assembly/notes.md`, each with its question id; readiness per part is `harness status` `parts[]` (`status`,
`blocking_open_ids`, `ready`) with `project_blocking_ids` and `parts_project_reasons`; a `parts_error` means fix the named record first.
*Done when* every check has a line (`run: result` or `not run: reason, Q-id`), every part is `locked` or named with its blocking ids, no
Breakdown node is `titled`, `part check --part all-assembly` exits 0, `status` and `questions-md` rerun.

## Blocked text

Each entry carries `meaning: allowed | blocked`; decide by that field alone. Blocked text is quoted verbatim with its entry id and read no
further; `harness finding` refuses it. Every class, value, topic and keyword you write (findings, questions, notes, rows, the hand-back)
rests on an allowed entry, a finding or an answer. A blocked title is written `<sheet id>: tiêu đề bị chặn (T…)` with its font question. A
phase whose items are all blocked for a file is done for it when one reader question lists them by entry id and the font question; its Reach
and coverage values are `unread`.

## Asking

- Reuse a producer's question (`questions.md`, `W/*questions.json`) before raising yours; one subject on several sheets or parts is one
  question listing every place (`ask --part` on an existing question adds the part). A work folder that already holds reader findings: edge
  case E35.
- Codes start with `reader_`; `--sheet` takes the detector sheet id; `--text` in Vietnamese, one subject and one question per call;
  `--found` verbatim, or the search record for an absence; in part mode every write has `--part`, except `ask --supplement` and `--withdraw-supplement`, which take none.
- **Blocking** (`--blocking`; it keeps `ready_for_gate1` false) when its answer sets or changes a gate 1 value or a gate 3 lot input. A row
  field but `material` and `other` that is `asked`, `unread`, `absent` or `seen` on one source needs a blocking question, and a question
  such a field cites is blocking. A question no row carries: grid per block; pile cut-off and cap-top levels; size, count or position of
  piles, caps, ground beams, column bases; slab thickness; or a rule of this skill, its method or its edge cases names it. Every other
  question is non-blocking.
- A size or count read from linework with no agreeing printed entry: one `reader_family_linework` question per part (tools.md § Measured
  findings); none where every measured row has an agreeing printed entry, none from copied linework (`linework_duplicate`, E40).
- Every discrepancy you find between drawings (a sheet with another block's grid origin or number series, a schedule row no plan shows, a
  printed dimension against its drawing, copied linework) is one question to the designer, even when no value depends on it, except within
  5 mm or 1 % (the larger) (E42).
- Amend your own earlier question (`ask --amend Q-… --text …`), never a new code. Only the orchestrator runs `harness answer`, with the engineer's words from its own chat:
  `harness answer W <Q-id> --text "<his words>" --by "<his name as he gives it>" --role engineer`, never the git user. No dispatched
  agent (scout, part reader, reviewer, assembler, report writer, intake runner) runs it. Units come only from such an answer: on
  `unit_unanswered` (no acknowledgement clears it) or `unit_answer_unread` hand the units question ids back and stop. A missing
  `question-registry.json` means `harness intake` has not run.
- An engineer answer that allowed, printed entries contradict → one blocking question quoting the answer id and entry ids. Comparing across
  files waits for the answer on whether the files form one set. Conventions come from the project's own legend and notes first, then
  [conventions.md](conventions.md); an unverified convention is a question.

## Hand-back

Each role stops at its done-when and reports. Scout: the `manifest-check` result, parts with sheet counts, `unread` counts. Part reader: the
`part check` result, the `needs:` lines, the blocking question ids. Assembler: the K1–K14 table, the locked parts that read `reopened`, `stale_input` or `check_failed`, findings by confidence, questions by
blocking, the Critical and Major problems with question ids. All: tool gaps, and `Part unreviewed: review round 1 not run.` (assembly:
`Reading unreviewed`). When the last part is locked, `drawing-analysis-report` reads `harness status` `parts[]`, each `PT/notes.md`,
`W/reading-record.md` and each part's latest review; its step 2 closes with `01-analysis.md` and `takeoff/`. A run that cannot finish stops
at its last green check; the next resumes there.

## Hard stops

A producer stays stale after its rerun; a phase needs a command whose fallback in [tools.md](tools.md) is `stop`; a set under
`projects/_heldout-*` is to be read; your part is locked: a write is refused, and `values.json`, `notes.md` and `receipts.json` of a locked part are never edited, deleted or moved; only the orchestrator records `reopened`, and you edit after it has. Name it,
stop, hand the questions to the orchestrator. Never search or list (`grep -r`, `rg`, `find`, a `**` glob) over `projects/` or above `P`:
search only inside `P`.
