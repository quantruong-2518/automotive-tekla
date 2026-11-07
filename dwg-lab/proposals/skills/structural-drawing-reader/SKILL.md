---
name: structural-drawing-reader
description: Expert reading of a structural drawing set after intake — sheet set, general notes, structural system, grid systems, levels, member marks and callouts — every finding tied to an extracted entry, every gap a question. Use when analysing drawings for a Tekla model or answering what a drawing says.
---

<!-- PROPOSAL rev 2 (2026-11-06, after REVIEW-1): not active until the engineer approves it (AGENTS.md principle 7). -->

# Structural drawing reader

Scripts measure; you classify, cross-check and ask. A finding you cannot tie to an extracted
entry (file + text entry id, or a grid/level/sheet id) does not exist.

## Before you start

- `drawing-intake` has run and `uv run harness status projects/<id>/work` shows every producer
  `fresh`. Stale → rerun the producer it names.
- Steps 1–2 may run before units are confirmed. **Steps 3–6 need every file's
  `units_confirm_all` answered** (status shows it): otherwise stop after step 2.
- Look at text only through `uv run harness list-sheets projects/<id>/work` and
  `uv run harness sheet-text projects/<id>/work <file> <sheet_id> [--contains …]`; never load a
  whole `text/<file>.json`. Use `display_text`; text flagged with unknown or proposed encoding
  is quoted as is.
- Raise every gap with `uv run harness ask projects/<id>/work --code <code> --file <file> --sheet <sheet_id> --where "…" --found "…" --text "…" [--blocking]`;
  it returns the question id. Add it to `questions.md` ([format](../drawing-intake/questions-format.md)).

## Steps

1. **Sheet set.** From `list-sheets`: classify each sheet (general notes, setting-out, foundation,
   floor framing, column/beam/slab details, schedules, steel details, other) by its title texts.
   Look for a drawing list; none found → blocking `drawing_list_missing`; found → every listed
   sheet present and every sheet listed, else a question per difference. Printed sheet numbers
   at `low` (position only) stay unconfirmed. *Done when* every sheet has a class or a question.
2. **General notes.** `sheet-text` of each notes sheet: design codes and editions, concrete
   class, rebar/steel/bolt/weld grades, cover, laps, "U.N.O."/"TYP." conventions. Quote each
   with its entry id. Plan notes contradicting general notes → record both, ask. *Done when*
   each of those items is quoted or asked about.
3. **Structural system.** Frame type (RC/steel/composite), foundation type, lateral system,
   floors, which floors are typical. *Done when* each claim cites the sheets it comes from.
4. **Grid systems.** `work/grid-systems.json` and the SVGs in `work/structure/grid-systems/`.
   For each system: views and independent views, conflicts, single-source flag. Ask the
   engineer to select the project's systems (`grid_system_select`) and assign Tekla X/Y.
   Never rebuild grids from member positions; never average. *Done when* each system is
   selected or rejected by an answer, or its questions are open.
5. **Levels.** `structure/<file>.levels.json`: storey levels vs local levels (beam soffits,
   steps, wet rooms). Storey heights only between levels the engineer confirmed as storeys
   (`level_storey_selection`); finished vs structural levels stays a question until answered.
   *Done when* every level used later is a confirmed storey level or asked about.
6. **Members and callouts.** `work/callouts.json`: member marks per sheet, rebar callouts,
   section labels, plates, bolts. `parsed` exists only for verified notations; unparsed ones
   are quoted. Prefix meanings come only from `member_mark_prefix_meaning` answers. Match each
   schedule row to a plan mark and back; unmatched → question. You never compute quantities,
   lengths or weights. *Done when* every mark on a framing/setting-out sheet is matched or asked.
7. **Cross-check.** Same mark → same size on plan, schedule, section; same grid labels →
   same system; values from a superseded revision rejected. *Done when* each mismatch is a
   question.

## Rules

- Conventions come from the project's own legend and notes first, then
  [conventions.md](conventions.md). Unverified conventions are questions.
- Provenance: use the extractor's provenance as written (`file` input-relative, `sheet` the
  printed number or `unknown`); the detector sheet id goes in your text, never in `sheet`.
- Confidence never rises above what the extractor gave; `high` comes only from an engineer answer.
- A typed-over dimension (`dimension_override_differs`) is a conflict to ask about, not a value.

## Hard stops

Units unanswered (after step 2); a producer stale; a step needs a tool not listed here — name
it and stop. Hand the questions to the orchestrator.
