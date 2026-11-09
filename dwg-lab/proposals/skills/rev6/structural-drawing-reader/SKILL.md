---
name: structural-drawing-reader
description: Expert reading of a structural drawing set after drawing-intake — sheet set, general notes, structural system, grid systems, levels, member marks and schedules — every judgement recorded as a finding tied to extracted entries, every gap a question. Use whenever the engineer asks what a drawing or sheet says, which sheet is which (đọc bản vẽ, phân loại các tờ, mặt bằng móng, chi tiết cột, loại móng), which levels are storey levels and which are local (cao độ tầng, cao độ cục bộ), which grid axes the project uses (lưới trục), what the general notes specify (mác bê tông, thép, lớp bảo vệ), whether beam or column marks on plans match the schedule (ký hiệu cấu kiện, bảng thống kê, schedule_only/plan_only), or to analyse a drawing set in projects/<id> for a Tekla model.
---


# Structural drawing reader

Scripts measure; you classify, cross-check and ask. Every judgement you make is a **finding**
(`harness finding add`) tied to text entries, or a question (`harness ask`). A judgement in
neither place does not exist: the report prints only what the artefacts hold.

`W` = `projects/<id>/work`, `I` = `projects/<id>/input`.

## Before you start

- `drawing-intake` has run; `uv run harness status W` shows every producer `fresh` (`reader`
  `n/a`). Stale → rerun the producer it names.
- Steps 1–2 may run before units are answered; **steps 3–7 need no reason starting `units:` in
  `gate1.reasons`** (a `simulated` units answer shows as an `answers:` reason instead and is
  enough for reading), else stop after step 2.
- Your tools (all read-only except `finding` and `ask`):
  - `uv run harness list-sheets W` — sheets with ranked titles and `blocked_text_count`;
  - `uv run harness sheet-text W <file> <sheet_id>|--unassigned [--contains …] [--max N]` — one
    sheet, or the text on no sheet or on several; when `counts.truncated` is true, rerun with the
    `--max` it names;
  - `uv run harness sheet-text W <file> <sheet_id> --region=x0,y0,x1,y1` — a table as `rows` of
    `cells`; absolute coordinates (entry `x`/`y`, `list-sheets` frame), in the `=` form because
    they are often negative;
  - `uv run harness find-text W --contains … [--file F] [--unassigned]` — every sheet at once;
    with `--unassigned` it searches only the text on no sheet or on several (hits carry
    `sheet_id: unassigned`);
  - `uv run harness dimensions W <file> --input-dir I [--sheet ID|--unassigned]` — measured
    value and override text per dimension, in drawing units;
  - `W/marks.json`, `W/callouts.json`, `W/grid-systems.json`, `W/structure/<file>.levels.json`;
  - `uv run harness finding add W --kind … --file … [--sheet …] --entries T…,T… --value "…" [--field k=v] [--question Q-…]`;
  - `uv run harness ask W --code reader_<topic> --file … --sheet <detector id> --where "…" --found "…" --text "…" [--blocking]`;
  - `uv run harness ask W --supplement Q-… [--file … --sheet …] --where "…" --found "…" --text "…"` —
    evidence on a producer's question (producer questions only; no `--code`, `--blocking`);
    `--withdraw-supplement <key> --reason "…"` withdraws one;
  - `uv run harness ask W --amend Q-… [--text "…"] [--places "…" …]` — correct or widen your own
    unanswered question in place (same id) instead of withdrawing and asking again.
- A step that needs something these tools do not give: name the gap and stop that step. The
  numbers you report come from these tools only, so a scratch script has nothing to add.

## Blocked text

Each entry carries `meaning: allowed | blocked`; decide by that field alone (ASCII text can be
blocked too: `legacy_ascii_suspect`). **Blocked** text is quoted verbatim with its entry id and
read no further; `harness finding` refuses it. Every class, value, topic and keyword you write —
finding values, question text, notes, step reports — rests on an allowed entry, a finding or an
answer. A blocked title is written `<sheet id>: tiêu đề bị chặn (T…)` with its font question
from `legacy_font_gate.question_ids`; for blocked ASCII text that is `legacy_ascii_text` (one per
file and style), whose answer records the engineer's reading and unblocks nothing. A step whose
items are all blocked for a file is done for that file when one reader question lists them
(entry ids only) and points at that font question. A finding that `finding list` marks stale (a
font row in its `decoded_by` changed) is checked again.

