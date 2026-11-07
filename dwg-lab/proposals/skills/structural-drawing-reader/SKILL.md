---
name: structural-drawing-reader
description: Expert reading of a structural drawing set after intake — sheet set, general notes, structural system, grid systems, levels, member marks and schedules — every judgement recorded as a finding tied to extracted entries, every gap a question. Use when analysing drawings for a Tekla model or answering what a drawing says.
---

<!-- PROPOSAL rev 3 (2026-11-07, after EVAL-1): not active until the engineer approves it (AGENTS.md principle 7). -->

# Structural drawing reader

Scripts measure; you classify, cross-check and ask. Every judgement you make is a **finding**
(`harness finding add`) tied to text entries, or a question (`harness ask`). A judgement in
neither place does not exist: the report prints only what the artefacts hold.

`W` = `projects/<id>/work`, `I` = `projects/<id>/input`.

## Before you start

- `drawing-intake` has run; `uv run harness status W` shows every producer `fresh` (`reader`
  `n/a`). Stale → rerun the producer it names.
- Steps 1–2 may run before units are answered; **steps 3–7 need `gate1.reasons` free of units
  reasons**, else stop after step 2.
- Your tools (all read-only except `finding` and `ask`):
  - `uv run harness list-sheets W` — sheets with ranked titles and `blocked_text_count`;
  - `uv run harness sheet-text W <file> <sheet_id> [--contains …] [--max N]` — one sheet; when
    `counts.truncated` is true, rerun with the `--max` it names;
  - `uv run harness find-text W --contains … [--file F]` — every sheet at once;
  - `W/marks.json`, `W/callouts.json`, `W/grid-systems.json`, `W/structure/<file>.levels.json`;
  - `uv run harness finding add W --kind … --file … [--sheet …] --entries T…,T… --value "…" [--field k=v] [--question Q-…]`;
  - `uv run harness ask W --code reader_<topic> --file … --sheet <detector id> --where "…" --found "…" --text "…" [--blocking]`.
- A step that needs something these tools do not give: name the gap and stop that step. The
  numbers you report come from these tools only, so a scratch script has nothing to add.

## Blocked text

Each entry carries `meaning: allowed | blocked`. **Blocked** text (legacy font not yet
approved) is quoted verbatim with its entry id and read no further: no class, value, keyword or
paraphrase comes from it, and `harness finding` refuses it. Tie it to the font question in
`legacy_font_gate.question_ids`. A step whose items are all blocked for a file is done for that
file when one reader question lists them and points at that font question.

## Asking

- First look for the question among the producers' (`questions.md`, `W/*questions.json`): reuse
  its id in your findings instead of asking again. Same subject on several sheets (datum,
  footing type) → one question listing every place.
- Your codes start with `reader_`. `--sheet` takes the detector sheet id (`model#03`).
- Write `--text` in Vietnamese, one question per call; `--found` verbatim.
- An engineer answer contradicted by drawing text → a blocking reader question quoting both
  (answer id and entry id). You never pick one.

## Steps

1. **Sheet set.** Classify every sheet with a `sheet_class` finding citing its title entry:
   `general_notes, setting_out, foundation, foundation_details, floor_framing, column_details,
   beam_details, slab_details, stairs, schedules, steel_details, mixed` (one sheet, several
   drawings), `other` (with `--note`). Look for a drawing list with `find-text` (danh mục,
   drawing list, index). None → one blocking `reader_drawing_list_missing` per file (one per set
   once the engineer says the files form one set); found → every listed sheet present and every
   sheet listed, else a question per difference. No floor-framing or foundation drawing in the
   set → blocking `reader_scope_drawings_missing` naming what is absent. *Done when* every sheet
   has a class or a question.
2. **General notes.** `note_item` findings (verbatim quotes) for design codes and editions,
   concrete class, rebar/steel/bolt/weld grades, cover, laps, U.N.O./TYP. conventions. No notes
   sheet → one non-blocking `reader_general_notes_missing` per file listing the items not found;
   notes on plans that differ from each other or from the notes sheet → one question per item.
   *Done when* each item is a finding or in a question.
3. **Structural system.** `structural_system` findings: frame type, foundation type, lateral
   system, floors, typical floors, each citing the entries it rests on. *Done when* each aspect
   is a finding or a question.
4. **Grid systems.** `W/grid-systems.json` and its SVGs: per system the views, independence,
   conflicts, single-source flag. The engineer selects systems (`grid_system_select`,
   `systems=`, `separate=` for different buildings) and assigns X/Y per system
   (`grid_system_axis_unassigned`, `dir1=X dir2=Y`). Sanity check each selected system: an
   overall dimension that differs from the sum of spacings, or unlabelled grid-layer lines
   beyond the last axis → `reader_grid_extent` quoting both. Grids are never rebuilt from member
   positions or averaged. *Done when* each system is selected or rejected by an answer, or its
   questions are open.
5. **Levels.** `structure/<file>.levels.json`: storey levels vs local ones (beam soffits, steps,
   wet rooms, storage platforms, canopies, landings — even when their title says TẦNG). The
   extractor's `storey_heights` stay unconfirmed. Unless the engineer has answered a storey
   selection, raise one blocking `reader_level_storey_selection` per file listing the candidate
   storey levels verbatim, and quote level texts the extractor missed (e.g. `(+ 6.00M LEVEL)`) as
   candidates. Finished vs structural stays a question until answered. *Done when* every level
   used later is a confirmed storey level or in a question.
6. **Members and schedules.** From `W/marks.json`: plan marks per sheet, schedule tables, the
   `matched` / `schedule_only` / `plan_only` lists, notation variants, size conflicts, tables
   with a blocked header. A member word in a title (`title_member_word`, `DẦM D1.1`) is evidence
   you cite as `Đề xuất (chưa xác nhận)` in the prefix question; prefix meanings come only from
   `member_mark_prefix_meaning` answers. From `W/callouts.json`: parsed callouts, and unparsed
   ones as counts per reason with at most 5 examples each. Quantities, lengths and weights stay
   uncomputed. *Done when* every `schedule_only` and `plan_only` mark is in a question or
   explained by a finding.
7. **Cross-check.** Same mark → same size on plan, schedule, section; same labels → same grid
   system; values from a superseded revision rejected. Each mismatch is a `cross_check` finding
   with its question. *Done when* every mismatch found has both.

## Rules

- Conventions come from the project's own legend and notes first, then
  [conventions.md](conventions.md); unverified conventions are questions.
- Provenance as the extractor wrote it; the detector sheet id goes in `--sheet` / `--where`, the
  printed sheet number only where the extractor gave it.
- Confidence never rises above the extractor's; `high` comes only from an engineer answer.
- A typed-over dimension (`dimension_override_differs`) is a conflict to ask about.

## Hard stops

Units reasons in `gate1.reasons` (after step 2); a producer stale; a step needs a tool not
listed here. Name it, stop, hand the questions to the orchestrator.
