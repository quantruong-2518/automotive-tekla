---
name: drawing-intake
description: First pass over a project's drawing files — convert DWG, probe every DXF, log every read, extract sheets/grids/levels, and hand the engineer the first blocking questions. Use when a project's input/ folder is new or has changed.
---

<!-- PROPOSAL rev 2 (2026-11-06, after REVIEW-1): not active until the engineer approves it (AGENTS.md principle 7). -->

# Drawing intake

You run deterministic commands and turn their output into the engineer's first questions.
You interpret nothing in the drawings here; `structural-drawing-reader` does, once the
engineer has answered the unit questions this step raises.

Layout: machine artefacts go to `projects/<id>/work/`; documents for the engineer
(`questions.md`, later `01-analysis.md`…) go to `projects/<id>/`.

## Steps

1. **Intake.** `uv run harness intake projects/<id>/input --out projects/<id>/work --project-id <id>`.
   Exit 3 = no DWG converter configured (`HARNESS_ODA_CONVERTER` or `HARNESS_DWG2DXF`) or an
   input file cannot be read: stop and tell the engineer exactly that. Exit 1 = a DWG/DXF could
   not be read, an output failed its schema, or `knowledge/font-encodings.csv` is malformed:
   report the stderr line. *Done when* exit 0, or you stopped with the reason.
2. **Structure, callouts, grid systems** — in this order, each after the previous one:
   `uv run harness read-structure projects/<id>/work --input-dir projects/<id>/input`,
   `uv run harness callouts projects/<id>/work --input-dir projects/<id>/input`,
   `uv run harness grid-system projects/<id>/work`.
   They never convert units; their grid spacings are the evidence the engineer needs to
   answer the unit questions. *Done when* all three exit 0.
3. **Status.** `uv run harness status projects/<id>/work`. *Done when* every producer is
   `fresh` and you have the counts of blocking open questions per producer.
4. **Inventory check.** Read `work/inventory.json`: every file is `read`, `partial` or
   `unreadable`, and you can state why for each non-`read` one (from `read-log.json`).
   `summary.changes` lists added/removed/changed files against the previous intake;
   `summary.stale_answers` lists answers that no longer apply. *Done when* both are reported.
5. **`projects/<id>/questions.md`** from `work/questions.json`, `structure-questions.json`,
   `callouts-questions.json` and `grid-system-questions.json`, using
   [questions-format.md](questions-format.md). *Done when* every question without an active
   answer has an entry — blocking first, then non-blocking — and each entry shows its id,
   `count` and whether its refs were truncated.
6. **Report** to the orchestrator: file counts by format and outcome, converter and confidence
   cap, blocking open counts per producer, unreadable files, changes and stale answers.

## Reading the results

- **Units.** Every probed file gets a blocking `units_confirm_all`; `units_conflict`,
  `units_suspect`, `units_unknown` and `grid_units_doubt` add evidence. Header units are never
  accepted: put the file's grid spacings (from `structure-summary.json`) into the question so
  the engineer can judge.
- **LibreDWG output** is capped at `medium`; a file with converter `ERROR:` lines is `partial`.
  Read the stderr tail before calling a partial file usable. `conversion_empty` (DXF opens but
  holds no entities) is unreadable for reading until the engineer answers.
- **Legacy Vietnamese fonts.** Text is decoded only by a positive font hint or an `approved`
  row of `knowledge/font-encodings.csv`. A `font_encoding_proposed` question is resolved by the
  engineer approving or rejecting that row in a reviewed commit, then rerunning intake — never by
  `harness answer`.
- **`dimension_override_differs`**: typed-over dimension text. List it; the engineer decides.
- **`no_reader_implemented`** (PDF, images, DOCX, XLSX): ask for DWG/DXF or wait for the reader.

## Answers

Only the engineer answers. When the engineer gives an answer in chat, record it with
`uv run harness answer projects/<id>/work <Q-id> --text "<their words>" --by "<their name>" [--value unit=mm]`
and rerun `harness status`. The command refuses obsolete ids and questions whose file changed.

## Hard stops

Intake exits 2 or 3; a file the engineer calls essential is `unreadable`; `status` shows a
producer `stale` that you cannot refresh. Stop, report, and wait for the engineer.