`find-text` and `sheet-text --contains` match allowed text only. `counts.blocked_in_scope` counts
the blocked entries in the searched scope, whatever the query, and `notes` names their font
questions. While it is above 0, "0 hits" means "not in the allowed text": write that, with the
count and those Q-ids.

## A file with no detected sheet

`list-sheets` lists no sheet for it and read-structure raised `sheets_not_detected`. Steps 2, 3
and 7 read its text with `sheet-text W <file> --unassigned` and `find-text --unassigned`. Step 1
has no sheet to classify: cite the `sheets_not_detected` question. Steps 4–6 run on the JSON
artefacts as usual. Any `unassigned` text, in this file or another: findings on it omit
`--sheet`; questions and supplements omit it too and name the place in `--where`.

## Asking

- First look for the question among the producers' (`questions.md`, `W/*questions.json`): reuse
  its id in your findings, and add your evidence to it with `ask --supplement`. Same subject on
  several sheets (datum, footing type) → one question listing every place.
- Your codes start with `reader_`. `--sheet` takes the detector sheet id (`model#03`).
- Write `--text` in Vietnamese, one question per call; `--found` verbatim.
- An answer (engineer or simulated) contradicted by drawing text → a blocking reader question
  quoting both (answer id and entry id). You never pick one.
- Comparing anything across files waits for the answer to intake's `file_set_relation` (raised
  when there are two or more readable drawing files); compare only within a set it names.

## Steps

1. **Sheet set.** Classify every sheet with a `sheet_class` finding citing its title entry:
   `general_notes, setting_out, foundation, foundation_details, floor_framing, column_details,
   beam_details, slab_details, stairs, schedules, steel_details, mixed` (one sheet, several
   drawings), `other` (with `--note`). Look for a drawing list with `find-text` (danh mục,
   drawing list, index). None → one blocking `reader_drawing_list_missing` per file (one per set
   once `file_set_relation` is answered); found → every listed sheet present and every sheet
   listed, else a question per difference. No floor-framing or foundation drawing in the
   set → blocking `reader_scope_drawings_missing` naming what is absent. Sheet numbers: cite
   read-structure's `sheet_number_gap` (missing numbers) and `sheet_number_missing` questions
   for the sheets they name. A sheet whose ranked titles name different subjects (`ĐỊNH VỊ
   CỘT` vs `ĐỊNH VỊ CỌC`) → one question quoting both, then a `cross_check` finding citing both
   entries with that `--question`. *Done when* every sheet has a class or a question.
2. **General notes.** `note_item` findings (verbatim quotes) for design codes and editions,
   concrete class, rebar/steel/bolt/weld grades, cover, laps, U.N.O./TYP. conventions. Each item
   records its scope, the clause heading it sits under, as `--field scope=T…` (the heading's
   entry id; it stays out of `--entries`, so the quote still matches). A blocked heading gives no
   scope: name it in the item's question. Two items conflict only when their scopes overlap;
   items with different scopes are both findings, each with its scope. Read a notes table with
   `sheet-text --region`, one row at a time; a cell is blank only when that row's `cells` lack
   it. No notes sheet → one non-blocking `reader_general_notes_missing` per file listing the
   items not found; notes on plans that differ from each other or from the notes sheet → one
   question per item. *Done when* each item is a finding or in a question.
3. **Structural system.** `structural_system` findings: frame type, foundation type, lateral
   system, floors, typical floors, each citing the entries it rests on. A finding that names a
   mark set (footings, pile caps) copies `members` from `W/marks.json` `summary.mark_sets` for
   that file and family, as listed, gaps kept; when `complete` is false it says `ít nhất` and
   names the `source`. *Done when* each aspect is a finding or a question.
4. **Grid systems.** `W/grid-systems.json` and its SVGs: per system the views, independence,
   conflicts, single-source flag. The engineer selects systems (`grid_system_select`,
   `systems=`, `separate=` for different buildings) and assigns X/Y per system
   (`grid_system_axis_unassigned`, `dir1=X dir2=Y`). Sanity check each selected system with
   `harness dimensions` on its plan sheets: an overall dimension whose measured value differs
   from the sum of spacings (both in drawing units), or unlabelled grid-layer lines beyond the
   last axis → `reader_grid_extent` quoting both (dimension `handle`, or `block_path` when it is
   null; spacing string). Grids are never rebuilt from member positions or averaged. A question
   is settled only by its answer or by `harness status` listing it in `gate1.closed`; one that
   seems to sit on a rejected system stays open until then. `proposed_simulated` (units, X/Y)
   and `proposed_closed_by` (conflicts) are proposals: not confirmed, answered or closed.
   A file with no usable or selected grid system has a blocking `grid_system_missing`: write
   "no usable or selected grid system" and name the systems the file does have. Its answer is
   the engineer's own step: grid values (`dir1_labels`, `dir1_spacings`, `dir2_labels`,
   `dir2_spacings`, optional `sheet`), or `no_grid=yes` for a file with no plan that needs a
   grid. It is settled only by a system whose `source_answer` names it, or by the engineer's
   `no_grid=yes`; words only or a simulated answer build nothing. You may read the grid off the
   drawing: add it to that question with `ask --supplement` (label and dimension entries cited,
   `Đề xuất (chưa xác nhận)`); it stays evidence, never a gate-1 input. Quote a
   `grid_answer_contradicts_drawing` with both values. *Done when* each system is selected or
   rejected by an answer, or its questions are open.
5. **Levels.** `structure/<file>.levels.json`: storey levels vs local ones (beam soffits, steps,
   wet rooms, storage platforms, canopies, landings — even when their title says TẦNG). The
   extractor's `storey_heights` stay unconfirmed; values in `blocked_candidates` are no
   candidates (cite their entry ids with the font question). When read-structure raised
   `level_storey_selection` for the file, give it your candidates with `ask --supplement`;
   otherwise, unless a storey selection is answered, raise one blocking
   `reader_level_storey_selection` per file listing the candidate storey levels verbatim. Quote
   allowed level texts the extractor missed (e.g. `(+ 6.00M LEVEL)`) as candidates. A finding
   that states a level value takes the extractor's confidence for it: `--confidence low` unless
   `levels.json` gives that value `medium`. Finished vs structural stays a question until
   answered. *Done when* every level used later is a confirmed storey level or in a question.
6. **Members and schedules.** From `W/marks.json`: plan marks per sheet, schedule tables, the
   `matched` / `schedule_only` / `plan_only` lists, notation variants, size conflicts, tables
   with a blocked header, `blocked_columns`. A match with `size_compared: false` is `chưa so
   sánh` with its `size_not_compared_reason`. A member word in a title (`title_member_word`,
   `DẦM D1.1`) goes to the file's `member_mark_prefix_meaning` question (one subject per prefix)
   as `ask --supplement`, worded `Đề xuất (chưa xác nhận)`; prefix meanings come only from its
   answers. A list of marks you write is copied from `summary.mark_sets`, as in step 3.
   Comparison scope, per file from `matching[]`: `schedule_tables` and `detail_headings` both 0
   → the file is not compared (`chưa so sánh`), and its empty `plan_only` says nothing. Without a
   schedule, only the families whose mark set `source` holds both `plan_marks` and
   `detail_heading` were compared. A `schedule_only` key with `compared_with: detail_heading`
   means no plain plan label was read for it, not that the plan lacks the member.
   From `W/callouts.json`: parsed callouts; unparsed ones per `summary.unparsed_by_code` with at
   most 5 examples each and the file's `callout_unparsed` Q-id; a `symbol_glyph_unverified`
   text (`2ù20`) is quoted as stored, never read as Ø. Before writing that a bar size or callout
   is absent, check `rejected[]` (`summary.rejected_by_reason`) and the unparsed candidates.
   Quantities, lengths and weights stay uncomputed. *Done when* every `schedule_only` and
   `plan_only` mark is in a question or explained by a finding.
7. **Cross-check.** Same mark → same size on plan, schedule, section; same labels → same grid
   system; values from a superseded revision rejected. Each mismatch is a `cross_check` finding
   with its question. *Done when* every mismatch found has both.

## Rules

- Conventions come from the project's own legend and notes first, then
  [conventions.md](conventions.md); unverified conventions are questions.
- Provenance as the extractor wrote it; the detector sheet id goes in `--sheet` / `--where`, the
  printed sheet number only where the extractor gave it.
- Confidence never rises above the extractor's; `high` comes only from an engineer answer. A
  `low` finding carries `--question` with a question that asks about that value (an existing id
  or one you ask); a font question alone does not.
- A typed-over dimension (`dimension_override_differs`) is a conflict to ask about.

## Hard stops

A `units:` reason in `gate1.reasons` (after step 2); a producer stale; a step needs a tool not
listed here. Name it, stop, hand the questions to the orchestrator.
